"""
frontend/auth.py
Centralized authentication state management for Brinkadata frontend.

WHY THIS MODULE EXISTS (Root Cause Analysis):
==============================================

The production login bug occurred because of THREE compounding issues:

1. STREAMLIT RERUN BEHAVIOR: Every user interaction triggers a full script rerun from top to bottom.
   Without explicit persistence, st.session_state keys can be lost or not properly initialized
   across reruns, especially when navigating between pages.

2. MULTIPAGE STATE DRIFT: The single-file app uses nav_page switching rather than true Streamlit
   multipage. Each page render function assumes auth state exists, but there was no guarantee
   that auth state was initialized at the TOP of every rerun cycle.

3. MISSING BEARER HEADER: Some API calls (especially on page navigation) didn't consistently
   attach the Authorization header, causing 401 responses even when auth_token existed in
   session_state.

THE FIX:
========

This module provides a SINGLE SOURCE OF TRUTH for auth state with:
- init_auth_state(): MUST be called at the top of main() to ensure keys exist on every rerun
- set_auth(): Atomically updates all auth-related keys when login succeeds
- clear_auth(): Safely wipes auth state on logout or session expiry
- require_auth(): Guards protected pages - stops execution if not authenticated
- get_auth_header(): Always returns correct Authorization header dict for API calls
- is_authenticated(): Simple boolean check without side effects

By calling init_auth_state() at the start of every rerun and using get_auth_header() for
every API call, we guarantee that:
1. Auth state persists across reruns (stored in st.session_state)
2. All pages see the same auth state (single source of truth)
3. All API calls include the Bearer token (consistent header attachment)

This eliminates the "login succeeds but pages don't see it" bug.
"""

from typing import Optional, Dict, Any
import streamlit as st


def init_auth_state() -> None:
    """
    Initialize authentication-related session state keys.
    
    MUST be called at the top of main() or each page entry point
    to ensure auth state exists on every Streamlit rerun.
    
    This is idempotent - safe to call multiple times.
    """
    ss = st.session_state
    
    # Core auth keys
    ss.setdefault("auth_token", None)
    ss.setdefault("refresh_token", None)
    ss.setdefault("session_id", None)
    ss.setdefault("current_user", None)
    ss.setdefault("is_authenticated", False)
    
    # Session rehydration guard (prevents protected calls before auth established)
    ss.setdefault("session_rehydrated", False)
    
    # Capabilities cache (plan, role, permissions)
    # Structure: {"plan": "pro", "role": "owner", "list": [...], "loaded_at": timestamp}
    ss.setdefault("capabilities", None)
    
    # Capability fetch status tracking
    ss.setdefault("_cap_fetch_status", "not_attempted")
    ss.setdefault("_cap_fetch_last_error", None)
    
    # Derived canonical keys (for backward compatibility with existing code)
    # These are populated by normalize_auth_context() in app.py
    ss.setdefault("account_id", None)
    ss.setdefault("role", None)
    ss.setdefault("plan", None)
    
    # Update is_authenticated flag based on token presence
    # This ensures the flag stays in sync with actual auth state
    if ss["auth_token"] and not ss["is_authenticated"]:
        ss["is_authenticated"] = True
    elif not ss["auth_token"] and ss["is_authenticated"]:
        ss["is_authenticated"] = False


def set_auth(
    auth_token: str,
    current_user: Dict[str, Any],
    session_id: str,
    refresh_token: str
) -> None:
    """
    Set authentication state after successful login/register/resume.
    
    This is the ONLY place that should write to auth-related session_state keys
    (except for clear_auth and token refresh logic).
    
    Args:
        auth_token: JWT access token (Bearer token for API calls)
        current_user: User object from backend (must include: id, email, account_id, role)
        session_id: Session UUID for refresh token rotation
        refresh_token: Long-lived refresh token for token renewal
    """
    ss = st.session_state
    
    ss["auth_token"] = auth_token
    ss["refresh_token"] = refresh_token
    ss["session_id"] = session_id
    ss["current_user"] = current_user
    ss["is_authenticated"] = True
    
    # Extract canonical keys from current_user for convenience
    # (These are also set by normalize_auth_context but we set them here for immediate availability)
    if isinstance(current_user, dict):
        ss["account_id"] = current_user.get("account_id")
        ss["role"] = current_user.get("role")
    
    # Mark session as rehydrated (allows protected API calls)
    ss["session_rehydrated"] = True


