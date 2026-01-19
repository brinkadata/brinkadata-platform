"""
backend/rbac.py

Role-Based Access Control (RBAC) overlay for capability-based authorization.

This module adds role-based restrictions on top of plan-based capabilities.
Effective capabilities = intersection of plan capabilities AND role capabilities.

Key principle: A role can NEVER grant more than the plan allows (SaaS security).

Pure Python logic - no FastAPI imports, no database access.
"""

from typing import Set

# Import capabilities and plan mapping from authz
try:
    from backend.authz import Capability, PLAN_CAPABILITIES
except ModuleNotFoundError:
    from authz import Capability, PLAN_CAPABILITIES


# ============================================================================
# Role Definitions
# ============================================================================

class Role:
    """Role constants for RBAC."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    READ_ONLY = "read_only"


# ============================================================================
# Role to Capabilities Mapping
# ============================================================================

ROLE_CAPABILITIES: dict[str, Set[str]] = {
    "owner": {
        # Owner has access to ALL capabilities (subject to plan limits)
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
    "admin": {
        # Admin has most capabilities except billing/ownership-level operations
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
    "member": {
        # Member can perform normal operations (create, analyze, manage portfolio)
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
    "read_only": {
        # Read-only can only view, no create/update/delete operations
        Capability.PROJECT_VIEW,
        Capability.ASSET_VIEW,
        Capability.SEARCH_BASIC,
        Capability.ANALYSIS_SINGLE_PROPERTY,
    },
}


# ============================================================================
# Effective Capability Calculation
# ============================================================================

def effective_capabilities(plan: str, role: str) -> Set[str]:
    """
    Calculate effective capabilities by intersecting plan and role capabilities.
    
    This ensures a role can NEVER exceed what the plan allows.
    Example: A member on a free plan gets only the capabilities that BOTH
    the free plan AND the member role allow.
    
    Args:
        plan: Account plan (e.g., "free", "pro", "team", "enterprise")
        role: User role (e.g., "owner", "admin", "member", "read_only")
    
    Returns:
        Set of capability strings that are allowed by BOTH plan AND role.
        Returns empty set if plan or role is unknown.
    """
    # Normalize to lowercase
    plan_lower = plan.lower() if plan else ""
    role_lower = role.lower() if role else ""
    
    # Get capabilities from plan and role
    plan_caps = PLAN_CAPABILITIES.get(plan_lower, set())
    role_caps = ROLE_CAPABILITIES.get(role_lower, set())
    
    # Return intersection: only capabilities allowed by BOTH plan AND role
    return plan_caps & role_caps


def has_effective_capability(plan: str, role: str, capability: str) -> bool:
    """
    Check if a user has effective capability based on their plan and role.
    
    Args:
        plan: Account plan
        role: User role
        capability: Capability to check (e.g., "asset:manage")
    
    Returns:
        True if the capability is allowed by BOTH the plan AND the role.
        Returns False for unknown plans, roles, or capabilities.
    """
    effective_caps = effective_capabilities(plan, role)
    return capability in effective_caps


# ============================================================================
# Role Hierarchy Helpers
# ============================================================================

ROLE_HIERARCHY = {
    "owner": 4,
    "admin": 3,
    "member": 2,
    "read_only": 1,
}


def role_level(role: str) -> int:
    """
    Get numeric level for a role.
    
    Args:
        role: Role name
    
    Returns:
        Numeric level (higher = more privileged), 0 if unknown
    """
    return ROLE_HIERARCHY.get(role.lower() if role else "", 0)


def role_at_least(user_role: str, required_role: str) -> bool:
    """
    Check if user_role meets or exceeds required_role in hierarchy.
    
    Args:
        user_role: User's actual role
        required_role: Minimum required role
    
    Returns:
        True if user_role >= required_role in hierarchy
    """
    return role_level(user_role) >= role_level(required_role)
