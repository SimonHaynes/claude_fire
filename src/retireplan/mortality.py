"""When people die.

The engine used to run everyone to a fixed age — 95 by default. That is
conservative for *success* (funding forty-five years is harder than funding the
twenty-five a fifty-two-year-old should expect) but wrong for *bequest*, which
was quoted as though the plan certainly ran that long. A "£19M estate" was
really "£19M conditional on both living to 95", and nothing said so.

`FixedAge` keeps the old behaviour and is still the default, so turning
mortality on is a deliberate act whose effect is attributable. `LifeTable`
samples an age at death per trial from published ONS rates.

The two deaths are sampled independently, deliberately. Real couples' deaths do
correlate, but modelling that would *shorten* the expected gap between them —
and the gap is what makes a plan expensive, since a survivor alone for fifteen
years on one State Pension and half a DB pension is the risk this exists to
expose. Most observable correlation in death dates is the couple's age gap,
already modelled in their dates of birth; a copula on top would be false
precision. Sex matters far more: a unisex table on a mixed-sex couple is about a
three-and-a-half year error each way, against a fraction of a year for
correlation.
"""
from __future__ import annotations

import csv
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

DATA_DIR = Path(__file__).parent / "data" / "mortality"
DEFAULT_TABLE = "ons_qx_ew_2022_2024.csv"

ABSOLUTE_MAX_AGE = 110
"""Nobody is modelled past this: the oldest verified human ages are barely
beyond it, and a life table's top rates are thin enough to be noise."""


@runtime_checkable
class MortalityModel(Protocol):
    """How an age at death is decided for one person in one trial."""

    def sample_age_at_death(
        self, current_age: int, sex: str | None, rng: random.Random
    ) -> int: ...

    def spec(self) -> dict:
        """Cache identity. Must not be the whole table.

        A life table naively serialised into a simulation's cache key adds
        hundreds of kilobytes of JSON to every key computation. It works,
        which is why nobody notices until it is slow.
        """
        ...


@dataclass(frozen=True)
class FixedAge:
    """Everyone dies at the same age. The previous behaviour, still the default.

    Kept as a real model rather than a special case so that "mortality is not
    modelled here" is a visible choice in a scenario rather than an absence.
    """

    age: int = 95

    def sample_age_at_death(
        self, current_age: int, sex: str | None, rng: random.Random
    ) -> int:
        return max(self.age, current_age)

    def spec(self) -> dict:
        return {"kind": "fixed_age", "age": self.age}


@dataclass(frozen=True)
class LifeTable:
    """Age at death sampled from published one-year mortality rates.

    Sampling walks forward from the person's current age, drawing against each
    year's `qx` in turn. That is exact rather than approximate, conditions
    correctly on having survived to today, and needs no dependency.
    """

    name: str
    qx: Mapping[tuple[str, int], float]
    digest: str
    """Content hash of the table, so the cache key can identify it in a few
    bytes rather than by serialising every rate."""

    age_rating: int = 0
    """Look the person up as if they were this many years younger.

    The standard actuarial lever for a population that does not match the
    table. An affluent household typically outlives national-average rates by
    two to four years, so `age_rating=3` is defensible for one — but the
    default is **0**, using the data as published, because a silent longevity
    adjustment is worse than a stated one. Note which way 0 errs: it
    understates lifespan, which flatters success probability and understates
    how long an estate has to last."""

    max_age: int = ABSOLUTE_MAX_AGE

    def sample_age_at_death(
        self, current_age: int, sex: str | None, rng: random.Random
    ) -> int:
        age = max(0, current_age)
        while age < self.max_age:
            if rng.random() < self._rate(age, sex):
                return age
            age += 1
        return self.max_age

    def _rate(self, age: int, sex: str | None) -> float:
        looked_up = max(0, age - self.age_rating)
        if sex in ("male", "female"):
            return self._lookup(sex, looked_up)
        # Sex unstated: blend evenly rather than silently pick one. Worth a few
        # years each way, so intake should ask — but guessing is worse.
        return 0.5 * self._lookup("male", looked_up) + 0.5 * self._lookup("female", looked_up)

    def _lookup(self, sex: str, age: int) -> float:
        while age >= 0:
            rate = self.qx.get((sex, age))
            if rate is not None:
                return rate
            age -= 1
        return 1.0

    def spec(self) -> dict:
        return {
            "kind": "life_table",
            "name": self.name,
            "digest": self.digest,
            "age_rating": self.age_rating,
            "max_age": self.max_age,
        }

    @classmethod
    def load(cls, path: str | Path | None = None, **kwargs) -> "LifeTable":
        """Read a qx table from CSV. Comment lines start with `#`."""
        path = Path(path) if path is not None else DATA_DIR / DEFAULT_TABLE
        raw = path.read_bytes()
        rows = [
            line for line in raw.decode("utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        qx: dict[tuple[str, int], float] = {}
        for row in csv.DictReader(rows):
            qx[(row["sex"], int(row["age"]))] = float(row["qx"])
        if not qx:
            raise ValueError(f"no mortality rates found in {path}")
        _validate(qx, path)
        return cls(
            name=path.stem,
            qx=qx,
            digest=hashlib.sha256(raw).hexdigest()[:16],
            **kwargs,
        )


def _validate(qx: Mapping[tuple[str, int], float], path: Path) -> None:
    """Reject a table with holes in it.

    A gap would be silently papered over by `_lookup` falling back to a
    younger age, which understates mortality — the flattering direction, and
    invisible in every figure the engine reports.
    """
    for sex in ("male", "female"):
        ages = sorted(age for s, age in qx if s == sex)
        if not ages:
            raise ValueError(f"{path}: no rates for {sex}")
        expected = list(range(ages[0], ages[-1] + 1))
        if ages != expected:
            missing = sorted(set(expected) - set(ages))
            raise ValueError(f"{path}: {sex} rates have gaps at ages {missing[:5]}")


def model_from_spec(spec: dict) -> MortalityModel:
    """Rebuild a model from its `spec()`, for JSON round-tripping."""
    kind = spec.get("kind")
    if kind == "fixed_age":
        return FixedAge(age=spec.get("age", 95))
    if kind == "life_table":
        return LifeTable.load(
            age_rating=spec.get("age_rating", 0),
            max_age=spec.get("max_age", ABSOLUTE_MAX_AGE),
        )
    raise ValueError(f"unknown mortality model {kind!r}")
