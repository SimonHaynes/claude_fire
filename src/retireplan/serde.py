"""JSON round-tripping for a `Household`.

Data intake writes a household as JSON so a human can check it before anything
downstream depends on it, and so a plan can be re-run months later against the
same inputs. Written explicitly rather than reflectively: the schema is the
contract with that file, and it should break loudly when it changes rather than
quietly accepting a field that no longer means what it did.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from .market import (
    Blend,
    FixedNominal,
    FixedReal,
    HeldToMaturityCredit,
    ParametricNormal,
    ReturnModel,
    SampledSeries,
)
from .mortality import FixedAge, model_from_spec
from .model import (
    Asset,
    AssetType,
    Assumptions,
    Contribution,
    Debt,
    DefinedBenefit,
    Expense,
    ExpenseCategory,
    FiscalDrag,
    Frequency,
    Goal,
    Household,
    IncomeSource,
    IncomeType,
    Maturity,
    Person,
    Phase,
)


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _pd(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None



def return_model_to_dict(model: ReturnModel) -> dict[str, Any]:
    if isinstance(model, SampledSeries):
        return {"kind": "sampled", "key": model.key}
    if isinstance(model, FixedReal):
        return {"kind": "fixed_real", "rate": model.rate}
    if isinstance(model, FixedNominal):
        return {"kind": "fixed_nominal", "nominal_rate": model.nominal_rate}
    if isinstance(model, ParametricNormal):
        return {"kind": "parametric_normal", "mean": model.mean, "stdev": model.stdev}
    if isinstance(model, Blend):
        return {
            "kind": "blend",
            "parts": [[return_model_to_dict(m), w] for m, w in model.parts],
        }
    if isinstance(model, HeldToMaturityCredit):
        return {
            "kind": "held_to_maturity_credit",
            "nominal_yield": model.nominal_yield,
            "default_rate": model.default_rate,
            "recovery_rate": model.recovery_rate,
            "stress_default_multiple": model.stress_default_multiple,
            "stress_recovery_rate": model.stress_recovery_rate,
            "n_holdings": model.n_holdings,
        }
    raise TypeError(f"cannot serialise return model {model!r}")


def return_model_from_dict(raw: dict[str, Any]) -> ReturnModel:
    kind = raw["kind"]
    if kind == "sampled":
        return SampledSeries(raw["key"])
    if kind == "fixed_real":
        return FixedReal(raw["rate"])
    if kind == "fixed_nominal":
        return FixedNominal(raw["nominal_rate"])
    if kind == "parametric_normal":
        return ParametricNormal(mean=raw["mean"], stdev=raw["stdev"])
    if kind == "blend":
        return Blend(tuple((return_model_from_dict(m), w) for m, w in raw["parts"]))
    if kind == "held_to_maturity_credit":
        return HeldToMaturityCredit(
            nominal_yield=raw["nominal_yield"],
            default_rate=raw["default_rate"],
            recovery_rate=raw["recovery_rate"],
            stress_default_multiple=raw["stress_default_multiple"],
            stress_recovery_rate=raw["stress_recovery_rate"],
            n_holdings=raw["n_holdings"],
        )
    raise ValueError(f"unknown return model kind {kind!r}")



def household_to_dict(household: Household) -> dict[str, Any]:
    return {
        "people": [
            {
                "name": p.name,
                "date_of_birth": _d(p.date_of_birth),
                "full_state_pension": p.full_state_pension,
                "sex": p.sex,
            }
            for p in household.people
        ],
        "incomes": [
            {
                "owner": i.owner,
                "type": i.type.value,
                "amount": i.amount,
                "frequency": i.frequency.value,
                "start": _d(i.start),
                "end": _d(i.end),
                "annual_real_growth": i.annual_real_growth,
                "stops_at_retirement": i.stops_at_retirement,
            }
            for i in household.incomes
        ],
        "expenses": [
            {
                "name": e.name,
                "amount": e.amount,
                "frequency": e.frequency.value,
                "category": e.category.value,
                "start": _d(e.start),
                "end": _d(e.end),
                "phase": e.phase.value,
                "years_from_retirement": e.years_from_retirement,
            }
            for e in household.expenses
        ],
        "debts": [
            {
                "name": d.name,
                "balance": d.balance,
                "monthly_payment": d.monthly_payment,
                "remaining_months": d.remaining_months,
                "last_payment": _d(d.last_payment),
                "interest_rate": d.interest_rate,
            }
            for d in household.debts
        ],
        "assets": [
            {
                "name": a.name,
                "type": a.type.value,
                "owner": a.owner,
                "value": a.value,
                "returns": return_model_to_dict(a.returns),
                "annual_charge_pct": a.annual_charge_pct,
                "flat_annual_fee": a.flat_annual_fee,
                "contributions": (
                    {
                        "employee_monthly": a.contributions.employee_monthly,
                        "employer_monthly": a.contributions.employer_monthly,
                        "start": _d(a.contributions.start),
                        "end": _d(a.contributions.end),
                    }
                    if a.contributions
                    else None
                ),
                "maturity": (
                    {"on": _d(a.maturity.on), "rollover_to": a.maturity.rollover_to}
                    if a.maturity
                    else None
                ),
                "defined_benefit": (
                    {
                        "annual_amount": a.defined_benefit.annual_amount,
                        "start_age": a.defined_benefit.start_age,
                        "lump_sum": a.defined_benefit.lump_sum,
                    }
                    if a.defined_benefit
                    else None
                ),
            }
            for a in household.assets
        ],
        "goals": [
            {
                "description": g.description,
                "target_amount": g.target_amount,
                "target_date": _d(g.target_date),
                "priority": g.priority,
            }
            for g in household.goals
        ],
        "assumptions": {
            "life_expectancy_age": household.assumptions.life_expectancy_age,
            "state_pension_age": household.assumptions.state_pension_age,
            "state_pension_annual": household.assumptions.state_pension_annual,
            "risk_tolerance": household.assumptions.risk_tolerance,
            "mortality": household.assumptions.mortality.spec(),
            "max_age": household.assumptions.max_age,
            "db_survivor_fraction": household.assumptions.db_survivor_fraction,
            "survivor_essential_factor": household.assumptions.survivor_essential_factor,
            "survivor_discretionary_factor": household.assumptions.survivor_discretionary_factor,
            "fiscal_drag": {
                "inflation": household.assumptions.fiscal_drag.inflation,
                "allowance_inflation": household.assumptions.fiscal_drag.allowance_inflation,
                "income_freeze_until": household.assumptions.fiscal_drag.income_freeze_until.isoformat(),
                "iht_freeze_until": household.assumptions.fiscal_drag.iht_freeze_until.isoformat(),
                "never_uprated_freeze_forever":
                    household.assumptions.fiscal_drag.never_uprated_freeze_forever,
            },
        },
    }


def _assumptions_from_dict(raw: dict[str, Any]) -> Assumptions:
    """Rebuild `Assumptions` field by field.

    This was `Assumptions(**raw)` -- the one reflective corner of a module
    whose whole point is being explicit. A splat survives a new scalar field
    by luck and fails silently on a nested one: `fiscal_drag` would arrive as
    a plain dict, `asdict` would still serialise it for the cache key, and
    nothing would raise until an attribute access much later. Or never, with
    the projection quietly using different rules than the caller asked for.
    """
    drag = raw.get("fiscal_drag", {})
    defaults = FiscalDrag()
    return Assumptions(
        # Defaults read off the dataclass, never restated: a second copy of
        # the state pension here went stale while the first was uprated.
        life_expectancy_age=raw.get("life_expectancy_age", Assumptions.life_expectancy_age),
        state_pension_age=raw.get("state_pension_age", Assumptions.state_pension_age),
        state_pension_annual=raw.get("state_pension_annual", Assumptions.state_pension_annual),
        risk_tolerance=raw.get("risk_tolerance", Assumptions.risk_tolerance),
        mortality=(
            model_from_spec(raw["mortality"]) if raw.get("mortality") else FixedAge()
        ),
        max_age=raw.get("max_age", 105),
        db_survivor_fraction=raw.get("db_survivor_fraction", 0.50),
        survivor_essential_factor=raw.get("survivor_essential_factor", 0.90),
        survivor_discretionary_factor=raw.get("survivor_discretionary_factor", 0.75),
        fiscal_drag=FiscalDrag(
            inflation=drag.get("inflation", defaults.inflation),
            allowance_inflation=drag.get(
                "allowance_inflation", defaults.allowance_inflation
            ),
            income_freeze_until=_date(
                drag.get("income_freeze_until"), defaults.income_freeze_until
            ),
            iht_freeze_until=_date(
                drag.get("iht_freeze_until"), defaults.iht_freeze_until
            ),
            never_uprated_freeze_forever=drag.get(
                "never_uprated_freeze_forever", defaults.never_uprated_freeze_forever
            ),
        ),
    )


def _date(value: Any, default: date) -> date:
    if value is None:
        return default
    return value if isinstance(value, date) else date.fromisoformat(value)


def household_from_dict(raw: dict[str, Any]) -> Household:
    return Household(
        people=[
            Person(
                name=p["name"],
                date_of_birth=_pd(p["date_of_birth"]),  # type: ignore[arg-type]
                full_state_pension=p.get("full_state_pension", True),
                sex=p.get("sex"),
            )
            for p in raw.get("people", [])
        ],
        incomes=[
            IncomeSource(
                owner=i["owner"],
                type=IncomeType(i["type"]),
                amount=i["amount"],
                frequency=Frequency(i.get("frequency", "yearly")),
                start=_pd(i.get("start")),
                end=_pd(i.get("end")),
                annual_real_growth=i.get("annual_real_growth", 0.0),
                stops_at_retirement=i.get("stops_at_retirement", True),
            )
            for i in raw.get("incomes", [])
        ],
        expenses=[
            Expense(
                name=e["name"],
                amount=e["amount"],
                frequency=Frequency(e["frequency"]),
                category=ExpenseCategory(e["category"]),
                start=_pd(e.get("start")),
                end=_pd(e.get("end")),
                phase=Phase(e.get("phase", "always")),
                years_from_retirement=e.get("years_from_retirement"),
            )
            for e in raw.get("expenses", [])
        ],
        debts=[
            Debt(
                name=d["name"],
                balance=d["balance"],
                monthly_payment=d["monthly_payment"],
                remaining_months=d.get("remaining_months"),
                last_payment=_pd(d.get("last_payment")),
                interest_rate=d.get("interest_rate"),
            )
            for d in raw.get("debts", [])
        ],
        assets=[
            Asset(
                name=a["name"],
                type=AssetType(a["type"]),
                owner=a.get("owner", "joint"),
                value=a.get("value", 0.0),
                returns=return_model_from_dict(a["returns"]),
                annual_charge_pct=a.get("annual_charge_pct", 0.0),
                flat_annual_fee=a.get("flat_annual_fee", 0.0),
                contributions=(
                    Contribution(
                        employee_monthly=a["contributions"]["employee_monthly"],
                        employer_monthly=a["contributions"]["employer_monthly"],
                        start=_pd(a["contributions"].get("start")),
                        end=_pd(a["contributions"].get("end")),
                    )
                    if a.get("contributions")
                    else None
                ),
                maturity=(
                    Maturity(on=_pd(a["maturity"]["on"]), rollover_to=a["maturity"]["rollover_to"])  # type: ignore[arg-type]
                    if a.get("maturity")
                    else None
                ),
                defined_benefit=(
                    DefinedBenefit(**a["defined_benefit"]) if a.get("defined_benefit") else None
                ),
            )
            for a in raw.get("assets", [])
        ],
        goals=[
            Goal(
                description=g["description"],
                target_amount=g.get("target_amount"),
                target_date=_pd(g.get("target_date")),
                priority=g.get("priority", 1),
            )
            for g in raw.get("goals", [])
        ],
        assumptions=_assumptions_from_dict(raw.get("assumptions", {})),
    )


def dump_household(household: Household, indent: int = 2) -> str:
    """Serialize to a JSON string (like `json.dumps`, not `json.dump`).

    This does not write a file. A second positional argument is `indent`,
    not a path — passing a path there is silently accepted (`json.dumps`
    treats any string `indent` as the indent string) and writes nothing.
    To save to disk: `Path(path).write_text(dump_household(household))`.
    """
    return json.dumps(household_to_dict(household), indent=indent)


def load_household(text: str) -> Household:
    """Parse a JSON string (like `json.loads`, not `json.load`) — not a path."""
    return household_from_dict(json.loads(text))
