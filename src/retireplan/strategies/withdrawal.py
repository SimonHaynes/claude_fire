"""Withdrawal strategies: how much to actually spend each year.

Essential spending, debt payments and one-off commitments are never touched —
a strategy only ever flexes the discretionary part, which is what makes these
rules something a household could plausibly agree to live by.

Four families, answering different questions.

**Needs-based** rules start from the spending plan and cut only when the money
will not stretch:

    SpendNominal          spend the plan; let a shortfall be a shortfall.
    Ratchet               spend the plan, raising it permanently after the
                          portfolio has grown far enough — never cutting.
    PostAccessStepUp      spend the plan, then permanently raise it once a
                          pension unlocks and the portfolio is clearly surplus.
    GuytonKlinger         the needs-based rule that genuinely adjusts, via
                          portfolio guardrails that move spending both ways.

**Portfolio-based** rules ignore the plan and spend a fraction of what the
portfolio is worth, so income falls after a crash and rises after a boom:

    PercentOfPortfolio    `rate` of the current portfolio — the "4% rule" in
                          its honest endowment form, 4% of what you have now.
    VariablePercentage    a rate that rises linearly with age, since a
                          90-year-old can safely spend a far higher fraction
                          than a 60-year-old.
    VPW                   the same idea derived rather than assumed: the rate
                          that exactly exhausts the pot over the remaining
                          horizon at an assumed return.

**Smoothed portfolio-based** rules take a fraction of the portfolio but damp
how fast the answer is allowed to move, buying spending stability at the cost
of tracking the portfolio less closely:

    VanguardDynamicSpending   clip the year-on-year change to a band.
    EndowmentSmoothing        blend the new answer with last year's.

**Bridge-aware** rules key off the money that is actually reachable before a
pension unlocks, rather than off a portfolio that includes a pot nobody can
touch yet:

    BridgeGuardrail       flex spending to make the accessible money reach
                          pension access, then hand over to another rule.

There is no free option. Needs-based rules give predictable income and put the
uncertainty into whether the plan survives; portfolio-based rules put it into
how much you get to spend — a rule that rarely fails can still deliver a 40%
pay cut in a bad decade. Smoothed rules move the uncertainty again rather than
removing it: a band that limits this year's cut to 2.5% guarantees that a 40%
overspend takes many years to correct. Read the spend percentiles alongside
the success probability, never the latter alone.

**A portfolio-based rule "cannot run out of money" only without a `floor`.**
Every one of them here has one, because a household cannot live on an
arithmetic fraction of a depleted pot, and the floor is what reintroduces
failure: `VPW` at a 3.5% assumed return scored 40% success on a bridge
household precisely because its 0.5 floor held spending up when the rule
itself wanted to spend less. Do not quote the textbook claim.

A `FixedFloorGuardrail` was removed rather than kept as an option: it cut only
once the accessible pots could no longer fund the year, far too late to protect
anything, and over 2,000 trials it cut 74 times and recovered zero times against
`GuytonKlinger`'s 638 and 561. Do not reintroduce a rule whose name promises a
safeguard it does not provide — it gets chosen for reports because it sounds
prudent.

Every strategy is handed `shortfall_for(amount)`, reporting what spending that
much would leave uncovered. That keeps rules generic: none needs to know the
drawdown order, the tax rules, or which pots are accessible.

Deliberately absent: **CAPE-based (valuation-aware) withdrawal**, which sets
the rate from `a + b/CAPE`. It cannot be tested honestly here. The sampler
draws blocks of historical returns without the valuation level that produced
them, so a CAPE path would have to be invented alongside the returns — and
block-bootstrapping destroys exactly the valuation mean-reversion the rule
exists to exploit. A result would measure the sampler, not the rule.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class WithdrawalContext:
    year_index: int
    is_retired: bool
    dc_accessible: bool
    nominal_discretionary: float
    fixed_spend: float
    net_income: float
    portfolio_value: float
    growth_return: float
    oldest_age: int
    years_remaining: int
    """Years until the household's last projected death -- a proxy for the
    remaining distribution period, the quantity Guyton-Klinger's final-years
    rule actually keys off. Tracks whichever alive-set variant this year
    belongs to, so a first death shortens it exactly when the plan's own
    schedule says it should."""
    bridge_value: float
    """Investable assets held *outside* any DC pension. Identical to
    `portfolio_value` once the pension unlocks; before that it is the only
    money the household can actually spend, which is what makes it the
    denominator a bridge rule has to key off."""
    years_to_access: int
    """Years until the DC pension unlocks -- 0 from the year it does. The
    length of the liability `bridge_value` has to cover."""
    shortfall_for: Callable[[float], float]


class WithdrawalStrategy(ABC):
    def reset(self) -> None:
        """Clear per-run state. Called once at the start of every trial."""

    @abstractmethod
    def decide(self, ctx: WithdrawalContext) -> float:
        """Discretionary spending to actually make this year."""


def _largest_affordable(
    ctx: WithdrawalContext, floor: float, ceiling: float, iterations: int = 10
) -> float:
    """Largest multiple of nominal discretionary in [floor, ceiling] with no shortfall.

    Bisection rather than algebra because affordability depends on the
    drawdown strategy and the tax gross-up, which are pluggable. `floor` is
    assumed already checked as affordable, so the returned `lo` is always a
    verified-feasible point.
    """
    lo, hi = floor, ceiling
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if ctx.shortfall_for(ctx.nominal_discretionary * mid) > 0:
            hi = mid
        else:
            lo = mid
    return ctx.nominal_discretionary * lo


def _affordable(ctx: WithdrawalContext, target: float, floor_amount: float) -> float:
    """`target` if it can be funded, else the most that can, never searching
    below `floor_amount`.

    Every rule needs this tail: a rule proposes a number, and the portfolio
    has the final say. When even `floor_amount` cannot be funded it is
    returned unchanged, so the projection records a real shortfall rather
    than a strategy quietly pretending the plan still works.
    """
    if ctx.shortfall_for(target) <= 0:
        return target
    if ctx.shortfall_for(floor_amount) > 0:
        return floor_amount
    return _largest_affordable(
        ctx, floor_amount / ctx.nominal_discretionary, target / ctx.nominal_discretionary
    )


def _pmt_rate(real_return: float, years: int) -> float:
    """Fraction of a pot payable every year for exactly `years`, earning
    `real_return` and ending at zero — the annuity (PMT) factor.

    At `real_return = 0` this is `1 / years`, the "1/N" rule that the IRS
    required-minimum-distribution tables approximate.
    """
    if years <= 1:
        return 1.0
    if real_return == 0.0:
        return 1.0 / years
    return real_return / (1.0 - (1.0 + real_return) ** -years)


@dataclass
class SpendNominal(WithdrawalStrategy):
    """Spend the plan regardless, and let a shortfall be a shortfall.

    The honest baseline: it measures whether the plan works, rather than
    whether the plan plus an assumed willingness to cut spending works.
    """

    def decide(self, ctx: WithdrawalContext) -> float:
        return ctx.nominal_discretionary


@dataclass
class GuytonKlinger(WithdrawalStrategy):
    """Guyton-Klinger dynamic withdrawal guardrails, adapted for pension income.

    Canonical Guyton-Klinger assumes the portfolio funds all of retirement.
    Here the household also has DB and State Pension income, so the
    "withdrawal rate" is redefined as the fraction of the *investable
    portfolio* drawn this year — `(spending - net income) / portfolio` — which
    is the quantity the rules exist to protect.

    Implemented:
      * Capital preservation — if the rate rises more than `guardrail` above
        the rate set in the first year of retirement, cut spending by
        `adjustment`. Suspended in the final `final_years` of the household's
        projected retirement (the canonical rule, not an adaptation): a cut
        this late defends an estate the retiree will not live to need, at the
        cost of the quality of life left, and Guyton's own finding was that
        continuing to cut barely changes failure rates while needlessly
        depressing spending. The prosperity rule below is not suspended —
        there is no equivalent argument against a raise near the end.
      * Prosperity — if it falls more than `guardrail` below, raise spending
        by `adjustment`, but never immediately after a down year (a
        simplification of the original's inflation/freeze rule).

    Adjustments are cumulative and persist.
    Not implemented: the portfolio management rule (which pot to sell) — that
    is `DrawdownStrategy`'s job here, kept separate so the two can be varied
    independently.
    """

    guardrail: float = 0.20
    adjustment: float = 0.10
    floor: float = 0.5
    ceiling: float = 1.5
    final_years: int = 15
    """How close to the household's last projected death "the final years"
    means. 15 is Guyton's own figure, not a tuned default -- change it only
    to model a household's plan running to a materially different horizon."""

    initial_rate: float | None = field(default=None, init=False, repr=False)
    multiplier: float = field(default=1.0, init=False, repr=False)

    def reset(self) -> None:
        self.initial_rate = None
        self.multiplier = 1.0

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired:
            return ctx.nominal_discretionary

        candidate = ctx.nominal_discretionary * self.multiplier
        drawn = ctx.fixed_spend + candidate - ctx.net_income
        rate = drawn / ctx.portfolio_value if ctx.portfolio_value > 0 else float("inf")

        if self.initial_rate is None:
            # A zero baseline would make every later year look infinitely worse.
            self.initial_rate = max(rate, 1e-6)
        elif (
            rate > self.initial_rate * (1 + self.guardrail)
            and ctx.years_remaining > self.final_years
        ):
            self.multiplier = max(self.floor, self.multiplier * (1 - self.adjustment))
        elif rate < self.initial_rate * (1 - self.guardrail) and ctx.growth_return >= 0:
            self.multiplier = min(self.ceiling, self.multiplier * (1 + self.adjustment))

        # The guardrail bounds are a heuristic, not a solvency guarantee, so
        # `_affordable` searches for what is genuinely fundable rather than
        # reporting a shortfall the strategy exists to prevent.
        return _affordable(
            ctx,
            ctx.nominal_discretionary * self.multiplier,
            ctx.nominal_discretionary * self.floor,
        )


@dataclass
class PercentOfPortfolio(WithdrawalStrategy):
    """Spend a fixed percentage of the *current* portfolio each year.

    The endowment rule, and the honest version of "the 4% rule": 4% of what
    the portfolio is worth today, not 4% of its value at retirement uprated
    for inflation ever since. Because the draw is always a fraction of what
    remains, the money cannot run out — but income tracks the market, so a
    50% crash means a 50% pay cut in the same year.

    Since income and pensions already cover part of the spending, the rate is
    applied to the portfolio and the result used as the *total* spending
    target, with the discretionary part being whatever is left after fixed
    commitments. `floor`/`ceiling` bound it against the plan so the answer
    stays recognisable as a lifestyle rather than an arithmetic output.
    """

    rate: float = 0.04
    floor: float = 0.5
    ceiling: float = 1.5

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        budget = ctx.portfolio_value * self.rate + ctx.net_income
        target = max(ctx.nominal_discretionary * self.floor,
                     min(budget - ctx.fixed_spend, ctx.nominal_discretionary * self.ceiling))
        return _affordable(ctx, target, ctx.nominal_discretionary * self.floor)


@dataclass
class VariablePercentage(WithdrawalStrategy):
    """A withdrawal rate that rises with age.

    Spending 4% at 60 and 4% at 90 makes little sense: the second has a far
    shorter horizon to fund. This raises the rate linearly from `start_rate`
    at `start_age` to `end_rate` at `end_age`, which spends the portfolio
    down deliberately rather than leaving an accidental estate — useful for a
    household that would rather enjoy the money than bequeath it, and a
    reasonable counterweight to rules that hoard by construction.

    Ages are taken from the oldest person in the household.
    """

    start_age: int = 60
    end_age: int = 95
    start_rate: float = 0.035
    end_rate: float = 0.10
    floor: float = 0.5
    ceiling: float = 2.0

    def rate_at(self, age: int) -> float:
        if age <= self.start_age:
            return self.start_rate
        if age >= self.end_age:
            return self.end_rate
        span = self.end_age - self.start_age
        t = (age - self.start_age) / span
        return self.start_rate + (self.end_rate - self.start_rate) * t

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        budget = ctx.portfolio_value * self.rate_at(ctx.oldest_age) + ctx.net_income
        target = max(ctx.nominal_discretionary * self.floor,
                     min(budget - ctx.fixed_spend, ctx.nominal_discretionary * self.ceiling))
        return _affordable(ctx, target, ctx.nominal_discretionary * self.floor)


@dataclass
class Ratchet(WithdrawalStrategy):
    """Kitces' ratcheting rule: raise spending after the portfolio has grown
    a long way, and never lower it.

    The observation behind it is that the 4% rule is priced for the worst
    historical sequence, so in every other sequence the retiree dies rich
    having under-spent for thirty years. A ratchet keeps the safety of a
    fixed real plan and spends some of the upside when it clearly arrived.

    **Rule.**

    | | |
    |---|---|
    | Trigger | portfolio ≥ `trigger` × its value in the first year of retirement |
    | Size | spending rises `step`, permanently and cumulatively |
    | Cadence | at most once every `min_years_between` years |
    | Downward | never — the rule has no cut in it |

    The baseline is the value at retirement and is **not** re-set after a
    ratchet, which is the published rule: a portfolio that grows to 150% and
    stays there keeps earning a raise every three years. `ceiling` bounds
    that, and is an addition here rather than part of the rule — the raises
    are self-limiting in practice, because spending more pulls the portfolio
    back below the trigger, but "in practice" is not a bound.

    What this cannot do is respond to a bad sequence: it is `SpendNominal`
    on the way down, and inherits its failure behaviour exactly.
    """

    trigger: float = 1.5
    step: float = 0.10
    min_years_between: int = 3
    ceiling: float = 2.0
    floor: float = 0.5

    baseline: float | None = field(default=None, init=False, repr=False)
    multiplier: float = field(default=1.0, init=False, repr=False)
    last_step_year: int = field(default=0, init=False, repr=False)

    def reset(self) -> None:
        self.baseline = None
        self.multiplier = 1.0
        self.last_step_year = 0

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        if self.baseline is None:
            self.baseline = ctx.portfolio_value
            self.last_step_year = ctx.year_index
        elif (
            ctx.portfolio_value >= self.baseline * self.trigger
            and ctx.year_index - self.last_step_year >= self.min_years_between
        ):
            self.multiplier = min(self.ceiling, self.multiplier * (1 + self.step))
            self.last_step_year = ctx.year_index

        return _affordable(
            ctx,
            ctx.nominal_discretionary * self.multiplier,
            ctx.nominal_discretionary * self.floor,
        )


@dataclass
class VPW(WithdrawalStrategy):
    """Bogleheads' Variable Percentage Withdrawal: the rate that exhausts the
    portfolio exactly at the end of the horizon.

    `VariablePercentage` ramps its rate linearly between two ages picked by
    hand. This derives the same shape instead: each year's rate is the
    annuity factor for the years remaining at `expected_real_return`, so it
    rises automatically as the horizon shortens and depends on nothing that
    has to be guessed twice.

    **Rule.** rate = PMT(`expected_real_return`, `ctx.years_remaining`),
    applied to the current portfolio; the result is the total spending
    budget alongside income, and the discretionary part is what is left
    after fixed commitments. Bounded to [`floor`, `ceiling`] multiples of the
    plan so the answer stays a lifestyle rather than an arithmetic output.

    At `expected_real_return = 0` the rate is `1 / years_remaining` — the
    "1/N" rule, which is what the IRS required-minimum-distribution tables
    approximate and is the most assumption-free rule in this module.

    Two deliberate departures from the published spreadsheet. Bogleheads
    derives the return from the asset allocation (roughly 5% real equity,
    1.9% real bonds, weighted); here it is a parameter, because the engine's
    allocation is a separate pluggable axis and reading through to it would
    couple them. And the spreadsheet's `PMT(..., type=1)` pays at the start
    of the year, while this engine grows the portfolio before the draw, so
    the end-of-period factor is the self-consistent one — a difference of
    (1 + r), under 4% of the rate.

    Like every portfolio-based rule this cannot run out of money, and that
    is not the same as succeeding: read the spend percentiles.
    """

    expected_real_return: float = 0.035
    floor: float = 0.5
    ceiling: float = 2.0

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        rate = _pmt_rate(self.expected_real_return, ctx.years_remaining)
        budget = ctx.portfolio_value * rate + ctx.net_income
        target = max(ctx.nominal_discretionary * self.floor,
                     min(budget - ctx.fixed_spend, ctx.nominal_discretionary * self.ceiling))
        return _affordable(ctx, target, ctx.nominal_discretionary * self.floor)


@dataclass
class VanguardDynamicSpending(WithdrawalStrategy):
    """Vanguard's dynamic spending rule: a percentage of the portfolio, with
    the year-on-year *change* clipped to a band.

    Percent-of-portfolio spending is safe and unliveable — a 30% fall means
    a 30% pay cut, immediately. This keeps the percentage as the target and
    limits how fast spending may follow it, which is the trade most
    households would actually make.

    **Rule.** Each year, take the middle of three numbers:

    | | |
    |---|---|
    | Target | `rate` × portfolio (plus income, less fixed spending) |
    | Ceiling | last year's spending × (1 + `ceiling_rise`) |
    | Floor | last year's spending × (1 − `floor_drop`) |

    Vanguard's published 5% / 2.5% pairing is asymmetric on purpose: a
    retiree will accept a slow rise more readily than a fast cut, and the
    tighter floor is what makes the rule liveable. The cost is arithmetic
    and unavoidable — after a large fall, spending stays above the
    sustainable target for years, drawing the portfolio down while it
    catches up. That is the mechanism to look for when this rule loses.

    The anchor is what was actually **spent** last year, not what the rule
    asked for, so a year in which the portfolio forced a cut restarts the
    band from the lower figure rather than from a fiction. The first year of
    retirement has no prior year and takes the unclipped target.
    """

    rate: float = 0.04
    ceiling_rise: float = 0.05
    floor_drop: float = 0.025
    floor: float = 0.0
    prior_spend: float | None = field(default=None, init=False, repr=False)

    def reset(self) -> None:
        self.prior_spend = None

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        target = ctx.portfolio_value * self.rate + ctx.net_income - ctx.fixed_spend
        if self.prior_spend is not None:
            target = max(self.prior_spend * (1 - self.floor_drop),
                         min(target, self.prior_spend * (1 + self.ceiling_rise)))

        spend = _affordable(ctx, max(0.0, target), ctx.nominal_discretionary * self.floor)
        self.prior_spend = spend
        return spend


@dataclass
class EndowmentSmoothing(WithdrawalStrategy):
    """The Yale endowment spending rule, applied to a household.

    Same problem as `VanguardDynamicSpending` and a gentler answer: rather
    than clipping the change, blend the new target into last year's
    spending, so a market move arrives as an exponentially-decaying series
    of small adjustments instead of one large one.

    **Rule.** spending = `weight_on_prior` × last year's spending
    + (1 − `weight_on_prior`) × (`rate` × portfolio, plus income, less fixed
    spending). Yale's own weighting is 80/20 against a 5.25% payout;
    `rate` defaults lower here because a household's horizon is finite and
    an endowment's is not.

    The blend is unbounded in both directions, which is the difference that
    matters: after a crash it cuts immediately (by a fifth of the gap, not
    by nothing), where Vanguard's floor forbids more than 2.5%. It is
    therefore the more responsive of the two despite feeling gentler, and it
    offers no promise at all about the size of a single year's move.

    Real terms throughout, so Yale's inflation uprating is already in the
    frame and no adjustment is applied.
    """

    rate: float = 0.04
    weight_on_prior: float = 0.8
    floor: float = 0.0
    prior_spend: float | None = field(default=None, init=False, repr=False)

    def reset(self) -> None:
        self.prior_spend = None

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        target = ctx.portfolio_value * self.rate + ctx.net_income - ctx.fixed_spend
        if self.prior_spend is not None:
            w = self.weight_on_prior
            target = w * self.prior_spend + (1 - w) * target

        spend = _affordable(ctx, max(0.0, target), ctx.nominal_discretionary * self.floor)
        self.prior_spend = spend
        return spend


@dataclass
class BridgeGuardrail(WithdrawalStrategy):
    """Guardrails on the money that can actually be spent before a pension
    unlocks — then hand over to another rule.

    Every other rule here keys off the whole portfolio. For a household that
    stops working before its pension is reachable, that denominator is
    wrong in the one place it matters: the pension is the largest holding
    and is untouchable, so a bridge emptying towards zero barely moves a
    whole-portfolio withdrawal rate and trips no guardrail until the money
    has gone. `GuytonKlinger` will not cut during a failing bridge; this
    will.

    **Rule.** While retired and the pension is still locked:

    | | |
    |---|---|
    | Measure | coverage = sustainable draw ÷ draw needed this year, where the sustainable draw is `bridge_value` annuitised over `ctx.years_to_access` at `assumed_real_return` |
    | Cut | coverage < 1 − `guardrail` → spending × (1 − `adjustment`), cumulative, floored at `floor` × the plan |
    | Restore | coverage > 1 + `guardrail`, and equities did not fall this year → spending × (1 + `adjustment`), capped at the plan |
    | Cadence | once a year, at most one move |
    | At access | the multiplier is dropped and `after` takes over entirely |

    Spending is never raised **above** the plan while bridging, however far
    ahead the bridge runs: a surplus mid-bridge is what makes the remaining
    years reach, and spending it converts a solved problem back into an open
    one. Upside belongs after access, which is `PostAccessStepUp`'s job.

    `assumed_real_return = 0` is the default and treats the bridge as a pile
    of cash to be divided by the years left. It is deliberately pessimistic:
    a bridge is short, so its arithmetic mean return is a poor description
    of what it will actually deliver, and the cost of over-estimating is
    that the household finds out too late to do anything about it.

    Handing over at access rather than continuing is the point — the
    constraint that justified the cuts is gone, so the cuts go with it. Note
    that `after` sees its first retired year at pension access, which is
    where a rule like `GuytonKlinger` will anchor its initial withdrawal
    rate. That is the right anchor for this household and the wrong one for
    any other reading of the same rule.

    Measured over a 105-run grid (REVIEW.md 1.18–1.19), against
    `diagnose(plan).bridge_coverage`: **+31.4 points** of success at coverage
    0.6–0.8, +12.9 at 0.8–1.0, and **+0.0 to +0.1 once coverage passes 1.2**
    — inert in every such cell, which is both the behaviour to expect and a
    regression check worth re-running after any change here. It is the only
    rule in this module that gets *better* as the accessible share shrinks;
    every whole-portfolio rule gets worse.
    """

    guardrail: float = 0.0
    """Dead band around coverage of 1.0. Zero by default, unlike
    `GuytonKlinger`'s 20%: a band exists to stop a rule reacting to noise it
    has decades to ride out, and a bridge has neither the decades nor the
    mean reversion. Measured on a seven-year bridge, widening it to 10% cost
    ~2 points of success and to 20% ~5, monotonically."""

    adjustment: float = 0.25
    """How hard each move is. Larger than `GuytonKlinger`'s 10% for the same
    reason: on a seven-year bridge a 10% step spends most of the bridge
    getting to a cut that mattered. 25% beat 10% by ~3 points at every
    band."""

    floor: float = 0.5
    """How far spending may be cut, as a multiple of the plan's
    discretionary. A household preference rather than a tuned figure — and
    the single biggest lever in the whole rule. Dropping it to 0 (spend
    essentials only) buys several more points of success, and is the honest
    thing to test whenever a bridge is the binding constraint."""

    assumed_real_return: float = 0.0
    after: WithdrawalStrategy = field(default_factory=SpendNominal)

    multiplier: float = field(default=1.0, init=False, repr=False)

    def reset(self) -> None:
        self.multiplier = 1.0
        self.after.reset()

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.years_to_access <= 0:
            return self.after.decide(ctx)
        if ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        candidate = ctx.nominal_discretionary * self.multiplier
        needed = ctx.fixed_spend + candidate - ctx.net_income
        sustainable = ctx.bridge_value * _pmt_rate(
            self.assumed_real_return, ctx.years_to_access
        )
        coverage = sustainable / needed if needed > 0 else float("inf")

        if coverage < 1 - self.guardrail:
            self.multiplier = max(self.floor, self.multiplier * (1 - self.adjustment))
        elif coverage > 1 + self.guardrail and ctx.growth_return >= 0:
            self.multiplier = min(1.0, self.multiplier * (1 + self.adjustment))

        return _affordable(
            ctx,
            ctx.nominal_discretionary * self.multiplier,
            ctx.nominal_discretionary * self.floor,
        )


@dataclass
class PostAccessStepUp(WithdrawalStrategy):
    """Spend more, permanently, once the money is unlocked and clearly surplus.

    Triggers when a DC pension is accessible *and* the portfolio covers at
    least `surplus_years` of total spending — a legible proxy for "this is
    more than we need", not a formal sustainability test.

    Once triggered it never steps back down, which is the point and also the
    risk: households do not casually reverse a lifestyle, so a permanent rise
    cannot be offset by an earlier good decade the way a one-off cost can.
    The floor search still applies underneath, so a bad enough sequence can
    still force a cut — this is a target, not a promise.
    """

    step_up: float = 1.25
    surplus_years: float = 25.0
    floor: float = 0.6
    stepped_up: bool = field(default=False, init=False, repr=False)

    def reset(self) -> None:
        self.stepped_up = False

    def decide(self, ctx: WithdrawalContext) -> float:
        if not ctx.is_retired or ctx.nominal_discretionary <= 0:
            return ctx.nominal_discretionary

        if not self.stepped_up and ctx.dc_accessible:
            annual_need = ctx.fixed_spend + ctx.nominal_discretionary
            if annual_need > 0 and ctx.portfolio_value / annual_need >= self.surplus_years:
                self.stepped_up = True

        multiplier = self.step_up if self.stepped_up else 1.0
        return _affordable(
            ctx,
            ctx.nominal_discretionary * multiplier,
            ctx.nominal_discretionary * self.floor,
        )
