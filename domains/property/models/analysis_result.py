from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AnalysisResult(BaseModel):
    """
    Result of a property analysis.
    This is what the backend returns to the frontend.
    """

    # Basic identity
    property_name: str
    summary: str

    # Core investment metrics
    estimated_roi: float = Field(
        ..., description="Estimated overall ROI as a decimal (e.g., 0.12 for 12%)"
    )
    cashflow_per_month: Optional[float] = Field(
        None, description="Estimated monthly cashflow in dollars (if rental)"
    )
    risk_level: str = Field(
        "unknown", description="High-level risk label (e.g., low/medium/high)"
    )

    # NEW: Deal grade (A–F) at a glance
    deal_grade: Optional[str] = Field(
        None,
        description="Overall deal grade from A (excellent) to F (poor).",
    )

    # Advanced metrics (we'll fill these with AI later)
    market_pulse_score: Optional[float] = Field(
        None, description="0–100 score for overall market conditions"
    )
    emotional_roi_score: Optional[float] = Field(
        None, description="0–100 score based on sentiment / emotional factors"
    )
    persona_fit_score: Optional[float] = Field(
        None, description="0–100 score: how well this fits the investor's profile"
    )

    # Metadata
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this analysis was generated (UTC).",
    )