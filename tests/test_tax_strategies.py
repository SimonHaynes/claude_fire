"""PCLS, tax-efficient drawdown, and the percentage withdrawal rules."""
from __future__ import annotations

from datetime import date

import pytest

from retireplan import (
    Asset,
    AssetType,
    Assumptions,
    Expense,
    ExpenseCategory,
    FixedReal,
    Frequency,
    Household,
    PensionAccess,
    PensionLumpSum,
    PercentOfPortfolio,
    Person,
    Scenario,
    SpendNominal,
    StandardOrder,
    TaxEfficientOrder,
    VariablePercentage,
    compile_plan,
    project,
)
from retireplan.strategies.withdrawal import WithdrawalContext
from retireplan.tax.uk import UK

AS_OF = date(2026, 1, 1)
FLAT = {"global_equity": 0.0, "gov_bonds": 0.0, "inflation": 0.0, "recession": 0.0}


def retired_household(pension=1_000_000.0, isa=200_000.0, spend=40_000.0, dob=date(1960, 1, 1)):
    return Household(
        people=[Person("Alex", dob)],
        expenses=[Expense("Living", spend, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
        assets=[
            Asset("Pension", AssetType.DC_PENSION, "Alex", pension, returns=FixedReal(0.0)),
            Asset("ISA", AssetType.ISA, "Alex", isa, returns=FixedReal(0.0)),
        ],
        assumptions=Assumptions(life_expectancy_age=80, state_pension_age=99),
    )


def run(household, scenario, years=None):
    plan = compile_plan(household, scenario, UK, AS_OF)
    return project(plan, [FLAT] * plan.n_years)


class TestPCLS:
    def test_not_taken_unless_asked_for(self):
        projection = run(retired_household(),
                         Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal()))
        assert all(y.pcls_taken == 0 for y in projection.years)

    def test_taken_once_at_pension_access(self):
        projection = run(retired_household(),
                         Scenario("s", retirement_dates={"Alex": AS_OF},
                                  withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS))
        taken = [y for y in projection.years if y.pcls_taken > 0]
        assert len(taken) == 1

    def test_capped_by_the_lump_sum_allowance_not_the_25_percent(self):
        """The cap binds above ~£1.07m — precisely where people assume it does not."""
        big = run(retired_household(pension=2_000_000),
                  Scenario("s", retirement_dates={"Alex": AS_OF},
                           withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS))
        lump = next(y.pcls_taken for y in big.years if y.pcls_taken > 0)
        assert lump == pytest.approx(UK.lump_sum_allowance)   # not 500,000
        assert lump < 2_000_000 * 0.25

    def test_uncapped_below_the_allowance(self):
        small = run(retired_household(pension=400_000),
                    Scenario("s", retirement_dates={"Alex": AS_OF},
                             withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS))
        lump = next(y.pcls_taken for y in small.years if y.pcls_taken > 0)
        assert lump == pytest.approx(100_000)

    def test_it_leaves_the_pension_and_is_not_taxed(self):
        household = retired_household(pension=400_000, spend=1_000)
        projection = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                             withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS))
        first = projection.years[0]
        assert first.balances["Pension"] == pytest.approx(300_000)
        assert first.tax_paid == 0.0  # tax-free by definition

    def test_the_lump_is_invested_not_left_in_cash(self):
        """A real finding, not a hypothetical: PCLS used to land straight in
        the shared cash reserve and sit there earning nothing -- the same
        idle-cash problem ordinary surplus income was already fixed for,
        just missed here. Confirmed against a real client's report as a
        visible, otherwise-unexplained bulge in a "cash" fan chart."""
        household = retired_household(pension=400_000, isa=0.0, spend=1_000)
        projection = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                             withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS))
        first = projection.years[0]
        assert first.pcls_taken == pytest.approx(100_000)
        assert first.balances["__cash_reserve"] == pytest.approx(0.0)
        # £20,000 into the ISA (the annual allowance), the rest into the GIA.
        assert first.balances["ISA"] == pytest.approx(20_000 - 1_000, abs=1.0)
        assert first.balances["Alex — Surplus GIA (Global Tracker)"] == pytest.approx(80_000, abs=1.0)

    def test_helper_respects_what_was_already_taken(self):
        assert UK.pcls_available(1_000_000, already_taken=UK.lump_sum_allowance) == 0.0
        assert UK.pcls_available(400_000, already_taken=50_000) == pytest.approx(100_000)

    def test_locked_pension_yields_no_lump_sum(self):
        """Alex is 55 at the as-of date and cannot touch it until 57."""
        household = retired_household(dob=date(1971, 1, 1))
        projection = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                             withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS))
        assert projection.years[0].pcls_taken == 0.0
        assert projection.years[1].pcls_taken == 0.0
        assert projection.years[2].pcls_taken > 0.0


