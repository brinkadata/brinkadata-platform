"""
backend/test_property_search_assets.py

Comprehensive security and validation tests for Property Search + Assets features.

Tests cover:
- Tenant isolation (no cross-tenant data leaks)
- RBAC enforcement (capability gating)
- Input validation
- SQL injection prevention
- Auth requirement enforcement

Run: pytest backend/test_property_search_assets.py -v
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path as FsPath
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# Mock modules for testing
import sys
sys.path.insert(0, str(FsPath(__file__).parent))

# We need to mock the database and config before importing main
import backend.config as config_module

# Create temp DB for tests
test_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
test_db_path = test_db.name
test_db.close()

# Patch DATABASE_PATH before importing main
config_module.DATABASE_PATH = test_db_path

from backend.main import app, init_db, get_db
from backend.auth_context import AuthContext
from backend.authz import Capability

# ========================================================================
# FIXTURES
# ========================================================================

@pytest.fixture(scope="function")
def db():
    """Create a fresh test database for each test."""
    # Initialize DB
    init_db()
    
    # Seed test data
    conn = get_db()
    cur = conn.cursor()
    
    # Create test accounts
    cur.execute("INSERT INTO accounts (id, name, owner_id) VALUES (1, 'Test Account A', 1)")
    cur.execute("INSERT INTO accounts (id, name, owner_id) VALUES (2, 'Test Account B', 2)")
    
    # Create test users
    cur.execute("INSERT INTO users (id, email, password_hash, account_id, role) VALUES (1, 'user_a@test.com', 'hash_a', 1, 'owner')")
    cur.execute("INSERT INTO users (id, email, password_hash, account_id, role) VALUES (2, 'user_b@test.com', 'hash_b', 2, 'owner')")
    cur.execute("INSERT INTO users (id, email, password_hash, account_id, role) VALUES (3, 'user_readonly@test.com', 'hash_ro', 1, 'read_only')")
    
    # Create test plans
    cur.execute("INSERT INTO plans (id, name, price_monthly) VALUES (1, 'free', 0)")
    cur.execute("INSERT INTO plans (id, name, price_monthly) VALUES (2, 'pro', 29.99)")
    
    # Create test subscriptions
    cur.execute("""
        INSERT INTO subscriptions (account_id, plan_id, status, current_period_start, current_period_end)
        VALUES (1, 2, 'active', datetime('now'), datetime('now', '+30 days'))
    """)
    cur.execute("""
        INSERT INTO subscriptions (account_id, plan_id, status, current_period_start, current_period_end)
        VALUES (2, 2, 'active', datetime('now'), datetime('now', '+30 days'))
    """)
    
    # Seed property_index for testing (tenant A and B)
    cur.execute("""
        INSERT INTO property_index (account_id, address_line1, city, state, postal_code, country, display_address, data)
        VALUES (1, '123 Main St', 'Atlanta', 'GA', '30301', 'US', '123 Main St, Atlanta, GA 30301', '{"beds": 3}')
    """)
    cur.execute("""
        INSERT INTO property_index (account_id, address_line1, city, state, postal_code, country, display_address, data)
        VALUES (1, '456 Oak Ave', 'Decatur', 'GA', '30030', 'US', '456 Oak Ave, Decatur, GA 30030', '{"beds": 4}')
    """)
    cur.execute("""
        INSERT INTO property_index (account_id, address_line1, city, state, postal_code, country, display_address, data)
        VALUES (2, '789 Pine Rd', 'Atlanta', 'GA', '30302', 'US', '789 Pine Rd, Atlanta, GA 30302', '{"beds": 2}')
    """)
    
    # Seed assets for testing (tenant A only)
    cur.execute("""
        INSERT INTO assets (account_id, created_by, name, address_line1, city, state, postal_code, country, source, property_data)
        VALUES (1, 1, 'Test Asset A', '100 Test St', 'Atlanta', 'GA', '30301', 'US', 'property_search', '{}')
    """)
    
    conn.commit()
    conn.close()
    
    yield
    
    # Cleanup (delete temp DB)
    try:
        FsPath(test_db_path).unlink()
    except Exception:
        pass


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def mock_auth_context(account_id: int, user_id: int, capabilities: list[str]) -> AuthContext:
    """Create mock auth context for testing."""
    return AuthContext(
        user_id=user_id,
        account_id=account_id,
        role="owner",
        subscription_status="active",
        subscription_plan="pro",
        effective_plan="pro",
        capabilities=set(capabilities),
    )


# ========================================================================
# PROPERTY SEARCH TESTS
# ========================================================================

class TestPropertySearch:
    """Test suite for property search endpoint."""
    
    def test_search_requires_auth(self, client, db):
        """Property search should require authentication."""
        resp = client.post("/api/property-search", json={"query": "atlanta", "limit": 25})
        assert resp.status_code in [401, 403], "Should require auth"
    
    def test_search_requires_capability(self, client, db, monkeypatch):
        """Property search should require 'property_search:read' capability."""
        # Mock auth context WITHOUT property_search:read capability
        def mock_require_auth():
            return mock_auth_context(1, 1, ["assets:read"])  # Missing property_search:read
        
        monkeypatch.setattr("backend.routes_property_search.require_auth_context", lambda: mock_require_auth())
        
        resp = client.post("/api/property-search", json={"query": "atlanta", "limit": 25})
        assert resp.status_code == 403, "Should deny without property_search:read capability"
    
    def test_search_tenant_isolation(self, client, db, monkeypatch):
        """Property search should only return results for authenticated account."""
        # Mock auth context for account 1
        def mock_require_auth_account_1():
            return mock_auth_context(1, 1, ["property_search:read"])
        
        monkeypatch.setattr("backend.routes_property_search.require_auth_context", lambda: mock_require_auth_account_1())
        
        resp = client.post("/api/property-search", json={"query": "atlanta", "limit": 25})
        assert resp.status_code == 200
        data = resp.json()
        
        # Should return only account 1's properties (123 Main St, 456 Oak Ave)
        # Should NOT return account 2's property (789 Pine Rd)
        results = data.get("results", [])
        addresses = [r["display_address"] for r in results]
        
        assert "123 Main St, Atlanta, GA 30301" in addresses
        assert "789 Pine Rd, Atlanta, GA 30302" not in addresses, "Should not leak account 2's data"
    
    def test_search_input_validation(self, client, db, monkeypatch):
        """Property search should validate input (min length, max limit)."""
        def mock_require_auth():
            return mock_auth_context(1, 1, ["property_search:read"])
        
        monkeypatch.setattr("backend.routes_property_search.require_auth_context", lambda: mock_require_auth())
        
        # Test query too short
        resp = client.post("/api/property-search", json={"query": "a", "limit": 25})
        assert resp.status_code == 422 or resp.status_code == 400, "Should reject query < 2 chars"
        
        # Test limit too high
        resp = client.post("/api/property-search", json={"query": "atlanta", "limit": 999})
        assert resp.status_code == 422 or resp.status_code == 400, "Should reject limit > 50"
    
    def test_search_sql_injection_safe(self, client, db, monkeypatch):
        """Property search should be safe from SQL injection."""
        def mock_require_auth():
            return mock_auth_context(1, 1, ["property_search:read"])
        
        monkeypatch.setattr("backend.routes_property_search.require_auth_context", lambda: mock_require_auth())
        
        # Try SQL injection payload
        malicious_query = "atlanta' OR '1'='1"
        resp = client.post("/api/property-search", json={"query": malicious_query, "limit": 25})
        
        # Should not crash; should return safe results (or none)
        assert resp.status_code == 200
        data = resp.json()
        # Should not return all properties; should be filtered safely
        assert len(data.get("results", [])) <= 2, "Should not leak all properties via injection"


# ========================================================================
# ASSETS TESTS
# ========================================================================

class TestAssetsCreate:
    """Test suite for asset creation endpoint."""
    
    def test_create_requires_auth(self, client, db):
        """Asset creation should require authentication."""
        resp = client.post("/api/assets", json={"name": "Test Asset"})
        assert resp.status_code in [401, 403], "Should require auth"
    
    def test_create_requires_capability(self, client, db, monkeypatch):
        """Asset creation should require 'assets:manage' capability."""
        def mock_require_auth():
            return mock_auth_context(1, 1, ["assets:read"])  # Missing assets:manage
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        resp = client.post("/api/assets", json={"name": "Test Asset"})
        assert resp.status_code == 403, "Should deny without assets:manage capability"
    
    def test_create_name_validation(self, client, db, monkeypatch):
        """Asset creation should validate name (non-empty, max length)."""
        def mock_require_auth():
            return mock_auth_context(1, 1, ["assets:manage"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        # Test empty name
        resp = client.post("/api/assets", json={"name": ""})
        assert resp.status_code == 422 or resp.status_code == 400, "Should reject empty name"
        
        # Test name too long
        resp = client.post("/api/assets", json={"name": "x" * 250})
        assert resp.status_code == 422 or resp.status_code == 400, "Should reject name > 200 chars"
    
    def test_create_tenant_scoped(self, client, db, monkeypatch):
        """Asset creation should use account_id from auth context."""
        def mock_require_auth():
            return mock_auth_context(2, 2, ["assets:manage"])  # Account 2
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        resp = client.post("/api/assets", json={
            "name": "Account 2 Asset",
            "address_line1": "999 Test Ave",
            "city": "Atlanta",
            "state": "GA",
        })
        assert resp.status_code == 200
        
        # Verify asset belongs to account 2
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM assets WHERE name = 'Account 2 Asset'")
        row = cur.fetchone()
        conn.close()
        
        assert row is not None
        assert row["account_id"] == 2, "Asset should belong to account 2"


class TestAssetsList:
    """Test suite for assets list endpoint."""
    
    def test_list_requires_auth(self, client, db):
        """Assets list should require authentication."""
        resp = client.get("/api/assets")
        assert resp.status_code in [401, 403], "Should require auth"
    
    def test_list_requires_capability(self, client, db, monkeypatch):
        """Assets list should require 'assets:read' capability."""
        def mock_require_auth():
            return mock_auth_context(1, 1, [])  # No capabilities
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        resp = client.get("/api/assets")
        assert resp.status_code == 403, "Should deny without assets:read capability"
    
    def test_list_tenant_isolation(self, client, db, monkeypatch):
        """Assets list should only return assets for authenticated account."""
        # Account 1 should see only their asset (Test Asset A)
        def mock_require_auth_account_1():
            return mock_auth_context(1, 1, ["assets:read"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth_account_1())
        
        resp = client.get("/api/assets")
        assert resp.status_code == 200
        data = resp.json()
        
        items = data.get("items", [])
        assert len(items) == 1, "Account 1 should see only 1 asset"
        assert items[0]["name"] == "Test Asset A"
        
        # Account 2 should see no assets (none created yet)
        def mock_require_auth_account_2():
            return mock_auth_context(2, 2, ["assets:read"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth_account_2())
        
        resp = client.get("/api/assets")
        assert resp.status_code == 200
        data = resp.json()
        
        items = data.get("items", [])
        assert len(items) == 0, "Account 2 should see no assets"
    
    def test_list_search_query(self, client, db, monkeypatch):
        """Assets list should support optional search query."""
        def mock_require_auth():
            return mock_auth_context(1, 1, ["assets:read"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        # Search by name
        resp = client.get("/api/assets?q=Test")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("items", [])) == 1
        
        # Search with no match
        resp = client.get("/api/assets?q=NonExistent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("items", [])) == 0


class TestAssetsGet:
    """Test suite for single asset retrieval endpoint."""
    
    def test_get_requires_auth(self, client, db):
        """Asset get should require authentication."""
        resp = client.get("/api/assets/1")
        assert resp.status_code in [401, 403], "Should require auth"
    
    def test_get_requires_capability(self, client, db, monkeypatch):
        """Asset get should require 'assets:read' capability."""
        def mock_require_auth():
            return mock_auth_context(1, 1, [])  # No capabilities
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        resp = client.get("/api/assets/1")
        assert resp.status_code == 403, "Should deny without assets:read capability"
    
    def test_get_tenant_isolation(self, client, db, monkeypatch):
        """Asset get should enforce tenant isolation (404 for other account's assets)."""
        # Account 1 can access their own asset
        def mock_require_auth_account_1():
            return mock_auth_context(1, 1, ["assets:read"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth_account_1())
        
        resp = client.get("/api/assets/1")  # Asset 1 belongs to account 1
        assert resp.status_code == 200
        
        # Account 2 CANNOT access account 1's asset (should get 404, not 403 to avoid info leak)
        def mock_require_auth_account_2():
            return mock_auth_context(2, 2, ["assets:read"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth_account_2())
        
        resp = client.get("/api/assets/1")  # Asset 1 belongs to account 1
        assert resp.status_code == 404, "Should return 404 (not 403) to avoid info leak"


class TestAssetsDelete:
    """Test suite for asset deletion endpoint."""
    
    def test_delete_requires_auth(self, client, db):
        """Asset deletion should require authentication."""
        resp = client.delete("/api/assets/1")
        assert resp.status_code in [401, 403], "Should require auth"
    
    def test_delete_requires_capability(self, client, db, monkeypatch):
        """Asset deletion should require 'assets:manage' capability."""
        def mock_require_auth():
            return mock_auth_context(1, 1, ["assets:read"])  # Missing assets:manage
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth())
        
        resp = client.delete("/api/assets/1")
        assert resp.status_code == 403, "Should deny without assets:manage capability"
    
    def test_delete_tenant_isolation(self, client, db, monkeypatch):
        """Asset deletion should enforce tenant isolation (404 for other account's assets)."""
        # Account 2 CANNOT delete account 1's asset
        def mock_require_auth_account_2():
            return mock_auth_context(2, 2, ["assets:manage"])
        
        monkeypatch.setattr("backend.routes_assets.require_auth_context", lambda: mock_require_auth_account_2())
        
        resp = client.delete("/api/assets/1")  # Asset 1 belongs to account 1
        assert resp.status_code == 404, "Should return 404 (not 403) to avoid info leak"
        
        # Verify asset still exists
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM assets WHERE id = 1")
        row = cur.fetchone()
        conn.close()
        
        assert row is not None, "Asset should not be deleted by wrong account"


# ========================================================================
# RUN TESTS
# ========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
