"""
backend/dependencies.py

Reusable FastAPI dependencies for authorization and capability enforcement.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

from fastapi import Depends, HTTPException

# Import auth context from dedicated module (breaks circular import)
try:
    from backend.auth_context import require_auth_context, AuthContext, get_db
    from backend.rbac import has_effective_capability
    from backend.config import IS_DEV
except ModuleNotFoundError:
    from auth_context import require_auth_context, AuthContext, get_db
    from rbac import has_effective_capability
    from config import IS_DEV


def require_capability(capability: str) -> Callable:
    """
    FastAPI dependency factory for subscription-aware capability authorization.
    
    Enforces that the user has effective capability based on role AND subscription status.
    This is the single point of truth for capability enforcement.
    
    Capabilities are automatically derived from:
    - User role (owner/admin/member/read_only)
    - Subscription status (active/trialing = full access, past_due/canceled = free)
    - Subscription plan (free/pro/team/enterprise)
    
    The intersection of role + subscription determines effective capabilities.
    
    Usage in routes:
        @app.get("/export", dependencies=[Depends(require_capability("export:csv"))])
        def export_data(ctx: AuthContext = Depends(require_auth_context)):
            ...
    
    Args:
        capability: The capability string to check (e.g., "export:csv")
    
    Returns:
        A dependency function that enforces the capability
        
    Raises:
        HTTPException(403): If the user lacks the required capability
        HTTPException(402): If subscription is past_due (payment required)
    """
    def _check_capability(ctx: AuthContext = Depends(require_auth_context)) -> AuthContext:
        """
        Inner dependency that checks effective capability for the authenticated user.
        Capabilities are pre-computed in AuthContext from subscription + role.
        """
        # Check if user has the capability (already computed in auth_context)
        if capability not in ctx.capabilities:
            # Special handling for past_due subscriptions
            if ctx.subscription_status == "past_due":
                if IS_DEV:
                    print(f"[AUTHZ] Payment required: capability={capability}, "
                          f"role={ctx.role}, sub_status={ctx.subscription_status}")
                raise HTTPException(
                    status_code=402,  # Payment Required
                    detail="Payment required - please update your billing information"
                )
            
            # General capability denial (role or plan insufficient)
            if IS_DEV:
                print(f"[AUTHZ] Capability denied: capability={capability}, "
                      f"role={ctx.role}, sub_plan={ctx.subscription_plan}, "
                      f"effective_plan={ctx.effective_plan}")
            
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions - this feature is not available with your current access level"
            )
        
        # Log success in dev mode
        if IS_DEV:
            print(f"[AUTHZ] Capability granted: capability={capability}, "
                  f"role={ctx.role}, effective_plan={ctx.effective_plan}")
        
        return ctx
    
    return _check_capability
