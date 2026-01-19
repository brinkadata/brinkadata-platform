"""
backend/routes_property_search.py

Property Search endpoints with tenant-safe queries and RBAC enforcement.

Security guarantees:
- All endpoints require authentication (require_auth_context)
- All endpoints require capability "property_search:read"
- All queries filtered by account_id from auth context
- No client-provided account_id accepted
- Input validation via Pydantic schemas
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

# Import auth and capability dependencies
try:
    from backend.auth_context import AuthContext, require_auth_context, get_db
    from backend.dependencies import require_capability
    from backend.schemas_assets import PropertySearchRequest, PropertySearchResponse, PropertySearchResult
    from backend.config import IS_DEV
except ModuleNotFoundError:
    from auth_context import AuthContext, require_auth_context, get_db
    from dependencies import require_capability
    from schemas_assets import PropertySearchRequest, PropertySearchResponse, PropertySearchResult
    from config import IS_DEV


router = APIRouter(
    prefix="/api/property-search",
    tags=["property_search"],
    dependencies=[Depends(require_capability("property_search:read"))],
)


@router.post("", response_model=PropertySearchResponse)
def search_properties(
    request: PropertySearchRequest,
    ctx: AuthContext = Depends(require_auth_context),
) -> PropertySearchResponse:
    """
    Search property index for addresses matching query.
    
    Security:
    - Requires capability "property_search:read"
    - Results scoped to ctx.account_id (tenant isolation)
    - Query parameterized (SQL injection safe)
    - Limit enforced (max 50)
    
    Args:
        request: PropertySearchRequest with query and limit
        ctx: Authenticated context with account_id
    
    Returns:
        PropertySearchResponse with matching properties
    
    Raises:
        HTTPException(400): Invalid query (too short, etc.)
        HTTPException(403): Missing capability (handled by dependency)
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Security: account_id from auth context ONLY (never from client)
    account_id = ctx.account_id
    
    # Parameterized query (SQL injection safe)
    # Use LIKE with wildcards for case-insensitive partial match
    query_pattern = f"%{request.query}%"
    
    try:
        # Query property_index table
        # Security: WHERE account_id = ? ensures tenant isolation
        cur.execute(
            """
            SELECT 
                id,
                display_address,
                address_line1,
                city,
                state,
                postal_code,
                country,
                data
            FROM property_index
            WHERE account_id = ?
              AND (
                  display_address LIKE ? COLLATE NOCASE
                  OR city LIKE ? COLLATE NOCASE
                  OR postal_code LIKE ? COLLATE NOCASE
              )
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account_id, query_pattern, query_pattern, query_pattern, request.limit)
        )
        
        rows = cur.fetchall()
        
        # Build results
        results = []
        for row in rows:
            # Parse data JSON (default to empty dict if invalid)
            import json
            try:
                data = json.loads(row["data"]) if row.get("data") else {}
            except (json.JSONDecodeError, TypeError):
                data = {}
            
            result = PropertySearchResult(
                source_ref=str(row["id"]),  # Use property_index ID as source_ref
                display_address=row["display_address"] or "",
                address_line1=row.get("address_line1"),
                city=row.get("city"),
                state=row.get("state"),
                postal_code=row.get("postal_code"),
                country=row.get("country", "US"),
                data=data,
            )
            results.append(result)
        
        if IS_DEV:
            print(f"[PROPERTY_SEARCH] account_id={account_id}, query={request.query!r}, results={len(results)}")
        
        return PropertySearchResponse(
            results=results,
            query=request.query,
            total=len(results),
        )
    
    except sqlite3.Error as e:
        # Log error but don't expose internal details
        if IS_DEV:
            print(f"[PROPERTY_SEARCH] DB error: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    finally:
        conn.close()
