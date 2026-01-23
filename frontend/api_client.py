"""
frontend/api_client.py
Centralized API client for all backend requests.

This module ensures:
1. All API calls automatically attach Authorization header when authenticated
2. Consistent error handling for 401/403 (session expiry)
3. Centralized API base URL configuration (dev/staging/prod)
4. No duplicate API logic scattered across the codebase
"""

import os
from typing import Any, Dict, Optional, Literal
import requests
import streamlit as st

# Import config (robust fallback for different run contexts)
try:
    from frontend.config import get_api_base_url, IS_DEV, ENV
except ModuleNotFoundError:
    from config import get_api_base_url, IS_DEV, ENV

# Import auth helpers
try:
    from frontend.auth import get_auth_header, clear_auth, is_authenticated
except ModuleNotFoundError:
    from auth import get_auth_header, clear_auth, is_authenticated


# Note: get_api_base_url is imported from config.py and re-exported for convenience
# This allows existing code to import it from api_client
__all__ = ["api_request", "get_api_base_url"]


def is_public_endpoint(path: str) -> bool:
    """
    Check if endpoint is public (doesn't require authentication).
    
    Public endpoints:
    - /auth/login
    - /auth/register
    - /auth/resume (uses resume_code, not Bearer token)
    
    All other endpoints are protected and require Authorization header.
    
    Args:
        path: API endpoint path (e.g., "/auth/login")
    
    Returns:
        True if public, False if protected
    """
    public_paths = ["/auth/login", "/auth/register", "/auth/resume"]
    return path in public_paths


def api_request(
    method: Literal["GET", "POST", "PUT", "DELETE"],
    path: str,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
    _retry: bool = True
) -> Optional[requests.Response]:
    """
    Make an API request with automatic auth header attachment and error handling.
    
    This is the ONLY function that should make backend API calls.
    
    Features:
    - Automatically attaches Authorization: Bearer <token> for protected endpoints
    - Handles 401 with automatic token refresh attempt (one retry max)
    - Handles 403 (insufficient permissions) consistently
    - Connection error handling with safe error messages (no token leakage)
    - Graceful timeout handling
    - Prevents infinite retry loops via _retry flag
    
    Security:
    - Never logs or prints tokens/auth headers
    - Sanitizes error messages to prevent credential exposure
    - Uses configured base URL with environment validation
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API endpoint path (e.g., "/property/analyze")
        json: JSON body for POST/PUT requests
        params: Query parameters for GET requests
        timeout: Request timeout in seconds (default: 20)
        _retry: Internal flag to prevent infinite retry loops (do not set manually)
    
    Returns:
        Response object if successful, None if connection error
    
    Raises:
        Does NOT raise exceptions - returns None on error and shows user-facing message
    """
    try:
        base_url = get_api_base_url()
    except RuntimeError as e:
        # Config error - backend URL not set properly
        st.error(f"⚙️ Configuration error: {str(e)}")
        return None
    
    url = f"{base_url}{path}"
    
    # Build headers
    headers = {"Accept": "application/json"}
    
    # Add Content-Type for JSON requests
    if json is not None:
        headers["Content-Type"] = "application/json"
    
    # Attach auth header for protected endpoints
    if not is_public_endpoint(path):
        auth_headers = get_auth_header()
        headers.update(auth_headers)
        
        # Security check: never proceed with protected endpoint if not authenticated
        if not auth_headers and not _retry:
            st.error("🔒 Authentication required. Please log in.")
            return None
    
    try:
        # Make request
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, json=json, headers=headers, params=params, timeout=timeout)
        elif method == "PUT":
            resp = requests.put(url, json=json, headers=headers, params=params, timeout=timeout)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, params=params, timeout=timeout)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        # Handle 401 Unauthorized with automatic token refresh
        if resp.status_code == 401 and _retry and not is_public_endpoint(path):
            if IS_DEV:
                print(f"[API] ⚠️  401 on {path}, attempting token refresh...")
            
            # Only attempt refresh if we actually have refresh credentials
            if st.session_state.get("refresh_token") and st.session_state.get("session_id"):
                # Try to refresh token
                if _try_refresh_token():
                    # Refresh succeeded - retry original request ONCE
                    if IS_DEV:
                        print(f"[API] 🔄 Retrying {path} with refreshed token...")
                    return api_request(method, path, json=json, params=params, timeout=timeout, _retry=False)
                else:
                    # Refresh failed - session is truly expired
                    if IS_DEV:
                        print("[API] ❌ Token refresh failed, session expired")
                    _handle_session_expired()
                    return None
            else:
                # No refresh token available - session is invalid
                if IS_DEV:
                    print("[API] ❌ No refresh token available, session invalid")
                _handle_session_expired()
                return None
        
        # Handle 403 Forbidden (insufficient permissions, no refresh needed)
        if resp.status_code == 403:
            if IS_DEV:
                print(f"[API] 403 Forbidden on {path}")
            st.error("⛔ You don't have permission to perform this action.")
            return resp  # Return response so caller can handle gracefully
        
        # Success or other error codes - return response for caller to handle
        return resp
        
    except requests.exceptions.Timeout:
        if IS_DEV:
            print(f"[API] Timeout on {method} {path}")
        st.error(f"⏱️ Request timed out after {timeout}s. Please try again.")
        _update_backend_status("timeout")
        return None
        
    except requests.exceptions.ConnectionError:
        if IS_DEV:
            print(f"[API] Connection error on {method} {path}")
        # Show configured backend URL (not full URL to avoid exposing paths)
        st.error(f"🔌 Cannot connect to backend at {base_url}. Please check your connection.")
        _update_backend_status("connection_error")
        return None
        
    except Exception as e:
        # Sanitize error message - never include URL params or headers
        error_msg = str(e)
        # Remove any bearer tokens from error messages (shouldn't happen but be safe)
        if "bearer" in error_msg.lower() or "authorization" in error_msg.lower():
            error_msg = "Authentication error (details hidden for security)"
        
        if IS_DEV:
            print(f"[API] Unexpected error on {method} {path}: {error_msg}")
        st.error(f"❌ Unexpected error: {error_msg[:100]}")
        _update_backend_status("error")
        return None


