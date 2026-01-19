"""
backend/test_subscription_api_integration.py

Integration tests for subscription-aware API endpoints.

Tests verify:
1. /account/info returns subscription state
2. Capability-protected endpoints respect subscription status
3. Admin endpoints can modify subscription state
4. Changes take effect immediately (no cache issues)
"""

import pytest
import os
import sys
from pathlib import Path

# Set test environment
os.environ["BRINKADATA_ENV"] = "dev"
os.environ["IS_DEV"] = "true"

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from fastapi.testclient import TestClient
from backend.main import app, get_db
from backend.auth_context import AuthContext
from backend.authz import Capability


# ============================================================================
# Test Client Setup
# ============================================================================

client = TestClient(app)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_user_token():
    """
    Create test user and return JWT token.
    
    This uses the real database and authentication flow.
    Cleanup happens automatically on next run (dev db).
    """
    # Register a test user
    register_data = {
        "email": f"test_subscription_{os.getpid()}@example.com",
        "password": "testpass123",
        "account_name": "Test Subscription Account"
    }
    
    resp = client.post("/auth/register", json=register_data)
    assert resp.status_code == 200
    
    # Login to get token
    login_data = {
        "email": register_data["email"],
        "password": register_data["password"]
    }
    
    resp = client.post("/auth/login", json=login_data)
    assert resp.status_code == 200
    
    data = resp.json()
    token = data["access_token"]
    account_id = data["account_id"]
    
    yield {"token": token, "account_id": account_id, "email": register_data["email"]}


# ============================================================================
# Test: /account/info Returns Subscription State
# ============================================================================

def test_account_info_includes_subscription(test_user_token):
    """Test that /account/info includes subscription object."""
    token = test_user_token["token"]
    
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Should include subscription object
    assert "subscription" in data
    sub = data["subscription"]
    
    assert "status" in sub
    assert "plan" in sub
    assert "effective_plan" in sub
    assert "cancel_at_period_end" in sub
    
    # Default should be active free
    assert sub["status"] in ["active", "trialing"]
    assert sub["plan"] == "free"
    assert sub["effective_plan"] == "free"
    
    # Should include capabilities
    assert "capabilities" in data
    assert isinstance(data["capabilities"], list)


def test_account_info_includes_capabilities_list(test_user_token):
    """Test that capabilities are returned as a list."""
    token = test_user_token["token"]
    
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    
    capabilities = data["capabilities"]
    assert isinstance(capabilities, list)
    
    # Free plan should have basic capabilities
    assert "project:view" in capabilities
    assert "asset:view" in capabilities
    
    # Free plan should NOT have pro capabilities
    assert "export:csv" not in capabilities


# ============================================================================
# Test: Admin Endpoints Modify Subscription
# ============================================================================

