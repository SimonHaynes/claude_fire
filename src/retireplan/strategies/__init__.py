"""Pluggable strategies, on three independent axes.

    withdrawal  — how much to spend when the plan is under pressure
    drawdown    — which pots to sell, and how any reserve is maintained
    allocation  — what each asset actually earns

They are separate because they answer separate questions and compose freely:
any withdrawal rule works with any drawdown order and any allocation. Testing
one at a time is how you find out which of them is doing the work — and, just
as often, which one is doing nothing.
"""
from .allocation import AllocationStrategy, BondTent, ByAssetTypeMix, GlidePath, StaticMix
from .drawdown import (
    CashBondLadder,
    DrawdownContext,
    DrawdownStrategy,
    DrawResult,
    StandardOrder,
    TaxEfficientOrder,
    ThreeBucketStrategy,
    credit_isa,
    isa_recipients,
)
from .withdrawal import (
        PercentOfPortfolio,
    GuytonKlinger,
    PostAccessStepUp,
    SpendNominal,
    VariablePercentage,
    WithdrawalContext,
    WithdrawalStrategy,
)

__all__ = [
    "AllocationStrategy",
    "BondTent",
    "ByAssetTypeMix",
    "CashBondLadder",
    "DrawResult",
    "DrawdownContext",
    "DrawdownStrategy",
    "GlidePath",
    "GuytonKlinger",
    "PercentOfPortfolio",
    "PostAccessStepUp",
    "SpendNominal",
    "StandardOrder",
    "StaticMix",
    "TaxEfficientOrder",
    "ThreeBucketStrategy",
    "VariablePercentage",
    "credit_isa",
    "isa_recipients",
    "WithdrawalContext",
    "WithdrawalStrategy",
]
