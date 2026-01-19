"""
backend/test_capabilities.py

Regression tests for capability-based authorization system.

Tests:
1. /account/capabilities endpoint returns correct structure
2. Capabilities vary correctly by role and plan
3. Endpoints requiring specific capabilities behave correctly
4. sqlite3.Row handling remains stable (no .get() calls on Row objects)

Run:
    pytest backend/test_capabilities.py -v
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

# Create unique test database BEFORE importing app
# Use DATABASE_PATH env var which config.py reads
TEST_DB_PATH = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_PATH"] = TEST_DB_PATH

# Import after setting environment variable
from backend.main import app
from backend.config import SECRET_KEY, ALGORITHM
from backend.rbac import Capability


def setup_test_database(db_path: str):
    """Set up test database with test data."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Create minimal schema for test
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT DEFAULT 'member',
            account_id INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)
    
    # Create test accounts with different plans
    cur.execute("INSERT INTO accounts (id, name, plan) VALUES (?, ?, ?)", (1, "Free Account", "free"))
    cur.execute("INSERT INTO accounts (id, name, plan) VALUES (?, ?, ?)", (2, "Pro Account", "pro"))
    cur.execute("INSERT INTO accounts (id, name, plan) VALUES (?, ?, ?)", (3, "Team Account", "team"))
    
    # Create test users with different roles and plans
    # Account 1 (Free): owner, member, read_only
    cur.execute("INSERT INTO users (id, email, password_hash, role, account_id) VALUES (?, ?, ?, ?, ?)", 
                (1, "owner@free.com", "test_hash", "owner", 1))
    cur.execute("INSERT INTO users (id, email, password_hash, role, account_id) VALUES (?, ?, ?, ?, ?)", 
                (2, "member@free.com", "test_hash", "member", 1))
    cur.execute("INSERT INTO users (id, email, password_hash, role, account_id) VALUES (?, ?, ?, ?, ?)", 
                (3, "readonly@free.com", "test_hash", "read_only", 1))
    # Account 2 (Pro): owner
    cur.execute("INSERT INTO users (id, email, password_hash, role, account_id) VALUES (?, ?, ?, ?, ?)", 
                (4, "owner@pro.com", "test_hash", "owner", 2))
    # Account 3 (Team): member
    cur.execute("INSERT INTO users (id, email, password_hash, role, account_id) VALUES (?, ?, ?, ?, ?)", 
                (5, "member@team.com", "test_hash", "member", 3))
    
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    """Create test client with isolated database."""
    # Setup test database
    setup_test_database(TEST_DB_PATH)
    
    # Create test client
    test_client = TestClient(app)
    
    yield test_client
    
    # Cleanup
    try:
        os.unlink(TEST_DB_PATH)
    except Exception:
        pass


def generate_test_token(user_id: int, email: str) -> str:
    """Generate a valid JWT token for testing."""
    import time
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