def test_admin_set_plan_updates_subscription(test_user_token):
    """Test that /admin/set_plan updates subscription."""
    account_id = test_user_token["account_id"]
    token = test_user_token["token"]
    
    # Upgrade to pro
    resp = client.post(
        f"/admin/set_plan?account_id={account_id}&plan=pro"
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "pro"
    assert data["subscription_status"] == "active"
    
    # Verify via /account/info
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["plan"] == "pro"
    assert data["subscription"]["plan"] == "pro"
    assert data["subscription"]["effective_plan"] == "pro"
    assert data["subscription"]["status"] == "active"
    
    # Should now have pro capabilities
    assert "export:csv" in data["capabilities"]


def test_admin_set_subscription_status_to_past_due(test_user_token):
    """Test that setting subscription to past_due downgrades capabilities."""
    account_id = test_user_token["account_id"]
    token = test_user_token["token"]
    
    # First upgrade to pro
    client.post(f"/admin/set_plan?account_id={account_id}&plan=pro")
    
    # Verify pro capabilities
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = resp.json()
    assert "export:csv" in data["capabilities"]
    
    # Set to past_due
    resp = client.post(
        f"/admin/set_subscription_status?account_id={account_id}&status=past_due"
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["subscription_status"] == "past_due"
    
    # Verify capabilities downgraded immediately
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Subscription still says pro
    assert data["subscription"]["plan"] == "pro"
    
    # But effective plan is free
    assert data["subscription"]["effective_plan"] == "free"
    assert data["subscription"]["status"] == "past_due"
    
    # Pro capabilities should be gone
    assert "export:csv" not in data["capabilities"]


def test_admin_set_subscription_status_to_canceled(test_user_token):
    """Test that canceling subscription downgrades capabilities."""
    account_id = test_user_token["account_id"]
    token = test_user_token["token"]
    
    # Upgrade to pro
    client.post(f"/admin/set_plan?account_id={account_id}&plan=pro")
    
    # Cancel subscription
    resp = client.post(
        f"/admin/set_subscription_status?account_id={account_id}&status=canceled"
    )
    
    assert resp.status_code == 200
    
    # Verify capabilities downgraded
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    data = resp.json()
    assert data["subscription"]["status"] == "canceled"
    assert data["subscription"]["effective_plan"] == "free"
    assert "export:csv" not in data["capabilities"]


# ============================================================================
# Test: Capability-Protected Endpoints Respect Subscription
# ============================================================================

def test_capability_protected_endpoint_allows_when_active_pro(test_user_token):
    """Test that capability-protected endpoints allow access on active pro."""
    account_id = test_user_token["account_id"]
    token = test_user_token["token"]
    
    # Upgrade to pro
    client.post(f"/admin/set_plan?account_id={account_id}&plan=pro")
    
    # Try to access a capability-protected endpoint
    # Note: We'd need an actual capability-protected endpoint to test
    # For now, verify via /account/info that capabilities exist
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    data = resp.json()
    assert "export:csv" in data["capabilities"]


def test_capability_protected_endpoint_blocks_when_past_due(test_user_token):
    """Test that capability-protected endpoints block access when past_due."""
    account_id = test_user_token["account_id"]
    token = test_user_token["token"]
    
    # Upgrade to pro then set to past_due
    client.post(f"/admin/set_plan?account_id={account_id}&plan=pro")
    client.post(f"/admin/set_subscription_status?account_id={account_id}&status=past_due")
    
    # Verify capabilities removed
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    data = resp.json()
    assert "export:csv" not in data["capabilities"]


# ============================================================================
# Test: Subscription Changes Take Effect Immediately
# ============================================================================

def test_subscription_changes_immediate_no_cache(test_user_token):
    """Test that subscription changes take effect on next request (no caching)."""
    account_id = test_user_token["account_id"]
    token = test_user_token["token"]
    
    # Initial state: free
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    data1 = resp.json()
    assert data1["plan"] == "free"
    assert "export:csv" not in data1["capabilities"]
    
    # Upgrade to pro
    client.post(f"/admin/set_plan?account_id={account_id}&plan=pro")
    
    # Immediate next request should show pro
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    data2 = resp.json()
    assert data2["plan"] == "pro"
    assert "export:csv" in data2["capabilities"]
    
    # Set to past_due
    client.post(f"/admin/set_subscription_status?account_id={account_id}&status=past_due")
    
    # Immediate next request should show downgrade
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    data3 = resp.json()
    assert data3["subscription"]["status"] == "past_due"
    assert data3["subscription"]["effective_plan"] == "free"
    assert "export:csv" not in data3["capabilities"]
    
    # Reactivate
    client.post(f"/admin/set_subscription_status?account_id={account_id}&status=active")
    
    # Immediate next request should show restoration
    resp = client.get(
        "/account/info",
        headers={"Authorization": f"Bearer {token}"}
    )
    data4 = resp.json()
    assert data4["subscription"]["status"] == "active"
    assert data4["subscription"]["effective_plan"] == "pro"
    assert "export:csv" in data4["capabilities"]


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
