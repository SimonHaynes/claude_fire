"""Monte Carlo simulation over sampled historical return paths.

Runs `cashflow.project` many times, each against a different block-bootstrapped
path, and reduces the results to the handful of numbers a household can act on:
how often the plan held, what it could actually spend, what was left over, and
— for a plan with a gap to bridge — how much was left in the bridge when it
was needed.

Results are memoised to disk. Report iteration re-runs the same scenarios
constantly, and the cache key covers everything that could change an answer,
including the engine version, so a stale result can never outlive a change to
the logic that produced it.
"""
from __future__ import annotations

import hashlib
import json
import random
import warnings
import dataclasses
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, fields as dataclass_fields, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .cashflow import Projection, project
from .market import BlockBootstrap, MarketData
from .model import AssetType, Household
from .plan import compile_plan, real_terms_factor
from .scenario import Scenario
from .serde import household_to_dict
from .tax import TaxSystem
from .tax.iht import UK_IHT, BequestBreakdown, IHTRules
from .tax.uk import UK

PERCENTILES = (5, 10, 25, 50, 75, 90, 95)


@dataclass
class SimulationResult:
    scenario_name: str
    n_trials: int
    n_years: int
    first_year: int

    success_probability: float
    """Share of trials that never failed to fund a year's spending."""

    median_shortfall_year: int | None
    wealth_percentiles: dict[int, list[float]]
    investable_percentiles: dict[int, list[float]]
    isa_percentiles: dict[int, list[float]]
    """ISA balance alone. `bridge_percentiles` supersedes it for bridge
    questions now a GIA can carry part of one."""

    bridge_percentiles: dict[int, list[float]]
    """Everything outside a pension (cash reserve, ISA, GIA) by year — what
    actually funds a retirement before pension access, and so the binding
    constraint for anyone retiring before then."""

    pension_access_year: int | None
    """First calendar year any DC pension unlocks, or `None` when the household
    has no DC pension and so nothing to bridge."""

    asset_type_percentiles: dict[str, dict[int, list[float]]]
    """Balances summed by `AssetType.value`, by year. Report totals from
    `wealth_percentiles`, not by adding these: medians do not add across
    trials. Cash, ladder and bond reserves all group under `"cash"`; a type the
    household holds none of simply has no key."""

    bequest_percentiles: dict[int, float]
    """GROSS estate, before any death taxes. Rarely the number a client wants."""

    net_bequest_percentiles: dict[int, float]
    """What beneficiaries actually receive, after IHT and (for death after 75)
    their own income tax on inherited pension funds. For a pension-heavy
    estate this can be little more than half the gross figure."""

    median_estate_tax: float
    median_effective_estate_tax_rate: float

    median_annual_spend: float
    worst_case_5pct_min_spend: float
    """5th percentile, across trials, of each trial's leanest single year."""

    sample_years: int
    """Historical years the bootstrap could draw from. Narrow windows mean the
    tails are thin — worth stating wherever the success figure is quoted."""

    sample_first_year: int
    sample_last_year: int

    alive_fraction: list[float] = dataclasses.field(default_factory=list)
    """Share of trials with anyone still living, by year. `wealth_percentiles`
    changes meaning as a cohort dies out — past about 85 it mixes living
    households with frozen estates — so a fan chart needs this to say where the
    living part stops."""

    median_second_death_year: int | None = None
    """Calendar year the household is expected to end. Bequest figures are
    conditional on it, which is worth stating rather than implying."""

    state_funded_care_probability: float = 0.0
    """Share of trials where the local authority met part of a care bill. Not a
    failure, but it is the outcome where the estate has been spent down to the
    means-test floor — the number to show a client who plans to leave something
    behind."""

    median_care_paid: float = 0.0
    """Median lifetime care cost met by the household after the means test. Zero
    for most trials, because most people never enter residential care."""

    def year_labels(self) -> list[int]:
        return [self.first_year + i for i in range(self.n_years)]

    def isa_at(self, year: int, percentile: int = 50) -> float:
        return self.isa_percentiles[percentile][year - self.first_year]

    def bridge_at(self, year: int, percentile: int = 50) -> float:
        return self.bridge_percentiles[percentile][year - self.first_year]

    def bridge_at_access(self) -> tuple[float, float] | None:
        """(10th, 90th) percentile of non-pension assets in the year access
        begins — "how much is there to spend from once the pension is in play".

        This already includes a year of pension-funded top-ups: a strategy that
        draws hard once the pension unlocks can refill, in that same year, a
        bridge that had run dry the year before, failed trials included. Use
        `bridge_before_access` to ask how close the bridge itself came."""
        if self.pension_access_year is None:
            return None
        return (
            self.bridge_at(self.pension_access_year, 10),
            self.bridge_at(self.pension_access_year, 90),
        )

    def bridge_before_access(self) -> tuple[float, float] | None:
        """(10th, 90th) percentile of non-pension assets in the last year before
        access — how close the bridge itself came to running out, before any
        pension money could be recycled into it. `None` when there is no DC
        pension, or it is accessible from the first plan-year."""
        if self.pension_access_year is None:
            return None
        pre_access_year = self.pension_access_year - 1
        if pre_access_year < self.first_year:
            return None
        return (self.bridge_at(pre_access_year, 10), self.bridge_at(pre_access_year, 90))

    def asset_type_at(self, asset_type: str, year: int, percentile: int = 50) -> float:
        """`asset_type` is an `AssetType.value` string ("dc_pension", "isa",
        "gia", "cash", "property"). Raises `KeyError` if the household has
        no asset of that type — check `self.asset_type_percentiles` first if
        that's a live possibility rather than a programming error."""
        return self.asset_type_percentiles[asset_type][percentile][year - self.first_year]


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile of an unsorted list."""
    if not values:
        raise ValueError("percentile of an empty sample")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _strategy_spec(obj) -> dict | None:
    """Stable identity for a strategy: class name plus its *configuration*.

    Not `dataclasses.asdict`: that would include `init=False` runtime state (a
    Guyton-Klinger multiplier, a ladder's seeded flag) whose value depends on
    how many trials have already run, and for a non-dataclass it falls back to
    an id()-based repr that changes every process — a bug that disabled this
    cache entirely once already.
    """
    if obj is None:
        return None
    if not is_dataclass(obj):
        raise TypeError(
            f"{type(obj).__name__} must be a dataclass to be cacheable — "
            "otherwise its identity is a memory address and the cache silently misses"
        )
    config = {f.name: getattr(obj, f.name) for f in dataclass_fields(obj) if f.init}
    return {"class": type(obj).__name__, **config}


def _json_default(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(str(x) for x in obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return str(obj)


def cache_key(
    household: Household,
    scenario: Scenario,
    tax: TaxSystem,
    as_of: date,
    n_trials: int,
    block_years: int,
    seed: int | None,
    data: MarketData,
    iht: IHTRules = UK_IHT,
    beneficiary_marginal_rate: float = 0.40,
    gift_growth_rate: float = 0.0,
) -> str:
    payload = {
        "engine_version": __version__,
        "household": household_to_dict(household),
        "scenario": {
            "name": scenario.name,
            "retirement_dates": {k: v.isoformat() for k, v in scenario.retirement_dates.items()},
            "spending_multiplier": scenario.spending_multiplier,
            "one_off_spends": [asdict(s) for s in scenario.one_off_spends],
            "gifts": [asdict(g) for g in scenario.gifts],
            "pension_lump_sums": [asdict(p) for p in scenario.pension_lump_sums],
            "gift_growth_rate": gift_growth_rate,
            "market_stress": [dict(m) for m in scenario.market_stress],
            "pension_access": scenario.pension_access.value,
            # Hand-written: a new scenario field that changes an answer and is
            # not added here silently returns another scenario's cached result.
            "death_ages": dict(sorted((scenario.death_ages or {}).items())),
            "care": scenario.care.spec() if scenario.care else None,
            "income_annuity": scenario.income_annuity.spec() if scenario.income_annuity else None,
            "withdrawal": _strategy_spec(scenario.withdrawal),
            "drawdown": _strategy_spec(scenario.drawdown),
            "allocation": _strategy_spec(scenario.allocation),
        },
        "mortality": household.assumptions.mortality.spec(),
        "max_age": household.assumptions.max_age,
        "tax": {"name": tax.name, "tax_year": tax.tax_year, "access_age": tax.pension_access_age},
        "iht": {"nrb": iht.nil_rate_band, "rnrb": iht.residence_nil_rate_band,
                "rate": iht.rate, "pensions_from": iht.pensions_in_estate_from.isoformat(),
                "beneficiary_rate": beneficiary_marginal_rate},
        "as_of": as_of.isoformat(),
        "n_trials": n_trials,
        "block_years": block_years,
        "seed": seed,
        "market": {str(y): dict(sorted(row.items())) for y, row in sorted(data.by_year.items())},
    }
    blob = json.dumps(payload, default=_json_default, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def _result_to_json(result: SimulationResult) -> str:
    return json.dumps(asdict(result))


def _result_from_json(blob: str) -> SimulationResult:
    raw = json.loads(blob)
    for key in ("wealth_percentiles", "investable_percentiles", "isa_percentiles",
                "bridge_percentiles", "bequest_percentiles", "net_bequest_percentiles"):
        raw[key] = {int(k): v for k, v in raw[key].items()}
    raw["asset_type_percentiles"] = {
        asset_type: {int(p): series for p, series in by_percentile.items()}
        for asset_type, by_percentile in raw["asset_type_percentiles"].items()
    }
    return SimulationResult(**raw)


def _death_index(age_at_death: int, age_now: int, n_years: int) -> int:
    """Plan-year index from which a person is no longer alive.

    Alive for indices `0 .. index-1`. Floored at 1 so someone already past
    their sampled age still lives the first year, matching the horizon, and
    capped at the horizon so a very long life simply reaches the end of it.
    """
    return max(1, min(n_years, age_at_death - age_now + 1))


def _iht_at(iht: IHTRules, drag, as_of: date, on: date) -> IHTRules:
    """`iht` with its nil-rate bands eroded to their real value on `on`.

    The bands and the £2m taper threshold are frozen in nominal terms to an
    announced date; the taper threshold has to move with them, or a shrinking
    band would be tested against a fixed estate size and the residence band
    would taper out at the wrong point.
    """
    if drag.inflation <= 0:
        return iht
    freeze_years = max(0.0, (drag.iht_freeze_until - as_of).days / 365.25)
    elapsed = max(0.0, (on - as_of).days / 365.25)
    factor = real_terms_factor(drag.inflation, min(elapsed, freeze_years))
    return dataclasses.replace(
        iht,
        nil_rate_band=iht.nil_rate_band * factor,
        residence_nil_rate_band=iht.residence_nil_rate_band * factor,
        taper_threshold=iht.taper_threshold * factor,
    )


class StaleTaxRulesWarning(UserWarning):
    """The tax figures behind a projection have not been re-checked recently."""


TAX_VERIFICATION_MAX_AGE_DAYS = 366
"""A UK tax year: the cadence at which rates actually move."""


def warn_if_tax_rules_stale(tax: TaxSystem, iht: IHTRules, as_of: date) -> None:
    """Warn when a tax system's figures are older than a tax year.

    Raised before the cache is consulted, because a cached result is exactly the
    case where nobody is looking at the tax module. It puts the omission next to
    the numbers it affects rather than leaving it to the reader's judgement.
    """
    for label, rules in (("tax", tax), ("iht", iht)):
        verified_on = getattr(rules, "verified_on", None)
        if verified_on is None:
            continue
        age_days = (as_of - verified_on).days
        if age_days > TAX_VERIFICATION_MAX_AGE_DAYS:
            warnings.warn(
                f"{label} rules were last verified on {verified_on:%d %b %Y}, "
                f"{age_days // 365} year(s) before this projection's as_of date "
                f"({as_of:%d %b %Y}). Re-check the figures against gov.uk before "
                f"showing this output to anyone, then move `verified_on`.",
                StaleTaxRulesWarning,
                stacklevel=3,
            )


def _slots_by_asset_type(plan) -> dict[str, list[int]]:
    """Slots grouped by wrapper type (isa/gia/pension/cash/property), not by
    asset class: a bond holding here is just an asset whose `ReturnModel`
    samples `gov_bonds`. The three synthetic reserves carry no `AssetType` of
    their own and group under `"cash"` — including the bond reserve, which is a
    real volatile bond holding despite the label.
    """
    by_type: dict[str, list[int]] = {}
    for slot, asset in enumerate(plan.assets):
        by_type.setdefault(asset.type.value, []).append(slot)
    by_type.setdefault(AssetType.CASH.value, []).extend(
        [plan.cash_slot, plan.ladder_slot, plan.bond_slot]
    )
    return by_type


def _sample_deaths(
    household: Household,
    scenario: Scenario,
    ages_now: dict[str, int],
    n_years: int,
    rng: random.Random,
) -> dict[str, int]:
    """When each person dies in this trial, as a plan-year index.

    Drawn from the same rng as the returns, so a seed still reproduces a run,
    and independently between people — see `mortality.py` for why that is the
    conservative choice. A `scenario.death_ages` entry pins the age, but the
    draw still happens, so pinning one person does not reshuffle the return
    path and turn an attributable comparison into noise.
    """
    mortality = household.assumptions.mortality
    deaths = {}
    for person in household.people:
        sampled = mortality.sample_age_at_death(ages_now[person.name], person.sex, rng)
        pinned = (scenario.death_ages or {}).get(person.name)
        deaths[person.name] = _death_index(
            sampled if pinned is None else pinned, ages_now[person.name], n_years
        )
    return deaths


def run_monte_carlo(
    household: Household,
    scenario: Scenario,
    as_of: date,
    *,
    tax: TaxSystem = UK,
    iht: IHTRules = UK_IHT,
    beneficiary_marginal_rate: float = 0.40,
    gift_growth_rate: float = 0.0,
    data: MarketData | None = None,
    n_trials: int = 2000,
    block_years: int = 5,
    seed: int | None = None,
    cache_dir: str | Path | None = None,
) -> SimulationResult:
    """Simulate `scenario` for `household` over `n_trials` sampled return paths.

    Pass a `seed` for a reproducible run — a report that changes its numbers
    every time it is regenerated is not a report. Pass a `cache_dir` to memoise;
    identical re-runs then return in milliseconds.
    """
    data = data or MarketData.load()
    warn_if_tax_rules_stale(tax, iht, as_of)

    cache_path = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = cache_key(household, scenario, tax, as_of, n_trials, block_years, seed, data,
                        iht, beneficiary_marginal_rate, gift_growth_rate)
        cache_path = cache_dir / f"{key}.json"
        if cache_path.exists():
            return _result_from_json(cache_path.read_text())

    plan = compile_plan(household, scenario, tax, as_of)
    window = data.window(plan.series_keys)
    if not window:
        raise ValueError(
            f"no historical years cover every series this scenario needs "
            f"({sorted(plan.series_keys)}) — check the data directory"
        )

    sampler = BlockBootstrap(block_years=block_years)
    rng = random.Random(seed)
    isa_names = [a.name for a in household.assets_of(AssetType.ISA)]
    pension_names = [a.name for a in household.assets_of(AssetType.DC_PENSION)]

    dc_slots = {s for slots in plan.dc_slots_by_person.values() for s in slots}
    bridge_slots = tuple(s for s in plan.investable_slots if s not in dc_slots)
    pension_access_year = (
        next((y.calendar_year for y in plan.years if y.dc_accessible), None)
        if dc_slots else None
    )

    slots_by_type = _slots_by_asset_type(plan)

    # The second death settles the estate. Sampled mortality moves it per trial,
    # so these are only the fallback for a trial-free read; the loop below
    # re-resolves both the settle date and the eroded bands each time.
    base_iht = iht
    second_death_index = min(
        plan.n_years - 1, max(plan.death_index_by_person.values(), default=plan.n_years) - 1
    )
    settle_date = plan.years[second_death_index].end
    final_date = settle_date
    trial_iht = _iht_at(base_iht, household.assumptions.fiscal_drag, as_of, settle_date)
    # Gifts are compared against a terminal estate, so they are carried to the
    # same date. A `gift_growth_rate` of 0.0 values them as spent on receipt;
    # the portfolio's real growth rate assumes the recipient invests instead.
    # Neither is right — it depends on what the children actually do.
    gift_history = [(g.on, g.amount) for g in scenario.gifts]
    gift_value_history = [
        (g.on, g.amount * (1 + gift_growth_rate) ** max(0.0, (final_date - g.on).days / 365.25))
        for g in scenario.gifts
    ]

    successes = 0
    shortfall_years: list[int] = []
    wealth_by_year: list[list[float]] = [[] for _ in range(plan.n_years)]
    investable_by_year: list[list[float]] = [[] for _ in range(plan.n_years)]
    isa_by_year: list[list[float]] = [[] for _ in range(plan.n_years)]
    bridge_by_year: list[list[float]] = [[] for _ in range(plan.n_years)]
    asset_type_by_year: dict[str, list[list[float]]] = {
        t: [[] for _ in range(plan.n_years)] for t in slots_by_type
    }
    bequests: list[float] = []
    net_bequests: list[float] = []
    estate_taxes: list[float] = []
    effective_rates: list[float] = []
    all_spend: list[float] = []
    trial_min_spend: list[float] = []
    second_death_years: list[int] = []
    state_funded_trials = 0
    care_paid: list[float] = []
    alive_counts: list[int] = [0] * plan.n_years

    ages_now = plan.years[0].ages

    for _ in range(n_trials):
        path = sampler.path(data, plan.series_keys, plan.n_years, rng)
        deaths = _sample_deaths(household, scenario, ages_now, plan.n_years, rng)
        care_needs = scenario.care.sample_needs(household.people, rng) if scenario.care else None
        projection = project(plan, path, rng, deaths=deaths, care_needs=care_needs)
        if any(y.care_state_funded > 0 for y in projection.years):
            state_funded_trials += 1
        care_paid.append(sum(y.care_cost for y in projection.years))
        second_death_index = min(plan.n_years - 1, max(deaths.values(), default=1) - 1)
        settle_date = plan.years[second_death_index].end
        trial_iht = _iht_at(base_iht, household.assumptions.fiscal_drag, as_of, settle_date)
        second_death_years.append(plan.years[second_death_index].calendar_year)

        if projection.succeeded:
            successes += 1
        else:
            shortfall_years.append(projection.first_shortfall_year)  # type: ignore[arg-type]

        # Living years only: pooling post-death years would drag
        # `median_annual_spend` toward zero and collapse
        # `worst_case_5pct_min_spend` to zero for every trial, which reads as a
        # catastrophic plan rather than as years with nobody alive to spend.
        spends = [y.total_spending for y in projection.years if y.alive]
        if spends:
            all_spend.extend(spends)
            trial_min_spend.append(min(spends))

        for i, y in enumerate(projection.years):
            if y.alive:
                alive_counts[i] += 1
            wealth_by_year[i].append(y.total_wealth)
            investable_by_year[i].append(sum(y.balances[plan.slot_names[s]] for s in plan.investable_slots))
            isa_by_year[i].append(sum(y.balances[n] for n in isa_names))
            bridge_by_year[i].append(sum(y.balances[plan.slot_names[s]] for s in bridge_slots))
            for t, slots in slots_by_type.items():
                asset_type_by_year[t][i].append(sum(y.balances[plan.slot_names[s]] for s in slots))
        # Read at the second death, not the end of the horizon: the spouse
        # exemption makes the first death IHT-free, so the estate is taxed once,
        # when the household ends.
        settle = projection.years[second_death_index]
        estate = settle.total_wealth
        pension_left = sum(settle.balances[n] for n in pension_names)
        breakdown = trial_iht.bequest(
            non_pension_assets=estate - pension_left,
            pension_assets=pension_left,
            on=settle_date,
            bands=len(household.people),
            beneficiary_marginal_rate=beneficiary_marginal_rate,
            gifts=gift_history,
        )
        breakdown.gifts_made = sum(v for _, v in gift_value_history)
        bequests.append(estate)
        net_bequests.append(breakdown.total_to_family)
        estate_taxes.append(breakdown.total_tax)
        effective_rates.append(breakdown.effective_tax_rate)

    def bands(series: list[list[float]]) -> dict[int, list[float]]:
        return {p: [percentile(year, p) for year in series] for p in PERCENTILES}

    median_shortfall = (
        int(round(percentile(shortfall_years, 50))) if shortfall_years else None  # type: ignore[arg-type]
    )

    result = SimulationResult(
        scenario_name=scenario.name,
        n_trials=n_trials,
        n_years=plan.n_years,
        first_year=plan.years[0].calendar_year,
        success_probability=successes / n_trials,
        median_shortfall_year=median_shortfall,
        wealth_percentiles=bands(wealth_by_year),
        investable_percentiles=bands(investable_by_year),
        isa_percentiles=bands(isa_by_year),
        bridge_percentiles=bands(bridge_by_year),
        pension_access_year=pension_access_year,
        asset_type_percentiles={t: bands(series) for t, series in asset_type_by_year.items()},
        bequest_percentiles={p: percentile(bequests, p) for p in PERCENTILES},
        net_bequest_percentiles={p: percentile(net_bequests, p) for p in PERCENTILES},
        median_estate_tax=percentile(estate_taxes, 50),
        median_effective_estate_tax_rate=percentile(effective_rates, 50),
        median_annual_spend=percentile(all_spend, 50),
        worst_case_5pct_min_spend=percentile(trial_min_spend, 5),
        sample_years=len(window),
        sample_first_year=window[0],
        sample_last_year=window[-1],
        alive_fraction=[c / n_trials for c in alive_counts],
        state_funded_care_probability=state_funded_trials / n_trials,
        median_care_paid=percentile(care_paid, 50) if care_paid else 0.0,
        median_second_death_year=(
            int(percentile([float(y) for y in second_death_years], 50))
            if second_death_years else None
        ),
    )

    if cache_path is not None:
        cache_path.write_text(_result_to_json(result))
    return result


def run_many(
    household: Household,
    scenarios: Mapping[Any, Scenario],
    as_of: date,
    *,
    workers: int | None = None,
    **kwargs,
) -> dict[Any, SimulationResult]:
    """Run every scenario, across processes, and return results in input order.

    A 2,000-trial call is seconds of single-threaded pure Python, and the sweeps
    this engine's own guidance requires — every candidate retirement date under
    three withdrawal rules — are dozens of those. On eight cores that is the
    difference between a minute and twenty. Each `cache_key` differs, including
    by scenario *name*, so a sweep shares nothing and parallelism is the only
    lever available.

    `kwargs` are passed to `run_monte_carlo` unchanged; pass `seed` and
    `cache_dir` for anything reported. The cache is one file per key, so
    concurrent workers do not collide.

    `workers=1` runs in-process, which is what to use from a debugger or a test.

    **Call this from behind an `if __name__ == "__main__":` guard.** Process
    start-up re-imports the calling module, so a bare module-level call spawns
    workers that call it again.
    """
    if workers == 1:
        return {key: run_monte_carlo(household, s, as_of, **kwargs)
                for key, s in scenarios.items()}

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            key: pool.submit(run_monte_carlo, household, s, as_of, **kwargs)
            for key, s in scenarios.items()
        }
        return {key: future.result() for key, future in futures.items()}


def project_once(
    household: Household,
    scenario: Scenario,
    as_of: date,
    *,
    tax: TaxSystem = UK,
    real_returns: dict[str, float] | None = None,
) -> Projection:
    """Convenience: compile and run a single deterministic projection.

    Useful for reading a plan year by year, and for checking the mechanics by
    hand before trusting anything probabilistic built on top of them.
    """
    plan = compile_plan(household, scenario, tax, as_of)
    fixed = real_returns or {"global_equity": 0.05, "gov_bonds": 0.02, "inflation": 0.025,
                             "short_corporate": 0.01}
    return project(plan, [fixed] * plan.n_years)
