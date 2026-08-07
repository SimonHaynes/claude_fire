"""Date arithmetic helpers — `add_years`, `add_months`, `months_remaining`."""
from __future__ import annotations

from datetime import date

from retireplan.timeline import add_months, add_years, months_remaining


class TestAddYears:
    def test_adds_whole_years(self):
        assert add_years(date(2026, 8, 6), 8) == date(2034, 8, 6)

    def test_clamps_29_february_in_a_non_leap_target_year(self):
        assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)


class TestAddMonths:
    def test_adds_within_the_same_year(self):
        assert add_months(date(2026, 8, 6), 3) == date(2026, 11, 6)

    def test_rolls_over_a_year_boundary(self):
        # The notice-period floor this household's stretch scenario uses.
        assert add_months(date(2026, 8, 6), 8) == date(2027, 4, 6)

    def test_rolls_over_several_year_boundaries(self):
        assert add_months(date(2026, 8, 6), 30) == date(2029, 2, 6)

    def test_clamps_to_the_target_months_last_day(self):
        # 31 January + 1 month lands on 28 (or 29) February, not March.
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap year

    def test_zero_months_is_a_no_op(self):
        assert add_months(date(2026, 8, 6), 0) == date(2026, 8, 6)


class TestMonthsRemaining:
    def test_is_the_inverse_of_add_months_offset_by_one(self):
        """If N payments remain, the last one is N-1 months from now (1
        remaining means it's due this month, at `add_months(as_of, 0)`)."""
        as_of = date(2026, 8, 6)
        for n in (1, 8, 21, 37):
            assert months_remaining(as_of, add_months(as_of, n - 1)) == n

    def test_a_payment_due_earlier_in_the_month_than_as_of_does_not_count(self):
        # Last payment on the 1st; today is the 6th of the same month -- that
        # payment has already happened, so nothing is left this month.
        assert months_remaining(date(2026, 8, 6), date(2026, 8, 1)) == 0
        # Last payment on the 6th or later in that month still counts.
        assert months_remaining(date(2026, 8, 6), date(2026, 8, 6)) == 1
        assert months_remaining(date(2026, 8, 6), date(2026, 8, 10)) == 1

    def test_a_last_payment_already_in_the_past_is_zero_not_negative(self):
        assert months_remaining(date(2026, 8, 6), date(2025, 1, 1)) == 0

    def test_matches_the_household_debt_examples(self):
        """The exact case this was built for: a client re-stated three loans
        by end date instead of a countdown, months later than the original
        countdown was true for -- this must recompute cleanly from `as_of`
        rather than needing the household file edited by hand every time."""
        as_of = date(2026, 8, 6)
        assert months_remaining(as_of, date(2028, 5, 1)) == 21
        assert months_remaining(as_of, date(2030, 2, 1)) == 42
        assert months_remaining(as_of, date(2029, 9, 1)) == 37