def clear_auth() -> None:
    """
    Clear all authentication state (logout or session expiry).
    
    Safe to call multiple times. Does not raise errors if keys already cleared.
    """
    ss = st.session_state
    
    # Core auth keys
    ss["auth_token"] = None
    ss["refresh_token"] = None
    ss["session_id"] = None
    ss["current_user"] = None
    ss["is_authenticated"] = False
    
    # Canonical keys
    ss["account_id"] = None
    ss["role"] = None
    ss["plan"] = None
    
    # Capabilities cache
    ss["capabilities"] = None
    ss["_cap_fetch_status"] = "not_attempted"
    ss["_cap_fetch_last_error"] = None
    
    # Reset rehydration guard
    ss["session_rehydrated"] = False


def is_authenticated() -> bool:
    """
    Check if user is currently authenticated.
    
    Returns:
        True if auth_token exists and is not None, False otherwise
    """
    return bool(st.session_state.get("auth_token"))


def get_current_user() -> Optional[Dict[str, Any]]:
    """
    Get current user object from session state.
    
    Returns:
        User dict if authenticated, None otherwise
    """
    return st.session_state.get("current_user")


def get_auth_header() -> Dict[str, str]:
    """
    Get Authorization header dict for API requests.
    
    This should be used by ALL API calls to protected endpoints.
    Automatically includes Bearer token if user is authenticated.
    
    Returns:
        {"Authorization": "Bearer <token>"} if authenticated, {} otherwise
    """
    token = st.session_state.get("auth_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def require_auth(redirect_to_login: bool = True) -> bool:
    """
    Guard for protected pages - stops execution if not authenticated.
    
    Usage at top of page render functions:
        if not require_auth():
            return  # Stop execution, user will see warning/redirect
    
    Args:
        redirect_to_login: If True, sets nav_page to "Login" when not authenticated
    
    Returns:
        True if authenticated (continue execution), False otherwise (execution should stop)
    """
    if not is_authenticated():
        st.warning("⚠️ You must be logged in to access this page.")
        
        if redirect_to_login:
            st.session_state["nav_page"] = "Login"
            st.info("Please log in to continue.")
        
        # Show login button for convenience
        if st.button("Go to Login", type="primary"):
            st.session_state["nav_page"] = "Login"
            st.rerun()
        
        return False
    
    return True


def get_account_id() -> Optional[int]:
    """
    Get current user's account_id.
    
    Returns:
        account_id if authenticated, None otherwise
    """
    user = get_current_user()
    if user and isinstance(user, dict):
        return user.get("account_id")
    
    # Fallback to top-level key (populated by normalize_auth_context)
    return st.session_state.get("account_id")


def get_role() -> Optional[str]:
    """
    Get current user's role.
    
    Returns:
        role string if authenticated, None otherwise
    """
    user = get_current_user()
    if user and isinstance(user, dict):
        return user.get("role")
    
    # Fallback to top-level key (populated by normalize_auth_context)
    return st.session_state.get("role")


def get_plan() -> Optional[str]:
    """
    Get current user's plan.
    
    Returns:
        plan string if capabilities loaded, None otherwise
    """
    caps = st.session_state.get("capabilities")
    if caps and isinstance(caps, dict):
        return caps.get("plan")
    
    # Fallback to top-level key (populated by normalize_auth_context)
    return st.session_state.get("plan")
