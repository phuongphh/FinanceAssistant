"""Pydantic schemas for the wealth domain.

Schemas live next to the model files but in a separate ``schemas/``
sub-package so import boundaries stay clean: a model can import from
``schemas`` (via TYPE_CHECKING) but ``schemas`` never imports a model
(would re-introduce the SQLAlchemy → pydantic cycle the v1 codebase
suffered from).
"""
from backend.wealth.schemas.income import (
    IncomeBreakdown,
    IncomeStreamCreate,
    IncomeStreamUpdate,
)
from backend.wealth.schemas.rental import (
    OccupancyStatus,
    RentalMetadata,
    RentalYieldSummary,
)

__all__ = [
    "OccupancyStatus",
    "RentalMetadata",
    "RentalYieldSummary",
    "IncomeBreakdown",
    "IncomeStreamCreate",
    "IncomeStreamUpdate",
]
