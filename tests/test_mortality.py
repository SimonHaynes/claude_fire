"""Stochastic mortality.

REVIEW.md §1.2, graded high. Everyone used to die at exactly 95, so a bequest
figure was really "conditional on both living to 95" and nothing said so.
"""
from __future__ import annotations

import dataclasses
import random
from datetime import date

import pytest

from retireplan import FixedAge, LifeTable
from retireplan.mortality import ABSOLUTE_MAX_AGE, model_from_spec
from retireplan.simulation import _death_index


@pytest.fixture(scope="module")
def table() -> LifeTable:
    return LifeTable.load()


class TestFixedAgeIsTheDefault:
    def test_it_always_returns_its_age(self):
        rng = random.Random(0)
        model = FixedAge(95)
        assert {model.sample_age_at_death(60, "male", rng) for _ in range(50)} == {95}

    def test_it_never_kills_someone_already_older(self):
        rng = random.Random(0)
        assert FixedAge(95).sample_age_at_death(100, None, rng) == 100

    def test_its_spec_is_small(self):
        assert FixedAge(95).spec() == {"kind": "fixed_age", "age": 95}


class TestTableLoads:
    def test_it_covers_both_sexes(self, table):
        assert any(sex == "male" for sex, _ in table.qx)
        assert any(sex == "female" for sex, _ in table.qx)

    def test_rates_are_probabilities(self, table):
        assert all(0.0 <= q <= 1.0 for q in table.qx.values())

    def test_mortality_rises_with_age(self, table):
        assert table.qx[("male", 80)] > table.qx[("male", 60)]
        assert table.qx[("female", 90)] > table.qx[("female", 70)]

    def test_men_die_sooner_than_women_at_the_same_age(self, table):
        assert table.qx[("male", 70)] > table.qx[("female", 70)]

    def test_a_table_with_gaps_is_rejected(self, tmp_path):
        # A hole would be papered over by falling back to a younger age,
        # understating mortality -- the flattering direction, and invisible.
        path = tmp_path / "holey.csv"
        path.write_text(
            "sex,age,qx\nmale,60,0.01\nmale,62,0.02\nfemale,60,0.01\nfemale,61,0.02\n"
        )
        with pytest.raises(ValueError, match="gaps at ages"):
            LifeTable.load(path)

    def test_an_empty_table_is_rejected(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("# just a comment\nsex,age,qx\n")
        with pytest.raises(ValueError, match="no mortality rates"):
            LifeTable.load(path)


class TestSampling:
    def test_nobody_dies_before_their_current_age(self, table):
        rng = random.Random(7)
        assert all(
            table.sample_age_at_death(70, "male", rng) >= 70 for _ in range(500)
        )

    def test_nobody_outlives_the_maximum(self, table):
        rng = random.Random(7)
        assert all(
            table.sample_age_at_death(60, "female", rng) <= table.max_age
            for _ in range(500)
        )

    def test_the_same_seed_gives_the_same_deaths(self, table):
        a = [table.sample_age_at_death(60, "male", random.Random(3)) for _ in range(20)]
        b = [table.sample_age_at_death(60, "male", random.Random(3)) for _ in range(20)]
        assert a == b

    def test_outcomes_actually_vary(self, table):
        rng = random.Random(11)
        ages = {table.sample_age_at_death(60, "male", rng) for _ in range(200)}
        assert len(ages) > 10, "a distribution, not a fixed age"

    def test_mean_matches_published_life_expectancy_at_65(self, table):
        # ONS 2022-2024 period life expectancy at 65 is about 18.5 further
        # years for men and 21 for women. This is the test that catches a
        # mis-parsed table, which is otherwise invisible.
        rng = random.Random(19)
        male = [table.sample_age_at_death(65, "male", rng) for _ in range(20_000)]
        female = [table.sample_age_at_death(65, "female", rng) for _ in range(20_000)]
        assert sum(male) / len(male) == pytest.approx(83.5, abs=1.0)
        assert sum(female) / len(female) == pytest.approx(86.0, abs=1.0)

    def test_women_outlive_men(self, table):
        rng = random.Random(23)
        male = [table.sample_age_at_death(65, "male", rng) for _ in range(5_000)]
        female = [table.sample_age_at_death(65, "female", rng) for _ in range(5_000)]
        assert sum(female) / len(female) > sum(male) / len(male)

    def test_unstated_sex_lands_between_the_two(self, table):
        rng = random.Random(29)
        both = [table.sample_age_at_death(65, None, rng) for _ in range(10_000)]
        male = [table.sample_age_at_death(65, "male", rng) for _ in range(10_000)]
        female = [table.sample_age_at_death(65, "female", rng) for _ in range(10_000)]
        assert (
            sum(male) / len(male)
            < sum(both) / len(both)
            < sum(female) / len(female)
        )


class TestAgeRating:
    def test_it_defaults_to_no_adjustment(self, table):
        # A silent longevity adjustment is worse than a stated one.
        assert table.age_rating == 0

    def test_rating_down_lengthens_life(self, table):
        rated = dataclasses.replace(table, age_rating=3)
        rng = random.Random(31)
        plain = [table.sample_age_at_death(65, "male", rng) for _ in range(5_000)]
        longer = [rated.sample_age_at_death(65, "male", rng) for _ in range(5_000)]
        assert sum(longer) / len(longer) > sum(plain) / len(plain)


class TestSpecIsCacheSafe:
    def test_the_spec_excludes_the_table_itself(self, table):
        spec = table.spec()
        # Serialising hundreds of rates into every cache key works, which is
        # exactly why nobody notices until it is slow.
        assert "qx" not in spec
        assert len(str(spec)) < 300

    def test_the_digest_identifies_the_table(self, table):
        assert table.spec()["digest"] == table.digest

    def test_a_spec_round_trips(self, table):
        restored = model_from_spec(table.spec())
        assert isinstance(restored, LifeTable)
        assert restored.digest == table.digest

    def test_a_fixed_age_spec_round_trips(self):
        assert model_from_spec(FixedAge(88).spec()) == FixedAge(88)

    def test_an_unknown_spec_is_rejected(self):
        with pytest.raises(ValueError, match="unknown mortality model"):
            model_from_spec({"kind": "wishful"})


class TestDeathIndex:
    def test_alive_through_the_year_of_death(self):
        # Alive for indices 0..index-1, so dying at 71 when currently 70
        # leaves two living years.
        assert _death_index(age_at_death=71, age_now=70, n_years=40) == 2

    def test_floored_at_one_year(self):
        # Someone already past their sampled age still lives the first year,
        # matching the horizon, rather than being dead before the plan starts.
        assert _death_index(age_at_death=60, age_now=90, n_years=40) == 1

    def test_capped_at_the_horizon(self):
        assert _death_index(age_at_death=200, age_now=60, n_years=40) == 40


class TestAbsoluteMaxAge:
    def test_it_is_plausible(self):
        assert 105 <= ABSOLUTE_MAX_AGE <= 120
