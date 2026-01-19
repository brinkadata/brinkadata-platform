"""
backend/entitlements.py

Subscription-aware entitlements engine for Brinkadata SaaS.

This module centralizes the logic for:
- Fetching subscription state from database
- Computing effective plan based on subscription status
- Deriving capabilities from (role + subscription + plan)

Key principles:
- Subscription status gates paid features (past_due/canceled = downgrade to free)
- Role restrictions still apply (read_only blocks writes even on pro plan)
- Owner/admin/member rules unchanged from RBAC
- No Stripe SDK yet - data model only

Source of truth: subscriptions table in SQLite
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Set

# Import existing RBAC and authz
try:
    from backend.rbac import effective_capabilities as rbac_effective_capabilities
    from backend.authz import Capability
    from backend.models import PlanName
except ModuleNotFoundError:
    from rbac import effective_capabilities as rbac_effective_capabilities
    from authz import Capability
    from models import PlanName


# ============================================================================
# Subscription Data Model
# ============================================================================

@dataclass
class Subscription:
    """
    Subscription state from database.
    
    This is the source of truth for billing and entitlements.
    """
    id: int
    account_id: int
    status: str  # "trialing", "active", "past_due", "canceled"
    plan_name: str  # "free", "pro", "team", "enterprise"
    provider: str  # "stripe", "manual"
    provider_customer_id: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @property
    def is_active(self) -> bool:
        """Check if subscription grants paid features."""
        return self.status in ("active", "trialing")
    
    @property
    def is_past_due(self) -> bool:
        """Check if subscription is past due (payment required)."""
        return self.status == "past_due"
    
    @property
    def is_canceled(self) -> bool:
        """Check if subscription is canceled."""
        return self.status == "canceled"


# ============================================================================
# Subscription Queries
# ============================================================================

def get_subscription(conn: sqlite3.Connection, account_id: int) -> Subscription:
    """
    Fetch subscription for an account.
    
    If no subscription exists, returns a default free subscription.
    This ensures every account always has a subscription state.
    
    Args:
        conn: SQLite connection with row_factory set
        account_id: Account ID to query
    
    Returns:
        Subscription object (never None)
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            id, account_id, status, plan_name, provider,
            provider_customer_id, provider_subscription_id,
            current_period_end, cancel_at_period_end,
            created_at, updated_at
        FROM subscriptions
        WHERE account_id = ?
        LIMIT 1
        """,
        (account_id,)
    )
    row = cur.fetchone()
    
    if row:
        return Subscription(
            id=row["id"],
            account_id=row["account_id"],
            status=row["status"] or "active",
            plan_name=row["plan_name"] or "free",
            provider=row["provider"] or "manual",
            provider_customer_id=row["provider_customer_id"],
            provider_subscription_id=row["provider_subscription_id"],
            current_period_end=row["current_period_end"],
            cancel_at_period_end=bool(row["cancel_at_period_end"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    # Fallback: return default free subscription
    # This should never happen after migration, but provides safety
    return Subscription(
        id=0,
        account_id=account_id,
        status="active",
        plan_name="free",
        provider="manual",
    )


# ============================================================================
# Effective Plan Calculation
# ============================================================================

def get_effective_plan(subscription: Subscription) -> str:
    """
    Compute effective plan based on subscription status.
    
    Rules:
    - If subscription is active or trialing: return subscription.plan_name
    - If subscription is past_due or canceled: return "free" (revoke paid features)
    
    This ensures immediate downgrade when payment fails or subscription ends.
    
    Args:
        subscription: Subscription object
    
    Returns:
        Effective plan name ("free", "pro", "team", "enterprise")
    """
    if subscription.is_active:
        # Active or trialing: use subscribed plan
        return subscription.plan_name
    
    # Past due, canceled, or unknown: downgrade to free
    return "free"


# ============================================================================
# Entitlements Calculation
# ============================================================================

def get_entitlements(role: str, subscription: Subscription) -> Set[str]:
    """
    Compute effective capabilities from (role + subscription).
    
    This is the central entitlements function that combines:
    1. Subscription status check (past_due/canceled = free plan)
    2. Effective plan capabilities
    3. Role-based restrictions
    
    Args:
        role: User role (owner/admin/member/read_only)
        subscription: Subscription object
    
    Returns:
        Set of capability strings allowed by BOTH role AND subscription
    """
    # Get effective plan (respects subscription status)
    effective_plan = get_effective_plan(subscription)
    
    # Use existing RBAC logic to intersect plan + role capabilities
    return rbac_effective_capabilities(effective_plan, role)


def has_entitlement(role: str, subscription: Subscription, capability: str) -> bool:
    """
    Check if user has specific capability based on role and subscription.
    
    Args:
        role: User role
        subscription: Subscription object
        capability: Capability to check
    
    Returns:
        True if allowed, False otherwise
    """
    return capability in get_entitlements(role, subscription)


# ============================================================================
# Subscription Management Helpers
# ============================================================================

def update_subscription_status(
    conn: sqlite3.Connection,
    account_id: int,
    status: str
) -> None:
    """
    Update subscription status (for admin/testing or webhook processing).
    
    Args:
        conn: SQLite connection
        account_id: Account ID
        status: New status (trialing/active/past_due/canceled)
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE subscriptions
        SET status = ?, updated_at = datetime('now')
        WHERE account_id = ?
        """,
        (status, account_id)
    )
    conn.commit()


def update_subscription_plan(
    conn: sqlite3.Connection,
    account_id: int,
    plan_name: str
) -> None:
    """
    Update subscription plan (for admin/testing or upgrade processing).
    
    Args:
        conn: SQLite connection
        account_id: Account ID
        plan_name: New plan (free/pro/team/enterprise)
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE subscriptions
        SET plan_name = ?, status = 'active', updated_at = datetime('now')
        WHERE account_id = ?
        """,
        (plan_name, account_id)
    )
    conn.commit()