def _try_refresh_token() -> bool:
    """
    Attempt to refresh access token using refresh token.
    
    Internal helper - not intended for direct use.
    Security: Never logs tokens or sensitive data.
    
    Returns:
        True if refresh succeeded and new token stored, False otherwise
    """
    ss = st.session_state
    
    session_id = ss.get("session_id")
    refresh_token = ss.get("refresh_token")
    
    if not session_id or not refresh_token:
        if IS_DEV:
            print("[API] Cannot refresh: missing session_id or refresh_token")
        return False
    
    try:
        base_url = get_api_base_url()
        resp = requests.post(
            f"{base_url}/auth/refresh",
            json={"session_id": session_id, "refresh_token": refresh_token},
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            new_token = data.get("access_token")
            new_refresh = data.get("refresh_token")
            user_data = data.get("user", {})
            
            if new_token:
                # Update access token in session state
                ss["auth_token"] = new_token
                
                # Update refresh token if provided (rotation)
                if new_refresh:
                    ss["refresh_token"] = new_refresh
                
                # Update user data if provided
                if user_data:
                    ss["current_user"] = user_data
                    # Update canonical keys for convenience
                    ss["account_id"] = user_data.get("account_id")
                    ss["role"] = user_data.get("role")
                
                # Keep is_authenticated flag true
                ss["is_authenticated"] = True
                
                if IS_DEV:
                    print("[API] ✅ Token refresh successful")
                return True
            else:
                if IS_DEV:
                    print("[API] ❌ Token refresh response missing access_token")
        
        if IS_DEV:
            print(f"[API] ❌ Token refresh failed: HTTP {resp.status_code}")
        return False
        
    except Exception as e:
        if IS_DEV:
            # Never log the actual exception which might contain tokens
            print(f"[API] ❌ Token refresh error: {type(e).__name__}")
        return False


def _handle_session_expired() -> None:
    """
    Handle session expiry - clear auth and redirect to login.
    
    Internal helper - not intended for direct use.
    """
    st.warning("🔒 Your session has expired. Please log in again.")
    
    # Clear auth state using centralized helper
    clear_auth()
    
    # Set navigation to login page via deferred pattern
    st.session_state["_apply_payload"] = {
        "auth_token": None,
        "current_user": None,
        "session_id": None,
        "refresh_token": None,
    }
    st.session_state["_post_login_nav"] = "Login"
    
    # Rerun to apply changes
    st.rerun()


def _update_backend_status(status: str) -> None:
    """
    Update backend connection status in session state.
    
    Internal helper for connection health tracking.
    
    Args:
        status: "ok", "timeout", "connection_error", "error", etc.
    """
    import time
    ss = st.session_state
    
    ss["_backend_status"] = status
    ss["_backend_last_ping_time"] = time.time()
    
    if status != "ok":
        ss["_backend_was_down"] = True
