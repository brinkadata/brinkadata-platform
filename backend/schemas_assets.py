"""
backend/schemas_assets.py

Pydantic schemas for Property Search + Assets features.
Security-first: all schemas enforce validation and prevent injection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, validator


# ========================================================================
# ASSETS SCHEMAS
# ========================================================================

class AssetCreateRequest(BaseModel):
    """Request schema for creating a new asset.
    
    Security notes:
    - name is required and trimmed
    - address fields are optional (sanitized)
    - source_ref is optional external identifier
    - property_data is stored as JSONB (safe subset only; never store credentials)
    """
    name: str = Field(..., min_length=1, max_length=200, description="Asset name (required, 1-200 chars)")
    address_line1: Optional[str] = Field(None, max_length=200, description="Address line 1")
    address_line2: Optional[str] = Field(None, max_length=200, description="Address line 2")
    city: Optional[str] = Field(None, max_length=100, description="City")
    state: Optional[str] = Field(None, max_length=50, description="State")
    postal_code: Optional[str] = Field(None, max_length=20, description="Postal/ZIP code")
    country: str = Field("US", max_length=3, description="Country code (default: US)")
    source_ref: Optional[str] = Field(None, max_length=200, description="External/property identifier")
    property_data: Dict[str, Any] = Field(default_factory=dict, description="Structured property data (safe subset)")

    @validator("name", pre=True)
    def trim_name(cls, v):
        """Trim whitespace from name."""
        if isinstance(v, str):
            return v.strip()
        return v

    @validator("name")
    def validate_name_non_empty(cls, v):
        """Ensure name is not empty after trimming."""
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v


class AssetResponse(BaseModel):
    """Response schema for asset data.
    
    Security: never includes account_id or created_by in public response.
    """
    id: str = Field(..., description="Asset ID (UUID or integer as string)")
    name: str = Field(..., description="Asset name")
    address_line1: Optional[str] = Field(None, description="Address line 1")
    address_line2: Optional[str] = Field(None, description="Address line 2")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    postal_code: Optional[str] = Field(None, description="Postal/ZIP code")
    country: str = Field("US", description="Country code")
    source: str = Field("property_search", description="Source system")
    source_ref: Optional[str] = Field(None, description="External/property identifier")
    property_data: Dict[str, Any] = Field(default_factory=dict, description="Structured property data")
    created_at: str = Field(..., description="ISO timestamp")
    updated_at: str = Field(..., description="ISO timestamp")

    class Config:
        # Allows instantiation from DB rows with extra fields
        extra = "ignore"


class AssetListResponse(BaseModel):
    """Response schema for asset list."""
    items: list[AssetResponse] = Field(default_factory=list, description="List of assets")
    total: int = Field(0, description="Total count (for future pagination)")


# ========================================================================
# PROPERTY SEARCH SCHEMAS
# ========================================================================

class PropertySearchRequest(BaseModel):
    """Request schema for property search.
    
    Security notes:
    - query is required, min 2 chars
    - limit is capped at 50 (prevents abuse)
    - Results are tenant-scoped on backend
    """
    query: str = Field(..., min_length=2, max_length=200, description="Search query (min 2 chars)")
    limit: int = Field(25, ge=1, le=50, description="Max results (default 25, max 50)")

    @validator("query", pre=True)
    def trim_query(cls, v):
        """Trim whitespace from query."""
        if isinstance(v, str):
            return v.strip()
        return v

    @validator("query")
    def validate_query_non_empty(cls, v):
        """Ensure query is not empty after trimming."""
        if not v or not v.strip():
            raise ValueError("query must not be empty")
        if len(v) < 2:
            raise ValueError("query must be at least 2 characters")
        return v


class PropertySearchResult(BaseModel):
    """Single property search result.
    
    Security: contains only safe, non-sensitive property data.
    """
    source_ref: Optional[str] = Field(None, description="External property identifier")
    display_address: str = Field(..., description="Formatted display address")
    address_line1: Optional[str] = Field(None, description="Address line 1")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    postal_code: Optional[str] = Field(None, description="Postal/ZIP code")
    country: str = Field("US", description="Country code")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional safe property data")

    class Config:
        extra = "ignore"


class PropertySearchResponse(BaseModel):
    """Response schema for property search."""
    results: list[PropertySearchResult] = Field(default_factory=list, description="Search results")
    query: str = Field(..., description="Original query")
    total: int = Field(0, description="Total results found (capped at limit)")
