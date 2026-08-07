"""The balance ledger.

Balances live in a flat list indexed by slot rather than a dict keyed by name.
Withdrawal strategies routinely need to ask "what if we spent this much?" and
then throw the answer away, so copying the ledger happens thousands of times
per simulation; a list copy is several times cheaper than a dict copy, and the
slot layout is fixed once in `compile_plan`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Portfolio:
    balances: list[float]
    cost_basis: list[float] | None = None
    """Cost basis per slot, tracked only for GIA-type slots (CGT needs it;
    nothing else does). `None` defaults to a basis equal to each slot's
    opening balance -- no embedded unrealised gain assumed at the start of
    the plan, since a client cannot usually state one precisely. Every
    non-GIA slot's basis is simply never read."""

    def __post_init__(self) -> None:
        if self.cost_basis is None:
            self.cost_basis = self.balances[:]

    def copy(self) -> "Portfolio":
        assert self.cost_basis is not None
        return Portfolio(self.balances[:], self.cost_basis[:])

    @property
    def total(self) -> float:
        return sum(self.balances)

    def sum_of(self, slots: tuple[int, ...]) -> float:
        return sum(self.balances[s] for s in slots)

    def draw_pro_rata(self, slots: tuple[int, ...], amount: float) -> float:
        """Take `amount` spread across `slots` in proportion to their balances.

        Returns what was actually taken, which is less than `amount` when the
        slots run dry. Cost basis is drawn down proportionally alongside the
        balance, so a slot sold from repeatedly keeps a consistent basis
        fraction without this method needing to know which slots are GIAs.
        """
        available = self.sum_of(slots)
        if available <= 0 or amount <= 0:
            return 0.0
        assert self.cost_basis is not None
        taken = min(amount, available)
        for slot in slots:
            share = self.balances[slot] / available
            slot_taken = taken * share
            basis_fraction = (
                self.cost_basis[slot] / self.balances[slot] if self.balances[slot] > 0 else 0.0
            )
            self.balances[slot] = max(0.0, self.balances[slot] - slot_taken)
            self.cost_basis[slot] = max(0.0, self.cost_basis[slot] - slot_taken * basis_fraction)
        return taken

    def basis_fraction_of(self, slots: tuple[int, ...]) -> float:
        """The fraction of `slots`' combined value that is cost basis (the
        rest is unrealised gain). 1.0 (no gain) for an empty or zero-value
        selection, so a GIA slot with nothing in it never looks like it has
        a taxable gain to realise."""
        assert self.cost_basis is not None
        value = self.sum_of(slots)
        if value <= 0:
            return 1.0
        basis = sum(self.cost_basis[s] for s in slots)
        return max(0.0, min(1.0, basis / value))