class TestUFPLS:
    def test_not_split_unless_asked_for(self):
        """PensionAccess.NONE: every withdrawal fully taxable, same as before
        UFPLS existed."""
        household = retired_household(pension=400_000, isa=0.0, spend=30_000)
        first = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal())).years[0]
        assert first.ufpls_tax_free_taken == 0.0
        assert first.dc_withdrawn_gross > 0

    def test_matches_the_hand_verified_figure(self):
        """No other income, £30,000 net target: gross £32,336.47, of which
        £8,084.12 is tax-free and £2,336.47 is tax -- independently verified
        by hand and by bisection against UK.income_tax() before this was
        wired into the drawdown strategies at all (see the session notes on
        UFPLS vs PCLS for the derivation)."""
        household = retired_household(pension=1_000_000, isa=0.0, spend=30_000)
        first = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS)).years[0]
        assert first.dc_withdrawn_gross == pytest.approx(32_336.47, abs=0.5)
        assert first.ufpls_tax_free_taken == pytest.approx(8_084.12, abs=0.5)
        assert first.tax_paid == pytest.approx(2_336.47, abs=0.5)
        assert first.pcls_taken == 0.0  # no crystallisation event under UFPLS

    def test_nets_the_same_target_as_a_fully_taxable_withdrawal_but_draws_less(self):
        """UFPLS's tax-free relief means less has to leave the pot to reach
        the same net income than a fully-taxable draw needs."""
        household = retired_household(pension=1_000_000, isa=0.0, spend=30_000)
        none = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                       withdrawal=SpendNominal())).years[0]
        ufpls = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS)).years[0]
        assert ufpls.dc_withdrawn_gross < none.dc_withdrawn_gross
        assert ufpls.tax_paid < none.tax_paid

    def test_degrades_to_fully_taxable_once_the_allowance_is_exhausted(self):
        """A household drawing well past the Lump Sum Allowance should end
        up paying the same tax on the excess as PensionAccess.NONE would --
        the relief has a lifetime ceiling, not an infinite supply."""
        # A pot with 25% far above the LSA (~£268,275): early withdrawals
        # get relief, but this tests the total after enough years to matter
        # is bounded the same way plain taxable drawdown is, not that any
        # single year matches exactly.
        household = retired_household(pension=3_000_000, isa=0.0, spend=200_000)
        household.assumptions.life_expectancy_age = 95
        ufpls = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS))
        # Once the allowance (£268,275) is used up, further tax-free relief
        # stops -- so the tax-free total across the whole projection cannot
        # exceed the allowance.
        total_tax_free = sum(y.ufpls_tax_free_taken for y in ufpls.years)
        assert total_tax_free <= UK.lump_sum_allowance + 1.0

    def test_state_pension_reduces_gross_withdrawal_needed(self):
        """No other income needs £32,336.47 gross for £30,000 net (see
        above); £11,973 of state pension already-taxable income needs only
        £21,067.76 more gross -- verified independently by bisection."""
        household = retired_household(pension=1_000_000, isa=0.0, spend=30_000)
        household.assumptions.state_pension_age = 60  # already receiving it at AS_OF
        household.assumptions.state_pension_annual = 11_973.0
        first = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS)).years[0]
        assert first.dc_withdrawn_gross == pytest.approx(21_067.76, abs=0.5)

    def test_locked_pension_yields_no_ufpls(self):
        household = retired_household(dob=date(1971, 1, 1), isa=0.0)
        projection = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                             withdrawal=SpendNominal(),
                                             pension_access=PensionAccess.UFPLS))
        assert projection.years[0].ufpls_tax_free_taken == 0.0
        assert projection.years[0].unmet_shortfall > 0  # nothing else to fund spending from
        assert projection.years[2].ufpls_tax_free_taken > 0.0

    def test_tax_efficient_order_respects_the_band_cap_under_ufpls(self):
        """The taxable *portion* of a UFPLS draw should stop at fill_to, not
        the gross amount -- a naive cap on gross would underfill the band,
        since only 75% of it counts as taxable."""
        household = retired_household(pension=1_000_000, isa=500_000, spend=60_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_access=PensionAccess.UFPLS,
                            drawdown=TaxEfficientOrder(fill_to=12_570, recycle_surplus=False))
        first = run(household, scenario).years[0]
        assert first.tax_paid == pytest.approx(0.0, abs=0.01)  # stayed within the allowance
        # Taxable portion should land at (approximately) the band ceiling.
        assert first.dc_withdrawn_gross * 0.75 == pytest.approx(12_570, abs=1.0)
        assert first.isa_withdrawn > 0  # the rest funded from the ISA


