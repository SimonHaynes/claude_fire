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
    IncomeAnnuity,
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
from retireplan.strategies.drawdown import DrawdownContext
from retireplan.strategies.withdrawal import WithdrawalContext
from retireplan.portfolio import Portfolio
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
    def test_matches_hand_verified_numbers_and_beats_fully_taxable_drawdown(self):
        """No other income, £30,000 net target: gross £32,336.47, of which
        £8,084.12 is tax-free -- independently verified by hand and by
        bisection against UK.income_tax() before this was wired into the
        drawdown strategies. Fully-taxable drawdown needs more gross for the
        same net, since none of it is relieved."""
        household = retired_household(pension=1_000_000, isa=0.0, spend=30_000)
        ufpls = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS)).years[0]
        assert ufpls.dc_withdrawn_gross == pytest.approx(32_336.47, abs=0.5)
        assert ufpls.ufpls_tax_free_taken == pytest.approx(8_084.12, abs=0.5)

        none = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                       withdrawal=SpendNominal())).years[0]
        assert none.dc_withdrawn_gross > ufpls.dc_withdrawn_gross

    def test_stacks_on_existing_taxable_income(self):
        """£11,973 of state pension already using up most of the personal
        allowance means only £21,067.76 more gross is needed for the same
        £30,000 net -- verified independently by bisection."""
        household = retired_household(pension=1_000_000, isa=0.0, spend=30_000)
        household.assumptions.state_pension_age = 60  # already receiving it at AS_OF
        household.assumptions.state_pension_annual = 11_973.0
        first = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS)).years[0]
        assert first.dc_withdrawn_gross == pytest.approx(21_067.76, abs=0.5)

    def test_relief_is_capped_by_the_lifetime_allowance(self):
        """The Lump Sum Allowance (£268,275) is a lifetime cap, not a
        per-withdrawal one -- drawing well past it should not generate
        unlimited tax-free cash."""
        household = retired_household(pension=3_000_000, isa=0.0, spend=200_000)
        household.assumptions.life_expectancy_age = 95
        ufpls = run(household, Scenario("s", retirement_dates={"Alex": AS_OF},
                                        withdrawal=SpendNominal(),
                                        pension_access=PensionAccess.UFPLS))
        total_tax_free = sum(y.ufpls_tax_free_taken for y in ufpls.years)
        assert total_tax_free <= UK.lump_sum_allowance + 1.0

    def test_tax_efficient_order_fills_the_band_using_taxable_not_gross(self):
        """A naive cap on gross would underfill the band, since only 75% of
        a UFPLS draw counts as taxable."""
        household = retired_household(pension=1_000_000, isa=500_000, spend=60_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_access=PensionAccess.UFPLS,
                            drawdown=TaxEfficientOrder(fill_to=12_570, recycle_surplus=False))
        first = run(household, scenario).years[0]
        assert first.tax_paid == pytest.approx(0.0, abs=0.01)  # stayed within the allowance
        assert first.dc_withdrawn_gross * 0.75 == pytest.approx(12_570, abs=1.0)
        assert first.isa_withdrawn > 0  # the rest funded from the ISA


class TestPensionLumpSum:
    def test_split_invested_and_taxed(self):
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
        assert projection.years[2].pension_lump_sum_taken == pytest.approx(50_000)

    def test_shares_the_lifetime_allowance_with_pcls(self):
        """A partial lump sum taken before the household's own PCLS event
        should reduce how much tax-free cash PCLS can still give -- they are
        not two independent allowances. Caught a real bug: PCLS used to
        greedily claim the whole allowance first if scheduled the same year."""
        household = retired_household(pension=2_000_000, isa=0.0, spend=1_000)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            pension_access=PensionAccess.PCLS,
                            pension_lump_sums=(PensionLumpSum(AS_OF, "Alex", 100_000),))
        first = run(household, scenario).years[0]
        lump_tax_free = min(100_000 * 0.25, UK.lump_sum_allowance)
        remaining_pcls_headroom = UK.lump_sum_allowance - lump_tax_free
        assert first.pcls_taken == pytest.approx(remaining_pcls_headroom, abs=1.0)


