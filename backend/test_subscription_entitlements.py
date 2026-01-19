"""
backend/test_subscription_entitlements.py

Regression tests for subscription-aware entitlements system.

Tests verify:
1. Active subscription + pro plan = full capabilities
2. Past_due/canceled subscription = downgrade to free capabilities
3. Role read_only blocks writes even with active pro subscription
4. Entitlement changes take effect immediately without re-login
"""

import pytest
import sqlite3
from pathlib import Path
import sys

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from entitlements import (
    get_subscription,
    get_effective_plan,
    get_entitlements,
    has_entitlement,
    update_subscription_status,
    update_subscription_plan,
    Subscription,
)
from authz import Capability
from rbac import effective_capabilities


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_db():
    """Create an in-memory test database with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Create accounts table
    cur.execute("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT,
            plan TEXT DEFAULT 'free'
        )
    """)
    
    # Create subscriptions table
    cur.execute("""
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY,
            account_id INTEGER UNIQUE NOT NULL,
            status TEXT DEFAULT 'active',
            plan_name TEXT DEFAULT 'free',
            provider TEXT DEFAULT 'manual',
            provider_customer_id TEXT,
            provider_subscription_id TEXT,
            current_period_end TEXT,
            cancel_at_period_end INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    
    # Insert test account
    cur.execute("INSERT INTO accounts (id, name, plan) VALUES (1, 'Test Account', 'pro')")
    
    # Insert test subscription (active pro)
    cur.execute("""
        INSERT INTO subscriptions (
            account_id, status, plan_name, provider, 
            current_period_end, created_at
        ) VALUES (
            1, 'active', 'pro', 'manual',
            datetime('now', '+1 month'), datetime('now')
        )
    """)
    
    conn.commit()
    yield conn
    conn.close()


# ============================================================================
# Test: Subscription Queries
# ============================================================================

def test_get_subscription_active_pro(test_db):
    """Test fetching active pro subscription."""
    sub = get_subscription(test_db, account_id=1)
    
    assert sub.account_id == 1
    assert sub.status == "active"
    assert sub.plan_name == "pro"
    assert sub.is_active is True
    assert sub.is_past_due is False
    assert sub.is_canceled is False


def test_get_subscription_missing_account_returns_default(test_db):
    """Test that missing subscription returns default free subscription."""
    sub = get_subscription(test_db, account_id=999)
    
    assert sub.account_id == 999
    assert sub.status == "active"
    assert sub.plan_name == "free"
    assert sub.is_active is True


# ============================================================================
# Test: Effective Plan Calculation
# ============================================================================

def test_effective_plan_active_subscription(test_db):
    """Test effective plan for active subscription."""
    sub = get_subscription(test_db, account_id=1)
    effective = get_effective_plan(sub)
    
    assert effective == "pro"


def test_effective_plan_trialing_subscription(test_db):
    """Test effective plan for trialing subscription."""
    # Update to trialing
    update_subscription_status(test_db, account_id=1, status="trialing")
    
    sub = get_subscription(test_db, account_id=1)
    effective = get_effective_plan(sub)
    
    assert effective == "pro"  # Trialing still gets full plan


def test_effective_plan_past_due_downgrades_to_free(test_db):
    """Test that past_due subscription downgrades to free."""
    # Update to past_due
    update_subscription_status(test_db, account_id=1, status="past_due")
    
    sub = get_subscription(test_db, account_id=1)
    effective = get_effective_plan(sub)
    
    assert sub.plan_name == "pro"  # Subscription still says pro
    assert effective == "free"  # But effective plan is free
    assert sub.is_past_due is True


def test_effective_plan_canceled_downgrades_to_free(test_db):
    """Test that canceled subscription downgrades to free."""
    # Update to canceled
    update_subscription_status(test_db, account_id=1, status="canceled")
    
    sub = get_subscription(test_db, account_id=1)
    effective = get_effective_plan(sub)
    
    assert sub.plan_name == "pro"  # Subscription still says pro
    assert effective == "free"  # But effective plan is free
    assert sub.is_canceled is True


# ============================================================================
# Test: Entitlements with Active Subscription
# ============================================================================

def test_entitlements_owner_active_pro(test_db):
    """Test that owner on active pro gets full capabilities."""
    sub = get_subscription(test_db, account_id=1)
    caps = get_entitlements(role="owner", subscription=sub)
    
    # Owner on pro should have all pro capabilities
    assert Capability.PROJECT_CREATE in caps
    assert Capability.ASSET_MANAGE in caps
    assert Capability.EXPORT_CSV in caps
    assert Capability.ANALYSIS_PORTFOLIO in caps


def test_entitlements_member_active_pro(test_db):
    """Test that member on active pro gets pro member capabilities."""
    sub = get_subscription(test_db, account_id=1)
    caps = get_entitlements(role="member", subscription=sub)
    
    # Member on pro should have pro capabilities
    assert Capability.PROJECT_CREATE in caps
    assert Capability.ASSET_MANAGE in caps
    assert Capability.EXPORT_CSV in caps


def test_entitlements_read_only_active_pro(test_db):
    """Test that read_only on active pro still has restricted capabilities."""
    sub = get_subscription(test_db, account_id=1)
    caps = get_entitlements(role="read_only", subscription=sub)
    
    # Read-only should NOT have write capabilities even on pro plan
    assert Capability.PROJECT_VIEW in caps
    assert Capability.ASSET_VIEW in caps
    
    # Should NOT have write capabilities
    assert Capability.PROJECT_CREATE not in caps
    assert Capability.ASSET_MANAGE not in caps
    assert Capability.EXPORT_CSV not in caps  # Read-only can't export


# ============================================================================
# Test: Entitlements with Past Due Subscription
# ============================================================================

def test_entitlements_owner_past_due_loses_pro_features(test_db):
    """Test that owner on past_due subscription loses pro features."""
    # Set to past_due
    update_subscription_status(test_db, account_id=1, status="past_due")
    
    sub = get_subscription(test_db, account_id=1)
    caps = get_entitlements(role="owner", subscription=sub)
    
    # Owner should have free plan capabilities only
    assert Capability.PROJECT_VIEW in caps
    assert Capability.ASSET_VIEW in caps
    
    # Should NOT have pro features
    assert Capability.PROJECT_CREATE not in caps  # Free plan restriction
    assert Capability.ASSET_MANAGE not in caps
    assert Capability.EXPORT_CSV not in caps


def test_entitlements_member_past_due_loses_pro_features(test_db):
    """Test that member on past_due subscription loses pro features."""
    # Set to past_due
    update_subscription_status(test_db, account_id=1, status="past_due")
    
    sub = get_subscription(test_db, account_id=1)
    caps = get_entitlements(role="member", subscription=sub)
    
    # Member should have free plan capabilities only (intersection of member role + free plan)
    assert Capability.PROJECT_VIEW in caps
    assert Capability.ASSET_VIEW in caps
    
    # Should NOT have pro features
    assert Capability.EXPORT_CSV not in caps


# ============================================================================
# Test: Entitlements with Canceled Subscription
# ============================================================================

def test_entitlements_owner_canceled_loses_pro_features(test_db):
    """Test that owner on canceled subscription loses pro features."""
    # Set to canceled
    update_subscription_status(test_db, account_id=1, status="canceled")
    
    sub = get_subscription(test_db, account_id=1)
    caps = get_entitlements(role="owner", subscription=sub)
    
    # Owner should have free plan capabilities only
    assert Capability.PROJECT_VIEW in caps
    assert Capability.ASSET_VIEW in caps
    
    # Should NOT have pro features
    assert Capability.EXPORT_CSV not in caps
    assert Capability.ANALYSIS_PORTFOLIO not in caps


# ============================================================================
# Test: Subscription Management
# ============================================================================

def test_update_subscription_status(test_db):
    """Test updating subscription status."""
    update_subscription_status(test_db, account_id=1, status="canceled")
    
    sub = get_subscription(test_db, account_id=1)
    assert sub.status == "canceled"


def test_update_subscription_plan(test_db):
    """Test updating subscription plan."""
    update_subscription_plan(test_db, account_id=1, plan_name="team")
    
    sub = get_subscription(test_db, account_id=1)
    assert sub.plan_name == "team"
    assert sub.status == "active"  # Should reset to active


# ============================================================================
# Test: has_entitlement Helper
# ============================================================================

def test_has_entitlement_active_pro_allows_export(test_db):
    """Test that active pro subscription allows CSV export."""
    sub = get_subscription(test_db, account_id=1)
    
    assert has_entitlement("owner", sub, Capability.EXPORT_CSV) is True
    assert has_entitlement("member", sub, Capability.EXPORT_CSV) is True


def test_has_entitlement_past_due_blocks_export(test_db):
    """Test that past_due subscription blocks CSV export."""
    update_subscription_status(test_db, account_id=1, status="past_due")
    sub = get_subscription(test_db, account_id=1)
    
    assert has_entitlement("owner", sub, Capability.EXPORT_CSV) is False
    assert has_entitlement("member", sub, Capability.EXPORT_CSV) is False


def test_has_entitlement_read_only_blocks_writes(test_db):
    """Test that read_only role blocks writes even on active pro."""
    sub = get_subscription(test_db, account_id=1)
    
    assert has_entitlement("read_only", sub, Capability.ASSET_MANAGE) is False
    assert has_entitlement("read_only", sub, Capability.PROJECT_CREATE) is False


# ============================================================================
# Test: Role + Subscription Interaction
# ============================================================================

def test_role_restrictions_override_plan(test_db):
    """Test that role restrictions apply even with pro subscription."""
    sub = get_subscription(test_db, account_id=1)
    
    # Owner on pro has full access
    owner_caps = get_entitlements("owner", sub)
    assert Capability.ASSET_MANAGE in owner_caps
    
    # Read-only on same pro subscription cannot manage
    readonly_caps = get_entitlements("read_only", sub)
    assert Capability.ASSET_MANAGE not in readonly_caps


def test_plan_restrictions_override_role(test_db):
    """Test that plan restrictions apply even with owner role."""
    # Set to free plan
    update_subscription_plan(test_db, account_id=1, plan_name="free")
    sub = get_subscription(test_db, account_id=1)
    
    # Owner on free plan cannot export CSV (plan limitation)
    owner_caps = get_entitlements("owner", sub)
    assert Capability.EXPORT_CSV not in owner_caps


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
