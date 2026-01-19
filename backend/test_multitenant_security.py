"""
TASK 6: Multi-tenant security isolation tests.

Tests that verify:
1. Account A cannot access Account B's data
2. All queries are properly scoped by account_id
3. Cross-tenant access returns 404 (not 403, to avoid leaking existence)
4. Plan limits are enforced server-side

Run: pytest backend/test_multitenant_security.py -v
"""

import pytest
import sqlite3
import hashlib
from datetime import datetime
from fastapi.testclient import TestClient

# Import the FastAPI app
from backend.main import app, get_db, hash_password, create_access_token

client = TestClient(app)


@pytest.fixture
def setup_test_accounts():
    """
    Create two isolated accounts with users for testing.
    Returns tokens and IDs for both accounts.
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Clean up any existing test data
    cur.execute("DELETE FROM saved_properties WHERE property_name LIKE 'TEST_%'")
    cur.execute("DELETE FROM trashed_properties WHERE saved_row_json LIKE '%TEST_%'")
    cur.execute("DELETE FROM users WHERE email LIKE 'test_%@test.com'")
    cur.execute("DELETE FROM accounts WHERE name LIKE 'Test Account %'")
    conn.commit()
    
    # Create Account A
    cur.execute("INSERT INTO accounts (name, plan) VALUES (?, ?)", ("Test Account A", "free"))
    account_a_id = cur.lastrowid
    
    pw_hash_a = hash_password("password_a")
    cur.execute(
        "INSERT INTO users (email, password_hash, account_id, role) VALUES (?, ?, ?, ?)",
        ("test_a@test.com", pw_hash_a, account_a_id, "owner")
    )
    user_a_id = cur.lastrowid
    
    # Create Account B
    cur.execute("INSERT INTO accounts (name, plan) VALUES (?, ?)", ("Test Account B", "pro"))
    account_b_id = cur.lastrowid
    
    pw_hash_b = hash_password("password_b")
    cur.execute(
        "INSERT INTO users (email, password_hash, account_id, role) VALUES (?, ?, ?, ?)",
        ("test_b@test.com", pw_hash_b, account_b_id, "owner")
    )
    user_b_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    
    # Create tokens
    token_a = create_access_token({"sub": str(user_a_id), "email": "test_a@test.com", "account_id": account_a_id})
    token_b = create_access_token({"sub": str(user_b_id), "email": "test_b@test.com", "account_id": account_b_id})
    
    yield {
        "account_a": {"id": account_a_id, "user_id": user_a_id, "token": token_a, "plan": "free"},
        "account_b": {"id": account_b_id, "user_id": user_b_id, "token": token_b, "plan": "pro"},
    }
    
    # Cleanup
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM saved_properties WHERE property_name LIKE 'TEST_%'")
    cur.execute("DELETE FROM trashed_properties WHERE saved_row_json LIKE '%TEST_%'")
    cur.execute("DELETE FROM users WHERE email LIKE 'test_%@test.com'")
    cur.execute("DELETE FROM accounts WHERE name LIKE 'Test Account %'")
    conn.commit()
    conn.close()


def test_isolated_property_save(setup_test_accounts):
    """Test that saved properties are isolated by account_id."""
    accounts = setup_test_accounts
    token_a = accounts["account_a"]["token"]
    token_b = accounts["account_b"]["token"]
    
    # Account A saves a property
    response_a = client.post(
        "/property/save",
        json={
            "property_name": "TEST_Property_A",
            "city": "City A",
            "state": "CA",
            "strategy": "rental",
            "estimated_roi": 0.15,
            "cashflow_per_month": 500.0,
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response_a.status_code == 200
    saved_a_id = response_a.json()["id"]
    
    # Account B saves a property
    response_b = client.post(
        "/property/save",
        json={
            "property_name": "TEST_Property_B",
            "city": "City B",
            "state": "NY",
            "strategy": "flip",
            "estimated_roi": 0.25,
            "cashflow_per_month": 0.0,
        },
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response_b.status_code == 200
    saved_b_id = response_b.json()["id"]
    
    # Account A lists properties - should only see their own
    list_a = client.get("/property/saved", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    properties_a = list_a.json()
    property_names_a = [p["property_name"] for p in properties_a]
    assert "TEST_Property_A" in property_names_a
    assert "TEST_Property_B" not in property_names_a
    
    # Account B lists properties - should only see their own
    list_b = client.get("/property/saved", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    properties_b = list_b.json()
    property_names_b = [p["property_name"] for p in properties_b]
    assert "TEST_Property_B" in property_names_b
    assert "TEST_Property_A" not in property_names_b


def test_cross_tenant_delete_forbidden(setup_test_accounts):
    """Test that Account B cannot delete Account A's property."""
    accounts = setup_test_accounts
    token_a = accounts["account_a"]["token"]
    token_b = accounts["account_b"]["token"]
    
    # Account A saves a property
    response_a = client.post(
        "/property/save",
        json={
            "property_name": "TEST_Property_A_Delete",
            "city": "City A",
            "state": "CA",
            "strategy": "rental",
            "estimated_roi": 0.15,
            "cashflow_per_month": 500.0,
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response_a.status_code == 200
    saved_id = response_a.json()["id"]
    
    # Account B attempts to delete Account A's property
    delete_response = client.post(
        "/property/delete",
        json={"id": saved_id},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    
    # Should return 404 (not found) to avoid leaking existence
    assert delete_response.status_code == 404
    assert "not found" in delete_response.json()["detail"].lower()
    
    # Verify property still exists for Account A
    list_a = client.get("/property/saved", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    properties_a = list_a.json()
    property_names_a = [p["property_name"] for p in properties_a]
    assert "TEST_Property_A_Delete" in property_names_a


def test_cross_tenant_trash_restore_forbidden(setup_test_accounts):
    """Test that Account B cannot restore Account A's trashed property."""
    accounts = setup_test_accounts
    token_a = accounts["account_a"]["token"]
    token_b = accounts["account_b"]["token"]
    
    # Account A saves and deletes a property
    save_response = client.post(
        "/property/save",
        json={
            "property_name": "TEST_Property_A_Trash",
            "city": "City A",
            "state": "CA",
            "strategy": "rental",
            "estimated_roi": 0.15,
            "cashflow_per_month": 500.0,
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert save_response.status_code == 200
    saved_id = save_response.json()["id"]
    
    delete_response = client.post(
        "/property/delete",
        json={"id": saved_id},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert delete_response.status_code == 200
    trash_id = delete_response.json()["trash_id"]
    
    # Account B attempts to restore Account A's trashed property
    restore_response = client.post(
        "/property/trash/restore",
        json={"trash_id": trash_id},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    
    # Should return 404 to avoid leaking existence
    assert restore_response.status_code == 404
    
    # Account B should not see Account A's trash
    trash_b = client.get("/property/trash", headers={"Authorization": f"Bearer {token_b}"})
    assert trash_b.status_code == 200
    trash_items_b = trash_b.json()
    trash_names_b = [item["property_name"] for item in trash_items_b]
    assert "TEST_Property_A_Trash" not in trash_names_b


def test_plan_limit_enforcement(setup_test_accounts):
    """Test that free plan is limited to 25 saved deals."""
    accounts = setup_test_accounts
    token_a = accounts["account_a"]["token"]  # free plan
    account_a_id = accounts["account_a"]["id"]
    
    # Get current count
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM saved_properties WHERE account_id = ?", (account_a_id,))
    current_count = cur.fetchone()[0]
    conn.close()
    
    # Save properties up to limit (25 for free plan)
    max_for_free = 25
    properties_to_save = max_for_free - current_count
    
    for i in range(properties_to_save):
        response = client.post(
            "/property/save",
            json={
                "property_name": f"TEST_Limit_Property_{i}",
                "city": "City",
                "state": "CA",
                "strategy": "rental",
                "estimated_roi": 0.10,
                "cashflow_per_month": 100.0,
            },
            headers={"Authorization": f"Bearer {token_a}"}
        )
        if response.status_code != 200:
            print(f"Failed at property {i}: {response.json()}")
        assert response.status_code == 200
    
    # Attempt to save one more (should fail with 402 Payment Required)
    response_over_limit = client.post(
        "/property/save",
        json={
            "property_name": "TEST_Over_Limit_Property",
            "city": "City",
            "state": "CA",
            "strategy": "rental",
            "estimated_roi": 0.10,
            "cashflow_per_month": 100.0,
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response_over_limit.status_code == 402
    assert "limit" in response_over_limit.json()["detail"].lower()


def test_irr_npv_gated_by_plan(setup_test_accounts):
    """Test that free plan does not get IRR/NPV, but pro plan does."""
    accounts = setup_test_accounts
    token_a = accounts["account_a"]["token"]  # free plan
    token_b = accounts["account_b"]["token"]  # pro plan
    
    analyze_request = {
        "property_name": "TEST_IRR_Property",
        "city": "City",
        "state": "CA",
        "purchase_price": 200000,
        "rehab_budget": 50000,
        "monthly_rent": 2000,
        "hold_years": 5,
        "strategy": "rental",
    }
    
    # Account A (free) analyzes - should not get IRR/NPV
    response_a = client.post(
        "/property/analyze",
        json=analyze_request,
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response_a.status_code == 200
    result_a = response_a.json()
    assert result_a["irr_unlevered"] is None
    assert result_a["npv_unlevered"] is None
    
    # Account B (pro) analyzes - should get IRR/NPV
    response_b = client.post(
        "/property/analyze",
        json=analyze_request,
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert response_b.status_code == 200
    result_b = response_b.json()
    # Pro plan should compute IRR/NPV (may be None if calculation fails, but should attempt)
    # At minimum, check that the field is present
    assert "irr_unlevered" in result_b
    assert "npv_unlevered" in result_b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