class TestPensionLumpSum:
    def test_a_one_off_lump_sum_is_split_and_invested(self):
        household = retired_household(pension=400_000, isa=0.0, spend=1_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_lump_sums=(PensionLumpSum(AS_OF, "Alex", 50_000),))
        first = run(household, scenario).years[0]
        assert first.pension_lump_sum_taken == pytest.approx(50_000)
        assert first.balances["Pension"] == pytest.approx(350_000, abs=1.0)
        # 25% tax-free (£12,500), 75% taxable (£37,500) at basic rate on top
        # of a £12,570 personal allowance and no other income: (37,500 -
        # 12,570) * 20% = £4,986.
        assert first.tax_paid == pytest.approx(4_986.0, abs=1.0)
        assert first.balances["Alex — Surplus GIA (Global Tracker)"] + first.balances.get("ISA", 0.0) > 0

    def test_only_lands_in_its_own_plan_year(self):
        household = retired_household(pension=400_000, isa=0.0, spend=1_000)
        later = date(AS_OF.year + 2, AS_OF.month, AS_OF.day)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_lump_sums=(PensionLumpSum(later, "Alex", 50_000),))
        projection = run(household, scenario)
        assert projection.years[0].pension_lump_sum_taken == 0.0
        assert projection.years[1].pension_lump_sum_taken == 0.0
        assert projection.years[2].pension_lump_sum_taken == pytest.approx(50_000)

    def test_shares_the_lifetime_allowance_with_pcls(self):
        """A partial lump sum taken before the household's own PCLS event
        should reduce how much tax-free cash PCLS can still give -- they are
        not two independent allowances."""
        household = retired_household(pension=2_000_000, isa=0.0, spend=1_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_access=PensionAccess.PCLS,
                            pension_lump_sums=(PensionLumpSum(AS_OF, "Alex", 100_000),))
        first = run(household, scenario).years[0]
        lump_tax_free = min(100_000 * 0.25, UK.lump_sum_allowance)
        remaining_pcls_headroom = UK.lump_sum_allowance - lump_tax_free
        assert first.pcls_taken == pytest.approx(remaining_pcls_headroom, abs=1.0)

    def test_capped_by_what_the_pot_actually_holds(self):
        household = retired_household(pension=30_000, isa=0.0, spend=1_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_lump_sums=(PensionLumpSum(AS_OF, "Alex", 100_000),))
        first = run(household, scenario).years[0]
        assert first.pension_lump_sum_taken == pytest.approx(30_000, abs=1.0)


