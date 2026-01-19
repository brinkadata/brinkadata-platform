"""
backend/authz.py

Phase 3: RBAC + Entitlements (Backend-Enforced Authorization)

Single source of truth for role-based access control and plan-based entitlements.
All authorization checks must go through this module.

Role Hierarchy: owner > admin > member > read_only
Plan Hierarchy: free < pro < team < enterprise
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Set
from fastapi import HTTPException


# ============================================================================
# Capability-Based Authorization
# ============================================================================

class Capability(str, Enum):
    """Available capabilities in the Brinkadata platform."""
    
    # Project capabilities
    PROJECT_CREATE = "project:create"
    PROJECT_VIEW = "project:view"
    
    # Asset capabilities
    ASSET_MANAGE = "asset:manage"
    ASSET_VIEW = "asset:view"
    
    # Search capabilities
    SEARCH_BASIC = "search:basic"
    SEARCH_ADVANCED = "search:advanced"
    
    # Analysis capabilities
    ANALYSIS_SINGLE_PROPERTY = "analysis:single_property"
    ANALYSIS_PORTFOLIO = "analysis:portfolio"
    
    # Export capabilities
    EXPORT_CSV = "export:csv"


# Plan to capabilities mapping
PLAN_CAPABILITIES: Dict[str, Set[str]] = {
    "free": {
        Capability.PROJECT_VIEW,
        Capability.ASSET_VIEW,
        Capability.SEARCH_BASIC,
        Capability.ANALYSIS_SINGLE_PROPERTY,
    },
    "pro": {
        Capability.PROJECT_CREATE,
        Capability.PROJECT_VIEW,
        Capability.ASSET_MANAGE,
        Capability.ASSET_VIEW,
        Capability.SEARCH_BASIC,
        Capability.SEARCH_ADVANCED,
        Capability.ANALYSIS_SINGLE_PROPERTY,
        Capability.ANALYSIS_PORTFOLIO,
        Capability.EXPORT_CSV,
    },
    "team": {
        # Same as pro for now
        Capability.PROJECT_CREATE,
        Capability.PROJECT_VIEW,
        Capability.ASSET_MANAGE,
        Capability.ASSET_VIEW,
        Capability.SEARCH_BASIC,
        Capability.SEARCH_ADVANCED,
        Capability.ANALYSIS_SINGLE_PROPERTY,
        Capability.ANALYSIS_PORTFOLIO,
        Capability.EXPORT_CSV,
    },
    "enterprise": {
        # Same as pro for now (placeholder)
        Capability.PROJECT_CREATE,
        Capability.PROJECT_VIEW,
        Capability.ASSET_MANAGE,
        Capability.ASSET_VIEW,
        Capability.SEARCH_BASIC,
        Capability.SEARCH_ADVANCED,
        Capability.ANALYSIS_SINGLE_PROPERTY,
        Capability.ANALYSIS_PORTFOLIO,
        Capability.EXPORT_CSV,
    },
}


def has_capability(account_plan: str, capability: str) -> bool:
    """
    Check if an account plan has a specific capability.
    
    Pure Python logic - no FastAPI imports, no database access.
    Safe for future Stripe integration.
    
    Args:
        account_plan: The plan tier (e.g., "free", "pro", "team", "enterprise")
        capability: The capability to check (e.g., "project:create")
    
    Returns:
        True if the plan has the capability, False otherwise.
        Returns False for unknown plans.
    """
    # Normalize plan name to lowercase
    plan = account_plan.lower() if account_plan else ""
    
    # Get capabilities for this plan
    plan_caps = PLAN_CAPABILITIES.get(plan, set())
    
    # Check if capability exists in plan's capability set
    return capability in plan_caps


# ============================================================================
# Role Hierarchy
# ============================================================================

ROLE_HIERARCHY = {
    "owner": 4,
    "admin": 3,
    "member": 2,
    "read_only": 1,
}


def role_at_least(user_role: str, required_role: str) -> bool:
    """
    Check if user_role meets the required role level.
    
    Role hierarchy: owner > admin > member > read_only
    
    Args:
        user_role: User's actual role
        required_role: Minimum required role
        
    Returns:
        True if user_role >= required_role in hierarchy
        
    Example:
        role_at_least("admin", "member") -> True
        role_at_least("member", "admin") -> False
    """
    user_level = ROLE_HIERARCHY.get(user_role.lower(), 0)
    required_level = ROLE_HIERARCHY.get(required_role.lower(), 0)
    return user_level >= required_level


# ============================================================================
# Plan Hierarchy
# ============================================================================

PLAN_HIERARCHY = {
    "free": 1,
    "pro": 2,
    "team": 3,
    "enterprise": 4,
}


def plan_at_least(account_plan: str, required_plan: str) -> bool:
    """
    Check if account_plan meets the required plan level.
    
    Plan hierarchy: free < pro < team < enterprise
    
    Args:
        account_plan: Account's actual plan
        required_plan: Minimum required plan
        
    Returns:
        True if account_plan >= required_plan in hierarchy
        
    Example:
        plan_at_least("pro", "free") -> True
        plan_at_least("free", "pro") -> False
    """
    account_level = PLAN_HIERARCHY.get(account_plan.lower(), 0)
    required_level = PLAN_HIERARCHY.get(required_plan.lower(), 0)
    return account_level >= required_level


# ============================================================================
# Plan Limits Configuration
# ============================================================================

PLAN_LIMITS = {
    "free": {
        "max_saved_deals": 25,
        "max_scenarios": 3,
        "can_export_csv": False,
        "can_use_irr_npv": False,
        "can_use_api": False,
    },
    "pro": {
        "max_saved_deals": 250,
        "max_scenarios": 25,
        "can_export_csv": True,
        "can_use_irr_npv": True,
        "can_use_api": False,
    },
    "team": {
        "max_saved_deals": 1000,
        "max_scenarios": 100,
        "can_export_csv": True,
        "can_use_irr_npv": True,
        "can_use_api": True,
    },
    "enterprise": {
        "max_saved_deals": 10000,
        "max_scenarios": 500,
        "can_export_csv": True,
        "can_use_irr_npv": True,
        "can_use_api": True,
    },
}


def get_plan_limits(plan: str) -> Dict[str, Any]:
    """
    Get limits and features for a plan.
    
    Args:
        plan: Plan name (free/pro/team/enterprise)
        
    Returns:
        Dictionary of limits and feature flags
    """
    return PLAN_LIMITS.get(plan.lower(), PLAN_LIMITS["free"])


def get_plan_limit(plan: str, limit_name: str) -> int:
    """
    Get a specific limit value for a plan.
    
    Args:
        plan: Plan name
        limit_name: Name of the limit (e.g., "max_saved_deals")
        
    Returns:
        Limit value (defaults to free plan if unknown)
    """
    limits = get_plan_limits(plan)
    return limits.get(limit_name, 0)


def check_plan_feature(plan: str, feature_name: str) -> bool:
    """
    Check if a plan includes a specific feature.
    
    Args:
        plan: Plan name
        feature_name: Feature flag name (e.g., "can_use_irr_npv")
        
    Returns:
        True if feature is enabled for the plan
    """
    limits = get_plan_limits(plan)
    return limits.get(feature_name, False)


# ============================================================================
# Main Enforcement Function
# ============================================================================

def require_entitlement(
    user: Optional[Dict[str, Any]],
    account: Optional[Dict[str, Any]],
    *,
    min_role: str = "member",
    min_plan: str = "free"
) -> None:
    """
    Enforce role and plan entitlements.
    
    This is the main authorization gate. Use this on all protected endpoints.
    
    Args:
        user: User dict with keys: id, role, is_active (optional), email
        account: Account dict with keys: id, plan
        min_role: Minimum required role (owner/admin/member/read_only)
        min_plan: Minimum required plan (free/pro/team/enterprise)
        
    Raises:
        HTTPException(401): If user is missing
        HTTPException(403): If user is inactive or insufficient role
        HTTPException(402): If insufficient plan (payment required)
        HTTPException(500): If account is missing (should not happen)
    """
    # Validate user exists
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    
    # Validate account exists
    if not account:
        print(f"[AUTHZ] ERROR: Missing account for user {user.get('id', 'unknown')}")
        raise HTTPException(
            status_code=500,
            detail="Account context missing - this is a server error"
        )
    
    # Check if user is active
    if "is_active" in user and not user["is_active"]:
        print(f"[AUTHZ] Inactive user attempted access: user_id={user.get('id')}")
        raise HTTPException(
            status_code=403,
            detail="Account inactive - please contact support"
        )
    
    # Check role requirement
    user_role = user.get("role", "read_only")
    if not role_at_least(user_role, min_role):
        print(f"[AUTHZ] Insufficient role: user={user.get('id')}, role={user_role}, required={min_role}")
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions - {min_role} role required"
        )
    
    # Check plan requirement
    account_plan = account.get("plan", "free")
    if not plan_at_least(account_plan, min_plan):
        print(f"[AUTHZ] Insufficient plan: account={account.get('id')}, plan={account_plan}, required={min_plan}")
        raise HTTPException(
            status_code=402,
            detail=f"Plan upgrade required - {min_plan} plan or higher needed for this feature"
        )
    
    # All checks passed
    print(f"[AUTHZ] Access granted: user_id={user.get('id')}, role={user_role}, account_plan={account_plan}")


# ============================================================================
# Convenience Wrappers
# ============================================================================

def require_write_access(user: Optional[Dict[str, Any]], account: Optional[Dict[str, Any]]) -> None:
    """
    Require write access (member role or higher).
    
    Use this for any endpoint that mutates tenant data.
    """
    require_entitlement(user, account, min_role="member", min_plan="free")


def require_admin(user: Optional[Dict[str, Any]], account: Optional[Dict[str, Any]]) -> None:
    """
    Require admin role or higher.
    
    Use this for account management operations.
    """
    require_entitlement(user, account, min_role="admin", min_plan="free")


def require_owner(user: Optional[Dict[str, Any]], account: Optional[Dict[str, Any]]) -> None:
    """
    Require owner role.
    
    Use this for critical account operations (plan changes, billing, etc.).
    """
    require_entitlement(user, account, min_role="owner", min_plan="free")


def require_pro_plan(user: Optional[Dict[str, Any]], account: Optional[Dict[str, Any]]) -> None:
    """
    Require pro plan or higher.
    
    Use this for premium features (IRR/NPV, exports, etc.).
    """
    require_entitlement(user, account, min_role="member", min_plan="pro")


def require_team_plan(user: Optional[Dict[str, Any]], account: Optional[Dict[str, Any]]) -> None:
    """
    Require team plan or higher.
    
    Use this for team features (API access, advanced analytics, etc.).
    """
    require_entitlement(user, account, min_role="member", min_plan="team")


# ============================================================================
# Usage Limit Helpers
# ============================================================================

def check_usage_against_limit(
    current_usage: int,
    plan: str,
    limit_name: str
) -> None:
    """
    Check if current usage is within plan limits.
    
    Args:
        current_usage: Current count (e.g., saved deals)
        plan: Account plan
        limit_name: Limit key (e.g., "max_saved_deals")
        
    Raises:
        HTTPException(402): If over limit
    """
    limit = get_plan_limit(plan, limit_name)
    
    if current_usage >= limit:
        print(f"[AUTHZ] Usage limit exceeded: plan={plan}, limit={limit_name}, current={current_usage}, max={limit}")
        raise HTTPException(
            status_code=402,
            detail=f"Plan limit reached: {current_usage}/{limit} {limit_name.replace('max_', '')}. Upgrade to continue."
        )
    
    print(f"[AUTHZ] Usage within limits: plan={plan}, limit={limit_name}, current={current_usage}/{limit}")


def require_feature_access(plan: str, feature_name: str) -> None:
    """
    Require a specific feature to be enabled on the plan.
    
    Args:
        plan: Account plan
        feature_name: Feature flag (e.g., "can_use_irr_npv")
        
    Raises:
        HTTPException(402): If feature not enabled
    """
    if not check_plan_feature(plan, feature_name):
        print(f"[AUTHZ] Feature not available: plan={plan}, feature={feature_name}")
        raise HTTPException(
            status_code=402,
            detail=f"Feature not available on {plan} plan. Upgrade to access this feature."
        )
    
    print(f"[AUTHZ] Feature access granted: plan={plan}, feature={feature_name}")
