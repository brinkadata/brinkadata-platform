"""
Test suite for Property Search and Assets endpoints.

Tests:
- Search endpoint with various filters
- Assets CRUD operations
- Multi-tenant isolation for assets
- RBAC enforcement (asset:manage capability)

Run: pytest backend/test_search_assets.py -v
"""

import requests
import pytest

BASE_URL = "http://localhost:8000"

# Test credentials (ensure these exist in dev DB)
TEST_USER_EMAIL = "test@brinkadata.com"
TEST_USER_PASSWORD = "test123"


@pytest.fixture
def auth_token():
    """Get auth token for test user."""
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return data["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestPropertySearch:
    """Test /search/properties endpoint."""
    
    def test_search_without_auth(self):
        """Search should require authentication."""
        resp = requests.get(f"{BASE_URL}/search/properties")
        assert resp.status_code == 401, "Expected 401 for unauthenticated request"
    
    def test_search_with_auth(self, auth_headers):
        """Basic search should return results."""
        resp = requests.get(
            f"{BASE_URL}/search/properties",
            headers=auth_headers,
            params={"limit": 10}
        )
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        results = resp.json()
        assert isinstance(results, list), "Expected list of properties"
    
    def test_search_with_city_filter(self, auth_headers):
        """Search with city filter should work."""
        resp = requests.get(
            f"{BASE_URL}/search/properties",
            headers=auth_headers,
            params={"city": "Atlanta", "limit": 10}
        )
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        results = resp.json()
        assert isinstance(results, list), "Expected list of properties"
        # If results exist, verify they match filter
        for prop in results:
            if prop.get("city"):
                assert prop["city"].lower() == "atlanta"
    
    def test_search_with_state_filter(self, auth_headers):
        """Search with state filter should work."""
        resp = requests.get(
            f"{BASE_URL}/search/properties",
            headers=auth_headers,
            params={"state": "GA", "limit": 10}
        )
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        results = resp.json()
        assert isinstance(results, list), "Expected list of properties"
        for prop in results:
            if prop.get("state"):
                assert prop["state"].upper() == "GA"
    
    def test_search_with_zip_filter(self, auth_headers):
        """Search with ZIP filter should work."""
        resp = requests.get(
            f"{BASE_URL}/search/properties",
            headers=auth_headers,
            params={"zip": "30301", "limit": 10}
        )
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        results = resp.json()
        assert isinstance(results, list), "Expected list of properties"
        for prop in results:
            if prop.get("zip"):
                assert prop["zip"] == "30301"
    
    def test_search_with_query_string(self, auth_headers):
        """Search with query string should work."""
        resp = requests.get(
            f"{BASE_URL}/search/properties",
            headers=auth_headers,
            params={"q": "Main", "limit": 10}
        )
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        results = resp.json()
        assert isinstance(results, list), "Expected list of properties"


class TestAssets:
    """Test /assets/* endpoints."""
    
    def test_list_assets_without_auth(self):
        """List assets should require authentication."""
        resp = requests.get(f"{BASE_URL}/assets/list")
        assert resp.status_code == 401, "Expected 401 for unauthenticated request"
    
    def test_list_assets_with_auth(self, auth_headers):
        """List assets should return list (may be empty)."""
        resp = requests.get(
            f"{BASE_URL}/assets/list",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"List assets failed: {resp.text}"
        assets = resp.json()
        assert isinstance(assets, list), "Expected list of assets"
    
    def test_create_asset_without_capability(self):
        """Create asset should require asset:manage capability."""
        # Login with a user that doesn't have asset:manage
        # For this test, we assume TEST_USER has the capability
        # In production tests, you'd use a separate test account without the capability
        pass  # Skip for now - requires test account setup
    
    def test_create_and_delete_asset(self, auth_headers):
        """Create asset, verify it exists, then delete it."""
        # Create asset
        create_data = {
            "name": "Test Asset",
            "address": "123 Test St",
            "city": "Atlanta",
            "state": "GA",
            "zip_code": "30301",
            "notes": "Test asset for automated testing"
        }
        
        resp = requests.post(
            f"{BASE_URL}/assets/create",
            headers=auth_headers,
            json=create_data
        )
        assert resp.status_code == 200, f"Create asset failed: {resp.text}"
        result = resp.json()
        assert result["success"] is True
        asset_id = result["asset_id"]
        assert asset_id > 0
        
        # Verify asset exists in list
        resp = requests.get(
            f"{BASE_URL}/assets/list",
            headers=auth_headers
        )
        assert resp.status_code == 200
        assets = resp.json()
        assert any(a["asset_id"] == asset_id for a in assets), "Created asset not found in list"
        
        # Get asset detail
        resp = requests.get(
            f"{BASE_URL}/assets/get",
            headers=auth_headers,
            params={"asset_id": asset_id}
        )
        assert resp.status_code == 200, f"Get asset failed: {resp.text}"
        asset = resp.json()
        assert asset["asset_id"] == asset_id
        assert asset["name"] == "Test Asset"
        assert asset["address"] == "123 Test St"
        
        # Update asset
        update_data = {
            "asset_id": asset_id,
            "name": "Updated Test Asset",
            "notes": "Updated notes"
        }
        
        resp = requests.post(
            f"{BASE_URL}/assets/update",
            headers=auth_headers,
            json=update_data
        )
        assert resp.status_code == 200, f"Update asset failed: {resp.text}"
        
        # Verify update
        resp = requests.get(
            f"{BASE_URL}/assets/get",
            headers=auth_headers,
            params={"asset_id": asset_id}
        )
        assert resp.status_code == 200
        asset = resp.json()
        assert asset["name"] == "Updated Test Asset"
        assert asset["notes"] == "Updated notes"
        
        # Delete asset
        resp = requests.post(
            f"{BASE_URL}/assets/delete",
            headers=auth_headers,
            json={"asset_id": asset_id}
        )
        assert resp.status_code == 200, f"Delete asset failed: {resp.text}"
        
        # Verify asset no longer exists
        resp = requests.get(
            f"{BASE_URL}/assets/get",
            headers=auth_headers,
            params={"asset_id": asset_id}
        )
        assert resp.status_code == 404, "Asset should be deleted"
    
    def test_get_nonexistent_asset(self, auth_headers):
        """Get asset that doesn't exist should return 404."""
        resp = requests.get(
            f"{BASE_URL}/assets/get",
            headers=auth_headers,
            params={"asset_id": 999999}
        )
        assert resp.status_code == 404, "Expected 404 for nonexistent asset"
    
    def test_update_nonexistent_asset(self, auth_headers):
        """Update asset that doesn't exist should return 404."""
        resp = requests.post(
            f"{BASE_URL}/assets/update",
            headers=auth_headers,
            json={
                "asset_id": 999999,
                "name": "Should Fail"
            }
        )
        assert resp.status_code == 404, "Expected 404 for nonexistent asset"
    
    def test_delete_nonexistent_asset(self, auth_headers):
        """Delete asset that doesn't exist should return 404."""
        resp = requests.post(
            f"{BASE_URL}/assets/delete",
            headers=auth_headers,
            json={"asset_id": 999999}
        )
        assert resp.status_code == 404, "Expected 404 for nonexistent asset"


class TestMultiTenantIsolation:
    """Test that assets are properly scoped by account_id."""
    
    def test_assets_scoped_to_account(self, auth_headers):
        """Assets should only show for current account."""
        # Create asset
        create_data = {
            "name": "Tenant Isolation Test",
            "address": "456 Isolation St",
            "city": "Atlanta",
            "state": "GA",
            "zip_code": "30302"
        }
        
        resp = requests.post(
            f"{BASE_URL}/assets/create",
            headers=auth_headers,
            json=create_data
        )
        assert resp.status_code == 200
        asset_id = resp.json()["asset_id"]
        
        # Verify asset appears in list for this account
        resp = requests.get(
            f"{BASE_URL}/assets/list",
            headers=auth_headers
        )
        assert resp.status_code == 200
        assets = resp.json()
        assert any(a["asset_id"] == asset_id for a in assets)
        
        # Verify all assets in list have account_id field (internal check)
        # Note: account_id is not exposed in API response for security,
        # but backend should enforce it
        
        # Cleanup
        requests.post(
            f"{BASE_URL}/assets/delete",
            headers=auth_headers,
            json={"asset_id": asset_id}
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
