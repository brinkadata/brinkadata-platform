"""
backend/auth_context.py

Shared authentication context primitives for FastAPI dependency injection.
This module breaks the circular import between main.py and dependencies.py.

Contains:
- AuthContext: Immutable tenant boundary context with subscription state
- require_auth_context: FastAPI dependency for auth enforcement
- get_db: Database connection helper
- verify_token: JWT token verification

This module MUST NOT import backend.main to avoid circular dependencies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path as FsPath
from typing import Optional, Set

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Import configuration (safe - no circular dependency)
try:
    from backend.config import (
        SECRET_KEY,
        ALGORITHM,
        DATABASE_PATH,
        IS_DEV,
    )
    from backend.entitlements import get_subscription, get_entitlements, Subscription
except ModuleNotFoundError:
    from config import (
        SECRET_KEY,
        ALGORITHM,
        DATABASE_PATH,
        IS_DEV,
    )
    from entitlements import get_subscription, get_entitlements, Subscription

# Security scheme for HTTPBearer
security = HTTPBearer()

# Database path
DB_PATH = str(FsPath(__file__).resolve().parent / DATABASE_PATH)


# ---------------------------------------------------------
# Row Conversion Helper
# ---------------------------------------------------------
def row_to_dict(row) -> dict:
    """
    Safely convert a sqlite3.Row to dict.
    
    This is the single boundary for converting DB rows to dicts.
    Use this whenever you need .get() behavior on a row.
    
    Args:
        row: sqlite3.Row object or None
        
    Returns:
        dict representation of the row, or {} if None
    """
    if row is None:
        return {}
    return dict(row)


# ---------------------------------------------------------
# DB Helper
# ---------------------------------------------------------
def get_db() -> sqlite3.Connection:
    """
    Create and return a SQLite connection with Row factory.
    Used by auth dependencies and endpoints.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------
# JWT Token Verification
# ---------------------------------------------------------
def verify_token(token: str) -> dict:
    """
    Verify JWT access token and return decoded payload.
    
    Raises:
        HTTPException(401): If token is expired or invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------
# AuthContext - Production-grade tenant boundary with subscription state
# ---------------------------------------------------------
class AuthContext(BaseModel):
    """
    Immutable tenant boundary context derived from JWT token with subscription state.
    This is the ONLY source of truth for account_id, user_id, and entitlements in protected endpoints.
    Never trust account_id/user_id from request bodies or query params.
    
    Fields:
        user_id: User ID from JWT token
        account_id: Account ID from user record
        role: User role (owner/admin/member/read_only)
        email: User email
        subscription_status: Subscription status (active/trialing/past_due/canceled)
        subscription_plan: Plan from subscription (free/pro/team/enterprise)
        effective_plan: Effective plan after status check (may downgrade to free)
        capabilities: Set of effective capabilities (role + subscription intersection)
        cancel_at_period_end: Whether subscription is set to cancel
        current_period_end: When current subscription period ends (ISO timestamp)
    """
    user_id: int
    account_id: int
    role: str
    email: str
    subscription_status: str
    subscription_plan: str
    effective_plan: str
    capabilities: Set[str]
    cancel_at_period_end: bool = False
    current_period_end: Optional[str] = None
    
    class Config:
        # Allow sets in pydantic model
        arbitrary_types_allowed = True


def require_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthContext:
    """
    Production-grade auth context dependency for FastAPI routes.
    
    Returns immutable AuthContext derived from server-side JWT verification with subscription state.
    Use this for all protected endpoints requiring authentication + tenant isolation.
    
    Process:
    1. Verify JWT token signature and expiration
    2. Extract user_id from token payload
    3. Fetch user record from database (source of truth)
    4. Validate user is active and has account_id
    5. Fetch subscription state for account
    6. Compute effective plan and capabilities (role + subscription)
    7. Return AuthContext with full entitlement context
    
    Usage:
        @app.get("/protected")
        def protected_route(ctx: AuthContext = Depends(require_auth_context)):
            # Use ctx.account_id for tenant scoping
            # Use ctx.capabilities to check permissions
            # Use ctx.subscription_status to show billing UI
            ...
    
    Raises:
        HTTPException(401): If token is invalid, expired, or user not found
        HTTPException(403): If user is inactive or has no account
    """
    # Verify JWT token and extract payload
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    
    if not user_id:
        print("[AUTH] Missing user_id in token payload")
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    # Get user and account info from database (backend is source of truth)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email, role, account_id, is_active FROM users WHERE id = ?",
        (user_id,)
    )
    user_row = cur.fetchone()
    
    if not user_row:
        conn.close()
        print(f"[AUTH] User not found: user_id={user_id}")
        raise HTTPException(status_code=401, detail="User not found")
    
    if not user_row["is_active"]:
        conn.close()
        print(f"[AUTH] Inactive user attempted access: user_id={user_id}")
        raise HTTPException(status_code=403, detail="Account inactive")
    
    if not user_row["account_id"]:
        conn.close()
        print(f"[AUTH] User has no account_id: user_id={user_id}")
        raise HTTPException(status_code=403, detail="No account associated")
    
    # Backward compatibility: default role to "member" if missing or null
    user_role = user_row["role"] if user_row["role"] else "member"
    account_id = user_row["account_id"]
    
    # Fetch subscription state (source of truth for entitlements)
    subscription = get_subscription(conn, account_id)
    conn.close()
    
    # Import here to avoid circular dependency
    try:
        from backend.entitlements import get_effective_plan, get_entitlements
    except ModuleNotFoundError:
        from entitlements import get_effective_plan, get_entitlements
    
    # Compute effective plan and capabilities
    effective_plan = get_effective_plan(subscription)
    capabilities = get_entitlements(user_role, subscription)
    
    # Create immutable auth context with subscription state
    ctx = AuthContext(
        user_id=user_row["id"],
        account_id=account_id,
        role=user_role,
        email=user_row["email"],
        subscription_status=subscription.status,
        subscription_plan=subscription.plan_name,
        effective_plan=effective_plan,
        capabilities=capabilities,
        cancel_at_period_end=subscription.cancel_at_period_end,
        current_period_end=subscription.current_period_end,
    )
    
    # Dev-only enhanced logging with subscription information
    if IS_DEV:
        print(f"[AUTH] Authenticated: user_id={ctx.user_id}, account_id={ctx.account_id}, "
              f"role={ctx.role}, sub_status={ctx.subscription_status}, "
              f"sub_plan={ctx.subscription_plan}, effective_plan={ctx.effective_plan}, "
              f"capabilities={len(ctx.capabilities)}")
    
    return ctx
