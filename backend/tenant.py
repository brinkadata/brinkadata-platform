"""
backend/tenant.py

Phase 2: Tenant Guardrails (Defense in Depth)

All tenant-owned queries must go through these guard helpers.
This module provides centralized tenant scoping to prevent accidental data leakage.

- In DEV: emit warnings for unsafe access
- In STAGING/PROD: fail fast with HTTP 500/403
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException


# Environment detection (import from config if available, otherwise derive)
try:
    from backend.config import IS_DEV, IS_STAGING, IS_PROD
except ImportError:
    ENV = os.environ.get("ENV", "dev")
    IS_DEV = (ENV == "dev")
    IS_STAGING = (ENV == "staging")
    IS_PROD = (ENV == "prod")


@dataclass
class TenantContext:
    """
    Immutable tenant context for request scoping.
    Used to ensure all tenant-owned queries include account_id.
    """
    account_id: int
    user_id: Optional[int] = None
    
    def __post_init__(self):
        """Validate context on creation."""
        if not self.account_id or self.account_id < 1:
            raise ValueError(f"Invalid account_id: {self.account_id}")


def require_account_id(account_id: Optional[int]) -> int:
    """
    Guardrail: Require account_id to be present for tenant-scoped operations.
    
    - In DEV: warns if missing but allows (for backwards compatibility during migration)
    - In STAGING/PROD: fails fast with HTTP 500
    
    Args:
        account_id: The account ID to validate
        
    Returns:
        The validated account_id
        
    Raises:
        HTTPException: If account_id is missing in non-dev environments
    """
    if not account_id or account_id < 1:
        error_msg = f"[TENANT] Missing or invalid account_id: {account_id}"
        
        if IS_DEV:
            print(f"{error_msg} (DEV warning - continuing)")
            # In dev, return a sentinel value that will likely cause visible errors
            # but won't crash the server
            return account_id or 0
        else:
            print(f"{error_msg} (PRODUCTION - failing fast)")
            raise HTTPException(
                status_code=500,
                detail="Tenant scope missing - this is a server error"
            )
    
    return account_id


def assert_rows_scoped(
    rows: Union[List[sqlite3.Row], List[Dict[str, Any]]],
    account_id: int,
    label: str = ""
) -> None:
    """
    Guardrail: Assert that all returned rows belong to the specified account.
    
    This prevents accidental data leakage when queries are missing account_id filters.
    
    - In DEV: warns about mismatched account_ids
    - In STAGING/PROD: fails fast with HTTP 500
    
    Args:
        rows: List of database rows (Row objects or dicts)
        account_id: Expected account_id for all rows
        label: Identifier for logging (e.g., endpoint name)
        
    Raises:
        HTTPException: If any row has mismatched account_id in non-dev environments
    """
    if not rows:
        return  # Empty result set is fine
    
    mismatches = []
    
    for i, row in enumerate(rows):
        # Extract account_id from row (handle both sqlite3.Row and dict)
        if isinstance(row, dict):
            row_account_id = row.get("account_id")
        else:
            try:
                row_account_id = row["account_id"]
            except (KeyError, TypeError, IndexError) as e:
                # account_id column missing from SELECT - this is a bug
                error_msg = f"[TENANT] Query missing account_id in SELECT for {label or 'unknown endpoint'}"
                detail_msg = f"Row at index {i} does not have account_id column. Error: {type(e).__name__}: {e}"
                print(f"ERROR: {error_msg} - {detail_msg}")
                raise RuntimeError(f"{error_msg}. {detail_msg}")
        
        # Check for mismatch
        if row_account_id is not None and row_account_id != account_id:
            mismatches.append({
                "index": i,
                "expected": account_id,
                "found": row_account_id
            })
    
    if mismatches:
        error_msg = f"[TENANT] Tenant isolation violation{f' in {label}' if label else ''}"
        detail_msg = f"Found {len(mismatches)} row(s) with mismatched account_id"
        
        if IS_DEV:
            print(f"{error_msg}: {detail_msg}")
            print(f"[TENANT][DEV] Expected account_id={account_id}, found mismatches: {mismatches[:3]}")  # Show first 3
        else:
            print(f"{error_msg}: {detail_msg} (PRODUCTION - failing fast)")
            raise HTTPException(
                status_code=500,
                detail="Tenant isolation violation detected - this is a server error"
            )


def assert_row_scoped(
    row: Union[sqlite3.Row, Dict[str, Any], None],
    account_id: int,
    label: str = ""
) -> None:
    """
    Guardrail: Assert that a single returned row belongs to the specified account.
    
    Similar to assert_rows_scoped but for single-row results.
    
    Args:
        row: Database row (Row object or dict) or None
        account_id: Expected account_id
        label: Identifier for logging
        
    Raises:
        HTTPException: If row has mismatched account_id in non-dev environments
    """
    if row is None:
        return  # No row is fine (e.g., 404 case)
    
    # Extract account_id from row
    if isinstance(row, dict):
        row_account_id = row.get("account_id")
    else:
        try:
            row_account_id = row["account_id"]
        except (KeyError, TypeError):
            row_account_id = None
    
    # Check for mismatch
    if row_account_id is not None and row_account_id != account_id:
        error_msg = f"[TENANT] Tenant isolation violation{f' in {label}' if label else ''}"
        detail_msg = f"Expected account_id={account_id}, found={row_account_id}"
        
        if IS_DEV:
            print(f"{error_msg}: {detail_msg} (DEV warning)")
        else:
            print(f"{error_msg}: {detail_msg} (PRODUCTION - failing fast)")
            raise HTTPException(
                status_code=500,
                detail="Tenant isolation violation detected - this is a server error"
            )


def execute_scoped(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple,
    account_id: int,
    label: str = ""
) -> sqlite3.Cursor:
    """
    Guardrail: Execute a SQL query with tenant context validation.
    
    Ensures account_id is present and optionally checks if the SQL includes account_id filter.
    
    Args:
        conn: Database connection
        sql: SQL query string
        params: Query parameters
        account_id: Required account_id for tenant scoping
        label: Identifier for logging (e.g., endpoint name)
        
    Returns:
        Cursor with query results
        
    Raises:
        HTTPException: If account_id is missing or query appears unsafe
    """
    # Validate account_id is present
    require_account_id(account_id)
    
    # TASK D: DEV-only check for account_id in SQL
    # (Best-effort detection - simple substring check)
    sql_lower = sql.lower()
    is_select = "select" in sql_lower
    is_update = "update" in sql_lower
    is_delete = "delete" in sql_lower
    
    # Check if this is a query on a tenant-owned table
    tenant_tables = ["saved_properties", "trashed_properties", "scenarios", "account_memberships"]
    is_tenant_query = any(table in sql_lower for table in tenant_tables)
    
    if is_tenant_query and (is_select or is_update or is_delete):
        # Check if account_id appears in the SQL
        if "account_id" not in sql_lower:
            warning_msg = f"[TENANT][DEV] Query missing 'account_id' filter{f' in {label}' if label else ''}"
            
            if IS_DEV:
                print(warning_msg)
                print(f"[TENANT][DEV] SQL: {sql[:100]}...")  # Show first 100 chars
            else:
                print(f"{warning_msg} (PRODUCTION - failing fast)")
                raise HTTPException(
                    status_code=500,
                    detail="Unsafe tenant query detected - missing account_id filter"
                )
    
    # Execute the query
    cur = conn.cursor()
    cur.execute(sql, params)
    
    return cur


def get_tenant_context(account_id: int, user_id: Optional[int] = None) -> TenantContext:
    """
    Create a validated TenantContext.
    
    Args:
        account_id: Account ID for tenant scoping
        user_id: Optional user ID
        
    Returns:
        Validated TenantContext instance
    """
    return TenantContext(account_id=account_id, user_id=user_id)
