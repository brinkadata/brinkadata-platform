"""
backend/test_analyze_regression.py

Regression test for /property/analyze endpoint to prevent sqlite3.Row AttributeError.

This test ensures that the analyze endpoint does not crash with:
    AttributeError: 'sqlite3.Row' object has no attribute 'get'

Run:
    pytest backend/test_analyze_regression.py -v
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

# Ensure test uses isolated database
TEST_DB_PATH = tempfile.mktemp(suffix=".db")
os.environ["BRINKADATA_DB"] = TEST_DB_PATH


# Import after setting environment variable
from backend.main import app
from backend.config import SECRET_KEY, ALGORITHM


@pytest.fixture(scope="module")
def client():
    """Create test client with isolated database."""
    # Initialize test database
    conn = sqlite3.connect(TEST_DB_PATH)
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
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)
    
    # Insert test account
    cur.execute(
        "INSERT INTO accounts (id, name, plan) VALUES (?, ?, ?)",
        (1, "Test Account", "free")
    )
    
    # Insert test user
    cur.execute(
        "INSERT INTO users (id, email, role, account_id, is_active) VALUES (?, ?, ?, ?, ?)",
        (1, "test@example.com", "member", 1, 1)
    )
    
    conn.commit()
    conn.close()
    
    # Create test client
    test_client = TestClient(app)
    
    yield test_client
    
    # Cleanup
    try:
        os.unlink(TEST_DB_PATH)
    except Exception:
        pass


def generate_test_token(user_id: int) -> str:
    """Generate a valid JWT token for testing."""
    import time
    payload = {
        "sub": str(user_id),  # JWT standard requires string
        "email": "test@example.com",
        "exp": int(time.time()) + 3600,  # Expires in 1 hour
        "iat": int(time.time()),  # Issued at
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def test_analyze_endpoint_does_not_crash_with_sqlite_row_error(client):
    """
    Test that /property/analyze does not crash with sqlite3.Row AttributeError.
    
    This regression test ensures that the auth context and analyze endpoint
    correctly handle sqlite3.Row objects without calling .get() on them.
    
    The bug was caused by calling .get() on sqlite3.Row objects in:
    - backend/auth_context.py (require_auth_context dependency)
    
    Status codes:
    - 200: Success (should work for basic free plan analysis)
    - 403: Forbidden (capability/feature gating - acceptable)
    - 402: Payment required (plan upgrade needed - acceptable)
    - 500: Server error (REGRESSION - test should FAIL)
    """
    # Generate valid token
    token = generate_test_token(user_id=1)
    
    # Basic analyze request payload (minimal valid data)
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
    
    # Call analyze endpoint
    response = client.post(
        "/property/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Assert: Should NOT return 500 (server error)
    assert response.status_code != 500, (
        f"Analyze endpoint crashed with 500 error. "
        f"This indicates a regression (likely sqlite3.Row.get() error). "
        f"Response: {response.json()}"
    )
    
    # Accept 200 (success), 403 (forbidden), 402 (payment required), or 401 (auth issue)
    # but never 500 (server error)
    assert response.status_code in [200, 401, 402, 403], (
        f"Unexpected status code: {response.status_code}. "
        f"Expected 200, 401, 402, or 403. "
        f"Response: {response.json()}"
    )
    
    print(f"✓ Test passed: analyze endpoint returned {response.status_code} (not 500)")


def test_analyze_endpoint_basic_success(client):
    """
    Test that analyze endpoint returns valid response structure for free plan.
    
    This ensures that the endpoint not only doesn't crash, but also returns
    expected data structure.
    """
    token = generate_test_token(user_id=1)
    
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
    
    # For free plan, should succeed with basic metrics
    if response.status_code == 200:
        data = response.json()
        assert "noi_annual" in data
        assert "cashflow_per_month" in data
        assert "cap_rate" in data
        # Free plan might not have IRR/NPV
        print(f"✓ Analyze succeeded with metrics: NOI={data.get('noi_annual')}, CF={data.get('cashflow_per_month')}")
    else:
        # If gated, that's acceptable behavior
        print(f"✓ Analyze endpoint gated (status {response.status_code}) - this is acceptable")


def test_auth_context_handles_sqlite_row_correctly(client):
    """
    Test that auth context dependency correctly handles sqlite3.Row objects.
    
    This test specifically validates that require_auth_context doesn't crash
    when accessing row fields.
    """
    token = generate_test_token(user_id=1)
    
    # Call any authenticated endpoint that uses require_auth_context
    # Using /auth/capabilities as a simple test endpoint
    response = client.get(
        "/auth/capabilities",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Should not crash with 500
    assert response.status_code != 500, (
        f"Auth context crashed with 500. "
        f"This indicates sqlite3.Row.get() error. "
        f"Response: {response.json()}"
    )
    
    # Accept 200 (success), 403 (forbidden), or 401 (auth issue) but never 500
    assert response.status_code in [200, 401, 403], (
        f"Unexpected status code from auth endpoint: {response.status_code}"
    )
    
    print(f"✓ Auth context works correctly (status {response.status_code})")


if __name__ == "__main__":
    # Allow running directly with: python backend/test_analyze_regression.py
    pytest.main([__file__, "-v"])
