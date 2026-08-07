"""Late-life care: who needs it, for how long, and who pays.

Care is the largest single spending risk a retired household faces, and it is
the one where "how much does it cost" is the wrong first question. What
actually determines the effect on an estate is the **means test**, which is
assessed on each person individually, and which disregards the family home for
as long as a spouse still lives in it. Two households with identical wealth can
see wildly different outcomes depending on how that wealth is held and who
enters care first.

## What is modelled

  * **Whether care is needed at all**, sampled per person per trial rather
    than assumed. Roughly a quarter of people aged 65 will spend time in
    residential care; assuming everybody does overstates the risk, and
    assuming nobody does is what this engine used to do.
  * **How long it lasts**, drawn from a skewed distribution. The mean stay is
    around two and a half years, but the median is shorter and the tail is
    long — a small number of very long stays drive most of the cost, which is
    exactly why an average is a poor planning number.
  * **The means test, per person** (England). Above the upper capital limit
    you pay in full. Below it the local authority contributes, and below the
    lower limit it funds the care while the resident contributes most of
    their income. **The home is disregarded entirely while a spouse, partner
    or dependent relative still lives there.**
  * **The state as a floor.** Nobody in England is left without essential
    care because they ran out of money. Once assessable capital falls to the
    limit, the local authority pays. Care therefore stops draining an estate
    at that point rather than driving it negative, and a household that
    exhausts its capital on care has not "failed" in the sense this engine
    uses the word — it has fallen back on the state, which is a real and
    materially different outcome, and is reported as its own figure.

## What is deliberately not modelled

NHS Continuing Healthcare (free care for a primarily health-driven need, but
hard to qualify for and impossible to predict), Attendance Allowance, the
deferred payment agreement, top-up fees from third parties, and any regional
variation — these figures are England-only. Care in Scotland, Wales and
Northern Ireland works differently.

**Deprivation of assets is not modelled and cannot be.** A local authority may
disregard a gift made to avoid care fees, with no time limit, and treat the
giver as still holding the money. That is a judgement about intention, not
arithmetic. It is the single most important reason that care-driven estate
planning belongs with a solicitor rather than with this model — see the
`legal-and-trust-structuring` skill.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# --- England, 2025/26. VERIFY BEFORE USE: these move most years. -----------

UPPER_CAPITAL_LIMIT = 23_250.0
"""Above this, a resident pays the full cost of their care."""

LOWER_CAPITAL_LIMIT = 14_250.0
"""Below this, capital is ignored entirely and only income is assessed."""

TARIFF_INCOME_STEP = 250.0
"""Between the limits, £1/week of assumed income per £250 of capital."""

PERSONAL_EXPENSES_ALLOWANCE_WEEKLY = 30.15
"""What a local-authority-funded resident keeps from their own income."""

#: Roughly a quarter of people aged 65 will spend time in residential care,
#: with women materially more likely than men -- they live longer, and are
#: more likely to outlive the partner who would otherwise care for them at
#: home. Widely cited planning figures; treat as an order of magnitude, not a
#: precision estimate, and see the class docstring on why the *length* matters
#: more than the incidence.
LIFETIME_CARE_PROBABILITY = {"male": 0.20, "female": 0.30, None: 0.25}

MEAN_STAY_YEARS = 2.5
"""Mean length of a residential stay. The median is nearer eighteen months --
the mean is dragged up by a long tail of multi-year stays, which is why this
is modelled as a distribution rather than as an average."""


@dataclass(frozen=True)
class CareNeed:
    """One person's sampled care episode."""

    person: str
    start_age: int
    years: float

    def active_at(self, age: int) -> bool:
        return self.start_age <= age < self.start_age + self.years


@dataclass(frozen=True)
class CareModel:
    """How likely care is, when it starts, and how long it lasts.

    Sampled per person per trial. `probability=0.0` disables it, which is the
    default everywhere -- care stays a question you ask deliberately.
    """

    annual_cost: float = 60_000.0
    """Residential care in England runs roughly £50,000-£70,000 a year, higher
    with nursing. This is the self-funded rate; a local authority pays less
    for the same bed, which is a real inequity and not modelled here."""

    probability: dict[str, float] | None = None
    """Chance of ever needing residential care, by sex. Defaults to the
    published figures above."""

    mean_stay_years: float = MEAN_STAY_YEARS
    onset_age: int = 85
    """Mean age at entry. Sampled around this, not fixed at it."""

    onset_spread_years: float = 5.0
    max_stay_years: float = 12.0
    """A cap, so a heavy-tailed draw cannot produce an implausible stay."""

    offsets_household_essential: float = 0.35
    """Ordinary essential spending that stops for a person in care -- their
    food, heating and share of running a home. Charging the full care cost on
    top of undiminished household spending overstates the hit by about a
    third, a larger error than the choice between £50,000 and £70,000."""

    def sample(self, person: str, sex: str | None, rng: random.Random) -> CareNeed | None:
        """Whether `person` needs care, and if so when and for how long."""
        table = self.probability if self.probability is not None else LIFETIME_CARE_PROBABILITY
        chance = table.get(sex, table.get(None, 0.25))
        if rng.random() >= chance:
            return None
        # Exponential: memoryless, heavily right-skewed, and a reasonable fit
        # to published length-of-stay data, where most stays are short and a
        # few are very long. The cap keeps the tail plausible.
        years = min(rng.expovariate(1.0 / self.mean_stay_years), self.max_stay_years)
        start = int(round(rng.gauss(self.onset_age, self.onset_spread_years)))
        return CareNeed(person=person, start_age=max(65, start), years=years)

    def spec(self) -> dict:
        """Cache identity."""
        return {
            "annual_cost": self.annual_cost,
            "probability": dict(sorted(
                (str(k), v) for k, v in
                (self.probability or LIFETIME_CARE_PROBABILITY).items()
            )),
            "mean_stay_years": self.mean_stay_years,
            "onset_age": self.onset_age,
            "onset_spread_years": self.onset_spread_years,
            "max_stay_years": self.max_stay_years,
            "offsets_household_essential": self.offsets_household_essential,
        }


