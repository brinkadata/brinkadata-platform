# frontend/app.py
# Brinkadata – Property Intelligence Analyzer + Portfolio
#
# Run from repo root: streamlit run frontend/app.py
# Or from frontend folder: streamlit run app.py

from __future__ import annotations

import math
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

# Import environment config (robust fallback for different run contexts)
try:
    from frontend.config import BACKEND_URL, IS_DEV, ENABLE_DEBUG_UI, RESUME_CODE_MINUTES, get_api_base_url, ENV, IS_LOCAL
except ModuleNotFoundError:
    from config import BACKEND_URL, IS_DEV, ENABLE_DEBUG_UI, RESUME_CODE_MINUTES, get_api_base_url, ENV, IS_LOCAL

# Import centralized auth state management
try:
    from frontend.auth import (
        init_auth_state, set_auth, clear_auth, is_authenticated,
        get_auth_header, require_auth, get_current_user,
        get_account_id, get_role, get_plan
    )
except ModuleNotFoundError:
    from auth import (
        init_auth_state, set_auth, clear_auth, is_authenticated,
        get_auth_header, require_auth, get_current_user,
        get_account_id, get_role, get_plan
    )

# Import centralized API client
try:
    from frontend.api_client import api_request
except ModuleNotFoundError:
    from api_client import api_request

# Import DEV-only observability tools
if IS_DEV:
    try:
        from frontend.dev_observability import (
            track_event, mark_key_set, snapshot_state, get_recent_events,
            clear_debug_history, export_snapshot_json
        )
    except ModuleNotFoundError:
        from dev_observability import (
            track_event, mark_key_set, snapshot_state, get_recent_events,
            clear_debug_history, export_snapshot_json
        )

# --------------------------------------------------------------------
# Custom CSS for theme
# --------------------------------------------------------------------

