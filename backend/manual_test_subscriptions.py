"""
backend/manual_test_subscriptions.py

Manual testing script for subscription system (no pytest required).
Run this to verify subscription-aware entitlements work correctly.
"""

import sqlite3
import sys
from pathlib import Path

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
)
from authz import Capability


def setup_test_db():
    """Create test database with one account."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Create tables
    cur.execute("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT,
            plan TEXT DEFAULT 'free'
        )
    """)
    
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
    
    # Insert test data
    cur.execute("INSERT INTO accounts (id, name, plan) VALUES (1, 'Test Account', 'pro')")
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
    return conn


def test_active_pro_subscription(conn):
    """Test 1: Active pro subscription grants pro capabilities."""
    print("\n=== TEST 1: Active Pro Subscription ===")
    
    sub = get_subscription(conn, account_id=1)
    print(f"Subscription: status={sub.status}, plan={sub.plan_name}")
    
    effective = get_effective_plan(sub)
    print(f"Effective plan: {effective}")
    
    owner_caps = get_entitlements("owner", sub)
    print(f"Owner capabilities: {len(owner_caps)} total")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in owner_caps}")
    print(f"  - Can manage assets: {Capability.ASSET_MANAGE in owner_caps}")
    
    assert effective == "pro", "Expected effective plan to be 'pro'"
    assert Capability.EXPORT_CSV in owner_caps, "Expected owner to have export capability"
    print("✅ TEST 1 PASSED")


def test_past_due_downgrades(conn):
    """Test 2: Past due subscription downgrades to free."""
    print("\n=== TEST 2: Past Due Subscription Downgrades ===")
    
    update_subscription_status(conn, account_id=1, status="past_due")
    
    sub = get_subscription(conn, account_id=1)
    print(f"Subscription: status={sub.status}, plan={sub.plan_name}")
    
    effective = get_effective_plan(sub)
    print(f"Effective plan: {effective}")
    
    owner_caps = get_entitlements("owner", sub)
    print(f"Owner capabilities: {len(owner_caps)} total")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in owner_caps}")
    print(f"  - Can view projects: {Capability.PROJECT_VIEW in owner_caps}")
    
    assert sub.plan_name == "pro", "Subscription plan should still be 'pro'"
    assert effective == "free", "Expected effective plan to be downgraded to 'free'"
    assert Capability.EXPORT_CSV not in owner_caps, "Expected export capability to be revoked"
    assert Capability.PROJECT_VIEW in owner_caps, "Expected basic view capability to remain"
    print("✅ TEST 2 PASSED")


def test_canceled_subscription(conn):
    """Test 3: Canceled subscription loses pro features."""
    print("\n=== TEST 3: Canceled Subscription ===")
    
    # Reset to active first
    update_subscription_status(conn, account_id=1, status="active")
    
    # Then cancel
    update_subscription_status(conn, account_id=1, status="canceled")
    
    sub = get_subscription(conn, account_id=1)
    print(f"Subscription: status={sub.status}, plan={sub.plan_name}")
    
    effective = get_effective_plan(sub)
    print(f"Effective plan: {effective}")
    
    member_caps = get_entitlements("member", sub)
    print(f"Member capabilities: {len(member_caps)} total")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in member_caps}")
    
    assert effective == "free", "Expected effective plan to be 'free' after cancellation"
    assert Capability.EXPORT_CSV not in member_caps, "Expected export capability to be revoked"
    print("✅ TEST 3 PASSED")


def test_read_only_role_restrictions(conn):
    """Test 4: Read-only role blocks writes even with pro subscription."""
    print("\n=== TEST 4: Read-Only Role Restrictions ===")
    
    # Reset to active pro
    update_subscription_status(conn, account_id=1, status="active")
    
    sub = get_subscription(conn, account_id=1)
    print(f"Subscription: status={sub.status}, plan={sub.plan_name}")
    
    readonly_caps = get_entitlements("read_only", sub)
    print(f"Read-only capabilities: {len(readonly_caps)} total")
    print(f"  - Can view projects: {Capability.PROJECT_VIEW in readonly_caps}")
    print(f"  - Can manage assets: {Capability.ASSET_MANAGE in readonly_caps}")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in readonly_caps}")
    
    assert Capability.PROJECT_VIEW in readonly_caps, "Expected read-only to view"
    assert Capability.ASSET_MANAGE not in readonly_caps, "Expected read-only to NOT manage"
    assert Capability.EXPORT_CSV not in readonly_caps, "Expected read-only to NOT export"
    print("✅ TEST 4 PASSED")


def test_trialing_subscription(conn):
    """Test 5: Trialing subscription grants full access."""
    print("\n=== TEST 5: Trialing Subscription ===")
    
    update_subscription_status(conn, account_id=1, status="trialing")
    
    sub = get_subscription(conn, account_id=1)
    print(f"Subscription: status={sub.status}, plan={sub.plan_name}")
    
    effective = get_effective_plan(sub)
    print(f"Effective plan: {effective}")
    
    owner_caps = get_entitlements("owner", sub)
    print(f"Owner capabilities: {len(owner_caps)} total")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in owner_caps}")
    
    assert effective == "pro", "Expected trialing to grant pro plan"
    assert Capability.EXPORT_CSV in owner_caps, "Expected trialing to have pro capabilities"
    print("✅ TEST 5 PASSED")


def test_plan_upgrade(conn):
    """Test 6: Upgrading plan adds capabilities."""
    print("\n=== TEST 6: Plan Upgrade ===")
    
    # Downgrade to free
    update_subscription_plan(conn, account_id=1, plan_name="free")
    
    sub = get_subscription(conn, account_id=1)
    owner_caps_free = get_entitlements("owner", sub)
    print(f"Free plan capabilities: {len(owner_caps_free)} total")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in owner_caps_free}")
    
    # Upgrade to pro
    update_subscription_plan(conn, account_id=1, plan_name="pro")
    
    sub = get_subscription(conn, account_id=1)
    owner_caps_pro = get_entitlements("owner", sub)
    print(f"Pro plan capabilities: {len(owner_caps_pro)} total")
    print(f"  - Can export CSV: {Capability.EXPORT_CSV in owner_caps_pro}")
    
    assert Capability.EXPORT_CSV not in owner_caps_free, "Free should not have export"
    assert Capability.EXPORT_CSV in owner_caps_pro, "Pro should have export"
    assert sub.status == "active", "Upgrade should set status to active"
    print("✅ TEST 6 PASSED")


def main():
    """Run all tests."""
    print("=" * 60)
    print("SUBSCRIPTION ENTITLEMENTS MANUAL TEST SUITE")
    print("=" * 60)
    
    conn = setup_test_db()
    
    try:
        test_active_pro_subscription(conn)
        test_past_due_downgrades(conn)
        test_canceled_subscription(conn)
        test_read_only_role_restrictions(conn)
        test_trialing_subscription(conn)
        test_plan_upgrade(conn)
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