class TestSpouseIsaSpillover:
    """A pound attributed to one person cannot literally land in someone
    else's ISA, but a real household achieves the same effect with an
    interspousal gift (tax-free) followed by the recipient's own
    subscription -- so once one partner's own £20,000 is full, the model
    should keep filling the other's rather than falling back to a GIA while
    real headroom sits unused a few feet away."""

    def test_pcls_spills_into_the_spouses_isa_once_the_owners_own_is_full(self):
        household = Household(
            people=[Person("Pat", date(1969, 1, 1)), Person("Robin", date(1972, 1, 1))],
            assets=[
                Asset("Pat ISA", AssetType.ISA, "Pat", 0.0, returns=FixedReal(0.0)),
                Asset("Pat Pension", AssetType.DC_PENSION, "Pat", 300_000, returns=FixedReal(0.0)),
                Asset("Robin ISA", AssetType.ISA, "Robin", 0.0, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=63, state_pension_age=99),
        )
        scenario = Scenario("s", retirement_dates={"Pat": AS_OF, "Robin": AS_OF},
                            withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS)
        plan = compile_plan(household, scenario, UK, AS_OF)
        first = project(plan, [FLAT] * plan.n_years).years[0]
        assert first.pcls_taken == pytest.approx(75_000)  # 25% of £300,000
        assert first.balances["Pat ISA"] == pytest.approx(20_000, abs=1.0)
        assert first.balances["Robin ISA"] == pytest.approx(20_000, abs=1.0)  # the spillover
        # The £35,000 left over (75,000 - 20,000 - 20,000) has nowhere further
        # to go once both allowances are full, so it lands in Pat's own GIA.
        assert first.balances["Pat — Surplus GIA (Global Tracker)"] == pytest.approx(35_000, abs=1.0)

    def test_a_spouse_with_no_isa_gets_no_spillover(self):
        """No ISA slot for the spouse means no legal destination -- the
        excess must fall to the owner's own GIA, not vanish or error."""
        household = Household(
            people=[Person("Pat", date(1969, 1, 1)), Person("Robin", date(1972, 1, 1))],
            assets=[
                Asset("Pat ISA", AssetType.ISA, "Pat", 0.0, returns=FixedReal(0.0)),
                Asset("Pat Pension", AssetType.DC_PENSION, "Pat", 300_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=63, state_pension_age=99),
        )
        scenario = Scenario("s", retirement_dates={"Pat": AS_OF, "Robin": AS_OF},
                            withdrawal=SpendNominal(), pension_access=PensionAccess.PCLS)
        plan = compile_plan(household, scenario, UK, AS_OF)
        first = project(plan, [FLAT] * plan.n_years).years[0]
        assert first.balances["Pat ISA"] == pytest.approx(20_000, abs=1.0)
        assert first.balances["Pat — Surplus GIA (Global Tracker)"] == pytest.approx(55_000, abs=1.0)


class TestTaxEfficientOrder:
    def test_it_draws_pension_before_isa(self):
        """The opposite of StandardOrder: cheap tax bands are use-it-or-lose-it."""
        household = retired_household(spend=20_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=50_270, recycle_surplus=False))
        first = run(household, scenario).years[0]
        assert first.dc_withdrawn_gross > 0
        assert first.isa_withdrawn == 0.0

    def test_standard_order_does_the_reverse(self):
        household = retired_household(spend=20_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=StandardOrder())
        first = run(household, scenario).years[0]
        assert first.isa_withdrawn > 0
        assert first.dc_withdrawn_gross == 0.0

    def test_it_stops_at_the_band_ceiling_and_uses_the_isa_beyond_it(self):
        household = retired_household(spend=60_000, isa=500_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=12_570, recycle_surplus=False))
        first = run(household, scenario).years[0]
        assert first.dc_withdrawn_gross == pytest.approx(12_570)
        assert first.tax_paid == pytest.approx(0.0)  # entirely within the allowance
        assert first.isa_withdrawn > 0

    def test_recycling_moves_surplus_into_the_isa(self):
        """Spending is small, so the band has room: money should still leave
        the pension and land in the ISA."""
        household = retired_household(spend=5_000, isa=10_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=12_570, recycle_surplus=True))
        first = run(household, scenario).years[0]
        assert first.balances["ISA"] > 10_000
        assert first.balances["Pension"] < 1_000_000

    def test_recycling_can_be_switched_off(self):
        household = retired_household(spend=5_000, isa=10_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=12_570, recycle_surplus=False))
        first = run(household, scenario).years[0]
        assert first.balances["ISA"] <= 10_000

    def test_recycling_respects_the_isa_subscription_limit(self):
        household = retired_household(spend=1_000, isa=0.0)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=200_000, isa_annual_limit=20_000))
        first = run(household, scenario).years[0]
        assert first.balances["ISA"] <= 20_000

    def test_recycling_credits_each_persons_own_isa_not_whichever_is_first(self):
        """A real, previously-dormant bug: recycled surplus used to land in
        `ctx.isa_slots[0]` regardless of whose pension it was drawn from --
        invisible for a single person, silently wrong for a couple, where it
        would have credited one partner's ISA with the other's money."""
        household = Household(
            people=[Person("Alex", date(1960, 1, 1)), Person("Sam", date(1960, 1, 1))],
            expenses=[Expense("Living", 5_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("Alex ISA", AssetType.ISA, "Alex", 0.0, returns=FixedReal(0.0)),
                Asset("Alex Pension", AssetType.DC_PENSION, "Alex", 1_000_000, returns=FixedReal(0.0)),
                Asset("Sam ISA", AssetType.ISA, "Sam", 0.0, returns=FixedReal(0.0)),
                Asset("Sam Pension", AssetType.DC_PENSION, "Sam", 1_000_000, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=63, state_pension_age=99),
        )
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF, "Sam": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=50_270, recycle_surplus=True))
        plan = compile_plan(household, scenario, UK, AS_OF)
        first = project(plan, [FLAT] * plan.n_years).years[0]
        assert first.balances["Alex ISA"] > 0
        assert first.balances["Sam ISA"] > 0

    def test_recycling_spills_into_the_spouses_isa_once_the_owners_own_is_full(self):
        """Alex alone has a pension large enough to recycle well past their
        own £20,000; Sam has no pension of their own, only an ISA. The
        excess should keep filling Sam's ISA rather than stop once Alex's
        own headroom is used, the same interspousal-gift-in-effect logic
        `_bed_and_isa`/`_invest_for_person` already apply elsewhere."""
        household = Household(
            people=[Person("Alex", date(1960, 1, 1)), Person("Sam", date(1960, 1, 1))],
            expenses=[Expense("Living", 5_000, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[
                Asset("Alex ISA", AssetType.ISA, "Alex", 0.0, returns=FixedReal(0.0)),
                Asset("Alex Pension", AssetType.DC_PENSION, "Alex", 2_000_000, returns=FixedReal(0.0)),
                Asset("Sam ISA", AssetType.ISA, "Sam", 0.0, returns=FixedReal(0.0)),
            ],
            assumptions=Assumptions(life_expectancy_age=63, state_pension_age=99),
        )
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF, "Sam": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=200_000, recycle_surplus=True))
        plan = compile_plan(household, scenario, UK, AS_OF)
        first = project(plan, [FLAT] * plan.n_years).years[0]
        assert first.balances["Alex ISA"] == pytest.approx(20_000, abs=1.0)
        assert first.balances["Sam ISA"] > 0  # the spillover -- Sam drew no pension at all

    def test_it_still_covers_spending_beyond_the_band(self):
        """A shortfall is worse than a tax bill: the band is a preference,
        not a hard limit."""
        household = retired_household(spend=80_000, isa=0.0)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            drawdown=TaxEfficientOrder(fill_to=12_570, recycle_surplus=False))
        first = run(household, scenario).years[0]
        assert first.unmet_shortfall == 0.0
        assert first.dc_withdrawn_gross > 12_570


