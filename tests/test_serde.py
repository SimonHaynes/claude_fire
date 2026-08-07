"""JSON round-tripping and household validation.

The intake step writes a household to JSON for a human to check; if that file
cannot come back in identically, the check was meaningless.
"""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Blend,
    Contribution,
    DefinedBenefit,
    FixedNominal,
    FixedReal,
    HeldToMaturityCredit,
    Household,
    Maturity,
    Person,
    SampledSeries,
    compile_plan,
    dump_household,
    load_household,
)
from retireplan.serde import return_model_from_dict, return_model_to_dict
from retireplan.tax.uk import UK


class TestReturnModelRoundTrip:
    @pytest.mark.parametrize("model", [
        SampledSeries("global_equity"),
        FixedReal(0.02),
        FixedNominal(0.08),
        Blend.of(global_equity=0.6, gov_bonds=0.4),
        HeldToMaturityCredit(nominal_yield=0.07, n_holdings=10),
    ])
    def test_round_trips(self, model):
        assert return_model_from_dict(return_model_to_dict(model)) == model

    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValueError, match="unknown return model"):
            return_model_from_dict({"kind": "wishful"})


class TestHouseholdRoundTrip:
    def test_full_household_survives_a_round_trip(self):
        original = Household(
            people=[Person("Simon", date(1974, 1, 14)),
                    Person("Susie", date(1975, 10, 29), full_state_pension=False)],
            assets=[
                Asset("ISA", AssetType.ISA, "Simon", 185_497,
                      returns=SampledSeries("global_equity"), annual_charge_pct=0.0014),
                Asset("Bond", AssetType.ISA, "Simon", 29_298, returns=FixedNominal(0.08),
                      maturity=Maturity(on=date(2026, 11, 5), rollover_to="ISA")),
                Asset("Pension", AssetType.DC_PENSION, "Susie", 115_000,
                      returns=SampledSeries("global_equity"),
                      contributions=Contribution(500, 300)),
                Asset("Teachers", AssetType.DB_PENSION, "Susie",
                      defined_benefit=DefinedBenefit(9_623, 60, 15_245)),
            ],
        )
        restored = load_household(dump_household(original))
        assert restored == original

    def test_dates_survive(self):
        original = Household(people=[Person("A", date(1980, 2, 29))])
        assert load_household(dump_household(original)).people[0].date_of_birth == date(1980, 2, 29)

    def test_debts_survive_either_form(self):
        from retireplan import Debt

        original = Household(
            people=[Person("A", date(1980, 1, 1))],
            debts=[
                Debt("Loan by count", 1_000, 100, remaining_months=10),
                Debt("Loan by date", 2_000, 200, last_payment=date(2028, 6, 1)),
            ],
        )
        restored = load_household(dump_household(original))
        assert restored == original
        by_date = [d for d in restored.debts if d.name == "Loan by date"][0]
        assert by_date.last_payment == date(2028, 6, 1)
        assert by_date.remaining_months is None

    def test_restored_household_still_compiles(self):
        from retireplan import Scenario

        original = Household(
            people=[Person("A", date(1960, 1, 1))],
            assets=[Asset("ISA", AssetType.ISA, "A", 100_000, returns=FixedReal(0.01))],
        )
        restored = load_household(dump_household(original))
        plan = compile_plan(restored, Scenario("s"), UK, date(2026, 1, 1))
        assert plan.n_years > 0


class TestValidation:
    def test_unknown_income_owner_is_rejected(self):
        from retireplan import Frequency, IncomeSource, IncomeType

        household = Household(
            people=[Person("A", date(1960, 1, 1))],
            incomes=[IncomeSource("Nobody", IncomeType.SALARY, 1000, Frequency.YEARLY)],
        )
        with pytest.raises(ValueError, match="unknown owner"):
            household.validate()

    def test_duplicate_asset_names_are_rejected(self):
        household = Household(
            people=[Person("A", date(1960, 1, 1))],
            assets=[
                Asset("ISA", AssetType.ISA, "A", 1.0, returns=FixedReal(0.0)),
                Asset("ISA", AssetType.ISA, "A", 2.0, returns=FixedReal(0.0)),
            ],
        )
        with pytest.raises(ValueError, match="unique"):
            household.validate()

    def test_rollover_to_a_missing_asset_is_rejected(self):
        household = Household(
            people=[Person("A", date(1960, 1, 1))],
            assets=[Asset("Bond", AssetType.ISA, "A", 1.0, returns=FixedReal(0.0),
                          maturity=Maturity(on=date(2027, 1, 1), rollover_to="Ghost"))],
        )
        with pytest.raises(ValueError, match="unknown asset"):
            household.validate()

    def test_db_pension_without_details_is_rejected(self):
        with pytest.raises(ValueError, match="needs a defined_benefit"):
            Asset("Teachers", AssetType.DB_PENSION, "A")

    def test_defined_benefit_on_a_non_db_asset_is_rejected(self):
        with pytest.raises(ValueError, match="not a DB_PENSION"):
            Asset("ISA", AssetType.ISA, "A", defined_benefit=DefinedBenefit(1000, 60))

    def test_retiring_someone_who_does_not_exist_is_rejected(self):
        from retireplan import Scenario

        household = Household(people=[Person("A", date(1960, 1, 1))])
        scenario = Scenario("s", retirement_dates={"Ghost": date(2030, 1, 1)})
        with pytest.raises(ValueError, match="retires people not in the household"):
            compile_plan(household, scenario, UK, date(2026, 1, 1))
