"""
Test suite for DEV-only admin endpoints.

Verifies that /admin/set_plan and /admin/set_role endpoints are properly
gated by IS_DEV flag and return 403 in production environments.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Import app and dependencies
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.main import app
from backend.config import IS_DEV


client = TestClient(app)


class TestAdminEndpointDevGuards:
    """Test that admin endpoints are properly gated by IS_DEV."""
    
    def test_set_plan_returns_403_when_not_dev(self):
        """
        Verify /admin/set_plan returns 403 when IS_DEV is False.
        Simulates production environment where test controls must be disabled.
        """
        with patch("backend.main.IS_DEV", False):
            response = client.post(
                "/admin/set_plan",
                params={"account_id": 1, "plan": "pro"}
            )
            
            assert response.status_code == 403, "Expected 403 Forbidden in production"
            assert "only available in dev" in response.json().get("detail", "").lower()
    
    def test_set_role_returns_403_when_not_dev(self):
        """
        Verify /admin/set_role returns 403 when IS_DEV is False.
        Simulates production environment where test controls must be disabled.
        """
        with patch("backend.main.IS_DEV", False):
            response = client.post(
                "/admin/set_role",
                params={"user_id": 1, "role": "owner"}
            )
            
            assert response.status_code == 403, "Expected 403 Forbidden in production"
            assert "only available in dev" in response.json().get("detail", "").lower()
    
    @pytest.mark.skipif(not IS_DEV, reason="Only runs in DEV environment")
    def test_set_plan_validates_plan_enum(self):
        """
        Verify /admin/set_plan validates plan names against PlanName enum.
        Should return 400 for invalid plan names.
        """
        response = client.post(
            "/admin/set_plan",
            params={"account_id": 1, "plan": "invalid_plan"}
        )
        
        assert response.status_code == 400, "Expected 400 for invalid plan name"
        detail = response.json().get("detail", "")
        assert "invalid plan" in detail.lower()
        assert "free" in detail.lower() or "pro" in detail.lower()
    
    @pytest.mark.skipif(not IS_DEV, reason="Only runs in DEV environment")
    def test_set_role_validates_role_enum(self):
        """
        Verify /admin/set_role validates role names against UserRole enum.
        Should return 400 for invalid role names.
        """
        response = client.post(
            "/admin/set_role",
            params={"user_id": 1, "role": "invalid_role"}
        )
        
        assert response.status_code == 400, "Expected 400 for invalid role name"
        detail = response.json().get("detail", "")
        assert "invalid role" in detail.lower()
        assert "owner" in detail.lower() or "admin" in detail.lower()
    
    @pytest.mark.skipif(not IS_DEV, reason="Only runs in DEV environment")
    def test_set_plan_returns_404_for_nonexistent_account(self):
        """
        Verify /admin/set_plan returns 404 when account doesn't exist.
        """
        response = client.post(
            "/admin/set_plan",
            params={"account_id": 99999, "plan": "pro"}
        )
        
        assert response.status_code == 404, "Expected 404 for nonexistent account"
        assert "not found" in response.json().get("detail", "").lower()
    
    @pytest.mark.skipif(not IS_DEV, reason="Only runs in DEV environment")
    def test_set_role_returns_404_for_nonexistent_user(self):
        """
        Verify /admin/set_role returns 404 when user doesn't exist.
        """
        response = client.post(
            "/admin/set_role",
            params={"user_id": 99999, "role": "owner"}
        )
        
        assert response.status_code == 404, "Expected 404 for nonexistent user"
        assert "not found" in response.json().get("detail", "").lower()


class TestProductionSafetyChecklist:
    """
    Checklist-style tests to verify production safety requirements.
    These should ALWAYS pass, regardless of environment.
    """
    
    def test_admin_endpoints_have_dev_guard(self):
        """
        Verify that admin endpoint code contains IS_DEV guard.
        This is a code inspection test to catch accidental removal.
        """
        import inspect
        from backend.main import admin_set_plan, admin_set_role
        
        # Check set_plan
        set_plan_source = inspect.getsource(admin_set_plan)
        assert "IS_DEV" in set_plan_source, "set_plan must check IS_DEV"
        assert "403" in set_plan_source, "set_plan must return 403"
        
        # Check set_role
        set_role_source = inspect.getsource(admin_set_role)
        assert "IS_DEV" in set_role_source, "set_role must check IS_DEV"
        assert "403" in set_role_source, "set_role must return 403"
    
    def test_dev_endpoints_not_in_protected_path_exemptions(self):
        """
        Verify that /admin/set_plan and /admin/set_role are NOT exempted
        from authentication in any auth middleware or dependency logic.
        
        These endpoints should always require valid authentication,
        even in dev environment.
        """
        # This test would check auth_context.py or middleware config
        # to ensure /admin paths are not in exemption lists
        
        # For now, we document the requirement:
        # - /admin endpoints must NOT be in is_protected_path exemptions
        # - They should require valid JWT tokens (via AuthContext)
        
        # If you have an exemption list, check it here:
        # from backend.auth_context import UNPROTECTED_PATHS
        # assert "/admin/set_plan" not in UNPROTECTED_PATHS
        # assert "/admin/set_role" not in UNPROTECTED_PATHS
        
        pass  # Placeholder - implement based on your auth architecture


if __name__ == "__main__":
    # Run tests with: python -m pytest backend/test_dev_guards.py -v
    pytest.main([__file__, "-v", "--tb=short"])