class TestCapabilitiesEndpoint:
    """Test /account/capabilities endpoint."""
    
    def test_capabilities_endpoint_exists(self, client):
        """Test that /account/capabilities endpoint exists and requires auth."""
        response = client.get("/account/capabilities")
        # Should return 401/403 without token, not 404
        assert response.status_code in [401, 403], "Endpoint should exist but require auth"
    
    def test_capabilities_returns_correct_structure(self, client):
        """Test that capabilities endpoint returns expected JSON structure."""
        token = generate_test_token(1, "owner@free.com")
        
        response = client.get(
            "/account/capabilities",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        
        data = response.json()
        assert "plan" in data, "Response should include 'plan'"
        assert "role" in data, "Response should include 'role'"
        assert "capabilities" in data, "Response should include 'capabilities'"
        assert isinstance(data["capabilities"], list), "Capabilities should be a list"
        assert len(data["capabilities"]) > 0, "Should have at least some capabilities"
        
        print(f"✓ Capabilities structure valid: plan={data['plan']}, role={data['role']}, caps={len(data['capabilities'])}")
    
    def test_auth_capabilities_alias_works(self, client):
        """Test that /auth/capabilities also works (backward compatibility)."""
        token = generate_test_token(1, "owner@free.com")
        
        response = client.get(
            "/auth/capabilities",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, "Legacy endpoint should still work"
        data = response.json()
        assert "capabilities" in data


class TestCapabilitiesByRoleAndPlan:
    """Test that capabilities vary correctly by role and plan."""
    
    def test_free_owner_has_basic_capabilities(self, client):
        """Test that free plan owner has basic capabilities."""
        token = generate_test_token(1, "owner@free.com")
        
        response = client.get(
            "/account/capabilities",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        data = response.json()
        assert data["plan"] == "free"
        assert data["role"] == "owner"
        
        caps = data["capabilities"]
        # Free plan should have basic capabilities
        assert Capability.ANALYSIS_SINGLE_PROPERTY in caps, "Free should allow single property analysis"
        assert Capability.SEARCH_BASIC in caps, "Free should allow basic search"
        
        # Free plan should NOT have premium capabilities
        assert Capability.EXPORT_CSV not in caps, "Free should NOT allow CSV export"
        assert Capability.ANALYSIS_PORTFOLIO not in caps, "Free should NOT allow portfolio analysis"
        
        print(f"✓ Free owner capabilities: {len(caps)} capabilities")
    
    def test_pro_owner_has_premium_capabilities(self, client):
        """Test that pro plan owner has premium capabilities."""
        token = generate_test_token(4, "owner@pro.com")
        
        response = client.get(
            "/account/capabilities",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        data = response.json()
        assert data["plan"] == "pro"
        assert data["role"] == "owner"
        
        caps = data["capabilities"]
        # Pro plan should have premium capabilities
        assert Capability.EXPORT_CSV in caps, "Pro should allow CSV export"
        assert Capability.ANALYSIS_PORTFOLIO in caps, "Pro should allow portfolio analysis"
        assert Capability.ANALYSIS_SINGLE_PROPERTY in caps, "Pro should allow single property analysis"
        
        print(f"✓ Pro owner capabilities: {len(caps)} capabilities")
    
    def test_readonly_has_limited_capabilities(self, client):
        """Test that read_only role has limited capabilities regardless of plan."""
        token = generate_test_token(3, "readonly@free.com")
        
        response = client.get(
            "/account/capabilities",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        data = response.json()
        assert data["role"] == "read_only"
        
        caps = data["capabilities"]
        # Read-only should NOT have write capabilities
        assert Capability.ASSET_MANAGE not in caps, "Read-only should NOT allow asset management"
        assert Capability.PROJECT_CREATE not in caps, "Read-only should NOT allow project creation"
        
        # Read-only should have view capabilities
        assert Capability.ASSET_VIEW in caps, "Read-only should allow viewing assets"
        assert Capability.PROJECT_VIEW in caps, "Read-only should allow viewing projects"
        
        print(f"✓ Read-only capabilities: {len(caps)} capabilities (limited as expected)")
    
    def test_member_free_vs_member_team(self, client):
        """Test that capabilities differ by plan even with same role."""
        # Member on free plan
        token_free = generate_test_token(2, "member@free.com")
        resp_free = client.get("/account/capabilities", headers={"Authorization": f"Bearer {token_free}"})
        caps_free = resp_free.json()["capabilities"]
        
        # Member on team plan
        token_team = generate_test_token(5, "member@team.com")
        resp_team = client.get("/account/capabilities", headers={"Authorization": f"Bearer {token_team}"})
        caps_team = resp_team.json()["capabilities"]
        
        # Team should have more capabilities than free
        assert len(caps_team) > len(caps_free), "Team plan should have more capabilities than free"
        
        # Team should have capabilities that free doesn't
        assert Capability.EXPORT_CSV in caps_team, "Team should allow CSV export"
        assert Capability.EXPORT_CSV not in caps_free, "Free should NOT allow CSV export"
        
        print(f"✓ Plan affects capabilities: free={len(caps_free)}, team={len(caps_team)}")


class TestCapabilityEnforcement:
    """Test that endpoints requiring capabilities behave correctly."""
    
    def test_analyze_endpoint_respects_capabilities(self, client):
        """Test that /property/analyze works for users with analysis capability."""
        token = generate_test_token(1, "owner@free.com")
        
        payload = {
            "property_name": "Test Property",
            "city": "Test City",
            "state": "CA",
            "purchase_price": 200000,
            "rehab_budget": 30000,
            "monthly_rent": 2000,
            "hold_years": 5,
            "strategy": "rental",
            "vacancy_rate": 0.05,
            "op_ex_pct_of_rent": 0.30,
            "op_ex_fixed_monthly": 0,
            "capex_reserves_pct": 0.05,
        }
        
        response = client.post(
            "/property/analyze",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should succeed (200) or be gated by plan features (402/403), but never crash (500)
        assert response.status_code != 500, f"Analyze should not crash: {response.json()}"
        assert response.status_code in [200, 402, 403], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "noi_annual" in data, "Successful analysis should include metrics"
            print("✓ Analyze endpoint works with valid capabilities")


class TestSqlite3RowStability:
    """Test that sqlite3.Row handling is stable (no .get() calls)."""
    
    def test_no_sqlite_row_attribute_error_in_capabilities(self, client):
        """Test that capabilities endpoint doesn't crash with sqlite3.Row errors."""
        token = generate_test_token(1, "owner@free.com")
        
        response = client.get(
            "/account/capabilities",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should not crash with AttributeError
        assert response.status_code != 500, \
            f"Capabilities endpoint should not crash with sqlite3.Row error: {response.json() if response.status_code == 500 else 'OK'}"
        assert response.status_code == 200, f"Should succeed: {response.status_code}"
        
        print("✓ No sqlite3.Row errors in capabilities endpoint")
    
    def test_auth_context_handles_row_objects_correctly(self, client):
        """Test that auth context dependency doesn't crash when accessing row fields."""
        token = generate_test_token(1, "owner@free.com")
        
        # Try multiple authenticated endpoints to verify auth context stability
        endpoints = [
            "/account/capabilities",
            "/account/info",
        ]
        
        for endpoint in endpoints:
            response = client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            assert response.status_code != 500, \
                f"Endpoint {endpoint} crashed (likely sqlite3.Row error): {response.json() if response.status_code == 500 else 'OK'}"
        
        print("✓ Auth context handles sqlite3.Row objects correctly across endpoints")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
