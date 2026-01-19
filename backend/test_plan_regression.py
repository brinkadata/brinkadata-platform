"""
Regression tests for plan/role upgrade and downgrade behavior.

Tests ensure that:
1. Plan changes take effect immediately without re-login (no stale caching)
2. Downgrades immediately revoke capabilities
3. Upgrades immediately grant capabilities
4. Role changes take effect immediately
5. Capability checks respect BOTH plan AND role (intersection)

Run: python -m pytest backend/test_plan_regression.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.main import app
from backend.config import IS_DEV
from backend.auth_context import get_db

client = TestClient(app)


@pytest.fixture
def test_user_token():
    """
    Fixture to create a test user on free plan and return auth token.
    """
    # Create test account
    conn = get_db()
    cur = conn.cursor()
    
    # Clean up any existing test data
    cur.execute("DELETE FROM users WHERE email = ?", ("test_plan@example.com",))
    cur.execute("DELETE FROM accounts WHERE name = ?", ("Test Plan Account",))
    conn.commit()
    
    # Create account (free plan by default)
    cur.execute(
        "INSERT INTO accounts (name, plan) VALUES (?, ?)",
        ("Test Plan Account", "free")
    )
    account_id = cur.lastrowid
    
    # Create user (owner role)
    import hashlib
    password_hash = hashlib.sha256("testpass123".encode()).hexdigest()
    cur.execute(
        "INSERT INTO users (email, password_hash, account_id, role, is_active) VALUES (?, ?, ?, ?, ?)",
        ("test_plan@example.com", password_hash, account_id, "owner", True)
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # Login to get token
    resp = client.post(
        "/auth/login",
        json={"email": "test_plan@example.com", "password": "testpass123"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    
    token = resp.json()["access_token"]
    
    yield {
        "token": token,
        "account_id": account_id,
        "user_id": user_id,
        "headers": {"Authorization": f"Bearer {token}"}
    }
    
    # Cleanup
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    cur.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()


class TestPlanUpgradeDowngradeRegression:
    """
    Test that plan changes take effect immediately without re-login.
    This prevents the regression where plan changes require logout/login to apply.
    """
    
    @pytest.mark.skipif(not IS_DEV, reason="Requires DEV environment for admin endpoints")
    def test_plan_upgrade_takes_effect_immediately(self, test_user_token):
        """
        Verify that upgrading from free to pro immediately grants capabilities.
        
        Steps:
        1. User starts on free plan
        2. Verify capability-protected endpoint is blocked (403)
        3. Admin upgrades account to pro plan
        4. WITHOUT obtaining new token, verify endpoint now succeeds
        """
        headers = test_user_token["headers"]
        account_id = test_user_token["account_id"]
        
        # Step 1: Verify starting on free plan
        resp = client.get("/auth/capabilities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "free", "Should start on free plan"
        assert "asset:manage" not in data["capabilities"], "Free plan should not have asset:manage"
        
        # Step 2: Attempt to call capability-protected endpoint (should fail on free)
        # Use /property/save as it requires asset:manage capability
        test_property = {
            "property_name": "Test Property",
            "purchase_price": 200000,
            "rehab_budget": 40000,
            "monthly_rent": 2000,
            "hold_years": 5,
            "strategy": "rental"
        }
        
        # First run analysis
        resp = client.post("/property/analyze", json=test_property, headers=headers)
        assert resp.status_code == 200, "Analysis should work on free plan"
        
        # Try to save (requires asset:manage)
        save_payload = {
            "property_id": None,
            "analysis_data": resp.json()
        }
        resp = client.post("/property/save", json=save_payload, headers=headers)
        assert resp.status_code == 403, "Save should be blocked on free plan (no asset:manage)"
        
        # Step 3: Upgrade to pro plan via admin endpoint
        resp = client.post(
            "/admin/set_plan",
            params={"account_id": account_id, "plan": "pro"},
            headers=headers
        )
        assert resp.status_code == 200, f"Plan upgrade failed: {resp.text}"
        
        # Step 4: WITHOUT NEW TOKEN, verify capabilities are updated
        resp = client.get("/auth/capabilities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro", "Plan should be updated to pro"
        assert "asset:manage" in data["capabilities"], "Pro plan should have asset:manage"
        
        # Step 5: Verify save now works (same token, new plan)
        resp = client.post("/property/save", json=save_payload, headers=headers)
        assert resp.status_code in (200, 201), f"Save should work on pro plan: {resp.text}"
    
    @pytest.mark.skipif(not IS_DEV, reason="Requires DEV environment for admin endpoints")
    def test_plan_downgrade_revokes_immediately(self, test_user_token):
        """
        Verify that downgrading from pro to free immediately revokes capabilities.
        
        This is CRITICAL for SaaS security: downgrades must take effect instantly.
        """
        headers = test_user_token["headers"]
        account_id = test_user_token["account_id"]
        
        # Step 1: Upgrade to pro first
        resp = client.post(
            "/admin/set_plan",
            params={"account_id": account_id, "plan": "pro"},
            headers=headers
        )
        assert resp.status_code == 200
        
        # Step 2: Verify pro capabilities work
        resp = client.get("/auth/capabilities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro"
        assert "asset:manage" in data["capabilities"]
        
        # Step 3: Verify save works on pro
        test_property = {
            "property_name": "Test Property",
            "purchase_price": 200000,
            "rehab_budget": 40000,
            "monthly_rent": 2000,
            "hold_years": 5,
            "strategy": "rental"
        }
        resp = client.post("/property/analyze", json=test_property, headers=headers)
        assert resp.status_code == 200
        
        save_payload = {
            "property_id": None,
            "analysis_data": resp.json()
        }
        resp = client.post("/property/save", json=save_payload, headers=headers)
        assert resp.status_code in (200, 201), "Save should work on pro plan"
        
        # Step 4: Downgrade to free
        resp = client.post(
            "/admin/set_plan",
            params={"account_id": account_id, "plan": "free"},
            headers=headers
        )
        assert resp.status_code == 200
        
        # Step 5: WITHOUT NEW TOKEN, verify capabilities are revoked
        resp = client.get("/auth/capabilities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "free", "Plan should be downgraded to free"
        assert "asset:manage" not in data["capabilities"], "Free plan should not have asset:manage"
        
        # Step 6: Verify save is now blocked (CRITICAL SECURITY TEST)
        resp = client.post("/property/save", json=save_payload, headers=headers)
        assert resp.status_code == 403, "Save MUST be blocked immediately after downgrade"
    
    @pytest.mark.skipif(not IS_DEV, reason="Requires DEV environment for admin endpoints")
    def test_role_change_takes_effect_immediately(self, test_user_token):
        """
        Verify that role changes (e.g., owner to read_only) take effect immediately.
        """
        headers = test_user_token["headers"]
        user_id = test_user_token["user_id"]
        account_id = test_user_token["account_id"]
        
        # Step 1: Upgrade to pro plan so role is the limiting factor
        resp = client.post(
            "/admin/set_plan",
            params={"account_id": account_id, "plan": "pro"},
            headers=headers
        )
        assert resp.status_code == 200
        
        # Step 2: Verify owner role on pro has asset:manage
        resp = client.get("/auth/capabilities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro"
        assert data["role"] == "owner"
        assert "asset:manage" in data["capabilities"]
        
        # Step 3: Change role to read_only
        resp = client.post(
            "/admin/set_role",
            params={"user_id": user_id, "role": "read_only"},
            headers=headers
        )
        assert resp.status_code == 200
        
        # Step 4: WITHOUT NEW TOKEN, verify capabilities are restricted
        resp = client.get("/auth/capabilities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro", "Plan should still be pro"
        assert data["role"] == "read_only", "Role should be read_only"
        assert "asset:manage" not in data["capabilities"], "read_only role should not have asset:manage even on pro"
        
        # Step 5: Verify save is blocked (role restriction)
        test_property = {
            "property_name": "Test Property",
            "purchase_price": 200000,
            "rehab_budget": 40000,
            "monthly_rent": 2000,
            "hold_years": 5,
            "strategy": "rental"
        }
        resp = client.post("/property/analyze", json=test_property, headers=headers)
        assert resp.status_code == 200
        
        save_payload = {
            "property_id": None,
            "analysis_data": resp.json()
        }
        resp = client.post("/property/save", json=save_payload, headers=headers)
        assert resp.status_code == 403, "Save should be blocked for read_only role"


class TestCapabilityMapping:
    """
    Verify that capability strings are consistent between backend and frontend.
    """
    
    def test_asset_manage_capability_exists(self):
        """
        Verify that 'asset:manage' capability is properly defined in RBAC.
        """
        from backend.rbac import effective_capabilities, Capability
        
        # Verify constant exists
        assert hasattr(Capability, 'ASSET_MANAGE'), "Capability.ASSET_MANAGE must be defined"
        assert Capability.ASSET_MANAGE == "asset:manage", "Capability string must be 'asset:manage'"
        
        # Verify pro + owner has it
        caps = effective_capabilities("pro", "owner")
        assert "asset:manage" in caps, "Pro plan + owner role should have asset:manage"
        
        # Verify free + owner does NOT have it
        caps = effective_capabilities("free", "owner")
        assert "asset:manage" not in caps, "Free plan should not have asset:manage regardless of role"
        
        # Verify pro + read_only does NOT have it
        caps = effective_capabilities("pro", "read_only")
        assert "asset:manage" not in caps, "read_only role should not have asset:manage regardless of plan"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