def ctx(**overrides) -> WithdrawalContext:
    affordable = overrides.pop("affordable_up_to", float("inf"))
    defaults = dict(year_index=0, is_retired=True, dc_accessible=True,
                    nominal_discretionary=20_000.0, fixed_spend=30_000.0,
                    net_income=10_000.0, portfolio_value=1_000_000.0,
                    growth_return=0.05, oldest_age=65,
                    shortfall_for=lambda a: max(0.0, a - affordable))
    defaults.update(overrides)
    return WithdrawalContext(**defaults)


class TestPercentageRules:
    def test_percent_of_portfolio_tracks_the_portfolio(self):
        rule = PercentOfPortfolio(rate=0.04)
        rich = rule.decide(ctx(portfolio_value=2_000_000))
        poor = rule.decide(ctx(portfolio_value=400_000))
        assert rich > poor

    def test_it_is_bounded_by_floor_and_ceiling(self):
        rule = PercentOfPortfolio(rate=0.04, floor=0.5, ceiling=1.5)
        assert rule.decide(ctx(portfolio_value=50_000_000)) == pytest.approx(30_000)  # 1.5x
        assert rule.decide(ctx(portfolio_value=1.0)) == pytest.approx(10_000)         # 0.5x

    def test_it_does_nothing_before_retirement(self):
        assert PercentOfPortfolio().decide(ctx(is_retired=False)) == 20_000.0

    def test_variable_percentage_rises_with_age(self):
        rule = VariablePercentage(start_age=60, end_age=95, start_rate=0.035, end_rate=0.10)
        assert rule.rate_at(60) == pytest.approx(0.035)
        assert rule.rate_at(95) == pytest.approx(0.10)
        assert rule.rate_at(77.5) == pytest.approx(0.0675, abs=0.002)

    def test_variable_percentage_is_flat_outside_its_range(self):
        rule = VariablePercentage()
        assert rule.rate_at(40) == rule.rate_at(60)
        assert rule.rate_at(120) == rule.rate_at(95)

    def test_an_older_household_spends_more_of_the_same_portfolio(self):
        rule = VariablePercentage()
        young = rule.decide(ctx(oldest_age=62))
        old = rule.decide(ctx(oldest_age=90))
        assert old > young

    def test_percentage_rules_never_exceed_what_is_affordable(self):
        for rule in (PercentOfPortfolio(), VariablePercentage()):
            assert rule.decide(ctx(affordable_up_to=0)) <= 20_000.0