@dataclass(frozen=True)
class MeansTest:
    """England's care means test, assessed on one person at a time.

    Per person is not a simplification -- it is how the rule actually works,
    and it is why who enters care first can matter more to an estate than how
    much the household has.
    """

    upper_limit: float = UPPER_CAPITAL_LIMIT
    lower_limit: float = LOWER_CAPITAL_LIMIT
    tariff_step: float = TARIFF_INCOME_STEP

    def self_funded_share(self, assessable_capital: float) -> float:
        """Fraction of the care bill this person must meet from their own funds.

        Between the limits the taper is expressed through tariff income rather
        than a fraction, so this returns 1.0 above the upper limit and 0.0 at
        or below it; `contribution` handles the band between.
        """
        return 1.0 if assessable_capital > self.upper_limit else 0.0

    def tariff_income(self, assessable_capital: float) -> float:
        """Assumed annual income from capital between the two limits."""
        if assessable_capital <= self.lower_limit:
            return 0.0
        banded = min(assessable_capital, self.upper_limit) - self.lower_limit
        return (banded / self.tariff_step) * 52.0

    def contribution(
        self, annual_cost: float, assessable_capital: float, assessable_income: float
    ) -> tuple[float, float]:
        """Split a year's care bill into (household pays, state pays).

        Above the upper limit the resident pays everything. Below it the local
        authority meets the balance, while the resident contributes their
        income and any tariff income, keeping only the personal expenses
        allowance. The state's share is what makes running out of money a
        fallback rather than a catastrophe.
        """
        if assessable_capital > self.upper_limit:
            return annual_cost, 0.0
        keep = PERSONAL_EXPENSES_ALLOWANCE_WEEKLY * 52.0
        payable = max(0.0, assessable_income - keep) + self.tariff_income(assessable_capital)
        household = min(annual_cost, payable)
        return household, annual_cost - household


@dataclass(frozen=True)
class ImmediateNeedsAnnuity:
    """A care fee payment plan, bought at the point of entering care.

    A single premium buys a guaranteed income for life, paid **direct to the
    care provider**, which is what makes it tax-free. It converts an
    open-ended, unknowable liability into a known one-off cost, which is
    precisely the thing that makes an estate plannable: whatever is left after
    the premium is safe from the care bill however long the stay lasts.

    The trade is stark and worth stating to a client plainly. Die soon after
    buying one and the family has lost most of the premium. Live a long time
    in care and it can be worth many times what it cost. It is insurance
    against longevity in care, not an investment, and it should be compared on
    what it protects rather than on its expected return.

    Pricing here is a **planning approximation**, not a quote: a real premium
    is medically underwritten and depends on the individual's health at the
    point of purchase, which is exactly what this model cannot know. A quote
    from an FCA-regulated specialist is the only real number.
    """

    enabled: bool = False
    life_expectancy_years: float = 3.0
    """Underwriters price these on an impaired life. Someone entering
    residential care has a materially shorter expectation than the population
    at that age -- around three years is a common planning figure."""

    loading: float = 1.25
    """Insurer margin and expenses on top of the expected payout. Real
    loadings vary; this is deliberately not generous."""

    escalation: float = 0.0
    """Annual increase in the benefit. Zero buys a level benefit, which is
    cheaper but erodes in real terms exactly when care costs are rising."""

    def premium(self, annual_benefit: float) -> float:
        """Single premium to secure `annual_benefit` of care fees for life."""
        years = self.life_expectancy_years
        if self.escalation:
            # Growing annuity, discounted only by mortality: real returns on
            # the insurer's book are not modelled, which is conservative for
            # the buyer since it makes the premium look higher.
            factor = sum((1 + self.escalation) ** t for t in range(int(years) + 1))
        else:
            factor = years
        return annual_benefit * factor * self.loading

    def spec(self) -> dict:
        return {
            "enabled": self.enabled,
            "life_expectancy_years": self.life_expectancy_years,
            "loading": self.loading,
            "escalation": self.escalation,
        }


@dataclass(frozen=True)
class CarePlan:
    """Everything about care for one scenario: the risk, the rules, the hedge.

    Bundled rather than three separate scenario fields because they are only
    meaningful together -- a means test with no care model tests nothing, and
    an annuity is priced against a care cost.
    """

    model: CareModel = None  # type: ignore[assignment]
    means_test: MeansTest = None  # type: ignore[assignment]
    annuity: ImmediateNeedsAnnuity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model", self.model or CareModel())
        object.__setattr__(self, "means_test", self.means_test or MeansTest())

    def sample_needs(self, people, rng: random.Random) -> list[CareNeed]:
        """Which of `people` need care in this trial, and for how long."""
        needs = []
        for person in people:
            need = self.model.sample(person.name, person.sex, rng)
            if need is not None:
                needs.append(need)
        return needs

    def spec(self) -> dict:
        return {
            "model": self.model.spec(),
            "means_test": {
                "upper": self.means_test.upper_limit,
                "lower": self.means_test.lower_limit,
            },
            "annuity": self.annuity.spec() if self.annuity else None,
        }