class TestIncomeAnnuity:
    def test_not_bought_unless_enabled(self):
        projection = run(retired_household(),
                         Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal()))
        assert all(y.income_annuity_premium == 0 for y in projection.years)
        assert all(y.income_annuity_income == 0 for y in projection.years)

    def test_bought_once_and_pays_a_level_income(self):
        household = retired_household(pension=400_000, isa=0.0, spend=1_000)
        annuity = IncomeAnnuity(enabled=True, fraction_of_pot=0.5, life_expectancy_years=20, loading=1.15)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
                            income_annuity=annuity)
        projection = run(household, scenario)
        first, second = projection.years[0], projection.years[1]
        expected_premium = 200_000.0
        expected_benefit = expected_premium / (20 * 1.15)
        assert first.income_annuity_premium == pytest.approx(expected_premium)
        assert first.income_annuity_income == pytest.approx(expected_benefit, rel=1e-6)
        # A one-off event: the second year draws no further premium, but the
        # income -- once secured -- keeps paying.
        assert second.income_annuity_premium == 0.0
        assert second.income_annuity_income == pytest.approx(expected_benefit, rel=1e-6)
        assert first.balances["Pension"] == pytest.approx(200_000.0, abs=1.0)

    def test_income_is_taxed_and_stops_at_death(self):
        """Folded into ordinary taxable income (unlike a care annuity's
        fees, which are paid tax-free direct to the provider), and single-life:
        it stops outright when the annuitant dies, even though the household
        -- and the plan -- continues."""
        household = Household(
            people=[Person("Alex", date(1960, 1, 1)), Person("Sam", date(1962, 1, 1))],
            expenses=[Expense("Living", 1_000.0, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
            assets=[Asset("Pension", AssetType.DC_PENSION, "Alex", 400_000.0, returns=FixedReal(0.0))],
            assumptions=Assumptions(life_expectancy_age=90, state_pension_age=99),
        )
        annuity = IncomeAnnuity(enabled=True, fraction_of_pot=1.0, life_expectancy_years=20, loading=1.0)
        scenario = Scenario("s", retirement_dates={"Alex": AS_OF, "Sam": AS_OF}, withdrawal=SpendNominal(),
                            income_annuity=annuity, death_ages={"Alex": 67})
        projection = run(household, scenario)
        assert projection.years[0].income_annuity_income == pytest.approx(20_000.0)
        assert projection.years[0].tax_paid > 0
        assert projection.years[2].income_annuity_income == 0.0
        assert projection.years[2].alive == frozenset({"Sam"})


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

    def test_a_spouse_with_no_explicit_isa_still_gets_the_spillover(self):
        """A spouse with no ISA `Asset` still gets a synthetic one (see
        `SURPLUS_ISA_NAME` in plan.py), so spillover has somewhere to land --
        only the true remainder, beyond both people's £20,000 headroom,
        falls to the owner's own GIA."""
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
        assert first.balances["Robin — Surplus ISA (Global Tracker)"] == pytest.approx(20_000, abs=1.0)
        assert first.balances["Pat — Surplus GIA (Global Tracker)"] == pytest.approx(35_000, abs=1.0)


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
        `_Accounts.bed_and_isa`/`invest_for` already apply elsewhere."""
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
                    growth_return=0.05, oldest_age=65, years_remaining=30,
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


def growing_household(pension, growth=0.04, spend=30_000.0, isa=50_000.0):
    return Household(
        people=[Person("Alex", date(1960, 1, 1))],
        expenses=[Expense("Living", spend, Frequency.YEARLY, ExpenseCategory.ESSENTIAL)],
        assets=[
            Asset("Pension", AssetType.DC_PENSION, "Alex", pension, returns=FixedReal(growth)),
            Asset("ISA", AssetType.ISA, "Alex", isa, returns=FixedReal(growth)),
        ],
        assumptions=Assumptions(life_expectancy_age=92, state_pension_age=99),
    )


def tax_free_released(household, access, **kwargs):
    projection = run(household, Scenario(
        "s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
        pension_access=access, **kwargs,
    ))
    return sum(y.pcls_taken + y.ufpls_tax_free_taken for y in projection.years)


class TestCrystallisation:
    """Only uncrystallised funds carry a further tax-free entitlement, so
    delaying crystallisation grows that entitlement whenever the pot grows."""

    def test_delay_releases_more_than_25_percent_of_todays_pot(self):
        small = growing_household(400_000.0)
        at_once = tax_free_released(small, PensionAccess.PCLS)
        phased = tax_free_released(small, PensionAccess.PHASED)
        ufpls = tax_free_released(small, PensionAccess.UFPLS)
        assert at_once == pytest.approx(400_000 * 0.25 * 1.04)   # 25% of the pot, once
        assert phased > at_once
        assert ufpls > phased
        assert ufpls > 400_000 * 0.25

    def test_delay_buys_nothing_once_the_allowance_binds(self):
        big = growing_household(2_000_000.0)
        assert tax_free_released(big, PensionAccess.PCLS) == pytest.approx(UK.lump_sum_allowance)
        assert tax_free_released(big, PensionAccess.PHASED) == pytest.approx(UK.lump_sum_allowance)

    def test_no_route_ever_exceeds_the_lump_sum_allowance(self):
        for access in PensionAccess:
            released = tax_free_released(growing_household(3_000_000.0), access)
            assert released <= UK.lump_sum_allowance + 1e-6

    def test_a_bigger_tranche_front_loads_the_tax_free_cash(self):
        household = growing_household(600_000.0)
        early = run(household, Scenario(
            "s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
            pension_access=PensionAccess.PHASED, phased_tranche=100_000.0,
        ))
        drip = run(household, Scenario(
            "s", retirement_dates={"Alex": AS_OF}, withdrawal=SpendNominal(),
            pension_access=PensionAccess.PHASED, phased_tranche=5_000.0,
        ))
        assert early.years[0].pcls_taken > drip.years[0].pcls_taken

    def test_a_dated_lump_sum_cannot_draw_on_crystallised_funds(self):
        """A 25/75 payment is a UFPLS, so funds already in drawdown are out of
        its reach — otherwise the same pound relieves twice."""
        household = growing_household(500_000.0)
        released = tax_free_released(
            household, PensionAccess.PHASED,
            pension_lump_sums=(PensionLumpSum(date(2030, 6, 1), "Alex", 200_000.0),),
        )
        assert released <= UK.lump_sum_allowance + 1e-6
        assert released <= 500_000 * 0.25 * 1.04 ** 30


class TestDryRunIsolation:
    def test_a_probe_does_not_consume_the_lump_sum_allowance(self):
        """`shortfall_for` resolves against a copied portfolio, but a strategy
        also spends allowance as it goes — and `VariablePercentage` probes
        inside a bisection loop, so a shared ledger was spent many times a year."""
        ctx = DrawdownContext(
            tax=UK, isa_slots=(), isa_slots_by_person={"a": ()},
            dc_slots_by_person={"a": (0,)}, gia_slots_by_person={"a": ()},
            cash_slot=1, ladder_slot=None, bond_slot=None,
            dc_accessible_by_person={"a": True}, is_retired=True, essential_spend=0.0,
            growth_return=0.0, bond_return=0.0, isa_headroom_used={},
            pension_access=PensionAccess.UFPLS,
            tax_free_cash_used={"a": 0.0}, crystallised={"a": 0.0},
        )
        TaxEfficientOrder().resolve(
            30_000.0, Portfolio([500_000.0, 0.0]), {"a": 0.0}, ctx.for_dry_run()
        )
        assert ctx.tax_free_cash_used["a"] == 0.0
        assert ctx.isa_headroom_used == {}
