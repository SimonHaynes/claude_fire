"""Drawdown-order strategies: which pots get sold to cover a shortfall.

Also responsible for end-of-year housekeeping, because a strategy that holds a
reserve bucket has to refill it in good years — a bucket you only ever draw
from is just a slowly emptying pot, not a strategy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..model import PensionAccess
from ..portfolio import Portfolio
from ..tax import TaxSystem


@dataclass(frozen=True)
class DrawdownContext:
    """The slice of the plan a drawdown strategy is allowed to know about.

    Deliberately plain data (slot indices, flags) rather than the `Plan`
    object: strategies are configured *into* a scenario, which is compiled
    *into* a plan, so a strategy that imported `Plan` would close an import
    cycle and, worse, invite reaching into state it has no business touching.
    """

    tax: TaxSystem
    isa_slots: tuple[int, ...]
    isa_slots_by_person: dict[str, tuple[int, ...]]
    dc_slots_by_person: dict[str, tuple[int, ...]]
    gia_slots_by_person: dict[str, tuple[int, ...]]
    cash_slot: int
    ladder_slot: int
    bond_slot: int
    dc_accessible_by_person: dict[str, bool]
    is_retired: bool
    essential_spend: float
    growth_return: float
    bond_return: float
    """This year's real `gov_bonds` return -- distinct from `growth_return`
    (equity). For a strategy whose middle tier is genuine bonds rather than
    another fixed-rate cash-like reserve; see `ThreeBucketStrategy`."""
    isa_headroom_used: dict[str, float]
    """Mutable, shared for the whole plan-year across every mechanism that
    can credit someone's ISA -- the surplus sweep, a PCLS or DB lump sum,
    this strategy's own recycling, and the end-of-year Bed-and-ISA sweep in
    `cashflow.py`. One counter per person, reset fresh each year, so the
    real £20,000 annual limit cannot be credited to twice over by two
    mechanisms that would otherwise each assume the full amount was free."""

    pension_access: PensionAccess = PensionAccess.NONE
    """Whether ordinary drawdown from an accessible DC pension is fully
    taxable (`NONE`, `PCLS` -- PCLS itself is handled once, at access, in
    `cashflow.py`; anything drawn afterwards from either mode is fully
    taxable) or UFPLS -- automatically 25%/75% split, here in the drawdown
    strategies themselves, since UFPLS has no separate crystallisation
    event to handle it at."""

    tax_free_cash_used: dict[str, float] = field(default_factory=dict)
    """Mutable, shared for the *whole plan* (not reset per year, unlike
    `isa_headroom_used`) -- the Lump Sum Allowance is a lifetime limit.
    Updated by a PCLS event in `cashflow.py` and by any UFPLS withdrawal
    here, so the two share one real cap regardless of which mode a
    household actually uses."""


@dataclass
class DrawResult:
    unmet: float = 0.0
    isa_withdrawn: float = 0.0
    gia_withdrawn: float = 0.0
    cgt_paid: float = 0.0
    dc_withdrawn_gross: float = 0.0
    ufpls_tax_free: float = 0.0
    """Tax-free portion of any UFPLS withdrawal made resolving this need.
    Zero under `PensionAccess.NONE` or `PCLS`, where a DC withdrawal made
    here is always fully taxable -- PCLS's own tax-free lump sum is a
    separate, one-off event handled in `cashflow.py`, not part of this."""


def _draw_dc_pension(
    person: str, slots: tuple[int, ...], need: float,
    portfolio: Portfolio, taxable_income: dict[str, float], ctx: DrawdownContext,
    result: DrawResult, *, taxable_cap: float | None = None,
) -> float:
    """Draw from one person's DC pension to net `need`, taxed according to
    `ctx.pension_access`. Returns net gained; mutates `portfolio`,
    `taxable_income`, `result` and `ctx.tax_free_cash_used` in place.

    `taxable_cap`, if given, additionally bounds how much *taxable* income
    this draw may add (a tax-band ceiling, e.g. `TaxEfficientOrder.fill_to`)
    -- distinct from `need`, which bounds net income, because under UFPLS
    the two are not proportional to gross in the same way once the tax-free
    relief runs out.
    """
    available = portfolio.sum_of(slots)
    if available <= 0 or need <= 0:
        return 0.0
    already = taxable_income.get(person, 0.0)
    tax_before = ctx.tax.income_tax(already)

    if ctx.pension_access is PensionAccess.UFPLS:
        used = ctx.tax_free_cash_used.get(person, 0.0)
        wanted_gross = ctx.tax.ufpls_gross_for_net(already, used, need)
        gross = min(wanted_gross, available)
        if taxable_cap is not None:
            gross = min(gross, ctx.tax.ufpls_gross_for_taxable(used, taxable_cap))
        tax_free, taxable = ctx.tax.ufpls_split(gross, used)
        ctx.tax_free_cash_used[person] = used + tax_free
        result.ufpls_tax_free += tax_free
    else:
        wanted_gross = ctx.tax.gross_pension_withdrawal_for_net(already, need)
        gross = min(wanted_gross, available)
        if taxable_cap is not None:
            gross = min(gross, taxable_cap)
        tax_free, taxable = 0.0, gross

    net_gained = tax_free + taxable - (ctx.tax.income_tax(already + taxable) - tax_before)
    portfolio.draw_pro_rata(slots, gross)
    taxable_income[person] = already + taxable
    result.dc_withdrawn_gross += gross
    return net_gained


def isa_recipients(person: str, isa_slots_by_person: dict[str, tuple[int, ...]]) -> list[str]:
    """`person` first, then everyone else in the household with an ISA.

    A pound attributed to one person cannot literally land in someone
    else's ISA -- subscriptions are personal. What a real household does
    once its own allowance is full is gift the excess to a spouse (exempt,
    interspousal transfers carry no tax) who then subscribes it under their
    own allowance. The net effect is the same as if the money could simply
    flow to whichever ISA has room, so that is what this models -- a couple
    gets a shared ~£40,000/year capacity, not a hard £20,000 ceiling tied to
    whoever the money is nominally attributed to. Order matters: a person's
    own headroom is used before anyone else's, so a household with only one
    ISA behaves exactly as before.
    """
    return [person] + [p for p in isa_slots_by_person if p != person]


def credit_isa(
    amount: float, person: str, isa_slots_by_person: dict[str, tuple[int, ...]],
    tax: TaxSystem, portfolio: Portfolio, isa_headroom_used: dict[str, float],
) -> float:
    """Credit `amount` (attributed to `person`) into an ISA, spilling to
    another household member's ISA once `person`'s own headroom is used up
    -- see `isa_recipients`. Updates `isa_headroom_used` for whoever
    actually received it. Returns whatever could not be absorbed by anyone's
    remaining headroom (the caller decides where that goes -- a GIA, cash).
    """
    remainder = amount
    for recipient in isa_recipients(person, isa_slots_by_person):
        if remainder <= 0:
            break
        isa_slots = isa_slots_by_person.get(recipient, ())
        if not isa_slots:
            continue
        used = isa_headroom_used.get(recipient, 0.0)
        headroom = max(0.0, tax.isa_annual_allowance - used)
        if headroom <= 0:
            continue
        into_isa = min(remainder, headroom)
        portfolio.balances[isa_slots[0]] += into_isa
        remainder -= into_isa
        isa_headroom_used[recipient] = used + into_isa
    return remainder


class DrawdownStrategy(ABC):
    def reset(self) -> None:
        """Clear per-run state. Called once at the start of every trial."""

    def series_keys(self) -> frozenset[str]:
        """Market series this strategy needs, for the sample-window
        intersection -- see `AllocationStrategy.series_keys`. Most built-in
        strategies need nothing beyond what the household's own assets
        already require; `ThreeBucketStrategy` is the exception."""
        return frozenset()

    @abstractmethod
    def resolve(
        self,
        need: float,
        portfolio: Portfolio,
        taxable_income: dict[str, float],
        ctx: DrawdownContext,
    ) -> DrawResult:
        """Cover `need` of net spending, mutating portfolio and taxable income."""

    def end_of_year(
        self,
        portfolio: Portfolio,
        taxable_income: dict[str, float],
        ctx: DrawdownContext,
    ) -> None:
        """Optional housekeeping once the year's spending is settled.

        Receives the live taxable-income dict, so a strategy can see how much
        room is left in each person's tax bands and act on it.
        """


#: Below this, an unfunded amount is floating-point dust rather than a real
#: gap. One penny: small enough that nothing economically meaningful is
#: swallowed, large enough to absorb the residue of several gross-up
#: inversions compounding.
SHORTFALL_TOLERANCE = 0.01


def _draw_isa_gia_then_pensions(
    need: float,
    portfolio: Portfolio,
    taxable_income: dict[str, float],
    ctx: DrawdownContext,
    result: DrawResult,
) -> float:
    """ISAs (tax-free, pro-rata), then GIAs (CGT on the gain portion only,
    per person), then accessible DC pensions (grossed up for income tax).

    Shared by every built-in strategy: they differ in what they try *before*
    this, not in the tax mechanics once they get here. GIA sits between ISA
    and pension because CGT (18%/24%, £3,000 exempt every year) is usually
    cheaper than income tax on a pension withdrawal, and unlike a pension a
    GIA carries no beneficiary income tax on death -- CGT is wiped entirely
    at death, so a GIA held to the end is *more* tax-efficient than one sold
    during life. That death-uplift isn't a reason to prefer pension over GIA
    while alive, though: it only matters for whatever is left unsold.
    """
    if need > 0:
        taken = portfolio.draw_pro_rata(ctx.isa_slots, need)
        result.isa_withdrawn += taken
        need -= taken

    if need > 0:
        for person, slots in ctx.gia_slots_by_person.items():
            if need <= 0:
                break
            available = portfolio.sum_of(slots)
            if available <= 0:
                continue
            already = taxable_income.get(person, 0.0)
            basis_fraction = portfolio.basis_fraction_of(slots)
            wanted_gross = ctx.tax.gia_gross_for_net(already, basis_fraction, need)
            gross = min(wanted_gross, available)
            gain = gross * (1.0 - basis_fraction)
            cgt = ctx.tax.capital_gains_tax(gain, already)
            portfolio.draw_pro_rata(slots, gross)
            result.gia_withdrawn += gross
            result.cgt_paid += cgt
            need -= gross - cgt

    if need > 0:
        for person, slots in ctx.dc_slots_by_person.items():
            if need <= 0:
                break
            if not ctx.dc_accessible_by_person.get(person, False):
                continue  # below the Normal Minimum Pension Age
            need -= _draw_dc_pension(person, slots, need, portfolio, taxable_income, ctx, result)

    # Anything under a penny is arithmetic residue, not a funding gap.
    #
    # `need` is chased down through several inversions -- a pension gross-up,
    # a CGT gross-up, a bisection on the withdrawal rule -- and each leaves a
    # little floating-point dust. A residue of 3.6e-12 was enough to mark a
    # year as unfunded, and `Projection.succeeded` tests `unmet > 0`, so a
    # household sitting on £2.5m was recorded as having failed its plan.
    #
    # It stayed invisible while tax thresholds were round numbers, because the
    # inversions happened to land exactly. Scaling them for fiscal drag made
    # the residue appear, and the resulting success rates were not merely
    # wrong but chaotic -- 2% inflation scored 65% while 1% scored 92%, and
    # both were reproducible. A number that moves like that is not a finding.
    return max(0.0, need) if need > SHORTFALL_TOLERANCE else 0.0


@dataclass
class StandardOrder(DrawdownStrategy):
    """Cash reserve, then ISAs, then accessible DC pensions.

    Spends tax-free money before taxable money, which is the right default but
    not a tax-optimal one: it makes no attempt to level income across two
    people or to fill unused personal allowances. Good enough to plan with,
    not good enough to file a tax return by.
    """

    def resolve(self, need, portfolio, taxable_income, ctx):
        result = DrawResult()
        taken = portfolio.draw_pro_rata((ctx.cash_slot,), need)
        need -= taken
        result.unmet = _draw_isa_gia_then_pensions(need, portfolio, taxable_income, ctx, result)
        return result


@dataclass
class TaxEfficientOrder(DrawdownStrategy):
    """Fill cheap tax bands from the pension on purpose, and bank the surplus.

    `StandardOrder` spends the ISA first and touches the pension only when it
    must. That is intuitive, and after April 2027 it is close to backwards.

    Two things drive this strategy:

    **Unused allowances do not carry forward.** Every year a retiree draws
    nothing taxable is a personal allowance thrown away — £12,570 each that
    could have left the pension at 0%. Drawing to `fill_to` and spending the
    ISA only for the remainder converts that allowance into money.

    **A pension is now the worst asset to die holding.** Once pensions sit in
    the estate, both wrappers bear IHT, so the only difference on death is the
    beneficiary's income tax on inherited pension funds. Moving money out
    during life at your own marginal rate pre-pays that at a lower rate than
    the children would pay — the rule is simply *move while your rate is below
    theirs*. Surplus withdrawn beyond spending is subscribed to **the same
    person's own ISA** (never pooled into whichever ISA slot happens to be
    first), up to `isa_annual_limit`, and shares that limit with every other
    mechanism that can credit an ISA this year via `ctx.isa_headroom_used` —
    a real £20,000 cannot be credited twice by two mechanisms that each
    assumed it was untouched.

    Deliberately not modelled: this ignores whether a withdrawal triggers the
    Money Purchase Annual Allowance (taking any taxable income drops future
    contribution room to £10,000), which matters if anyone intends to keep
    contributing.
    """

    fill_to: float = 50_270.0
    """Taxable income to top each person up to. The basic-rate ceiling by
    default; pass a personal allowance figure to be more conservative, or a
    higher number to deliberately accept 40% now against a worse rate later."""

    isa_annual_limit: float = 20_000.0
    recycle_surplus: bool = True
    """Whether to withdraw *beyond* spending needs to use up the band."""

    def resolve(self, need, portfolio, taxable_income, ctx):
        result = DrawResult()
        need -= portfolio.draw_pro_rata((ctx.cash_slot,), need)

        # Pension first, but only as far as the cheap bands reach.
        for person, slots in ctx.dc_slots_by_person.items():
            if need <= 0:
                break
            if not ctx.dc_accessible_by_person.get(person, False):
                continue
            already = taxable_income.get(person, 0.0)
            headroom = self.fill_to - already
            if headroom <= 0:
                continue
            need -= _draw_dc_pension(
                person, slots, need, portfolio, taxable_income, ctx, result,
                taxable_cap=headroom,
            )

        # Whatever is left comes from the ISA, then from the pension at
        # whatever rate it takes — a shortfall is worse than a tax bill.
        result.unmet = _draw_isa_gia_then_pensions(need, portfolio, taxable_income, ctx, result)
        return result

    def end_of_year(self, portfolio, taxable_income, ctx):
        if not (self.recycle_surplus and ctx.is_retired):
            return
        # Thrown away, not merged into the year's real DrawResult: recycling
        # withdrawals were never surfaced in dc_withdrawn_gross even before
        # UFPLS existed -- this preserves that, rather than quietly starting
        # to report a number nothing previously accounted for.
        result = DrawResult()
        for person, slots in ctx.dc_slots_by_person.items():
            if not ctx.dc_accessible_by_person.get(person, False):
                continue
            if not ctx.isa_slots_by_person.get(person, ()):
                continue
            already = taxable_income.get(person, 0.0)
            # Bounded by the *household's* remaining ISA capacity, not just
            # this person's own -- the destination can spill to a spouse's
            # ISA (see `credit_isa`), so the amount worth drawing extra
            # pension for should reflect that shared capacity too.
            cap = min(self.isa_annual_limit, ctx.tax.isa_annual_allowance)
            total_isa_headroom = sum(
                max(0.0, cap - ctx.isa_headroom_used.get(recipient, 0.0))
                for recipient in isa_recipients(person, ctx.isa_slots_by_person)
                if ctx.isa_slots_by_person.get(recipient)
            )
            headroom = min(self.fill_to - already, total_isa_headroom)
            if headroom <= 0 or portfolio.sum_of(slots) <= 0:
                continue
            # `need=headroom` is a deliberately generous stand-in: there is
            # no net-income target here, only a gross/taxable ceiling, and
            # net is never more than gross, so it never binds ahead of
            # `taxable_cap` -- the cap below is what actually limits this.
            net = _draw_dc_pension(
                person, slots, headroom, portfolio, taxable_income, ctx, result,
                taxable_cap=headroom,
            )
            # Same IHT treatment, no income tax for the heirs, wherever it
            # lands -- person's own ISA first, a spouse's if that's full.
            credit_isa(net, person, ctx.isa_slots_by_person, ctx.tax, portfolio, ctx.isa_headroom_used)


@dataclass
class CashBondLadder(DrawdownStrategy):
    """Hold `target_years` of essential spending in a stable reserve.

    The point is not the return on the reserve — it is deliberately low — but
    that it removes the forced sale of growth assets in a bad year, which is
    the mechanism by which sequence-of-returns risk actually does its damage.
    The reserve is seeded from ISAs at retirement and topped back up in years
    the market did not fall.

    **Tested against a same-average-allocation rebalanced portfolio and it
    lost — worse success probability, worse worst-decile outcome, both on
    the classic historical worst-start years and a 2,000-trial Monte
    Carlo.** See REVIEW.md 1.15 for the numbers and the mechanism: topping
    the reserve back up to its *full* target on every qualifying year
    over-extracts from equities in years that were merely okay, not just
    genuinely strong ones. A plain `StaticMix`/`ByAssetTypeMix` at the same
    average equity percentage is not just simpler than this — it tested
    better. Do not reach for this strategy assuming it reduces sequence
    risk; run the comparison for the household in front of you first.
    """

    target_years: float = 3.0
    real_return: float = 0.01
    seeded: bool = field(default=False, init=False, repr=False)

    def reset(self) -> None:
        self.seeded = False

    def resolve(self, need, portfolio, taxable_income, ctx):
        result = DrawResult()
        need -= portfolio.draw_pro_rata((ctx.cash_slot,), need)
        need -= portfolio.draw_pro_rata((ctx.ladder_slot,), need)
        result.unmet = _draw_isa_gia_then_pensions(need, portfolio, taxable_income, ctx, result)
        return result

    def end_of_year(self, portfolio, taxable_income, ctx):
        portfolio.balances[ctx.ladder_slot] *= 1.0 + self.real_return
        if not ctx.is_retired:
            return
        target = self.target_years * ctx.essential_spend
        if not self.seeded:
            seed = portfolio.draw_pro_rata(ctx.isa_slots, target)
            portfolio.balances[ctx.ladder_slot] += seed
            self.seeded = True
            return
        shortfall = target - portfolio.balances[ctx.ladder_slot]
        if ctx.growth_return >= 0 and shortfall > 0:
            portfolio.balances[ctx.ladder_slot] += portfolio.draw_pro_rata(ctx.isa_slots, shortfall)


@dataclass
class ThreeBucketStrategy(DrawdownStrategy):
    """The classic three-bucket retirement income strategy: cash for
    near-term spending, bonds as the refill layer, equities for long-term
    growth -- Harold Evensky's original structure, popularised for retail
    investors by Christine Benz at Morningstar. Genuinely three tiers,
    unlike `CashBondLadder`'s single fixed-rate reserve:

    **Bucket 1 (cash)** -- `cash_years` of essential spending (2, by
    convention), held at zero real return. Spent first, refilled from
    Bucket 2 *every year*, unconditionally -- bonds are the shock absorber
    for near-term spending here, not a matter of market timing.

    **Bucket 2 (bonds)** -- `bond_years` further years of essential spending
    (5, by convention), earning the real `gov_bonds` series
    (`ctx.bond_return`) rather than a fixed rate -- a genuine bond holding
    with its own volatility, not another cash-like reserve dressed up as
    one. Refilled from Bucket 3 only in years equities are up: the actual
    "don't sell stocks in a crash" mechanic the strategy is known for.

    **Bucket 3 (equities)** -- everything else, spent last via the ordinary
    ISA/GIA/pension fallback once both reserves are empty.

    Both reserves are seeded once, at retirement, from the ISA -- 7 years of
    spending (the sum of the two defaults) carved out of the growth
    portfolio up front, matching the canonical "stocks for everything beyond
    year 7" description of this strategy.

    **Implemented faithfully from the published rules and tested -- it is
    the worst of four strategies compared, not the best.** Same-average-
    allocation rebalanced portfolio, `CashBondLadder`, this, and all-equity,
    stress-tested on the classic historical worst-start years and a
    2,000-trial Monte Carlo: this strategy had the *lowest* success
    probability of the four (84.5%, against 92.2% for the rebalanced
    comparison), worse even than `CashBondLadder`. See REVIEW.md 1.15. The
    mechanism is the same over-extraction `CashBondLadder` shows, worse
    here because the reserve is bigger (7 years vs 3) and Bucket 1's
    unconditional annual refill from Bucket 2 adds a second drain with no
    market-direction check at all. Building this "properly" from the
    canonical description did not rescue the idea -- it sharpened the case
    against it. Prefer a plain `StaticMix`/`ByAssetTypeMix` at a tested
    equity percentage if the goal is genuinely reducing sequence risk.
    """

    cash_years: float = 2.0
    bond_years: float = 5.0
    seeded: bool = field(default=False, init=False, repr=False)

    def series_keys(self) -> frozenset[str]:
        return frozenset({"gov_bonds"})

    def reset(self) -> None:
        self.seeded = False

    def resolve(self, need, portfolio, taxable_income, ctx):
        result = DrawResult()
        need -= portfolio.draw_pro_rata((ctx.cash_slot,), need)
        need -= portfolio.draw_pro_rata((ctx.bond_slot,), need)
        result.unmet = _draw_isa_gia_then_pensions(need, portfolio, taxable_income, ctx, result)
        return result

    def end_of_year(self, portfolio, taxable_income, ctx):
        # The bond bucket earns real bond returns -- an actual holding, not
        # a fixed-rate reserve dressed up as one.
        portfolio.balances[ctx.bond_slot] *= 1.0 + ctx.bond_return
        if not ctx.is_retired:
            return

        cash_target = self.cash_years * ctx.essential_spend
        bond_target = self.bond_years * ctx.essential_spend

        if not self.seeded:
            portfolio.balances[ctx.cash_slot] += portfolio.draw_pro_rata(ctx.isa_slots, cash_target)
            portfolio.balances[ctx.bond_slot] += portfolio.draw_pro_rata(ctx.isa_slots, bond_target)
            self.seeded = True
            return

        # Bucket 1 refilled from Bucket 2 every year, unconditionally --
        # bonds are the buffer for near-term spending, not a timing call.
        # If bonds themselves are short, top up straight from equities
        # rather than leave the one bucket meant to never run dry empty.
        cash_shortfall = cash_target - portfolio.balances[ctx.cash_slot]
        if cash_shortfall > 0:
            from_bonds = portfolio.draw_pro_rata((ctx.bond_slot,), cash_shortfall)
            portfolio.balances[ctx.cash_slot] += from_bonds
            cash_shortfall -= from_bonds
            if cash_shortfall > 0:
                portfolio.balances[ctx.cash_slot] += portfolio.draw_pro_rata(ctx.isa_slots, cash_shortfall)

        # Bucket 2 refilled from Bucket 3 only in years equities are up --
        # the actual "don't sell stocks in a crash" rule this strategy is
        # known for.
        bond_shortfall = bond_target - portfolio.balances[ctx.bond_slot]
        if ctx.growth_return >= 0 and bond_shortfall > 0:
            portfolio.balances[ctx.bond_slot] += portfolio.draw_pro_rata(ctx.isa_slots, bond_shortfall)