CUSTOM_CSS = """
<style>
/* Blue theme for all interactive elements */
.stButton > button {
    background-color: #1f77b4 !important;
    color: white !important;
    border: none !important;
}

.stButton > button:hover {
    background-color: #2e86c1 !important;
}

/* Radio buttons - navigation options */
.stRadio > div {
    color: #1f77b4 !important;
}

.stRadio > div > div > label > div {
    background-color: #1f77b4 !important;
    border-color: #1f77b4 !important;
}

.stRadio > div > div > label > div[data-baseweb="radio"] {
    background-color: #1f77b4 !important;
}

/* Checkboxes - Auto-run option */
.stCheckbox > div > div > label > div {
    background-color: #1f77b4 !important;
    border-color: #1f77b4 !important;
}

.stCheckbox > div > div > label > div[data-baseweb="checkbox"] {
    background-color: #1f77b4 !important;
}

/* Select boxes - Deal grades, Strategies, etc. */
.stSelectbox > div > div {
    border-color: #1f77b4 !important;
}

.stSelectbox > div > div:hover {
    border-color: #2e86c1 !important;
}

.stSelectbox > div > div > div {
    color: #1f77b4 !important;
}

/* Sliders */
.stSlider > div > div > div > div {
    background-color: #1f77b4 !important;
}

/* Progress bars */
.stProgress > div > div > div > div {
    background-color: #1f77b4 !important;
}

/* Radio button labels */
.stRadio label {
    color: #1f77b4 !important;
}

/* Checkbox labels */
.stCheckbox label {
    color: #1f77b4 !important;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------
# DEV Observability - Keys to track
# --------------------------------------------------------------------

KEYS_OF_INTEREST = [
    "nav_page",
    "_post_login_nav",
    "_apply_payload",
    "_apply_address_payload",
    "_refresh_portfolio_lists",
    "session_rehydrated",
    "current_user",
    "account_id",
    "plan",
    "role",
    "capabilities",
    "auth_token",
    "session_id",
    "_cap_fetch_status",
    "_cap_fetch_last_error",
]

# --------------------------------------------------------------------
# Config (now imported from config.py)
# --------------------------------------------------------------------

LOGO_PATH = "../Brink_1.jpg"  # in project root

# --------------------------------------------------------------------
# Portfolio Auto-Recovery Configuration
# --------------------------------------------------------------------

# Enable automatic recovery retry when backend is unreachable (Portfolio page only)
PORTFOLIO_RECOVERY_ENABLED = True

# Auto-refresh interval in milliseconds (2 seconds = 2000ms)
PORTFOLIO_RECOVERY_INTERVAL_MS = 2000

# Maximum recovery attempts before stopping auto-refresh
PORTFOLIO_RECOVERY_MAX_ATTEMPTS = 10

# --------------------------------------------------------------------
# State helpers
# --------------------------------------------------------------------


def init_state() -> None:
    ss = st.session_state

    # Initialize auth state FIRST using centralized module
    # This ensures auth keys are properly initialized on every rerun
    init_auth_state()
    
    # Navigation - DO NOT set default here; will be set intelligently in main() based on auth state
    # This prevents the bug where logged-out users see Analyzer with "must be logged in" message
    ss.setdefault("nav_page", None)

    # Behavior
    ss.setdefault("auto_run_after_load", True)

    # Core analysis state
    ss.setdefault("analysis_inputs", None)
    ss.setdefault("analysis_result", None)
    ss.setdefault("loaded_from_portfolio", False)
    ss.setdefault("previous_inputs", None)

    # Presets + market context
    ss.setdefault("selected_preset", "None")
    ss.setdefault("zip_code", "")

    # Thresholds (for legends + future scoring panel)
    ss.setdefault(
        "thresholds",
        {
            "roi_good": 0.15,
            "roi_ok": 0.10,
            "cap_rate_good": 0.07,
            "cap_rate_ok": 0.05,
            "coc_good": 0.08,
            "coc_ok": 0.06,
            "dscr_safe": 1.25,
            "dscr_min": 1.1,
        },
    )
    
    # Portfolio auto-recovery state (timer-based retry when backend unreachable)
    ss.setdefault("_portfolio_recovery_active", False)
    ss.setdefault("_portfolio_recovery_attempts", 0)
    ss.setdefault("_portfolio_recovery_last_attempt_ts", 0.0)
    
    # Backend connection status tracking (interaction-driven)
    ss.setdefault("_backend_status", "unknown")  # "ok", "unreachable", "unknown"
    ss.setdefault("_backend_last_error_time", 0.0)
    ss.setdefault("_backend_was_down", False)  # Track if backend was previously down for reconnection message
    ss.setdefault("_backend_last_ping_time", 0.0)  # Throttle pings
    ss.setdefault("_force_backend_ping", False)  # Force ping on retry button


init_state()

ss = st.session_state

# --------------------------------------------------------------------
# Navigation helper (single source of truth)
# --------------------------------------------------------------------

def go_to(page: str) -> None:
    """
    Deterministic navigation helper - SINGLE SOURCE OF TRUTH for page changes.
    
    Sets ss["nav_page"] and immediately triggers st.rerun().
    This is the ONLY function that should be used for navigation.
    
    Args:
        page: Target page name ("Login", "Analyzer", "Portfolio", etc.)
    """
    st.session_state["nav_page"] = page
    st.rerun()

# --------------------------------------------------------------------
# Debug helpers
# --------------------------------------------------------------------

def set_debug_cause(cause: str) -> None:
    """Set one-time cause tag for state change debugging."""
    st.session_state["_debug_cause"] = cause

def pop_debug_cause(default: str = "unknown") -> str:
    """Get and clear the cause tag (single-use consumption)."""
    return st.session_state.pop("_debug_cause", default)

# --------------------------------------------------------------------
# Backend Status Ping
# --------------------------------------------------------------------

def should_ping_backend() -> bool:
    """Check if we should ping backend to update status."""
    import time
    
    # Always ping if forced (retry button)
    if ss.get("_force_backend_ping"):
        return True
    
    # Check if status is stale/unknown
    backend_status = ss.get("_backend_status", "unknown")
    if backend_status == "unknown":
        return True
    
    # Throttle: only ping if last ping was > 3 seconds ago
    last_ping = ss.get("_backend_last_ping_time", 0.0)
    now = time.time()
    if now - last_ping < 3.0:
        return False
    
    return True

def ping_backend_if_needed() -> None:
    """Lightweight backend ping to update connection status."""
    import time
    
    if not should_ping_backend():
        return
    
    # Clear force flag if set
    ss.pop("_force_backend_ping", None)
    
    # Update last ping time
    ss["_backend_last_ping_time"] = time.time()
    
    # Ping a cheap endpoint (don't need response, just want to update health tracking)
    # Use /account/info if authenticated, otherwise just mark as needs auth
    if not is_logged_in():
        # Not authenticated - skip ping (status will be "unknown" which is fine)
        return
    
    # Make lightweight ping call using tracked wrapper (updates API health automatically)
    _ = api_request("GET", "/account/info", timeout=5)
    # Status is now updated via call_backend_tracked

def is_backend_unreachable() -> bool:
    """Check if backend is currently unreachable based on API health."""
    # Check API health for any no_response status
    api_health = ss.get("_api_health", {})
    for endpoint_data in api_health.values():
        status = endpoint_data.get("status", "unknown")
        if status == "no_response":
            return True
    
    # Also check global backend status
    backend_status = ss.get("_backend_status", "unknown")
    if backend_status == "unreachable":
        return True
    
    return False

def mark_backend_connected() -> None:
    """Mark backend as connected - clears all error states."""
    import time
    
    # Clear global backend status
    ss["_backend_status"] = "ok"
    ss["_backend_was_down"] = False
    ss["_backend_last_ping_time"] = time.time()
    
    # Clear stale "no_response" statuses from API health
    # This prevents is_backend_unreachable() from returning True due to old data
    api_health = ss.get("_api_health", {})
    for endpoint, data in api_health.items():
        if data.get("status") == "no_response":
            # Don't delete, just mark as unknown to avoid false positives
            data["status"] = "unknown"

def mark_backend_unreachable(err_msg: Optional[str] = None) -> None:
    """Mark backend as unreachable."""
    import time
    
    ss["_backend_status"] = "unreachable"
    ss["_backend_last_ping_time"] = time.time()
    if err_msg and IS_DEV:
        print(f"[BACKEND] Unreachable: {err_msg[:80]}")

# --------------------------------------------------------------------
# API Health Tracking (State Observability v2 - Phase 2)
# --------------------------------------------------------------------

def _api_health_init(ss: dict) -> None:
    """Initialize API health registry if not present."""
    if "_api_health" not in ss:
        ss["_api_health"] = {}

def _api_health_set(
    ss: dict,
    endpoint: str,
    status: str,
    http_status: Optional[int] = None,
    err: Optional[str] = None
) -> None:
    """
    Update API health status for an endpoint.
    
    Args:
        ss: Session state dict
        endpoint: Endpoint path (e.g., "/account/info")
        status: "ok" | "error" | "no_response" | "not_authenticated" | "throttled"
        http_status: HTTP status code if available
        err: Short error message (sanitized, no PII)
    """
    import time
    _api_health_init(ss)
    
    health = ss["_api_health"]
    old_status = None
    
    if endpoint not in health:
        health[endpoint] = {
            "status": status,
            "last_ts": time.time(),
            "last_error": err,
            "count_ok": 1 if status == "ok" else 0,
            "count_err": 0 if status == "ok" else 1,
            "last_http_status": http_status,
            "prev_status": None  # Track previous status for transition detection
        }
    else:
        entry = health[endpoint]
        old_status = entry.get("status")
        entry["prev_status"] = old_status  # Store previous before updating
        entry["status"] = status
        entry["last_ts"] = time.time()
        entry["last_error"] = err
        entry["last_http_status"] = http_status
        if status == "ok":
            entry["count_ok"] = entry.get("count_ok", 0) + 1
        else:
            entry["count_err"] = entry.get("count_err", 0) + 1
    
    # Detect recovery transition and handle auto-refresh
    if old_status and old_status != status:
        handle_api_health_transition(ss, endpoint, old_status, status)
    
    # Track status change event
    if IS_DEV and 'track_event' in globals():
        track_event(ss, "api_health_update", {
            "endpoint": endpoint,
            "status": status,
            "http_status": http_status,
            "prev_status": old_status
        })

def _api_health_snapshot(ss: dict) -> dict:
    """Get safe snapshot of API health for display."""
    _api_health_init(ss)
    health = ss["_api_health"]
    
    # Return copy with human-readable timestamps
    import time
    snapshot = {}
    for endpoint, data in health.items():
        last_ts = data.get("last_ts", 0)
        age_seconds = int(time.time() - last_ts) if last_ts else 999999
        
        # Format age as human-readable
        if age_seconds < 60:
            age_str = f"{age_seconds}s ago"
        elif age_seconds < 3600:
            age_str = f"{age_seconds // 60}m ago"
        else:
            age_str = f"{age_seconds // 3600}h ago"
        
        snapshot[endpoint] = {
            "status": data.get("status", "unknown"),
            "age": age_str,
            "ok_count": data.get("count_ok", 0),
            "err_count": data.get("count_err", 0),
            "last_error": data.get("last_error", "none"),
            "http_status": data.get("last_http_status")
        }
    
    return snapshot

def handle_api_health_transition(ss: dict, endpoint: str, old_status: str, new_status: str) -> None:
    """
    Handle API health status transitions and trigger appropriate recovery actions.
    
    Recovery detection: When endpoint transitions from failure state to "ok",
    set page-aware deferred refresh flags for ONE-SHOT auto-refresh.
    
    Args:
        ss: Session state dict
        endpoint: API endpoint (e.g., "/property/saved")
        old_status: Previous status ("no_response", "error", etc.)
        new_status: Current status ("ok", etc.)
    """
    # Only trigger recovery actions if transitioning TO "ok" FROM a failure state
    if new_status != "ok":
        return
    
    if old_status in ("no_response", "error", "not_authenticated"):
        # Recovery detected!
        if IS_DEV and 'track_event' in globals():
            track_event(ss, "backend_recovered", {
                "endpoint": endpoint,
                "old_status": old_status,
                "new_status": new_status
            })
        
        # Page-aware refresh logic
        nav_page = ss.get("nav_page", "")
        
        # Portfolio page: Refresh if saved/trash endpoint recovered
        if nav_page == "Portfolio" and endpoint in ("/property/saved", "/property/trash"):
            ss["_refresh_portfolio_lists"] = True
            ss["_post_recovery_rerun"] = True
            if IS_DEV:
                print(f"[RECOVERY] Portfolio auto-refresh triggered for {endpoint}")
        
        # Analyzer page: Refresh if analyze endpoint recovered
        # (Currently analyzer doesn't have persistent data to refresh,
        # but we still trigger rerun to clear error banners)
        elif nav_page == "Analyzer" and endpoint in ("/property/analyze", "/market/lookup"):
            ss["_post_recovery_rerun"] = True
            if IS_DEV:
                print(f"[RECOVERY] Analyzer rerun triggered for {endpoint}")
        
        # Generic: Any other page, just trigger rerun to clear error states
        elif endpoint in ("/account/info", "/scenario/list"):
            ss["_post_recovery_rerun"] = True
            if IS_DEV:
                print(f"[RECOVERY] Generic rerun triggered for {endpoint}")

def _api_log_throttled(endpoint: str, message: str, throttle_seconds: int = 15) -> None:
    """Log API error with per-endpoint throttling."""
    if not IS_DEV:
        return
    
    import time
    ss = st.session_state
    
    # Per-endpoint throttle state
    throttle_key = f"_api_log_throttle_{endpoint.replace('/', '_')}"
    last_log_ts = ss.get(throttle_key, 0)
    now = time.time()
    
    if (now - last_log_ts) >= throttle_seconds:
        print(f"[API] {endpoint}: {message}")
        ss[throttle_key] = now

# --------------------------------------------------------------------
# Capability helpers
# --------------------------------------------------------------------


def fetch_and_cache_capabilities() -> bool:
    """
    Fetch capabilities from backend and cache in session_state.
    Should be called once after successful login/resume.
    
    Returns:
        True if successful, False otherwise
    """
    import time
    
    # Check if authenticated first
    if not ss.get("auth_token"):
        _set_cap_status("not_authenticated", "No auth token")
        return False
    
    try:
        resp = api_request("GET", "/auth/capabilities", timeout=10)
        if resp and resp.status_code == 200:
            data = resp.json()
            ss["capabilities"] = {
                "plan": data.get("plan", "free"),
                "role": data.get("role", "member"),
                "list": data.get("capabilities", []),
                "loaded_at": time.time()
            }
            _set_cap_status("ok", None)
            if IS_DEV:
                print(f"[CAPABILITIES] Cached: plan={ss['capabilities']['plan']}, "
                      f"role={ss['capabilities']['role']}, "
                      f"capabilities={len(ss['capabilities']['list'])}")
            return True
        elif resp and resp.status_code in [401, 403]:
            _set_cap_status("auth_failed", f"HTTP {resp.status_code}")
            _log_cap_error(f"Auth failed: {resp.status_code}")
            if "capabilities" in ss:
                del ss["capabilities"]
            return False
        elif resp and resp.status_code >= 500:
            _set_cap_status("backend_error", f"HTTP {resp.status_code}")
            _log_cap_error(f"Backend error: {resp.status_code}")
            if "capabilities" in ss:
                del ss["capabilities"]
            return False
        else:
            _set_cap_status("backend_unreachable", "No response")
            _log_cap_error("No response from backend")
            if "capabilities" in ss:
                del ss["capabilities"]
            return False
    except requests.exceptions.Timeout:
        _set_cap_status("backend_unreachable", "Timeout")
        _log_cap_error("Request timeout")
        if "capabilities" in ss:
            del ss["capabilities"]
        return False
    except requests.exceptions.ConnectionError:
        _set_cap_status("backend_unreachable", "Connection failed")
        _log_cap_error("Connection error")
        if "capabilities" in ss:
            del ss["capabilities"]
        return False
    except Exception as e:
        _set_cap_status("backend_error", str(e)[:50])
        _log_cap_error(f"Error: {str(e)[:50]}")
        if "capabilities" in ss:
            del ss["capabilities"]
        return False


def _set_cap_status(status: str, error: Optional[str]) -> None:
    """Set capabilities fetch status and track changes for observability."""
    old_status = ss.get("_cap_fetch_status")
    ss["_cap_fetch_status"] = status
    ss["_cap_fetch_last_error"] = error
    
    # Track status change event
    if old_status != status and IS_DEV and 'track_event' in globals():
        track_event(ss, "capabilities_fetch_status", {
            "status": status,
            "changed": True,
            "old_status": old_status
        })


def _log_cap_error(message: str) -> None:
    """Log capability fetch error with throttling (max 3 times, once per 15 seconds)."""
    if not IS_DEV:
        return
    
    import time
    now = time.time()
    last_warn_ts = ss.get("_cap_fetch_last_warn_ts", 0)
    warn_count = ss.get("_cap_fetch_warn_count", 0)
    
    # Throttle: max once every 15 seconds, max 3 times per session
    if (now - last_warn_ts) >= 15 and warn_count < 3:
        print(f"[CAPABILITIES] {message}")
        ss["_cap_fetch_last_warn_ts"] = now
        ss["_cap_fetch_warn_count"] = warn_count + 1


def can(capability: str) -> bool:
    """
    Check if current user has a specific capability.
    
    Safe to call from anywhere - returns False if not logged in or capability missing.
    Auto-hydrates capabilities on first call if user is authenticated but caps not loaded.
    
    Args:
        capability: Capability string to check (e.g., "asset:manage")
    
    Returns:
        True if user has the capability, False otherwise
    """
    # If not logged in, no capabilities
    if not is_logged_in():
        return False
    
    caps = ss.get("capabilities")
    
    # Auto-hydrate capabilities if missing for authenticated user
    # This prevents false negatives when user is logged in but caps not loaded yet
    if not caps or not isinstance(caps, dict):
        # Only try once per session to avoid infinite loops
        if not ss.get("_capabilities_fetch_attempted"):
            ss["_capabilities_fetch_attempted"] = True
            if IS_DEV:
                print(f"[CAPABILITIES] Auto-hydrating for authenticated user")
            # Try to fetch capabilities synchronously
            # Note: This should ideally be called proactively after login/resume,
            # but this provides a safety net
            if fetch_and_cache_capabilities():
                caps = ss.get("capabilities")
            else:
                # Failed to fetch - return False (safe default)
                return False
        else:
            # Already attempted fetch, still missing - return False
            return False
    
    cap_list = caps.get("list", [])
    return capability in cap_list


def normalize_auth_context() -> None:
    """
    Normalize canonical auth keys from authenticated sources.
    
    Ensures top-level session_state keys are always present when authenticated:
    - account_id (from current_user)
    - role (from current_user or capabilities)
    - plan (from capabilities)
    
    This eliminates ambiguity across pages and prevents regressions from missing keys.
    Only extracts values from already-authenticated sources - never invents data.
    
    Called after:
    - _apply_payload is processed (auth token/current_user set)
    - Capabilities are hydrated
    
    Safe to call multiple times - uses setdefault to avoid overwriting.
    """
    # Track what we actually set (for signal-only logging)
    actually_set = []
    
    # Extract from current_user (authoritative for account_id and role)
    current_user = ss.get("current_user")
    if current_user and isinstance(current_user, dict):
        if "account_id" in current_user and "account_id" not in ss:
            ss["account_id"] = current_user["account_id"]
            actually_set.append("account_id")
        if "role" in current_user and "role" not in ss:
            ss["role"] = current_user["role"]
            actually_set.append("role")
    
    # Extract from capabilities (authoritative for plan, backup for role)
    capabilities = ss.get("capabilities")
    if capabilities and isinstance(capabilities, dict):
        if "plan" in capabilities and "plan" not in ss:
            ss["plan"] = capabilities["plan"]
            actually_set.append("plan")
        # Backup: if role still missing but present in capabilities
        if "role" in capabilities and "role" not in ss:
            ss["role"] = capabilities["role"]
            actually_set.append("role_from_cap")
    
    # Track normalization ONLY if we actually set something (signal-only, no noise)
    if IS_DEV and 'track_event' in globals() and actually_set:
        track_event(ss, "auth_context_normalized", {"set": actually_set})


def apply_pending_actions() -> bool:
    """
    Centralized handler for all deferred actions that must execute BEFORE widgets are created.
    
    This prevents Streamlit widget-key ownership conflicts by ensuring session_state is
    populated with correct values before widget instantiation.
    
    Execution order (strict):
        0. _post_recovery_rerun: Backend recovery auto-refresh (SAFE rerun before widgets)
        1. _apply_payload: Auth/session data from login/register/resume
        2. _post_login_nav: Navigation redirect after successful auth
        3. _apply_address_payload: Analyzer address field prefill
        4. _refresh_portfolio_lists: Trigger portfolio/trash list refresh
        5. normalize_auth_context: Ensure canonical auth keys are present
    
    Returns:
        True if any action was applied (caller should st.rerun() once)
    
    Why this works:
        - Widgets in Streamlit "own" their session_state key once instantiated in a run.
        - Writing to a widget-owned key after the widget is created raises errors or is ignored.
        - This function runs at the TOP of main(), before render_sidebar() or any page render.
        - All deferred actions set widget-owned keys here, then we rerun ONCE so the next
          run creates widgets with correct session_state already populated.
        - Infinite rerun prevention: Each action is popped (consumed) on first application.
    
    Fixes:
        - Login/resume navigation stuck on Login page
        - ZIP code not auto-filling in Analyzer
        - Restore from trash not refreshing until manual navigation
        - Success message flicker after resume
        - Backend recovery not refreshing data until navigation away/back
    """
    applied_any = False
    applied_keys = []
    
    # 0. Handle backend recovery rerun (SAFE: before any widgets)
    # This flag is set by handle_api_health_transition when endpoint recovers (no_response -> ok)
    if ss.get("_post_recovery_rerun"):
        ss.pop("_post_recovery_rerun")
        applied_any = True
        applied_keys.append("_post_recovery_rerun")
        if IS_DEV:
            print("[DEFERRED] Backend recovery rerun")
    
    # 1. Apply auth payload (from login/register/resume OR token refresh)
    if ss.get("_apply_payload"):
        payload = ss.pop("_apply_payload")  # Pop to consume it
        
        # Check if this is an auth operation (has all required auth fields)
        if all(k in payload for k in ["auth_token", "current_user", "session_id", "refresh_token"]):
            # Use centralized set_auth to ensure proper state management
            set_auth(
                payload["auth_token"],
                payload["current_user"],
                payload["session_id"],
                payload["refresh_token"]
            )
        else:
            # Partial update (e.g., logout/clear) - apply individual keys
            if "auth_token" in payload:
                ss["auth_token"] = payload["auth_token"]
            if "current_user" in payload:
                ss["current_user"] = payload["current_user"]
            if "session_id" in payload:
                ss["session_id"] = payload["session_id"]
            if "refresh_token" in payload:
                ss["refresh_token"] = payload["refresh_token"]
        
        applied_any = True
        applied_keys.append("_apply_payload")
        if IS_DEV:
            print("[DEFERRED] Applied auth payload")
    
    # 2. Apply navigation redirect (after successful login/resume)
    if ss.get("_post_login_nav"):
        target_page = ss.pop("_post_login_nav")  # Pop removes it permanently
        ss["nav_page"] = target_page
        applied_any = True
        applied_keys.append("_post_login_nav")
        if IS_DEV:
            print(f"[DEFERRED] Navigation redirect to {target_page}")
    
    # 3. Apply address payload (from preset selection or scenario load)
    if ss.get("_apply_address_payload"):
        addr_payload = ss.pop("_apply_address_payload")
        # Write to the ACTUAL widget keys
        if "property_name" in addr_payload:
            ss["property_name"] = addr_payload["property_name"]
        if "city" in addr_payload:
            ss["city"] = addr_payload["city"]
        if "state" in addr_payload:
            ss["state"] = addr_payload["state"]
        if "zip_code" in addr_payload:
            # Write to BOTH ZIP widget keys:
            # - zip_code_property: Analyzer widget (line ~1035)
            # - zip_code: Sidebar market context widget (line ~836)
            ss["zip_code_property"] = addr_payload["zip_code"]
            ss["zip_code"] = addr_payload["zip_code"]
        applied_any = True
        applied_keys.append("_apply_address_payload")
        if IS_DEV:
            print("[DEFERRED] Applied address payload")
    
    # 4. Handle list refresh flag (after restore from trash)
    if ss.get("_refresh_portfolio_lists"):
        ss.pop("_refresh_portfolio_lists")
        # Clear any cached portfolio/trash data
        # Next render will re-fetch from backend automatically
        applied_any = True
        applied_keys.append("_refresh_portfolio_lists")
        if IS_DEV:
            print("[DEFERRED] Portfolio lists will refresh")
    
    # 5. Normalize auth context (ensure canonical keys are present)
    # This runs after _apply_payload is processed and ensures top-level
    # account_id/role/plan keys are always available when authenticated.
    # Safe to call even if not authenticated - it only extracts from existing data.
    normalize_auth_context()
    
    # Track deferred key application for debugging
    if applied_any and IS_DEV and 'track_event' in globals():
        track_event(ss, "deferred_keys_applied", {"keys": applied_keys})
    
    return applied_any


# --------------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------------


def format_money(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"${value:,.0f}"


def format_pct(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value * 100:.1f}%"


def safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    val = d.get(key, default)
    if isinstance(val, float) and math.isnan(val):
        return default
    return val


def is_logged_in() -> bool:
    """Check if user is authenticated.
    
    DEPRECATED: Use is_authenticated() from frontend.auth instead.
    Kept for backward compatibility with existing code.
    """
    return is_authenticated()


# --------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------

PRESET_DEALS: Dict[str, Dict[str, Any]] = {
    "Balanced rental (baseline)": {
        "property_name": "123 Main St",
        "city": "Baltimore",
        "state": "MD",
        "zip_code": "21207",
        "purchase_price": 220000.0,
        "rehab_budget": 30000.0,
        "monthly_rent": 2200.0,
        "hold_years": 5.0,
        "strategy": "rental",
        "investor_profile": "balanced",
    },
    "Aggressive BRRRR": {
        "property_name": "Value-add BRRRR",
        "city": "Baltimore",
        "state": "MD",
        "zip_code": "21207",
        "purchase_price": 200000.0,
        "rehab_budget": 60000.0,
        "monthly_rent": 2500.0,
        "hold_years": 2.0,
        "strategy": "BRRRR",
        "investor_profile": "aggressive",
    },
    "Conservative rental": {
        "property_name": "Stable rental",
        "city": "Baltimore",
        "state": "MD",
        "zip_code": "21228",
        "purchase_price": 260000.0,
        "rehab_budget": 15000.0,
        "monthly_rent": 2100.0,
        "hold_years": 7.0,
        "strategy": "rental",
        "investor_profile": "conservative",
    },
}


def apply_preset(preset_name: str) -> None:
    """Apply preset deal values to session state using deferred payload pattern."""
    if preset_name == "None":
        return
    preset = PRESET_DEALS.get(preset_name)
    if not preset:
        return

    # TASK B Fix: Use deferred pattern to apply address fields BEFORE widgets are created
    # This prevents widget key conflicts and ensures ZIP populates correctly
    ss["_apply_address_payload"] = preset.copy()
    if IS_DEV and 'mark_key_set' in globals():
        mark_key_set(ss, "_apply_address_payload", "preset_selection")
        track_event(ss, "preset_applied", {"preset": preset_name})
    
    # Mark cause for state change tracking
    set_debug_cause("preset")
    
    # Clear analysis state when switching presets
    ss["analysis_inputs"] = None
    ss["analysis_result"] = None
    ss["loaded_from_portfolio"] = False
    
    st.rerun()  # Rerun so main() can apply payload before widgets instantiate


# --------------------------------------------------------------------
# Layout helpers
# --------------------------------------------------------------------


def render_header() -> None:
    cols = st.columns([1, 6])
    with cols[0]:
        try:
            st.image(LOGO_PATH, width='stretch')
        except Exception:
            st.write("💠 Brinkadata")
    with cols[1]:
        st.title("Brinkadata — Property Intelligence Analyzer")
        st.caption(
            "Turn any rental, flip, or BRRRR into clear grades, ROI metrics, and portfolio insights."
        )


def render_sidebar() -> None:
    with st.sidebar:
        # Logo (small)
        try:
            st.image(LOGO_PATH, width='stretch')
        except Exception:
            st.write("Brinkadata")
        
        # Backend API status indicator
        if is_backend_unreachable():
            st.error("⚠️ Backend unreachable")
            if st.button("🔄 Retry Connection", use_container_width=True, key="retry_connection_btn"):
                # Clear error state, force ping, and trigger rerun
                ss["_backend_status"] = "unknown"
                ss["_backend_was_down"] = True
                ss["_force_backend_ping"] = True
                st.rerun()
        elif ss.get("_backend_status") == "ok":
            st.success("✅ Connected")
        # Don't show anything for "unknown" (initial state)
        
        # Auth Debug Section (always visible - production-safe)
        st.markdown("---")
        st.markdown("### 🔐 Auth Status")
        
        # Show configured API base URL
        try:
            api_base = get_api_base_url()
            # Mask full URL in production - just show domain
            if IS_LOCAL:
                st.caption(f"**API:** {api_base}")
            else:
                # Show just the domain in production
                from urllib.parse import urlparse
                parsed = urlparse(api_base)
                domain = parsed.netloc or parsed.path.split('/')[0]
                st.caption(f"**API:** {domain}")
            st.caption(f"**Environment:** {ENV}")
        except Exception as e:
            st.error(f"⚠️ API config error: {str(e)[:60]}")
        
        # Auth token presence (never show actual token)
        has_token = bool(st.session_state.get("auth_token"))
        if has_token:
            st.caption("**Auth token:** ✅ Present")
        else:
            st.caption("**Auth token:** ❌ None")
        
        # Current user email (if authenticated)
        current_user = st.session_state.get("current_user")
        if current_user and isinstance(current_user, dict):
            email = current_user.get("email", "Unknown")
            # Mask email in production (show first 3 chars + domain)
            if not IS_LOCAL and "@" in email:
                parts = email.split("@")
                masked = f"{parts[0][:3]}***@{parts[1]}"
                st.caption(f"**User:** {masked}")
            else:
                st.caption(f"**User:** {email}")
        else:
            st.caption("**User:** Not logged in")

        # Account info - dynamically show based on auth state
        st.markdown("### Account")
        if current_user and isinstance(current_user, dict):
            user_display = current_user.get("email", "User").split("@")[0]  # Show first part of email
            role_display = current_user.get("role", "member").title()
            st.info(f"Logged in as: **{user_display}** ({role_display})")
            
            # Show plan from capabilities if available
            caps = ss.get("capabilities")
            if caps and isinstance(caps, dict):
                plan_display = caps.get("plan", "free").title()
                st.caption(f"Plan: {plan_display}")
            else:
                st.caption("Plan: Loading...")
        else:
            st.caption("Not logged in")
        
        # Debug info (dev only)
        if ENABLE_DEBUG_UI:
            st.caption(f"Auth token present: {'Yes' if st.session_state.get('auth_token') else 'No'}")
            
            # Show cached capabilities (if available)
            caps = ss.get("capabilities")
            if caps:
                st.caption(f"Plan: {caps.get('plan', 'unknown')} | Role: {caps.get('role', 'unknown')}")
                st.caption(f"Capabilities: {len(caps.get('list', []))} cached")
                # Test can() helper
                st.caption(f"can('asset:manage'): {can('asset:manage')}")
            else:
                # If logged in but capabilities missing, show loading state
                if is_logged_in():
                    st.caption("⏳ Loading permissions...")
                    # Trigger capability fetch (can() will auto-hydrate)
                    _ = can("asset:manage")  # This will trigger auto-hydration
                else:
                    st.caption("Capabilities: not loaded (not authenticated)")
        
        # Usage stats (only fetch if rehydration complete and authenticated)
        auth_token = st.session_state.get('auth_token')
        session_rehydrated = st.session_state.get('session_rehydrated', False)
        
        if auth_token and session_rehydrated:
            try:
                resp = api_request("GET", "/account/info", timeout=10)
                if resp and resp.status_code == 200:
                    account_data = resp.json()
                    usage = account_data.get("usage", {})
                    limits = account_data.get("limits", {})
                    
                    st.markdown("**Usage:**")
                    saved_deals = usage.get("saved_deals", 0)
                    max_deals = limits.get("saved_deals", 5)
                    if max_deals == -1:  # unlimited
                        st.caption(f"Saved deals: {saved_deals} (unlimited)")
                    else:
                        st.caption(f"Saved deals: {saved_deals}/{max_deals}")
                        if saved_deals >= max_deals * 0.8:  # 80% usage
                            st.warning("⚠️ Approaching deal limit")
            except Exception:
                pass
        else:
            st.caption("_Not logged in_")
        
        # Session management buttons (only show when authenticated)
        if auth_token:
            st.markdown("---")
            st.markdown("**Session Management**")
            
            # Get resume code button
            # Resume codes allow session restoration after browser refresh/rerun WITHOUT requiring re-login.
            # Important: Resume codes ONLY work if the backend session is still active.
            # After logout, the backend session is REVOKED and resume codes will fail (by design).
            if st.button("🔑 Get Resume Code", key="get_resume_code_btn", use_container_width=True):
                try:
                    resp = api_request("POST", "/auth/resume/request", json={}, timeout=10)
                    if resp and resp.status_code == 200:
                        data = resp.json()
                        resume_code = data.get("resume_code")
                        if resume_code:
                            st.success("Resume code generated!")
                            st.code(resume_code, language="text")
                            st.caption(f"✅ Copy this code. After browser refresh, paste it into 'Resume Session' on the Login page to continue.")
                            st.caption(f"⏱️ Code expires in {RESUME_CODE_MINUTES} minutes.")
                        else:
                            st.error("Failed to generate resume code.")
                    else:
                        st.error(f"Failed to request resume code. Status: {resp.status_code if resp else 'No response'}")
                        if resp:
                            try:
                                error_data = resp.json()
                                st.code(json.dumps(error_data, indent=2), language="json")
                            except Exception:
                                st.code(resp.text, language="text")
                except Exception as e:
                    st.error(f"Error: {e}")
            
            # DEBUG ONLY: Simulate Refresh button (visible only in dev environment)
            if ENABLE_DEBUG_UI:
                # This clears Streamlit session state (simulating browser refresh) WITHOUT revoking backend session.
                # Use this to test resume flow. After clicking, use "Get Resume Code" first, then paste it.
                # Different from Logout: Logout REVOKES the backend session permanently; resume will fail after logout.
                if st.button("🔄 Simulate Refresh (DEBUG)", key="simulate_refresh_btn", use_container_width=True):
                    # Clear only Streamlit session state; do NOT call backend /auth/logout
                    # This simulates a browser refresh where tokens are lost but backend session is still active
                    for key in ["auth_token", "current_user", "session_id", "refresh_token"]:
                        if key in ss:
                            del ss[key]
                    st.info("Session state cleared (simulating refresh). Backend session still active. Use 'Resume Session' on login page.")
                    st.rerun()
            
            # Logout button
            # This REVOKES the backend session permanently. Resume codes will NOT work after logout.
            if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
                # Call backend logout if session exists
                session_id = ss.get("session_id")
                refresh_token = ss.get("refresh_token")
                
                if session_id and refresh_token:
                    try:
                        api_request(
                            "POST",
                            "/auth/logout",
                            json={"session_id": session_id, "refresh_token": refresh_token},
                            timeout=5
                        )
                    except Exception:
                        pass  # Continue logout even if backend call fails
                
                # Clear auth state using centralized helper
                clear_auth()
                
                # Navigate to login page using deterministic router
                go_to("Login")
        
        # Auth Smoke Test (visible when authenticated)
        if auth_token:
            st.markdown("---")
            st.markdown("**🔬 Auth Smoke Test**")
            st.caption("Test authentication status with protected endpoint")
            
            if st.button("🧪 Test Auth", key="auth_smoke_test_btn", use_container_width=True):
                try:
                    # Call a protected endpoint to verify auth is working
                    resp = api_request("GET", "/account/info", timeout=10)
                    
                    if resp and resp.status_code == 200:
                        data = resp.json()
                        st.success("✅ Auth working correctly!")
                        st.caption(f"Account: {data.get('account_name', 'Unknown')}")
                        st.caption(f"Plan: {data.get('plan', 'unknown')}")
                    elif resp and resp.status_code == 401:
                        st.error("❌ Auth token invalid or expired")
                        st.caption("Try logging out and back in")
                    elif resp and resp.status_code == 403:
                        st.warning("⚠️ Authenticated but missing permissions")
                    elif resp:
                        st.error(f"❌ Error: HTTP {resp.status_code}")
                    else:
                        st.error("❌ Cannot connect to backend")
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)[:100]}")
            
            # Show current connection status
            api_base = get_api_base_url()
            st.caption(f"API: {api_base}")
            if is_authenticated():
                st.caption("✅ Token present")
            else:
                st.caption("❌ No auth token")
        
        # DEV Test Controls Panel (DEV-only, gated by IS_DEV or ENABLE_DEBUG_UI)
        if ENABLE_DEBUG_UI and auth_token:
            st.markdown("---")
            with st.expander("🧪 DEV Test Controls", expanded=False):
                st.caption("**Permission Testing (DEV-only)**")
                
                # Fetch user/account info from backend (use cached version if available)
                dev_context_key = "_dev_context"
                dev_context = ss.get(dev_context_key)
                
                # Fetch if not cached or auth state changed
                if not dev_context or ss.get("_dev_context_token") != auth_token:
                    try:
                        resp = api_request("GET", "/account/info", timeout=10)
                        if resp and resp.status_code == 200:
                            account_data = resp.json()
                            # Fetch user info from current_user in session (set during login)
                            current_user = ss.get("current_user", {})
                            user_id = current_user.get("user_id") or current_user.get("id")
                            
                            dev_context = {
                                "user_id": user_id,
                                "account_id": account_data.get("account_id"),
                                "current_plan": account_data.get("plan", "free"),
                                "loaded": True
                            }
                            ss[dev_context_key] = dev_context
                            ss["_dev_context_token"] = auth_token
                            # Auto-rerun once after first successful context load to display controls
                            if not ss.get("_dev_context_initial_loaded"):
                                ss["_dev_context_initial_loaded"] = True
                                st.rerun()
                        else:
                            dev_context = {"loaded": False, "error": f"Status {resp.status_code if resp else 'no response'}"}
                            ss[dev_context_key] = dev_context
                    except Exception as e:
                        dev_context = {"loaded": False, "error": str(e)}
                        ss[dev_context_key] = dev_context
                
                # Display controls if context loaded successfully
                if dev_context and dev_context.get("loaded"):
                    user_id = dev_context.get("user_id")
                    account_id = dev_context.get("account_id")
                    
                    st.text(f"User ID: {user_id}")
                    st.text(f"Account ID: {account_id}")
                    
                    # Plan selector
                    plan_options = ["free", "pro", "team", "enterprise"]
                    current_plan = ss.get("capabilities", {}).get("plan") or dev_context.get("current_plan", "free")
                    
                    selected_plan = st.selectbox(
                        "Test Plan",
                        options=plan_options,
                        index=plan_options.index(current_plan) if current_plan in plan_options else 0,
                        key="dev_test_plan"
                    )
                    
                    # Role selector
                    role_options = ["owner", "admin", "member", "read_only"]
                    current_role = ss.get("capabilities", {}).get("role", "member")
                    
                    selected_role = st.selectbox(
                        "Test Role",
                        options=role_options,
                        index=role_options.index(current_role) if current_role in role_options else 2,
                        key="dev_test_role"
                    )
                    
                    # Apply buttons
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("Apply Plan", key="dev_apply_plan_btn", use_container_width=True):
                            try:
                                resp = api_request(
                                    "POST",
                                    f"/admin/set_plan?account_id={account_id}&plan={selected_plan}",
                                    timeout=10
                                )
                                if resp and resp.status_code == 200:
                                    # Clear all cached state
                                    if "capabilities" in ss:
                                        del ss["capabilities"]
                                    if dev_context_key in ss:
                                        del ss[dev_context_key]
                                    if "_dev_context_token" in ss:
                                        del ss["_dev_context_token"]
                                    if "_dev_context_initial_loaded" in ss:
                                        del ss["_dev_context_initial_loaded"]
                                    
                                    # Immediately re-fetch capabilities to update UI
                                    if fetch_and_cache_capabilities():
                                        # Normalize auth context to update canonical keys
                                        normalize_auth_context()
                                        set_debug_cause("plan_change")
                                        st.success(f"✅ Plan set to {selected_plan} - Capabilities updated")
                                    else:
                                        st.warning(f"✅ Plan set to {selected_plan} - Reload to update UI")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed: {resp.status_code if resp else 'No response'}")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)[:100]}")
                    
                    with col2:
                        if st.button("Apply Role", key="dev_apply_role_btn", use_container_width=True):
                            try:
                                resp = api_request(
                                    "POST",
                                    f"/admin/set_role?user_id={user_id}&role={selected_role}",
                                    timeout=10
                                )
                                if resp and resp.status_code == 200:
                                    # Clear all cached state
                                    if "capabilities" in ss:
                                        del ss["capabilities"]
                                    if dev_context_key in ss:
                                        del ss[dev_context_key]
                                    if "_dev_context_token" in ss:
                                        del ss["_dev_context_token"]
                                    if "_dev_context_initial_loaded" in ss:
                                        del ss["_dev_context_initial_loaded"]
                                    
                                    # Immediately re-fetch capabilities to update UI
                                    if fetch_and_cache_capabilities():
                                        # Normalize auth context to update canonical keys
                                        normalize_auth_context()
                                        set_debug_cause("role_change")
                                        st.success(f"✅ Role set to {selected_role} - Capabilities updated")
                                    else:
                                        st.warning(f"✅ Role set to {selected_role} - Reload to update UI")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed: {resp.status_code if resp else 'No response'}")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)[:100]}")
                    
                    st.caption("⚠️ Changes take effect immediately. Cached capabilities will be cleared and UI will reload.")
                else:
                    # Show compact error message without exposing tokens
                    error_msg = dev_context.get("error", "Unable to load") if dev_context else "Loading..."
                    st.caption(f"⚠️ Context unavailable: {error_msg}")
                    if st.button("🔄 Retry", key="dev_retry_context", use_container_width=True):
                        # Clear cached context to force refresh
                        if dev_context_key in ss:
                            del ss[dev_context_key]
                        if "_dev_context_token" in ss:
                            del ss["_dev_context_token"]
                        st.rerun()

        st.markdown("### Navigation")
        
        # Build navigation options with capability-based availability
        nav_options = ["Login", "Analyzer", "Portfolio", "Plans & Billing"]
        
        # Add future feature placeholders (disabled based on capabilities)
        future_features = []
        
        # Projects (requires project:create capability)
        if can("project:create"):
            future_features.append("🔹 Projects")
        else:
            future_features.append("🔒 Projects (Coming Soon)")
        
        # Assets (requires asset:manage capability)
        if can("asset:manage"):
            future_features.append("🔹 Assets")
        else:
            future_features.append("🔒 Assets (Coming Soon)")
        
        # Property Search (requires search:advanced capability)
        if can("search:advanced"):
            future_features.append("🔹 Property Search")
        else:
            future_features.append("🔒 Property Search (Coming Soon)")
        
        # Combine core and future features
        all_nav_options = nav_options + future_features
        
        # CRITICAL FIX: Map display options to canonical page names
        # This enables locked/disabled features to show in sidebar without breaking navigation
        nav_option_map = {
            "Login": "Login",
            "Analyzer": "Analyzer",
            "Portfolio": "Portfolio",
            "Plans & Billing": "Plans & Billing",
            "🔹 Projects": "Projects",
            "🔒 Projects (Coming Soon)": "Projects",
            "🔹 Assets": "Assets",
            "🔒 Assets (Coming Soon)": "Assets",
            "🔹 Property Search": "Property Search",
            "🔒 Property Search (Coming Soon)": "Property Search",
        }
        
        # Determine current index based on actual nav_page state
        current_page = ss.get("nav_page", "Analyzer")
        
        # Find which display option corresponds to current page
        current_index = 1  # Default to Analyzer
        for idx, opt in enumerate(all_nav_options):
            if nav_option_map.get(opt) == current_page:
                current_index = idx
                break
        
        # Radio button now directly controls nav_page via on_change callback
        # We'll handle the mapping after the radio is rendered
        nav_choice_display = st.radio(
            "Go to",
            all_nav_options,
            index=current_index,
            key="_nav_radio_display",  # Temporary key for display value
        )
        
        # Map selected display option to canonical page name
        target_page = nav_option_map.get(nav_choice_display, "Analyzer")
        
        # Check if user selected a locked feature
        if "🔒" in nav_choice_display:
            # Show info message but don't navigate
            if "Projects" in nav_choice_display:
                st.info("🔒 Projects requires project management permissions. Available in higher plans or future release.")
            elif "Assets" in nav_choice_display:
                st.info("🔒 Assets requires asset management permissions. Upgrade your plan or contact your admin.")
            elif "Property Search" in nav_choice_display:
                st.info("🔒 Property Search requires advanced search permissions. Available in Pro+ plans.")
            # Keep current page (don't navigate)
            target_page = current_page
        elif "🔹" in nav_choice_display:
            # Feature is available - check permission
            if "Projects" in nav_choice_display and not can("project:create"):
                st.info("🔒 Projects requires project management permissions.")
                target_page = current_page
            elif "Assets" in nav_choice_display and not can("asset:manage"):
                st.info("🔒 Assets requires asset management permissions.")
                target_page = current_page
            elif "Property Search" in nav_choice_display and not can("search:advanced"):
                st.info("🔒 Property Search requires advanced search permissions.")
                target_page = current_page
        
        # Update nav_page ONLY if it changed (avoids unnecessary reruns)
        if ss.get("nav_page") != target_page:
            ss["nav_page"] = target_page

        st.markdown("### Behavior")
        st.checkbox(
            "Auto-run analysis after loading from portfolio",
            key="auto_run_after_load",
            help="When on, loading a deal from the portfolio will immediately re-run the analysis.",
        )

        st.markdown("### Presets & Market")
        preset_names = ["None"] + list(PRESET_DEALS.keys())
        st.selectbox(
            "Quick preset",
            preset_names,
            index=preset_names.index(ss.get("selected_preset", "None")),
            key="selected_preset",
        )

        st.text_input(
            "ZIP code (for market context)",
            key="zip_code",
        )

        if st.button("Apply preset"):
            apply_preset(ss["selected_preset"])

        st.markdown(
            "<p style='font-size: 0.75rem; color: #6b7280;'>"
            "Preset applies on this session only. Values are editable after load."
            "</p>",
            unsafe_allow_html=True,
        )
        
        # DEV-only State Debug UI
        if ENABLE_DEBUG_UI and 'snapshot_state' in globals():
            st.markdown("---")
            with st.expander("🔎 State Debug (DEV)", expanded=False):
                st.caption("DEV-only diagnostics for session state debugging")
                
                # Navigation debug info
                st.markdown("##### Navigation State")
                st.text(f"nav_page: {ss.get('nav_page', 'NONE')}")
                st.text(f"_nav_radio_display: {ss.get('_nav_radio_display', 'NONE')}")
                st.text(f"is_authenticated: {is_authenticated()}")
                st.text(f"auth_token present: {'Yes' if ss.get('auth_token') else 'No'}")
                st.text(f"current_user present: {'Yes' if ss.get('current_user') else 'No'}")
                if ss.get("current_user"):
                    st.text(f"user role: {ss.get('current_user', {}).get('role', 'NONE')}")
                st.text(f"session_rehydrated: {ss.get('session_rehydrated', False)}")
                
                # Change detection summary
                if 'detect_state_changes' in globals():
                    changed, old_fp, new_fp = detect_state_changes(ss)
                    last_change_time = ss.get("_debug_last_change_time", "never")
                    # Peek at cause without consuming it (will be consumed on next state change log)
                    pending_cause = ss.get("_debug_cause", "none")
                    
                    st.markdown("##### Change Detection")
                    change_icon = "✅" if changed else "❌"
                    st.text(f"Changed since last: {change_icon} {'Yes' if changed else 'No'}")
                    st.text(f"Current fingerprint: {new_fp}")
                    if old_fp:
                        st.text(f"Previous fingerprint: {old_fp}")
                    st.text(f"Last change: {last_change_time}")
                    st.text(f"Pending cause: {pending_cause}")
                    st.markdown("---")
                
                # Capabilities fetch status
                cap_status = ss.get("_cap_fetch_status", "unknown")
                cap_error = ss.get("_cap_fetch_last_error")
                cap_warn_count = ss.get("_cap_fetch_warn_count", 0)
                
                st.markdown("##### Capabilities Fetch")
                status_icon = {
                    "ok": "✅",
                    "not_authenticated": "🔒",
                    "backend_unreachable": "🔌",
                    "auth_failed": "🚫",
                    "backend_error": "⚠️",
                    "unknown": "❓"
                }.get(cap_status, "❓")
                st.text(f"Status: {status_icon} {cap_status}")
                if cap_error:
                    st.text(f"Last error: {cap_error}")
                st.text(f"Warnings logged: {cap_warn_count}/3")
                st.markdown("---")
                
                # API Health (Phase 2)
                api_health = _api_health_snapshot(ss)
                if api_health:
                    st.markdown("##### API Health")
                    for endpoint, health in api_health.items():
                        status = health["status"]
                        status_icon = {
                            "ok": "✅",
                            "error": "❌",
                            "no_response": "🔌",
                            "not_authenticated": "🔒",
                            "throttled": "⏸️"
                        }.get(status, "❓")
                        
                        st.text(f"{endpoint}")
                        st.text(f"  Status: {status_icon} {status} ({health['age']})")
                        st.text(f"  OK: {health['ok_count']} | Err: {health['err_count']}")
                        if health["last_error"] != "none":
                            st.text(f"  Last error: {health['last_error']}")
                        if health["http_status"]:
                            st.text(f"  HTTP: {health['http_status']}")
                    st.markdown("---")
                
                # Portfolio Recovery Status
                st.markdown("##### Portfolio Auto-Recovery")
                recovery_active = ss.get("_portfolio_recovery_active", False)
                recovery_attempts = ss.get("_portfolio_recovery_attempts", 0)
                recovery_ts = ss.get("_portfolio_recovery_last_attempt_ts", 0.0)
                
                recovery_icon = "🔄" if recovery_active else "⏸️"
                st.text(f"Active: {recovery_icon} {'YES' if recovery_active else 'NO'}")
                st.text(f"Attempts: {recovery_attempts}/{PORTFOLIO_RECOVERY_MAX_ATTEMPTS}")
                
                if recovery_ts > 0:
                    import time
                    age_seconds = int(time.time() - recovery_ts)
                    if age_seconds < 60:
                        age_str = f"{age_seconds}s ago"
                    else:
                        age_str = f"{age_seconds // 60}m ago"
                    st.text(f"Last attempt: {age_str}")
                else:
                    st.text("Last attempt: never")
                
                # Show /property/saved endpoint status
                if api_health.get("/property/saved"):
                    saved_status = api_health["/property/saved"]["status"]
                    st.text(f"Endpoint /property/saved: {saved_status}")
                
                st.markdown("---")
                
                # Current state snapshot
                st.markdown("##### Current State")
                snapshot = snapshot_state(ss, KEYS_OF_INTEREST)
                
                # Display as table
                for key in KEYS_OF_INTEREST:
                    if key in snapshot:
                        entry = snapshot[key]
                        if entry["exists"]:
                            value_str = str(entry["value"])
                            if len(value_str) > 50:
                                value_str = value_str[:50] + "..."
                            
                            meta_str = ""
                            if "meta" in entry:
                                meta = entry["meta"]
                                meta_str = f" | {meta['source']} @ {meta['ts'][-12:-4]}"
                            
                            st.text(f"{key}: {value_str}{meta_str}")
                        else:
                            st.text(f"{key}: (not set)")
                
                st.markdown("##### Recent Events")
                events = get_recent_events(ss, limit=30)
                if events:
                    for evt in events[-10:]:  # Show last 10
                        ts_short = evt["ts"][-12:-4] if "ts" in evt else ""
                        details_str = ""
                        if "details" in evt:
                            details_str = f" | {evt['details']}"
                        st.caption(f"{ts_short} - {evt['name']}{details_str}")
                else:
                    st.caption("No events recorded yet")
                
                # Action buttons
                col_copy, col_clear = st.columns(2)
                with col_copy:
                    if st.button("📋 Copy Snapshot", key="dev_copy_snapshot", use_container_width=True):
                        json_export = export_snapshot_json(ss, KEYS_OF_INTEREST)
                        st.text_area("Snapshot JSON (copy this)", json_export, height=200, key="dev_snapshot_output")
                
                with col_clear:
                    if st.button("🗑️ Clear History", key="dev_clear_history", use_container_width=True):
                        clear_debug_history(ss)
                        st.success("Debug history cleared")
                        st.rerun()


# --------------------------------------------------------------------
# Analyzer page
# --------------------------------------------------------------------


def render_underwriting_assumptions() -> Dict[str, Any]:
    with st.expander("Underwriting assumptions (Batch A)", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            vacancy_rate = st.number_input(
                "Vacancy rate (%)",
                min_value=0.0,
                max_value=50.0,
                value=5.0,
                step=0.5,
            )
        with col2:
            op_ex_percent = st.number_input(
                "Operating expenses (% of rent)",
                min_value=0.0,
                max_value=100.0,
                value=35.0,
                step=1.0,
            )
        with col3:
            capex_reserves = st.number_input(
                "CapEx reserves ($/month)",
                min_value=0.0,
                value=150.0,
                step=25.0,
            )

        col4, col5 = st.columns(2)
        with col4:
            debt_service = st.number_input(
                "Annual debt service ($/yr)",
                min_value=0.0,
                value=0.0,
                step=500.0,
                help="If you add your annual principal+interest here, DSCR will be calculated.",
            )
        with col5:
            other_expenses = st.number_input(
                "Other annual expenses ($/yr)",
                min_value=0.0,
                value=0.0,
                step=250.0,
            )

        return {
            "vacancy_rate_pct": vacancy_rate,
            "op_ex_percent_rent": op_ex_percent,
            "capex_reserves_month": capex_reserves,
            "debt_service_annual": debt_service,
            "other_expenses_annual": other_expenses,
        }


def render_legends() -> None:
    th = ss["thresholds"]
    with st.expander("Legends (DSCR / Cap Rate / CoC)", expanded=False):
        st.markdown("**DSCR (Debt Service Coverage Ratio)**")
        st.markdown(
            f"- ≥ {th['dscr_safe']:.2f}: Generally lender-friendly (strong cushion)\n"
            f"- {th['dscr_min']:.2f} – {th['dscr_safe']:.2f}: Borderline / moderate cushion\n"
            f"- &lt; {th['dscr_min']:.2f}: Tight – lender or you may be uncomfortable"
        )

        st.markdown("---")
        st.markdown("**Cap rate (Year 1)**")
        st.markdown(
            f"- ≥ {th['cap_rate_good']*100:.1f}%: Strong relative yield\n"
            f"- {th['cap_rate_ok']*100:.1f}% – {th['cap_rate_good']*100:.1f}%: Solid / typical\n"
            f"- &lt; {th['cap_rate_ok']*100:.1f}%: Thin for many buy-and-hold investors"
        )

        st.markdown("---")
        st.markdown("**Cash-on-Cash (Year 1)**")
        st.markdown(
            f"- ≥ {th['coc_good']*100:.1f}%: Very healthy CoC\n"
            f"- {th['coc_ok']*100:.1f}% – {th['coc_good']*100:.1f}%: Acceptable for many\n"
            f"- &lt; {th['coc_ok']*100:.1f}%: May feel tight unless upside is strong"
        )


def handle_api_error(resp: requests.Response, operation: str = "operation") -> None:
    """Handle API errors with user-friendly messages.
    
    Phase 3: Added handling for 402 (payment required) and 403 (forbidden).
    """
    if resp.status_code == 401:
        st.error("❌ Not authenticated. Please log in again.")
    elif resp.status_code == 402:
        # Payment required (plan upgrade needed)
        try:
            error_data = resp.json()
            detail = error_data.get("detail", "Plan upgrade required")
            st.error(f"💳 **Upgrade Required:** {detail}")
            st.info("💡 Upgrade your plan to access this feature. Visit the Account page in DEV mode to change plans.")
        except Exception:
            st.error(f"💳 **Upgrade Required:** This feature requires a higher plan.")
    elif resp.status_code == 403:
        # Forbidden (insufficient permissions)
        try:
            error_data = resp.json()
            detail = error_data.get("detail", "Insufficient permissions")
            st.error(f"🔒 **Permission Denied:** {detail}")
            st.info("💡 You need a higher role (member, admin, or owner) to perform this action. Contact your account owner.")
        except Exception:
            st.error(f"🔒 **Permission Denied:** You don't have permission for this {operation}.")
    else:
        st.error(f"Backend error {resp.status_code} on {operation}")
        try:
            st.code(resp.text, language="json")
        except Exception:
            pass


def run_analysis(inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not is_authenticated():
        st.error("Authentication required. Please log in to run analysis.")
        return None
    resp = api_request("POST", "/property/analyze", json=inputs, timeout=40)
    if resp is None:
        return None
    if resp.status_code != 200:
        handle_api_error(resp, "/property/analyze")
        return None
    return resp.json()


def render_analyzer() -> None:
    # Auth guard - stop execution if not authenticated
    if not require_auth(redirect_to_login=True):
        return
    
    # Note: Address payload is now handled centrally in apply_pending_actions()
    # at the top of main(), before any widgets are created. No guard needed here.
    render_header()

    # Auth status
    st.caption(f"Auth token present: {'Yes' if st.session_state.get('auth_token') else 'No'}")

    st.markdown("### Property details")

    c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
    with c1:
        property_name = st.text_input(
            "Property name / label",
            value=ss.get("property_name", "123 Main St Test Deal"),
            key="property_name",
        )
    with c2:
        city = st.text_input(
            "City",
            value=ss.get("city", "Baltimore"),
            key="city",
        )
    with c3:
        state = st.text_input(
            "State",
            value=ss.get("state", "MD"),
            key="state",
        )
    with c4:
        # FIX: Use zip_code_property as value source to match widget key
        # This ensures payload writes to zip_code_property are reflected immediately
        zip_code = st.text_input(
            "ZIP code",
            value=ss.get("zip_code_property", "21207"),
            key="zip_code_property",
        )

    st.markdown("### Deal setup")

    c5, c6 = st.columns(2)
    with c5:
        purchase_price = st.number_input(
            "Purchase price ($)",
            min_value=0.0,
            value=float(ss.get("purchase_price", 200000.0)),
            step=5000.0,
        )
        rehab_budget = st.number_input(
            "Rehab budget ($)",
            min_value=0.0,
            value=float(ss.get("rehab_budget", 40000.0)),
            step=5000.0,
        )
        hold_years = st.number_input(
            "Hold period (years)",
            min_value=0.5,
            value=float(ss.get("hold_years", 5.0)),
            step=0.5,
        )
    with c6:
        monthly_rent = st.number_input(
            "Monthly rent ($)",
            min_value=0.0,
            value=float(ss.get("monthly_rent", 2200.0)),
            step=50.0,
        )
        strategy = st.selectbox(
            "Strategy",
            ["rental", "flip", "BRRRR", "unknown"],
            index=["rental", "flip", "BRRRR", "unknown"].index(
                ss.get("strategy", "rental")
            ),
            key="strategy",
        )
        investor_profile = st.selectbox(
            "Investor profile",
            ["balanced", "conservative", "aggressive", "cashflow_first", "flip_focused"],
            index=["balanced", "conservative", "aggressive", "cashflow_first", "flip_focused"].index(
                ss.get("investor_profile", "balanced")
            ),
            key="investor_profile",
        )

    assumptions = render_underwriting_assumptions()

    with st.expander("Notes / assumptions (optional)", expanded=False):
        notes = st.text_area(
            "Notes / assumptions",
            value=ss.get("notes", ""),
            key="notes",
        )

    run_col, loaded_col = st.columns([1, 3])
    with run_col:
        # Disable analysis when not logged in
        logged_in = is_logged_in()
        run_clicked = st.button("▶ Run analysis", disabled=not logged_in)
        if not logged_in:
            st.caption("🔒 Login required.")

    if run_clicked or (ss.get("loaded_from_portfolio") and ss.get("auto_run_after_load")):
        # Capture previous inputs for "revert" later
        ss["previous_inputs"] = ss.get("analysis_inputs")

        payload: Dict[str, Any] = {
            "property_name": property_name,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "purchase_price": purchase_price,
            "rehab_budget": rehab_budget,
            "monthly_rent": monthly_rent,
            "hold_years": hold_years,
            "strategy": strategy,
            "investor_profile": investor_profile,
            "notes": notes or None,
            **assumptions,
        }

        with st.spinner("Running Brinkadata analysis…"):
            result = run_analysis(payload)

        if result is not None:
            ss["analysis_inputs"] = payload
            ss["analysis_result"] = result
            ss["loaded_from_portfolio"] = False
            st.success("Analysis complete!")

    result = ss.get("analysis_result")
    inputs = ss.get("analysis_inputs")

    if result and inputs:
        render_analysis_results(inputs, result)
        render_scenarios_section(inputs, result)
    else:
        st.info("Enter deal details and click **Run analysis** to get started.")


def render_analysis_results(inputs: Dict[str, Any], result: Dict[str, Any]) -> None:
    st.markdown("### Deal Snapshot")

    deal_grade = safe_get(result, "deal_grade", "—")
    est_roi = safe_get(result, "estimated_roi", None)
    monthly_cf = safe_get(result, "cashflow_per_month", None)
    noi_year = safe_get(result, "noi_year", None)
    dscr = safe_get(result, "dscr", None)
    irr = safe_get(result, "irr_hold_period", None)
    npv = safe_get(result, "npv_hold_period", None)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Grade", deal_grade)
    c2.metric("ROI (hold)", format_pct(est_roi) if est_roi is not None else "n/a")
    c3.metric("Monthly cashflow", format_money(monthly_cf))
    c4.metric("Yearly NOI", format_money(noi_year))

    c5, c6 = st.columns(2)
    with c5:
        st.metric("DSCR", f"{dscr:.2f}" if dscr is not None else "n/a")
    with c6:
        # Check if user has IRR feature
        can_use_irr = False
        auth_token = st.session_state.get('auth_token')
        if auth_token:
            try:
                resp = api_request("GET", "/account/info", timeout=10)
                if resp and resp.status_code == 200:
                    account_data = resp.json()
                    plan = account_data.get("plan", "free")
                    can_use_irr = plan in ["pro", "team", "enterprise"]
            except Exception:
                pass
        
        if can_use_irr:
            irr_label = "IRR (hold)" if irr is not None else "IRR (hold)"
            st.metric(irr_label, format_pct(irr) if irr is not None else "n/a")
        else:
            st.metric("IRR (Pro+)", "🔒 Upgrade")
            if st.button("Unlock IRR/NPV", key="unlock_irr"):
                st.info("**Pro Plan ($29.99/month):** Unlock IRR, NPV, and advanced metrics")
                if st.button("Upgrade to Pro", key="upgrade_irr"):
                    try:
                        upgrade_resp = api_request("POST", "/account/upgrade", json={"new_plan": "pro"}, timeout=10)
                        if upgrade_resp and upgrade_resp.status_code == 200:
                            st.success("Upgraded to Pro plan! IRR now unlocked.")
                            # st.rerun()
                        else:
                            st.error("Upgrade failed. Please try again.")
                    except Exception as e:
                        st.error(f"Upgrade error: {e}")

    st.markdown("#### Ways to improve this deal")
    improvement = safe_get(result, "improvement_tips", [])
    if not improvement:
        st.caption("No specific suggestions yet. Tweak your inputs to explore scenarios.")
    else:
        for tip in improvement:
            st.markdown(f"- {tip}")

    render_legends()

    # Save deal controls
    st.markdown("---")
    
    # Check if user can save more deals
    can_save = True
    auth_token = st.session_state.get('auth_token')
    if auth_token:
        try:
            resp = api_request("GET", "/account/info", timeout=10)
            if resp and resp.status_code == 200:
                account_data = resp.json()
                usage = account_data.get("usage", {})
                limits = account_data.get("limits", {})
                saved_deals = usage.get("saved_deals", 0)
                max_deals = limits.get("saved_deals", 5)
                if max_deals != -1 and saved_deals >= max_deals:
                    can_save = False
        except Exception:
            pass
    
    if not can_save:
        st.error("🚫 You've reached your plan's deal limit!")
        if st.button("🔄 Upgrade Plan", type="primary"):
            st.info("**Pro Plan ($29.99/month):** 50 saved deals, IRR/NPV, CSV export")
            if st.button("Upgrade to Pro"):
                try:
                    upgrade_resp = api_request("POST", "/account/upgrade", json={"new_plan": "pro"}, timeout=10)
                    if upgrade_resp and upgrade_resp.status_code == 200:
                        st.success("Upgraded to Pro plan! Refreshing...")
                        # st.rerun()
                    else:
                        st.error("Upgrade failed. Please try again.")
                except Exception as e:
                    st.error(f"Upgrade error: {e}")
    else:
        # Check capability for saving (asset:manage)
        has_save_capability = can("asset:manage")
        logged_in = is_logged_in()
        
        # Only show save button if user has capability
        if has_save_capability:
            if st.button("💾 Save this deal to portfolio", disabled=not logged_in):
                payload = {
                    **inputs,
                    **result,
                    "account_id": 1,  # For development: mock account
                    "user_id": 1,     # For development: mock user
                }
                resp = api_request("POST", "/property/save", json=payload, timeout=20)
                if resp is None:
                    return
                if resp.status_code == 200:
                    st.success("Deal saved to portfolio.")
                    # Set current_property_id for scenarios
                    deals = load_saved_deals()
                    for deal in deals:
                        if (deal.get("property_name") == inputs.get("property_name") and 
                            deal.get("city") == inputs.get("city")):
                            ss["current_property_id"] = deal.get("id")
                            break
                else:
                    # Phase 3: Use centralized error handler for 402/403
                    handle_api_error(resp, "/property/save")
            
            if not logged_in:
                st.caption("🔒 Login required.")
        else:
            # Show message for users without save capability
            st.info("💡 Saving deals requires additional permissions. Contact your account admin or upgrade your plan.")
            if ENABLE_DEBUG_UI:
                st.caption("⚠️ DEV: Some actions are unavailable due to your role or plan")


# --------------------------------------------------------------------
# Scenario comparison (A/B/C) – in-analyzer
# --------------------------------------------------------------------


def render_scenarios_section(inputs: Dict[str, Any], result: Dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("Scenario comparison (A / B / C)")

    property_id = ss.get("current_property_id")
    if not property_id:
        st.info("💡 Save this deal to portfolio first to enable scenario comparison.")
        return

    scenarios = load_scenarios(property_id)
    scenario_dict = {s["slot"]: s for s in scenarios}

    # Display current slots
    st.markdown("#### Saved Scenarios")
    cols = st.columns(3)
    for i, slot in enumerate(["A", "B", "C"], 1):
        with cols[i-1]:
            st.markdown(f"**Scenario {slot}**")
            if slot in scenario_dict:
                s = scenario_dict[slot]
                label = s.get("label") or f"Scenario {slot}"
                created_at = s.get("created_at", "")
                st.caption(f"{label} (saved {created_at})")
            else:
                st.caption("Empty")

    # Action buttons
    st.markdown("#### Actions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        save_slot = st.selectbox(
            "Save current analysis to slot:",
            ["None", "A", "B", "C"],
            index=0,
            key="save_scenario_slot",
        )
        if st.button("💾 Save to Slot"):
            if save_slot in ["A", "B", "C"]:
                label = inputs.get("property_name", f"Scenario {save_slot}")
                payload = {
                    "property_id": property_id,
                    "slot": save_slot,
                    "label": label,
                    "metrics": result
                }
                resp = api_request("POST", "/scenario/save", json=payload, timeout=20)
                if resp and resp.status_code == 200:
                    st.success(f"Scenario {save_slot} saved!")
                    st.rerun()  # Refresh to show updated list
                else:
                    st.error(f"Failed to save scenario: HTTP {resp.status_code if resp else 'no response'}")

    with col2:
        load_slot = st.selectbox(
            "Load scenario from slot:",
            ["None", "A", "B", "C"],
            index=0,
            key="load_scenario_slot",
        )
        if st.button("📂 Load from Slot"):
            if load_slot in ["A", "B", "C"] and load_slot in scenario_dict:
                # Use address payload pattern to load scenario metrics (includes property address fields)
                ss["_apply_address_payload"] = scenario_dict[load_slot]["metrics"]
                if IS_DEV and 'mark_key_set' in globals():
                    mark_key_set(ss, "_apply_address_payload", "scenario_load")
                    track_event(ss, "scenario_loaded", {"slot": load_slot})
                set_debug_cause("scenario_load")
                st.rerun()
            elif load_slot in ["A", "B", "C"]:
                st.warning(f"Scenario {load_slot} is empty.")

    with col3:
        clear_slot = st.selectbox(
            "Clear scenario slot:",
            ["None", "A", "B", "C"],
            index=0,
            key="clear_scenario_slot",
        )
        if st.button("🗑️ Clear Slot"):
            if clear_slot in ["A", "B", "C"]:
                payload = {
                    "property_id": property_id,
                    "slot": clear_slot
                }
                resp = api_request("POST", "/scenario/clear", json=payload, timeout=20)
                if resp and resp.status_code == 200:
                    st.success(f"Scenario {clear_slot} cleared!")
                    st.rerun()  # Refresh to show updated list
                else:
                    st.error(f"Failed to clear scenario: HTTP {resp.status_code if resp else 'no response'}")

    # Comparison UI
    if scenarios:
        st.markdown("#### Comparison")

        # Baseline selection
        baseline_options = ["None"] + [slot for slot in ["A", "B", "C"] if slot in scenario_dict]
        baseline_slot = st.selectbox(
            "Baseline slot (for deltas):",
            baseline_options,
            index=0,
            key="scenario_baseline_slot",
        )
        baseline_metrics = scenario_dict.get(baseline_slot, {}).get("metrics") if baseline_slot != "None" else None

        # Build comparison table
        rows = []
        for slot in ["A", "B", "C"]:
            if slot not in scenario_dict:
                continue
            s = scenario_dict[slot]
            metrics = s["metrics"]
            row = {
                "Slot": slot,
                "Label": s.get("label") or f"Scenario {slot}",
                "Grade": safe_get(metrics, "deal_grade", "n/a"),
                "Strategy": safe_get(metrics, "strategy", "n/a"),
                "ROI (%)": format_pct(safe_get(metrics, "estimated_roi")),
                "Monthly cashflow": format_money(safe_get(metrics, "cashflow_per_month")),
                "NOI (yr)": format_money(safe_get(metrics, "noi_year")),
                "Cap rate": format_pct(safe_get(metrics, "cap_rate")),
                "CoC": format_pct(safe_get(metrics, "coc_return")),
                "IRR": format_pct(safe_get(metrics, "irr_hold_period")),
                "NPV": format_money(safe_get(metrics, "npv_hold_period")),
                "Flip profit": format_money(safe_get(metrics, "flip_profit")),
                "Flip velocity": format_money(safe_get(metrics, "flip_velocity")),
            }
            # Add deltas if baseline
            if baseline_metrics:
                for col in ["ROI (%)", "Monthly cashflow", "NOI (yr)", "IRR", "NPV"]:
                    base_val = None
                    curr_val = None
                    if col == "ROI (%)":
                        base_val = safe_get(baseline_metrics, "estimated_roi")
                        curr_val = safe_get(metrics, "estimated_roi")
                    elif col == "Monthly cashflow":
                        base_val = safe_get(baseline_metrics, "cashflow_per_month")
                        curr_val = safe_get(metrics, "cashflow_per_month")
                    elif col == "NOI (yr)":
                        base_val = safe_get(baseline_metrics, "noi_year")
                        curr_val = safe_get(metrics, "noi_year")
                    elif col == "IRR":
                        base_val = safe_get(baseline_metrics, "irr_hold_period")
                        curr_val = safe_get(metrics, "irr_hold_period")
                    elif col == "NPV":
                        base_val = safe_get(baseline_metrics, "npv_hold_period")
                        curr_val = safe_get(metrics, "npv_hold_period")
                    if base_val is not None and curr_val is not None:
                        delta = curr_val - base_val
                        if col.endswith("(%)"):
                            row[f"Δ {col}"] = format_pct(delta)
                        else:
                            row[f"Δ {col}"] = format_money(delta)
                    else:
                        row[f"Δ {col}"] = "n/a"
            rows.append(row)

        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)

        # Charts
        chart_data = []
        for slot in ["A", "B", "C"]:
            if slot in scenario_dict:
                metrics = scenario_dict[slot]["metrics"]
                chart_data.append({
                    "Slot": slot,
                    "ROI (%)": safe_get(metrics, "estimated_roi", 0),
                    "Monthly cashflow": safe_get(metrics, "cashflow_per_month", 0),
                    "NOI (yr)": safe_get(metrics, "noi_year", 0),
                })

        if chart_data:
            chart_df = pd.DataFrame(chart_data).set_index("Slot")
            st.bar_chart(chart_df, use_container_width=True)
    else:
        st.info("No scenarios saved yet. Save to A/B/C to compare.")


# --------------------------------------------------------------------
# Portfolio + Trash
# --------------------------------------------------------------------


def load_saved_deals() -> List[Dict[str, Any]]:
    """
    Load saved deals from backend.
    """
    resp = api_request("GET", "/property/saved", timeout=20)
    
    if resp is None or resp.status_code != 200:
        return []
    
    try:
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def load_trash() -> List[Dict[str, Any]]:
    resp = api_request("GET", "/property/trash", timeout=20)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def load_scenarios(property_id: int) -> List[Dict[str, Any]]:
    resp = api_request("GET", f"/scenario/list/{property_id}", timeout=20)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def render_portfolio_and_trash() -> None:
    # Auth guard - stop execution if not authenticated
    if not require_auth(redirect_to_login=True):
        return
    
    st.header("Saved Deals — Portfolio")
    
    deals = load_saved_deals()
    if not deals:
        st.info("No saved deals yet. Run an analysis and save it from the Analyzer page.")
        return

    df = pd.DataFrame(deals)

    # Ensure expected columns exist
    for col in [
        "estimated_roi",
        "cap_rate",
        "coc_return",
        "cashflow_per_month",
        "total_investment",
        "noi_year",
        "irr_hold_period",
        "npv_hold_period",
    ]:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Basic KPIs
    df["roi_pct"] = df["estimated_roi"] * 100.0
    avg_roi = df["roi_pct"].mean()
    avg_cap = (df["cap_rate"] * 100.0).mean()
    avg_coc = (df["coc_return"] * 100.0).mean()

    total_cf = df["cashflow_per_month"].fillna(0).sum()
    total_invested = df["total_investment"].fillna(0).sum()
    total_noi = df["noi_year"].fillna(0).sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total saved deals", len(df))
    c2.metric("Avg ROI", f"{avg_roi:.1f}%" if not math.isnan(avg_roi) else "n/a")
    c3.metric("Avg cap rate", f"{avg_cap:.1f}%" if not math.isnan(avg_cap) else "n/a")
    c4.metric("Avg CoC", f"{avg_coc:.1f}%" if not math.isnan(avg_coc) else "n/a")

    c5, c6 = st.columns(2)
    c5.metric("Portfolio monthly cashflow", format_money(total_cf))
    c6.metric("Portfolio NOI (year)", format_money(total_noi))

    st.markdown("### Filters")

    min_roi_val = float(df["roi_pct"].fillna(0).min())
    max_roi_val = float(df["roi_pct"].fillna(0).max())
    roi_slider = st.slider(
        "Minimum ROI (%)",
        min_value=max(0.0, math.floor(min_roi_val)),
        max_value=max(10.0, math.ceil(max_roi_val + 1.0)),
        value=max(0.0, math.floor(min_roi_val)),
    )

    # Grades and strategies
    grades = sorted(df["deal_grade"].dropna().astype(str).unique().tolist()) \
        if "deal_grade" in df.columns else []
    strategies = (
        sorted(df["strategy"].dropna().astype(str).unique().tolist())
        if "strategy" in df.columns
        else []
    )

    col_g, col_s = st.columns(2)
    with col_g:
        selected_grades = st.multiselect(
            "Deal grades", options=grades, default=grades, key="filter_grades"
        )
    with col_s:
        selected_strategies = st.multiselect(
            "Strategies", options=strategies, default=strategies, key="filter_strategies"
        )

    mask = df["roi_pct"].fillna(0) >= roi_slider
    if selected_grades:
        mask &= df["deal_grade"].astype(str).isin(selected_grades)
    if selected_strategies:
        mask &= df["strategy"].astype(str).isin(selected_strategies)

    df_filtered = df[mask].copy()

    # Display filtered portfolio table
    if df_filtered.empty:
        st.warning("No deals match the current filters.")
    else:
        df_filtered = df_filtered.reset_index(drop=True)
        df_filtered.index = df_filtered.index + 1  # start at 1 for display

        cols_order = [
            "property_name",
            "city",
            "state",
            "zip_code",
            "deal_grade",
            "strategy",
            "investor_profile",
            "roi_pct",
            "cap_rate",
            "coc_return",
            "cashflow_per_month",
            "total_investment",
            "noi_year",
            "irr_hold_period",
            "npv_hold_period",
        ]

        cols_present = [c for c in cols_order if c in df_filtered.columns]
        df_view = df_filtered[cols_present].copy()

        # Pretty-print percentages & currency for the view
        if "roi_pct" in df_view.columns:
            df_view["ROI_%"] = df_view["roi_pct"].map(
                lambda v: f"{v:.1f}%" if pd.notna(v) else "n/a"
            )
            df_view.drop(columns=["roi_pct"], inplace=True)
        for col in ["cap_rate", "coc_return"]:
            if col in df_view.columns:
                df_view[col] = df_view[col].map(
                    lambda v: f"{v*100:.1f}%" if pd.notna(v) else "n/a"
                )
        money_cols = ["cashflow_per_month", "total_investment", "noi_year", "npv_hold_period"]
        for col in money_cols:
            if col in df_view.columns:
                df_view[col] = df_view[col].map(
                    lambda v: f"${v:,.0f}" if pd.notna(v) else "n/a"
                )

        st.dataframe(df_view, width='stretch')

        # Export
        csv = df.to_csv(index=False)
        st.download_button(
            "Download filtered portfolio as CSV",
            csv,
            file_name="brinkadata_portfolio.csv",
            mime="text/csv",
        )

    # Scenario Comparison Section
    deals_with_id = [d for d in deals if d.get("id")]
    if deals_with_id:
        st.markdown("---")
        st.subheader("Scenario Comparison (A / B / C)")

        # Build options
        options = []
        counter = 1
        for deal in deals:
            if not deal.get("id"):
                continue
            name = deal.get("property_name", "Unknown")
            city = deal.get("city", "")
            state = deal.get("state", "")
            grade = deal.get("deal_grade", "—")
            label = f"{counter}: {name} ({city}, {state}) — Grade {grade}"
            options.append((label, deal["id"]))
            counter += 1

        if options:
            selected_label = st.selectbox(
                "Select a saved deal to compare scenarios",
                [opt[0] for opt in options],
                key="scenario_compare_select"
            )
            selected_property_id = next(pid for lab, pid in options if lab == selected_label)

            # Fetch scenarios
            scenarios = load_scenarios(selected_property_id)
            if not scenarios:
                st.info("No scenarios saved yet for this deal. Save A/B/C from the Analyzer first.")
            else:
                # Process scenarios into dict slot -> scenario
                scenario_dict = {s["slot"]: s for s in scenarios}
                available_slots = sorted(scenario_dict.keys())

                # Build comparison table
                rows = []
                for slot in ["A", "B", "C"]:
                    if slot in scenario_dict:
                        s = scenario_dict[slot]
                        metrics = s.get("metrics_json", {})
                        if isinstance(metrics, str):
                            metrics = json.loads(metrics)
                        label = s.get("label", f"Scenario {slot}")
                        strategy = metrics.get("strategy", "—")
                        grade = metrics.get("deal_grade", "—")
                        roi = normalize_metric(metrics, "estimated_roi")
                        monthly_cf = normalize_metric(metrics, "cashflow_per_month")
                        noi_yr = normalize_metric(metrics, "noi_year")
                        dscr = normalize_metric(metrics, "dscr")
                        cap_rate = normalize_metric(metrics, "cap_rate")
                        coc = normalize_metric(metrics, "coc_return")
                        irr = normalize_metric(metrics, "irr_hold_period")
                        npv = normalize_metric(metrics, "npv_hold_period")
                        flip_profit = normalize_metric(metrics, "flip_profit")
                        flip_velocity = normalize_metric(metrics, "flip_velocity")

                        row = {
                            "Slot": slot,
                            "Label": label,
                            "Strategy": strategy,
                            "Grade": grade,
                            "ROI %": f"{roi*100:.1f}%" if roi is not None else "—",
                            "Monthly cashflow": f"${monthly_cf:,.0f}" if monthly_cf is not None else "—",
                            "NOI/yr": f"${noi_yr:,.0f}" if noi_yr is not None else "—",
                            "DSCR": f"{dscr:.2f}" if dscr is not None else "—",
                            "Cap rate": f"{cap_rate*100:.1f}%" if cap_rate is not None else "—",
                            "CoC": f"{coc*100:.1f}%" if coc is not None else "—",
                            "IRR": f"{irr*100:.1f}%" if irr is not None else "—",
                            "NPV": f"${npv:,.0f}" if npv is not None else "—",
                            "Flip profit": f"${flip_profit:,.0f}" if flip_profit is not None else "—",
                            "Flip velocity (profit/yr)": f"${flip_velocity:,.0f}" if flip_velocity is not None else "—",
                        }
                        rows.append(row)
                    else:
                        rows.append({
                            "Slot": slot, "Label": "—", "Strategy": "—", "Grade": "—", "ROI %": "—",
                            "Monthly cashflow": "—", "NOI/yr": "—", "DSCR": "—", "Cap rate": "—",
                            "CoC": "—", "IRR": "—", "NPV": "—", "Flip profit": "—", "Flip velocity (profit/yr)": "—"
                        })

                df_compare = pd.DataFrame(rows).set_index("Slot")
                st.dataframe(df_compare, width='stretch')

                # Baseline deltas
                if available_slots:
                    baseline = st.selectbox("Baseline slot", available_slots, key="baseline_select")
                    baseline_s = scenario_dict[baseline]
                    baseline_metrics = baseline_s.get("metrics_json", {})
                    if isinstance(baseline_metrics, str):
                        baseline_metrics = json.loads(baseline_metrics)

                    st.markdown("**Deltas from baseline:**")
                    for slot in available_slots:
                        if slot == baseline:
                            continue
                        s = scenario_dict[slot]
                        metrics = s.get("metrics_json", {})
                        if isinstance(metrics, str):
                            metrics = json.loads(metrics)

                        delta_roi = safe_delta(
                            normalize_metric(metrics, "estimated_roi"),
                            normalize_metric(baseline_metrics, "estimated_roi"),
                            is_percentage=True
                        )
                        delta_cf = safe_delta(
                            normalize_metric(metrics, "cashflow_per_month"),
                            normalize_metric(baseline_metrics, "cashflow_per_month")
                        )
                        delta_noi = safe_delta(
                            normalize_metric(metrics, "noi_year"),
                            normalize_metric(baseline_metrics, "noi_year")
                        )
                        st.write(f"**{slot} vs {baseline}:** Δ ROI: {delta_roi}, Δ Monthly cashflow: {delta_cf}, Δ NOI/yr: {delta_noi}")

                # Charts
                chart_data = {"Slot": [], "ROI %": [], "Monthly cashflow": [], "NOI/yr": []}
                for slot in ["A", "B", "C"]:
                    if slot in scenario_dict:
                        s = scenario_dict[slot]
                        metrics = s.get("metrics_json", {})
                        if isinstance(metrics, str):
                            metrics = json.loads(metrics)
                        roi = normalize_metric(metrics, "estimated_roi")
                        cf = normalize_metric(metrics, "cashflow_per_month")
                        noi = normalize_metric(metrics, "noi_year")
                        chart_data["Slot"].append(slot)
                        chart_data["ROI %"].append(roi * 100 if roi is not None else 0)
                        chart_data["Monthly cashflow"].append(cf if cf is not None else 0)
                        chart_data["NOI/yr"].append(noi if noi is not None else 0)

                if chart_data["Slot"]:
                    df_chart = pd.DataFrame(chart_data).set_index("Slot")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.bar_chart(df_chart["ROI %"])
                    with col2:
                        st.bar_chart(df_chart["Monthly cashflow"])
                    with col3:
                        st.bar_chart(df_chart["NOI/yr"])

    # ---------------- Delete + Trash ----------------
    st.markdown("---")
    st.subheader("Delete a saved deal")

    # Check capability for delete operations (asset:manage)
    has_delete_capability = can("asset:manage")
    
    if not has_delete_capability:
        st.info("💡 Deleting deals requires additional permissions. Contact your account admin or upgrade your plan.")
        if ENABLE_DEBUG_UI:
            st.caption("⚠️ DEV: Some actions are unavailable due to your role or plan")
    else:
        # Build options using numeric deal IDs from backend
        deal_ids: List[Optional[int]] = [None]
        deal_map: Dict[Optional[int], str] = {None: "None"}

        for idx, deal in enumerate(deals):
            name = deal.get("property_name")
            if not name:
                continue
            deal_id = deal.get("id")
            if deal_id is None:
                continue
            city = deal.get("city", "")
            state = deal.get("state", "")
            grade = deal.get("deal_grade", "—")
            label = f"{idx + 1}: {name} ({city}, {state}) – Grade {grade}"
            deal_ids.append(deal_id)
            deal_map[deal_id] = label

        def format_deal_option(deal_id: Optional[int]) -> str:
            return deal_map.get(deal_id, "Unknown")

        selected_id = st.selectbox(
            "Select a deal to delete",
            options=deal_ids,
            format_func=format_deal_option,
            index=0,
            key="delete_select",
        )

        if st.button("Move to trash", disabled=(selected_id is None)):
            if selected_id is None:
                st.warning("Choose a specific deal to delete.")
            else:
                resp = api_request(
                    "POST",
                    "/property/delete",
                    json={"id": int(selected_id)},
                    timeout=20,
                )
                if resp is None:
                    return
                if resp.status_code == 200:
                    st.success("Deal moved to trash.")
                    # st.rerun()
                else:
                    # Phase 3: Use centralized error handler
                    handle_api_error(resp, "/property/delete")

    # Trash view
    st.markdown("---")
    st.subheader("🗑 Trash (auto-purges after 7 days)")

    trash_items = load_trash()
    if not trash_items:
        st.caption("Trash is empty.")
        return

    df_trash = pd.DataFrame(trash_items)
    df_trash.index = df_trash.index + 1

    cols_trash = [
        "trash_id",
        "property_name",
        "city",
        "state",
        "deal_grade",
        "deleted_at",
    ]
    cols_trash = [c for c in cols_trash if c in df_trash.columns]
    st.dataframe(df_trash[cols_trash], width='stretch')

    # Check capability for restore operations (asset:manage)
    has_restore_capability = can("asset:manage")
    
    if not has_restore_capability:
        st.info("💡 Restoring deals requires additional permissions. Contact your account admin or upgrade your plan.")
        if ENABLE_DEBUG_UI:
            st.caption("⚠️ DEV: Some actions are unavailable due to your role or plan")
    else:
        # Restore - build options using numeric trash_id from backend
        trash_ids: List[Optional[int]] = [None]
        trash_map: Dict[Optional[int], str] = {None: "None"}

        for idx, item in enumerate(trash_items):
            trash_id = item.get("trash_id")
            if trash_id is None:  # Explicit None check - 0 is valid
                continue
            name = item.get("property_name", "Unknown")
            city = item.get("city", "")
            state = item.get("state", "")
            grade = item.get("deal_grade", "—")
            label = f"{idx + 1}: {name} ({city}, {state}) – Grade {grade}"
            trash_ids.append(trash_id)
            trash_map[trash_id] = label

        def format_trash_option(trash_id: Optional[int]) -> str:
            return trash_map.get(trash_id, "Unknown")

        selected_trash_id = st.selectbox(
            "Select a deal to restore from trash",
            options=trash_ids,
            format_func=format_trash_option,
            index=0,
            key="restore_select",
        )

        if st.button("Restore from trash", disabled=(selected_trash_id is None)):
            if selected_trash_id is None:
                st.warning("Pick a deal to restore.")
            else:
                resp = api_request(
                    "POST",
                    "/property/trash/restore",
                    json={"trash_id": int(selected_trash_id)},
                    timeout=20,
                )
                if resp is None:
                    return
                if resp.status_code == 200:
                    # UX Fix Task 2: Restore from trash with immediate list refresh
                    # Set flag to refresh lists on next run (before widgets are created).
                    # This ensures the restored deal disappears from trash and reappears in portfolio.
                    st.success("Deal restored from trash.")
                    ss["_refresh_portfolio_lists"] = True
                    if IS_DEV and 'mark_key_set' in globals():
                        mark_key_set(ss, "_refresh_portfolio_lists", "restore_from_trash")
                        track_event(ss, "deal_restored", {"trash_id": selected_trash_id})
                    set_debug_cause("restore")
                    st.rerun()  # Trigger immediate UI refresh
                else:
                    # Phase 3: Use centralized error handler
                    handle_api_error(resp, "/property/trash/restore")


# --------------------------------------------------------------------
# Plans & Billing Page
# --------------------------------------------------------------------


def render_plans_billing() -> None:
    # Auth guard - stop execution if not authenticated
    if not require_auth(redirect_to_login=True):
        return
    
    st.header("Plans & Billing")
    
    # Current plan info
    auth_token = st.session_state.get('auth_token')
    if not auth_token:
        st.info("Please log in to view your plan details.")
        return
    
    try:
        resp = api_request("GET", "/account/info", timeout=10)
        if resp and resp.status_code == 200:
            account_data = resp.json()
            current_plan = account_data.get("plan", "free")
            usage = account_data.get("usage", {})
            limits = account_data.get("limits", {})
            subscription = account_data.get("subscription", {})
            
            # Extract subscription details
            sub_status = subscription.get("status", "active")
            sub_plan = subscription.get("plan", current_plan)
            effective_plan = subscription.get("effective_plan", current_plan)
            cancel_at_period_end = subscription.get("cancel_at_period_end", False)
            current_period_end = subscription.get("current_period_end")
            
            st.subheader("Current Plan")
            
            # Show subscription status warnings
            if sub_status == "past_due":
                st.error("⚠️ **Payment Required** - Your subscription is past due. Please update your payment method to restore access to paid features.")
            elif sub_status == "canceled":
                st.warning("⚠️ **Subscription Canceled** - Your subscription has been canceled. Paid features are no longer available.")
            elif cancel_at_period_end and current_period_end:
                st.warning(f"⚠️ **Scheduled for Cancellation** - Your subscription will end on {current_period_end}. Renew to maintain access.")
            elif sub_status == "trialing":
                st.info(f"🎉 **Trial Period** - You're currently on a trial. Trial ends: {current_period_end or 'Unknown'}")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.info(f"**Plan:** {effective_plan.title()}")
            with col2:
                if effective_plan == "free":
                    st.info("**Price:** Free")
                else:
                    st.info(f"**Price:** ${get_plan_price(effective_plan)}/month")
            with col3:
                # Status badge
                status_emoji = {
                    "active": "✅",
                    "trialing": "🎯",
                    "past_due": "⚠️",
                    "canceled": "❌"
                }.get(sub_status, "❓")
                st.info(f"**Status:** {status_emoji} {sub_status.replace('_', ' ').title()}")
            
            # Show downgrade notice if effective plan differs from subscription plan
            if effective_plan != sub_plan:
                st.warning(f"📉 **Limited Access**: Subscribed to {sub_plan.title()} but currently on {effective_plan.title()} due to {sub_status} status.")
            
            st.markdown("**Usage:**")
            saved_deals = usage.get("saved_deals", 0)
            max_deals = limits.get("saved_deals", 5)
            scenarios = usage.get("scenarios", 0)
            max_scenarios = limits.get("max_scenarios", 1)
            
            if max_deals == -1:
                st.caption(f"📊 Saved deals: {saved_deals} (unlimited)")
            else:
                st.caption(f"📊 Saved deals: {saved_deals}/{max_deals}")
                st.progress(min(saved_deals / max_deals, 1.0) if max_deals > 0 else 0)
            
            if max_scenarios == -1:
                st.caption(f"📈 Scenarios: {scenarios} (unlimited)")
            else:
                st.caption(f"📈 Scenarios: {scenarios}/{max_scenarios}")
                st.progress(min(scenarios / max_scenarios, 1.0) if max_scenarios > 0 else 0)
    except Exception as e:
        st.error(f"Could not load account info: {e}")
    
    st.markdown("---")
    st.subheader("Available Plans")
    
    # Plan comparison
    try:
        resp = api_request("GET", "/account/plans", timeout=10)
        if resp and resp.status_code == 200:
            plans_data = resp.json()
            plans = plans_data.get("plans", [])
            
            for plan in plans:
                with st.expander(f"**{plan['name'].title()} Plan** - ${plan['price_monthly']}/month", expanded=(plan['name'] == 'free')):
                    features = plan.get('features', {})
                    limits = plan.get('limits', {})
                    
                    st.markdown("**Features:**")
                    feature_list = []
                    if features.get('can_export_csv'): feature_list.append("✅ CSV Export")
                    else: feature_list.append("❌ CSV Export")
                    
                    if features.get('can_use_irr'): feature_list.append("✅ IRR/NPV Calculations")
                    else: feature_list.append("❌ IRR/NPV Calculations")
                    
                    if features.get('can_save_scenarios'): feature_list.append("✅ Scenario Saving")
                    else: feature_list.append("❌ Scenario Saving")
                    
                    if features.get('can_use_api'): feature_list.append("✅ API Access")
                    else: feature_list.append("❌ API Access")
                    
                    for feature in feature_list:
                        st.caption(feature)
                    
                    st.markdown("**Limits:**")
                    max_deals = limits.get('saved_deals', 0)
                    max_scenarios = limits.get('scenarios', 0)
                    
                    if max_deals == -1:
                        st.caption(f"📊 Unlimited saved deals")
                    else:
                        st.caption(f"📊 {max_deals} saved deals")
                    
                    if max_scenarios == -1:
                        st.caption(f"📈 Unlimited scenarios")
                    else:
                        st.caption(f"📈 {max_scenarios} scenarios")
                    
                    # Upgrade button
                    if plan['name'] != 'free':
                        if st.button(f"Upgrade to {plan['name'].title()}", key=f"upgrade_{plan['name']}"):
                            try:
                                upgrade_resp = api_request("POST", "/account/upgrade", json={"new_plan": plan['name']}, timeout=10)
                                if upgrade_resp and upgrade_resp.status_code == 200:
                                    st.success(f"Successfully upgraded to {plan['name'].title()} plan!")
                                    # st.rerun()
                                else:
                                    st.error("Upgrade failed. Please try again.")
                            except Exception as e:
                                st.error(f"Upgrade error: {e}")
    except Exception as e:
        st.error(f"Could not load plans: {e}")


def get_plan_price(plan_name: str) -> float:
    """Helper to get plan price."""
    prices = {
        "free": 0.0,
        "pro": 29.99,
        "team": 99.99,
        "enterprise": 299.99
    }
    return prices.get(plan_name, 0.0)


def normalize_metric(metrics: Dict[str, Any], key: str) -> Optional[float]:
    """Safely extract and normalize a metric value."""
    val = metrics.get(key)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_delta(val1: Optional[float], val2: Optional[float], is_percentage: bool = False) -> str:
    """Compute safe delta for display."""
    if val1 is None or val2 is None:
        return "n/a"
    try:
        diff = val1 - val2
        if is_percentage:
            return f"{diff * 100:.1f} pp"
        else:
            return f"${diff:,.0f}"
    except (ValueError, TypeError):
        return "n/a"


def render_login() -> None:
    # CRITICAL: Clear widget keys BEFORE creating widgets to avoid Streamlit mutation error.
    # Streamlit owns widget keys once created; we can't modify them in the same run.
    # Pattern: Set flag on success → rerun → clear keys before widget creation.
    if ss.get("_clear_login_fields"):
        ss.pop("login_email", None)
        ss.pop("login_password", None)
        ss.pop("_clear_login_fields", None)
    
    if ss.get("_clear_register_fields"):
        ss.pop("register_email", None)
        ss.pop("register_password", None)
        ss.pop("register_account_name", None)
        ss.pop("_clear_register_fields", None)
    
    if ss.get("_clear_resume_field"):
        ss.pop("resume_code_input", None)
        ss.pop("_clear_resume_field", None)
    
    st.header("Login")

    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if not email or not password:
                st.error("Please enter email and password.")
                return

            resp = api_request("POST", "/auth/login", json={"email": email, "password": password}, timeout=10)
            if resp is None:
                return
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                user = data.get("user", {})
                session_id = data.get("session_id")
                refresh_token = data.get("refresh_token")
                
                if token and session_id and refresh_token:
                    # Use centralized auth setter
                    set_auth(token, user, session_id, refresh_token)
                    
                    # Set deferred navigation to Analyzer
                    ss["_post_login_nav"] = "Analyzer"
                    if IS_DEV and 'mark_key_set' in globals():
                        mark_key_set(ss, "_post_login_nav", "login_success")
                        track_event(ss, "login_success", {"user": user.get("email", "unknown")})
                    set_debug_cause("login")
                    
                    # Set flag to clear login form fields on next run (safe pattern)
                    ss["_clear_login_fields"] = True
                    
                    # Fetch and cache capabilities after successful login
                    fetch_and_cache_capabilities()
                    st.rerun()
                else:
                    st.error("Login failed: incomplete session data.")
            else:
                st.error(f"Login failed: {resp.status_code}")
                try:
                    st.code(resp.text, language="json")
                except Exception:
                    pass

    st.divider()
    st.subheader("Register New Account")

    with st.form("register_form"):
        reg_email = st.text_input("Email", key="register_email")
        reg_password = st.text_input("Password", type="password", key="register_password")
        reg_account_name = st.text_input("Account Name", key="register_account_name")
        reg_submitted = st.form_submit_button("Register")

        if reg_submitted:
            if not reg_email or not reg_password or not reg_account_name:
                st.error("Please fill in all registration fields.")
                return

            # Call register endpoint
            resp = api_request(
                "POST",
                "/auth/register",
                json={"email": reg_email, "password": reg_password, "account_name": reg_account_name},
                timeout=10
            )
            if resp is None:
                return

            if resp.status_code in (200, 201):
                st.success("Registration successful! Logging you in...")
                # Auto-login with same credentials
                login_resp = api_request(
                    "POST", "/auth/login", json={"email": reg_email, "password": reg_password}, timeout=10
                )
                if login_resp and login_resp.status_code == 200:
                    data = login_resp.json()
                    token = data.get("access_token")
                    user = data.get("user", {})
                    session_id = data.get("session_id")
                    refresh_token = data.get("refresh_token")
                    
                    if token and session_id and refresh_token:
                        # Use centralized auth setter
                        set_auth(token, user, session_id, refresh_token)
                        
                        # Set deferred navigation to Analyzer
                        ss["_post_login_nav"] = "Analyzer"
                        if IS_DEV and 'mark_key_set' in globals():
                            mark_key_set(ss, "_post_login_nav", "register_success")
                            track_event(ss, "register_success", {"user": user.get("email", "unknown")})
                        set_debug_cause("register")
                        
                        # Set flag to clear register form fields on next run (safe pattern)
                        ss["_clear_register_fields"] = True
                        
                        # Fetch and cache capabilities after successful auto-login
                        fetch_and_cache_capabilities()
                        st.rerun()
                    else:
                        st.info("Registered. Please log in above.")
                else:
                    st.info("Registered. Please log in above.")
            else:
                st.error(f"Registration failed: {resp.status_code}")
                try:
                    st.code(resp.text, language="json")
                except Exception:
                    pass

    st.divider()
    st.subheader("Resume Session")
    st.caption("Already have a resume code? Enter it below to continue your session.")
    st.caption("⚠️ **Important**: Resume codes only work for browser refresh/rerun. If you logged out, the backend session is revoked and resume will fail. You must login again.")

    with st.form("resume_form"):
        resume_code = st.text_input("Resume Code", key="resume_code_input", placeholder="XXXX-XXXX")
        resume_submitted = st.form_submit_button("Resume")

        if resume_submitted:
            if not resume_code:
                st.error("Please enter a resume code.")
                return

            # Call resume endpoint
            resp = api_request(
                "POST",
                "/auth/resume",
                json={"resume_code": resume_code.strip()},
                timeout=10
            )
            if resp is None:
                return

            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                user = data.get("user", {})
                session_id = data.get("session_id")
                refresh_token = data.get("refresh_token")
                
                if token and session_id and refresh_token:
                    # Use centralized auth setter
                    set_auth(token, user, session_id, refresh_token)
                    
                    # Set deferred navigation to Analyzer
                    ss["_post_login_nav"] = "Analyzer"
                    if IS_DEV and 'mark_key_set' in globals():
                        mark_key_set(ss, "_post_login_nav", "resume_success")
                        track_event(ss, "resume_success", {"user": user.get("email", "unknown")})
                    set_debug_cause("resume")
                    
                    # Set flag to clear resume form field on next run (safe pattern)
                    ss["_clear_resume_field"] = True
                    
                    # Fetch and cache capabilities after successful resume
                    fetch_and_cache_capabilities()
                    st.rerun()
                else:
                    st.error("Resume failed: incomplete session data.")
            else:
                st.error(f"Resume failed: {resp.status_code}")
                try:
                    error_detail = resp.json().get("detail", resp.text)
                    st.caption(f"Details: {error_detail}")
                except Exception:
                    pass


# ============================================================================
# DEV TEST CONTROLS - VERIFICATION CHECKLIST
# ============================================================================
# 
# After implementing DEV-only test controls and widget clearing fixes:
#
# MANUAL VERIFICATION STEPS:
# 1. Start backend: uvicorn backend.main:app --reload
# 2. Start frontend: streamlit run frontend/app.py
# 3. Login page test:
#    - Enter email/password → Click Login
#    - After successful login, verify email/password fields are BLANK (not showing credentials)
#    - Navigate back to Login page → Verify fields remain blank
# 4. Register page test:
#    - Enter new account details → Click Register
#    - After successful registration + auto-login, verify all register fields are BLANK
# 5. DEV Test Controls test:
#    - After login, open sidebar → Find "🧪 DEV Test Controls" expander
#    - Verify it shows User ID and Account ID (not "Context unavailable")
#    - Verify Plan and Role selectors appear with current values
#    - Change plan to "free" → Click "Apply Plan" → Verify save buttons disappear from Analyzer
#    - Change plan to "pro" → Click "Apply Plan" → Verify save buttons reappear
#    - Change role to "read_only" → Click "Apply Role" → Verify save buttons disappear (role override)
#    - Change role to "owner" → Click "Apply Role" → Verify save buttons reappear
# 6. Navigation test:
#    - Navigate between Analyzer, Portfolio, Login pages
#    - Verify DEV Test Controls panel persists and works on each page
#    - Verify cached context is used (no repeated backend calls visible in logs)
# 7. Production safety test:
#    - Set ENV=prod or ENV=staging in environment variables
#    - Restart frontend
#    - Verify DEV Test Controls panel does NOT appear anywhere
#    - Verify login form clearing still works (not DEV-gated)
# 8. Security verification:
#    - Check backend logs → No auth tokens should be printed
#    - Check browser console → No auth tokens should be visible
#    - Check Streamlit terminal → No auth tokens in output
#
# EXPECTED BEHAVIORS:
# ✅ Login/register forms clear immediately after successful auth
# ✅ DEV Test Controls shows user/account info reliably when authenticated
# ✅ Plan/role changes update UI permissions immediately
# ✅ DEV controls are hidden in production (ENV != dev)
# ✅ No auth tokens logged anywhere
# ✅ Existing auth/tenant isolation unchanged
#
# ============================================================================


# --------------------------------------------------------------------
# Property Search Page
# --------------------------------------------------------------------

def render_property_search() -> None:
    """Render Property Search MVP page."""
    # Auth guard - stop execution if not authenticated
    if not require_auth(redirect_to_login=True):
        return
    
    ss = st.session_state
    
    st.markdown("## 🔍 Property Search")
    
    if not can("search:advanced"):
        st.warning("⚠️ Property Search requires advanced search permissions. Available in Pro+ plans.")
        st.info("Upgrade your plan to access this feature.")
        return
    
    st.markdown("### Search Criteria")
    
    # Search form in columns
    col1, col2 = st.columns(2)
    
    with col1:
        search_q = st.text_input("Address or Keyword", key="search_q", placeholder="123 Main St")
        search_city = st.text_input("City", key="search_city", placeholder="Atlanta")
    
    with col2:
        search_state = st.text_input("State", key="search_state", placeholder="GA")
        search_zip = st.text_input("ZIP Code", key="search_zip", placeholder="30301")
    
    # Optional: strategy filter (future enhancement)
    # search_strategy = st.selectbox("Strategy (Optional)", ["All", "Rental", "Flip", "BRRRR"], key="search_strategy")
    
    search_limit = st.slider("Max Results", 10, 100, 50, key="search_limit")
    
    search_button = st.button("🔍 Search Properties", key="search_submit", type="primary")
    
    # Handle search
    if search_button or ss.get("search_results"):
        if search_button:
            # Clear previous selection
            ss.pop("search_selected_property_id", None)
            
            # Build params
            params = {"limit": search_limit}
            if search_q:
                params["q"] = search_q
            if search_city:
                params["city"] = search_city
            if search_state:
                params["state"] = search_state
            if search_zip:
                params["zip"] = search_zip
            
            # Build URL with query params
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            search_url = f"/search/properties?{param_str}"
            
            # Call backend
            with st.spinner("Searching properties..."):
                resp = api_request("GET", search_url)
            
            if resp and resp.status_code == 200:
                results = resp.json()
                ss["search_results"] = results
                if results:
                    st.success(f"✅ Found {len(results)} properties")
                else:
                    st.info("No properties found matching your criteria.")
            else:
                st.error(f"Search failed: {resp.status_code if resp else 'No response'}")
                return
        
        # Display results
        results = ss.get("search_results", [])
        
        if results:
            st.markdown("### Search Results")
            
            # Convert to DataFrame for display
            df = pd.DataFrame(results)
            
            # Display as interactive table
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "property_id": "ID",
                    "address": "Address",
                    "city": "City",
                    "state": "State",
                    "zip": "ZIP",
                    "beds": "Beds",
                    "baths": "Baths",
                    "sqft": "Sq Ft",
                    "est_price": st.column_config.NumberColumn("Est. Price", format="$%.0f")
                },
                hide_index=True
            )
            
            # Property selection
            st.markdown("### Property Details")
            selected_id = st.selectbox(
                "Select property to view details",
                options=[None] + [p["property_id"] for p in results],
                format_func=lambda x: "-- Select --" if x is None else f"Property #{x}",
                key="search_selected_property_id"
            )
            
            if selected_id:
                # Find selected property
                selected = next((p for p in results if p["property_id"] == selected_id), None)
                
                if selected:
                    # Display detail panel
                    st.markdown("---")
                    
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        st.metric("Address", selected.get("address", "N/A"))
                        st.metric("City/State", f"{selected.get('city', 'N/A')}, {selected.get('state', 'N/A')}")
                    
                    with col_b:
                        st.metric("ZIP", selected.get("zip", "N/A"))
                        st.metric("Beds / Baths", f"{selected.get('beds', 0)} / {selected.get('baths', 0)}")
                    
                    with col_c:
                        st.metric("Sq Ft", f"{selected.get('sqft', 0):,}")
                        st.metric("Est. Price", f"${selected.get('est_price', 0):,.0f}")
                    
                    st.markdown("---")
                    st.markdown("### Actions")
                    
                    col_action1, col_action2 = st.columns(2)
                    
                    with col_action1:
                        analyze_btn = st.button("📊 Analyze this Property", key="search_analyze_btn", type="primary")
                        if analyze_btn:
                            # Use deferred pattern: set payload and navigate
                            ss["_apply_address_payload"] = {
                                "property_name": selected.get("address", ""),
                                "city": selected.get("city", ""),
                                "state": selected.get("state", ""),
                                "zip_code": selected.get("zip", ""),
                            }
                            ss["nav_page"] = "Analyzer"
                            st.rerun()
                    
                    with col_action2:
                        # Save as Asset (gated by asset:manage)
                        if can("asset:manage"):
                            save_asset_btn = st.button("💾 Save as Asset", key="search_save_asset_btn")
                            if save_asset_btn:
                                # Call backend to create asset
                                asset_data = {
                                    "name": selected.get("address", ""),
                                    "address": selected.get("address", ""),
                                    "city": selected.get("city", ""),
                                    "state": selected.get("state", ""),
                                    "zip_code": selected.get("zip", ""),
                                    "notes": f"Added from Property Search on {datetime.utcnow().isoformat()}"
                                }
                                
                                resp = api_request("POST", "/assets/create", json=asset_data)
                                
                                if resp and resp.status_code == 200:
                                    asset_id = resp.json().get("asset_id")
                                    st.success(f"✅ Asset #{asset_id} created successfully!")
                                else:
                                    st.error(f"Failed to create asset: {resp.status_code if resp else 'No response'}")
                        else:
                            st.button("🔒 Save as Asset", key="search_save_asset_btn_locked", disabled=True)
                            st.caption("⚠️ Requires asset management permissions. Upgrade your plan.")


# --------------------------------------------------------------------
# Assets Page
# --------------------------------------------------------------------

def render_assets() -> None:
    """Render Assets MVP page."""
    # Auth guard - stop execution if not authenticated
    if not require_auth(redirect_to_login=True):
        return
    
    ss = st.session_state
    
    # Deferred form clearing (before widgets are instantiated)
    if ss.pop("_clear_asset_create_form", False):
        ss["asset_create_name"] = ""
        ss["asset_create_address"] = ""
        ss["asset_create_city"] = ""
        ss["asset_create_state"] = ""
        ss["asset_create_zip"] = ""
        ss["asset_create_notes"] = ""
    
    st.markdown("## 📦 Assets")
    
    if not can("asset:manage"):
        st.warning("⚠️ Assets requires asset management permissions.")
        st.info("Contact your account admin or upgrade your plan to access this feature.")
        return
    
    # Load assets
    with st.spinner("Loading assets..."):
        resp = api_request("GET", "/assets/list")
    
    if not resp or resp.status_code != 200:
        st.error(f"Failed to load assets: {resp.status_code if resp else 'No response'}")
        return
    
    assets = resp.json()
    
    # Display assets list
    st.markdown(f"### Your Assets ({len(assets)})")
    
    if not assets:
        st.info("No assets yet. Create one below or save from Property Search.")
    else:
        # Convert to DataFrame
        df_assets = pd.DataFrame(assets)
        
        # Display table
        st.dataframe(
            df_assets[["asset_id", "name", "address", "city", "state", "zip_code", "created_at"]],
            use_container_width=True,
            column_config={
                "asset_id": "ID",
                "name": "Name",
                "address": "Address",
                "city": "City",
                "state": "State",
                "zip_code": "ZIP",
                "created_at": "Created"
            },
            hide_index=True
        )
        
        # Asset selection
        st.markdown("### Asset Details")
        selected_asset_id = st.selectbox(
            "Select asset to view/manage",
            options=[None] + [a["asset_id"] for a in assets],
            format_func=lambda x: "-- Select --" if x is None else f"Asset #{x}",
            key="asset_selected_id"
        )
        
        if selected_asset_id:
            # Fetch asset detail
            with st.spinner("Loading asset details..."):
                resp_detail = api_request("GET", f"/assets/get?asset_id={selected_asset_id}")
            
            if resp_detail and resp_detail.status_code == 200:
                asset = resp_detail.json()
                
                st.markdown("---")
                
                # Display asset info
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Name", asset.get("name") or "N/A")
                    st.metric("Address", asset.get("address") or "N/A")
                
                with col2:
                    st.metric("City/State", f"{asset.get('city') or 'N/A'}, {asset.get('state') or 'N/A'}")
                    st.metric("ZIP", asset.get("zip_code") or "N/A")
                
                with col3:
                    st.metric("Created", asset.get("created_at", "N/A")[:10])
                    st.metric("Updated", asset.get("updated_at", "N/A")[:10])
                
                if asset.get("notes"):
                    st.markdown(f"**Notes:** {asset['notes']}")
                
                # Related deals
                related_deals = asset.get("related_deals", [])
                if related_deals:
                    st.markdown(f"### Related Deals ({len(related_deals)})")
                    df_deals = pd.DataFrame(related_deals)
                    st.dataframe(
                        df_deals[["id", "property_name", "city", "state", "strategy", "deal_grade", "created_at"]],
                        use_container_width=True,
                        hide_index=True
                    )
                
                st.markdown("---")
                st.markdown("### Actions")
                
                # Analyze Asset button (bridge to Analyzer)
                if can("analysis:single_property"):
                    analyze_asset_btn = st.button("📊 Analyze this Asset", key="asset_analyze_btn", type="primary")
                    if analyze_asset_btn:
                        # Use deferred pattern: set payload and navigate to Analyzer
                        ss["_apply_address_payload"] = {
                            "property_name": asset.get("name") or asset.get("address") or "Asset",
                            "city": asset.get("city", ""),
                            "state": asset.get("state", ""),
                            "zip_code": asset.get("zip_code", ""),
                        }
                        ss["nav_page"] = "Analyzer"
                        st.rerun()
                else:
                    st.button("🔒 Analyze this Asset", key="asset_analyze_btn_locked", disabled=True)
                    st.caption("⚠️ Requires analysis permissions. Available in all plans.")
                
                st.markdown("---")
                st.markdown("### Manage Asset")
                
                # Edit form
                with st.expander("✏️ Edit Asset", expanded=False):
                    edit_name = st.text_input("Name", value=asset.get("name", ""), key="asset_edit_name")
                    edit_address = st.text_input("Address", value=asset.get("address", ""), key="asset_edit_address")
                    edit_city = st.text_input("City", value=asset.get("city", ""), key="asset_edit_city")
                    edit_state = st.text_input("State", value=asset.get("state", ""), key="asset_edit_state")
                    edit_zip = st.text_input("ZIP", value=asset.get("zip_code", ""), key="asset_edit_zip")
                    edit_notes = st.text_area("Notes", value=asset.get("notes", ""), key="asset_edit_notes")
                    
                    if st.button("💾 Save Changes", key="asset_edit_save"):
                        update_data = {
                            "asset_id": selected_asset_id,
                            "name": edit_name,
                            "address": edit_address,
                            "city": edit_city,
                            "state": edit_state,
                            "zip_code": edit_zip,
                            "notes": edit_notes
                        }
                        
                        resp_update = api_request("POST", "/assets/update", json=update_data)
                        
                        if resp_update and resp_update.status_code == 200:
                            st.success("✅ Asset updated successfully!")
                            st.rerun()
                        else:
                            st.error(f"Failed to update asset: {resp_update.status_code if resp_update else 'No response'}")
                
                # Delete button
                st.markdown("---")
                if st.button("🗑️ Delete Asset", key="asset_delete_btn", type="secondary"):
                    if st.checkbox(f"Confirm deletion of Asset #{selected_asset_id}", key="asset_delete_confirm"):
                        resp_delete = api_request("POST", "/assets/delete", json={"asset_id": selected_asset_id})
                        
                        if resp_delete and resp_delete.status_code == 200:
                            st.success("✅ Asset deleted successfully!")
                            ss.pop("asset_selected_id", None)
                            st.rerun()
                        else:
                            st.error(f"Failed to delete asset: {resp_delete.status_code if resp_delete else 'No response'}")
            else:
                st.error(f"Failed to load asset detail: {resp_detail.status_code if resp_detail else 'No response'}")
    
    # Create new asset
    st.markdown("---")
    st.markdown("### Create New Asset")
    
    with st.expander("➕ Create Asset", expanded=False):
        st.text_input("Name", key="asset_create_name", placeholder="My Investment Property")
        st.text_input("Address", key="asset_create_address", placeholder="123 Main St")
        st.text_input("City", key="asset_create_city", placeholder="Atlanta")
        st.text_input("State", key="asset_create_state", placeholder="GA")
        st.text_input("ZIP", key="asset_create_zip", placeholder="30301")
        st.text_area("Notes (Optional)", key="asset_create_notes")
        
        # DEV debug output
        if IS_DEV or ss.get("_enable_debug_ui"):
            create_name_val = ss.get("asset_create_name", "")
            create_address_val = ss.get("asset_create_address", "")
            create_city_val = ss.get("asset_create_city", "")
            create_state_val = ss.get("asset_create_state", "")
            st.caption(f"🐛 DEBUG: addr='{create_address_val}' ({len(create_address_val)}), city='{create_city_val}' ({len(create_city_val)}), state='{create_state_val}' ({len(create_state_val)})")
        
        if st.button("➕ Create Asset", key="asset_create_submit", type="primary"):
            # Read from session_state using widget keys (single source of truth)
            create_name = ss.get("asset_create_name", "").strip()
            create_address = ss.get("asset_create_address", "").strip()
            create_city = ss.get("asset_create_city", "").strip()
            create_state = ss.get("asset_create_state", "").strip()
            create_zip = ss.get("asset_create_zip", "").strip()
            create_notes = ss.get("asset_create_notes", "").strip()
            
            if not create_address or not create_city or not create_state:
                st.warning("⚠️ Please provide at least Address, City, and State.")
            else:
                asset_data = {
                    "name": create_name,
                    "address": create_address,
                    "city": create_city,
                    "state": create_state,
                    "zip_code": create_zip,
                    "notes": create_notes
                }
                
                resp_create = api_request("POST", "/assets/create", json=asset_data)
                
                if resp_create and resp_create.status_code == 200:
                    asset_id = resp_create.json().get("asset_id")
                    st.success(f"✅ Asset #{asset_id} created successfully!")
                    
                    # Set flag to clear form on next run (before widgets instantiate)
                    ss["_clear_asset_create_form"] = True
                    st.rerun()
                else:
                    st.error(f"Failed to create asset: {resp_create.status_code if resp_create else 'No response'}")


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------

# UX Verification Checklist (Manual Testing)
# ============================================================================
# Task 1: Login Flow
#   1. Navigate to Login page
#   2. Enter valid credentials and click Login
#   3. ✅ EXPECTED: User automatically lands on Analyzer page (not stuck on Login)
#   4. ✅ EXPECTED: No StreamlitAPIException in console
#   5. ✅ EXPECTED: Refresh/rerun shows Login if not authenticated
#
# Task 1b: Resume Session Flow
#   1. Get a resume code (from sidebar "Get Resume Code" button)
#   2. Simulate refresh: Use sidebar "Simulate Refresh" button
#   3. Enter resume code on Login page and click Resume
#   4. ✅ EXPECTED: User automatically lands on Analyzer page (not stuck on Resume form)
#   5. ✅ EXPECTED: No success message flicker
#   6. ✅ EXPECTED: Logout then resume fails (session revoked by design)
#
# Task 2: Restore from Trash Flow
#   1. Navigate to Portfolio page
#   2. Find a deal in trash section
#   3. Select deal and click "Restore from trash"
#   4. ✅ EXPECTED: Deal immediately disappears from trash dropdown
#   5. ✅ EXPECTED: Deal reappears in main portfolio list (at top)
#   6. ✅ EXPECTED: No manual refresh required
#   7. ✅ EXPECTED: Success message displays
# ============================================================================


def main() -> None:
    # ========================================================================
    # AUTH STATE INITIALIZATION (CRITICAL - DO NOT REMOVE)
    # ========================================================================
    # Initialize auth state BEFORE any widgets or logic.
    # This ensures auth keys persist across Streamlit reruns and page navigation.
    # See frontend/auth.py for implementation details and root cause analysis.
    # ========================================================================
    init_auth_state()
    
    # ========================================================================
    # CENTRALIZED DEFERRED ACTION HANDLER
    # ========================================================================
    # Apply ALL pending actions BEFORE any widgets are created.
    # This prevents Streamlit widget-key ownership conflicts.
    # 
    # Why: Once a widget is instantiated with a key, that key becomes "owned"
    # by the widget for the current run. Writing to widget-owned session_state
    # keys after widget creation causes errors or is silently ignored.
    # 
    # Solution: Set all widget-owned keys BEFORE widgets are created, then
    # rerun once so the next run creates widgets with correct state.
    # 
    # See apply_pending_actions() for details on execution order and safety.
    # ========================================================================
    
    # DEV Observability v2: Diff-based change detection (signal-only logging)
    if IS_DEV and 'detect_state_changes' in globals():
        changed, old_fp, new_fp = detect_state_changes(ss)
        
        if changed:
            # State has changed - log with cause tag
            cause = get_cause_tag(ss, default="navigation")
            
            deferred_present = [
                k for k in ["_apply_payload", "_post_login_nav", "_apply_address_payload", "_refresh_portfolio_lists"]
                if ss.get(k)
            ]
            
            details = {
                "cause": cause,
                "old_fp": old_fp,
                "new_fp": new_fp,
            }
            if deferred_present:
                details["deferred_present"] = deferred_present
            
            track_event(ss, "state_changed", details)
            update_fingerprint(ss)
        # If not changed, no log (eliminates noise)
    
    if apply_pending_actions():
        # At least one deferred action was applied.
        # Rerun ONCE so widgets are created with correct session_state.
        # No infinite loop: actions are popped (consumed) on first application.
        st.rerun()
    
    # Session rehydration guard
    # On first load, check if there's a persisted session (future: cookies, localStorage, etc.)
    # For now, we just mark rehydration as complete immediately since we don't have persistence yet.
    # This prevents protected API calls before auth state is established.
    if not ss.get("session_rehydrated"):
        # Future: Check for session cookie/token here
        # For now, just mark as complete since we rely on login flow
        ss["session_rehydration"] = True
        
        # After rehydration, if user is authenticated but capabilities not loaded,
        # fetch them once (this handles cookie-based session restoration in future)
        if is_logged_in() and not ss.get("capabilities"):
            fetch_and_cache_capabilities()

    # FIX: Set default navigation based on auth state EVERY time nav_page is missing/None
    # This ensures logged-out users ALWAYS land on Login, not Analyzer
    # 
    # CRITICAL: This must run on EVERY rerun when nav_page is None (not just first load)
    # because nav_page can be cleared/reset in various flows (logout, session expire, etc.)
    # 
    # The is_authenticated() check is deterministic: True iff access token exists and non-empty
    if not ss.get("nav_page"):
        # Set default based on current auth state
        ss["nav_page"] = "Analyzer" if is_authenticated() else "Login"
    
    # =========================================================================
    # SAFE STARTUP ROUTING DIAGNOSTICS (PRODUCTION-SAFE)
    # =========================================================================
    # Log critical routing state on EVERY rerun to stdout (never logs tokens/emails)
    # This helps diagnose "stuck on wrong page" issues without exposing sensitive data
    # =========================================================================
    _selected_page = ss.get("nav_page", "UNKNOWN")
    _token_present = bool(ss.get("auth_token"))
    _user_present = bool(ss.get("current_user"))
    _user_role = None
    if _user_present and isinstance(ss.get("current_user"), dict):
        _user_role = ss.get("current_user", {}).get("role", "NONE")
    
    # Always print to stdout (safe for production - no PII)
    print(f"[ROUTING] page={_selected_page} | token_present={_token_present} | user_present={_user_present} | role={_user_role}")
    
    # DEV-only: Also track via observability if available
    if IS_DEV and 'track_event' in globals():
        track_event(ss, "routing_state", {
            "page": _selected_page,
            "token_present": _token_present,
            "user_present": _user_present,
            "role": _user_role
        })
    # =========================================================================
    
    # Ping backend if needed (updates connection status for immediate UX feedback)
    # This runs before sidebar so status indicator updates immediately
    ping_backend_if_needed()

    # Render sidebar (updates nav_page in session_state)
    render_sidebar()
    
    # Use session_state nav_page as single source of truth for navigation
    # This fixes the "button turns blue but page doesn't change" bug
    nav_page = ss.get("nav_page", "Login")

    if nav_page == "Login":
        render_login()
    elif nav_page == "Analyzer":
        render_analyzer()
    elif nav_page == "Portfolio":
        render_portfolio_and_trash()
    elif nav_page == "Plans & Billing":
        render_plans_billing()
    elif nav_page == "Property Search":
        render_property_search()
    elif nav_page == "Assets":
        render_assets()
    else:
        # Fallback to Login for unknown pages
        ss["nav_page"] = "Login"
        render_login()


if __name__ == "__main__":
    main()
