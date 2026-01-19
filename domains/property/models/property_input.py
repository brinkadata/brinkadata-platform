from pydantic import BaseModel, Field
from typing import Optional


class PropertyInput(BaseModel):
    """
    Input data for property analysis.
    This is what the frontend sends to the backend.
    """

    # Basic identity & location
    name: str
    city: str
    state: str

    # Deal basics
    property_type: str
    purchase_price: float
    rehab_budget: float
    expected_monthly_rent: Optional[float] = None
    hold_years: float
    strategy: str

    # NEW: investor profile / persona
    investor_profile: Optional[str] = Field(
        default="balanced",
        description=(
            "Investor profile, e.g. conservative, balanced, aggressive, "
            "cashflow_first, flip_focused."
        ),
    )

    # Free-form notes
    notes: Optional[str] = None