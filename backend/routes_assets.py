"""
backend/routes_assets.py

Assets CRUD endpoints with tenant-safe queries and RBAC enforcement.

Security guarantees:
- All endpoints require authentication (require_auth_context)
- Read operations require capability "assets:read"
- Write operations require capability "assets:manage"
- All queries filtered by account_id from auth context
- No client-provided account_id accepted
- Input validation via Pydantic schemas
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path

# Import auth and capability dependencies
try:
    from backend.auth_context import AuthContext, require_auth_context, get_db
    from backend.dependencies import require_capability
    from backend.schemas_assets import AssetCreateRequest, AssetResponse, AssetListResponse
    from backend.config import IS_DEV
except ModuleNotFoundError:
    from auth_context import AuthContext, require_auth_context, get_db
    from dependencies import require_capability
    from schemas_assets import AssetCreateRequest, AssetResponse, AssetListResponse
    from config import IS_DEV


router = APIRouter(
    prefix="/api/assets",
    tags=["assets"],
)


@router.post("", response_model=AssetResponse, dependencies=[Depends(require_capability("assets:manage"))])
def create_asset(
    request: AssetCreateRequest,
    ctx: AuthContext = Depends(require_auth_context),
) -> AssetResponse:
    """
    Create a new asset.
    
    Security:
    - Requires capability "assets:manage"
    - account_id from auth context ONLY (never from client)
    - created_by = ctx.user_id
    - Input validated via Pydantic schema
    
    Args:
        request: AssetCreateRequest with name, address, etc.
        ctx: Authenticated context with account_id and user_id
    
    Returns:
        AssetResponse with created asset data
    
    Raises:
        HTTPException(400): Invalid input (name empty, etc.)
        HTTPException(403): Missing capability (handled by dependency)
        HTTPException(500): Database error
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Security: account_id and user_id from auth context ONLY
    account_id = ctx.account_id
    user_id = ctx.user_id
    
    # Timestamps
    now = datetime.utcnow().isoformat() + "Z"
    
    # Serialize property_data to JSON
    property_data_json = json.dumps(request.property_data)
    
    try:
        # Insert asset
        # Security: account_id and created_by from auth context
        cur.execute(
            """
            INSERT INTO assets (
                account_id,
                created_by,
                name,
                address_line1,
                address_line2,
                city,
                state,
                postal_code,
                country,
                source,
                source_ref,
                property_data,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                user_id,
                request.name,
                request.address_line1,
                request.address_line2,
                request.city,
                request.state,
                request.postal_code,
                request.country,
                "property_search",  # Default source
                request.source_ref,
                property_data_json,
                now,
                now,
            )
        )
        
        asset_id = cur.lastrowid
        conn.commit()
        
        if IS_DEV:
            print(f"[ASSETS] Created asset_id={asset_id}, account_id={account_id}, user_id={user_id}")
        
        # Return created asset
        return AssetResponse(
            id=str(asset_id),
            name=request.name,
            address_line1=request.address_line1,
            address_line2=request.address_line2,
            city=request.city,
            state=request.state,
            postal_code=request.postal_code,
            country=request.country,
            source="property_search",
            source_ref=request.source_ref,
            property_data=request.property_data,
            created_at=now,
            updated_at=now,
        )
    
    except sqlite3.Error as e:
        # Log error but don't expose internal details
        if IS_DEV:
            print(f"[ASSETS] DB error on create: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    finally:
        conn.close()


@router.get("", response_model=AssetListResponse, dependencies=[Depends(require_capability("assets:read"))])
def list_assets(
    q: Optional[str] = Query(None, min_length=1, max_length=200, description="Search query (name/address)"),
    limit: int = Query(50, ge=1, le=200, description="Max results (default 50, max 200)"),
    offset: int = Query(0, ge=0, le=5000, description="Offset for pagination (default 0, max 5000)"),
    ctx: AuthContext = Depends(require_auth_context),
) -> AssetListResponse:
    """
    List assets for the authenticated account.
    
    Security:
    - Requires capability "assets:read"
    - Results filtered by ctx.account_id (tenant isolation)
    - Query parameterized (SQL injection safe)
    
    Args:
        q: Optional search query (name/address)
        limit: Max results (default 50, max 200)
        offset: Pagination offset (default 0, max 5000)
        ctx: Authenticated context with account_id
    
    Returns:
        AssetListResponse with list of assets
    
    Raises:
        HTTPException(403): Missing capability (handled by dependency)
        HTTPException(500): Database error
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Security: account_id from auth context ONLY
    account_id = ctx.account_id
    
    try:
        # Build query with optional search filter
        if q:
            query_pattern = f"%{q}%"
            cur.execute(
                """
                SELECT 
                    id,
                    name,
                    address_line1,
                    address_line2,
                    city,
                    state,
                    postal_code,
                    country,
                    source,
                    source_ref,
                    property_data,
                    created_at,
                    updated_at
                FROM assets
                WHERE account_id = ?
                  AND (
                      name LIKE ? COLLATE NOCASE
                      OR address_line1 LIKE ? COLLATE NOCASE
                      OR city LIKE ? COLLATE NOCASE
                  )
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (account_id, query_pattern, query_pattern, query_pattern, limit, offset)
            )
        else:
            cur.execute(
                """
                SELECT 
                    id,
                    name,
                    address_line1,
                    address_line2,
                    city,
                    state,
                    postal_code,
                    country,
                    source,
                    source_ref,
                    property_data,
                    created_at,
                    updated_at
                FROM assets
                WHERE account_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (account_id, limit, offset)
            )
        
        rows = cur.fetchall()
        
        # Build asset list
        items = []
        for row in rows:
            # Parse property_data JSON
            try:
                property_data = json.loads(row["property_data"]) if row.get("property_data") else {}
            except (json.JSONDecodeError, TypeError):
                property_data = {}
            
            asset = AssetResponse(
                id=str(row["id"]),
                name=row["name"] or "",
                address_line1=row.get("address_line1"),
                address_line2=row.get("address_line2"),
                city=row.get("city"),
                state=row.get("state"),
                postal_code=row.get("postal_code"),
                country=row.get("country", "US"),
                source=row.get("source", "property_search"),
                source_ref=row.get("source_ref"),
                property_data=property_data,
                created_at=row["created_at"] or "",
                updated_at=row["updated_at"] or "",
            )
            items.append(asset)
        
        if IS_DEV:
            print(f"[ASSETS] List: account_id={account_id}, q={q!r}, results={len(items)}")
        
        return AssetListResponse(items=items, total=len(items))
    
    except sqlite3.Error as e:
        if IS_DEV:
            print(f"[ASSETS] DB error on list: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    finally:
        conn.close()


@router.get("/{asset_id}", response_model=AssetResponse, dependencies=[Depends(require_capability("assets:read"))])
def get_asset(
    asset_id: int = Path(..., description="Asset ID"),
    ctx: AuthContext = Depends(require_auth_context),
) -> AssetResponse:
    """
    Get a single asset by ID.
    
    Security:
    - Requires capability "assets:read"
    - Asset must belong to ctx.account_id (tenant isolation)
    - Returns 404 if not found or belongs to different account
    
    Args:
        asset_id: Asset ID to retrieve
        ctx: Authenticated context with account_id
    
    Returns:
        AssetResponse with asset data
    
    Raises:
        HTTPException(403): Missing capability (handled by dependency)
        HTTPException(404): Asset not found or access denied
        HTTPException(500): Database error
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Security: account_id from auth context ONLY
    account_id = ctx.account_id
    
    try:
        # Query with account_id filter (tenant isolation)
        cur.execute(
            """
            SELECT 
                id,
                name,
                address_line1,
                address_line2,
                city,
                state,
                postal_code,
                country,
                source,
                source_ref,
                property_data,
                created_at,
                updated_at
            FROM assets
            WHERE id = ? AND account_id = ?
            """,
            (asset_id, account_id)
        )
        
        row = cur.fetchone()
        
        if not row:
            # 404 whether asset doesn't exist or belongs to different account (no info leak)
            raise HTTPException(status_code=404, detail="Asset not found")
        
        # Parse property_data JSON
        try:
            property_data = json.loads(row["property_data"]) if row.get("property_data") else {}
        except (json.JSONDecodeError, TypeError):
            property_data = {}
        
        if IS_DEV:
            print(f"[ASSETS] Get: asset_id={asset_id}, account_id={account_id}")
        
        return AssetResponse(
            id=str(row["id"]),
            name=row["name"] or "",
            address_line1=row.get("address_line1"),
            address_line2=row.get("address_line2"),
            city=row.get("city"),
            state=row.get("state"),
            postal_code=row.get("postal_code"),
            country=row.get("country", "US"),
            source=row.get("source", "property_search"),
            source_ref=row.get("source_ref"),
            property_data=property_data,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )
    
    except HTTPException:
        raise
    except sqlite3.Error as e:
        if IS_DEV:
            print(f"[ASSETS] DB error on get: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    finally:
        conn.close()


@router.delete("/{asset_id}", status_code=204, dependencies=[Depends(require_capability("assets:manage"))])
def delete_asset(
    asset_id: int = Path(..., description="Asset ID to delete"),
    ctx: AuthContext = Depends(require_auth_context),
) -> None:
    """
    Delete an asset.
    
    Security:
    - Requires capability "assets:manage"
    - Asset must belong to ctx.account_id (tenant isolation)
    - Returns 404 if not found or belongs to different account (no info leak)
    
    Args:
        asset_id: Asset ID to delete
        ctx: Authenticated context with account_id
    
    Returns:
        204 No Content on success
    
    Raises:
        HTTPException(403): Missing capability (handled by dependency)
        HTTPException(404): Asset not found or access denied
        HTTPException(500): Database error
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Security: account_id from auth context ONLY
    account_id = ctx.account_id
    
    try:
        # Delete with account_id filter (tenant isolation)
        cur.execute(
            """
            DELETE FROM assets
            WHERE id = ? AND account_id = ?
            """,
            (asset_id, account_id)
        )
        
        if cur.rowcount == 0:
            # 404 whether asset doesn't exist or belongs to different account (no info leak)
            raise HTTPException(status_code=404, detail="Asset not found")
        
        conn.commit()
        
        if IS_DEV:
            print(f"[ASSETS] Deleted: asset_id={asset_id}, account_id={account_id}")
        
        # Return 204 No Content (no response body)
        return None
    
    except HTTPException:
        raise
    except sqlite3.Error as e:
        if IS_DEV:
            print(f"[ASSETS] DB error on delete: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    finally:
        conn.close()
