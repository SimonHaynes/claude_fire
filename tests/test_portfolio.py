"""The balance ledger's cost-basis tracking, used only by GIA/CGT logic."""
from __future__ import annotations

import pytest

from retireplan.portfolio import Portfolio


class TestCostBasis:
    def test_defaults_to_the_opening_balance(self):
        """No embedded gain assumed at the start of the plan."""
        portfolio = Portfolio([100.0, 200.0])
        assert portfolio.cost_basis == [100.0, 200.0]

    def test_copy_carries_its_own_cost_basis(self):
        portfolio = Portfolio([100.0], [40.0])
        clone = portfolio.copy()
        clone.balances[0] = 999.0
        clone.cost_basis[0] = 999.0
        assert portfolio.balances[0] == 100.0
        assert portfolio.cost_basis[0] == 40.0

    def test_draw_pro_rata_reduces_basis_proportionally(self):
        """A slot worth 100 with a basis of 40 (60 unrealised gain): selling
        half should take half the basis too, keeping the basis fraction the
        gain came from the same before and after."""
        portfolio = Portfolio([100.0], [40.0])
        taken = portfolio.draw_pro_rata((0,), 50.0)
        assert taken == pytest.approx(50.0)
        assert portfolio.balances[0] == pytest.approx(50.0)
        assert portfolio.cost_basis[0] == pytest.approx(20.0)

    def test_basis_fraction_of_an_empty_slot_is_one(self):
        """No value, no gain to realise -- never divide by zero into a
        phantom taxable gain."""
        portfolio = Portfolio([0.0], [0.0])
        assert portfolio.basis_fraction_of((0,)) == 1.0

    def test_basis_fraction_across_multiple_slots(self):
        portfolio = Portfolio([100.0, 300.0], [100.0, 150.0])
        # combined value 400, combined basis 250 -> 62.5% basis
        assert portfolio.basis_fraction_of((0, 1)) == pytest.approx(0.625)

    def test_growth_alone_does_not_touch_basis(self):
        """Cost basis only moves on contribution or disposal -- market growth
        (applied elsewhere, to `balances` only) should never call anything
        here, so this just documents the invariant `draw_pro_rata` relies on."""
        portfolio = Portfolio([100.0], [100.0])
        portfolio.balances[0] = 150.0  # simulates a year of growth
        assert portfolio.cost_basis[0] == 100.0
        assert portfolio.basis_fraction_of((0,)) == pytest.approx(100.0 / 150.0)
