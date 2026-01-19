# frontend/dev_observability.py
# DEV-only state observability for debugging session state in Streamlit

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Sensitive keys that must be redacted
SENSITIVE_KEYS = {
    "auth_token",
    "refresh_token",
    "resume_code",
    "password",
    "session_id",
    "login_password",
    "register_password",
    "_jwt",
    "jwt",
    "token",
    "secret",
    "api_key",
}


def redact_value(key: str, value: Any) -> Any:
    """
    Redact sensitive values.
    - If key is sensitive: return "[REDACTED]"
    - If key contains "id" or "session" in name: return last 4 chars (e.g., "…a9f2")
    - Otherwise: return actual value
    """
    key_lower = key.lower()
    
    # Full redaction for known sensitive keys
    if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
        return "[REDACTED]"
    
    # Partial redaction for IDs
    if ("id" in key_lower or "session" in key_lower) and isinstance(value, str) and len(value) > 4:
        return f"…{value[-4:]}"
    
    # Safe to display
    return value


def now_iso() -> str:
    """Return current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def compute_state_fingerprint(session_state: dict) -> str:
    """
    Compute a stable fingerprint of critical session state for change detection.
    
    Includes:
    - nav_page
    - session_rehydrated
    - current_user (id, account_id, role - NOT email)
    - Canonical keys (account_id, role, plan)
    - capabilities (plan, role, list length)
    - Deferred key presence (booleans only)
    
    DOES NOT include:
    - auth_token, session_id, passwords (security)
    - Timestamps (would cause false changes)
    - Full user objects (too noisy)
    
    Returns:
        Short hash string (first 12 chars of SHA256)
    """
    fingerprint_data = {
        "nav_page": session_state.get("nav_page"),
        "session_rehydrated": session_state.get("session_rehydrated"),
        "account_id": session_state.get("account_id"),
        "role": session_state.get("role"),
        "plan": session_state.get("plan"),
    }
    
    # Extract minimal current_user info (no email/PII)
    current_user = session_state.get("current_user")
    if current_user and isinstance(current_user, dict):
        fingerprint_data["user_account_id"] = current_user.get("account_id")
        fingerprint_data["user_role"] = current_user.get("role")
        # Use id if present, but don't include email
        fingerprint_data["user_id"] = current_user.get("id")
    
    # Extract minimal capabilities info
    capabilities = session_state.get("capabilities")
    if capabilities and isinstance(capabilities, dict):
        fingerprint_data["cap_plan"] = capabilities.get("plan")
        fingerprint_data["cap_role"] = capabilities.get("role")
        cap_list = capabilities.get("list", [])
        fingerprint_data["cap_count"] = len(cap_list) if isinstance(cap_list, list) else 0
    
    # Deferred key presence (boolean only, not values)
    fingerprint_data["has_apply_payload"] = "_apply_payload" in session_state
    fingerprint_data["has_post_login_nav"] = "_post_login_nav" in session_state
    fingerprint_data["has_apply_address"] = "_apply_address_payload" in session_state
    fingerprint_data["has_refresh_lists"] = "_refresh_portfolio_lists" in session_state
    
    # Convert to stable JSON string and hash
    json_str = json.dumps(fingerprint_data, sort_keys=True, default=str)
    hash_obj = hashlib.sha256(json_str.encode())
    return hash_obj.hexdigest()[:12]  # Short hash for readability


def detect_state_changes(session_state: dict) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Detect if session state has changed since last check.
    
    Returns:
        (changed, old_fingerprint, new_fingerprint)
        - changed: True if state changed
        - old_fingerprint: Previous fingerprint (or None if first run)
        - new_fingerprint: Current fingerprint
    """
    new_fingerprint = compute_state_fingerprint(session_state)
    old_fingerprint = session_state.get("_debug_last_fingerprint")
    
    if old_fingerprint is None:
        # First run or no previous fingerprint
        return True, None, new_fingerprint
    
    changed = (new_fingerprint != old_fingerprint)
    return changed, old_fingerprint, new_fingerprint


def update_fingerprint(session_state: dict) -> None:
    """
    Update stored fingerprint after logging a change.
    """
    new_fingerprint = compute_state_fingerprint(session_state)
    session_state["_debug_last_fingerprint"] = new_fingerprint
    session_state["_debug_last_change_time"] = now_iso()


def get_cause_tag(session_state: dict, default: str = "navigation") -> str:
    """
    Get and clear the cause tag for this state change.
    
    Args:
        session_state: Session state dict
        default: Default cause if none set
    
    Returns:
        Cause string (e.g., "login", "resume", "restore")
    """
    cause = session_state.get("_debug_cause", default)
    # Clear cause after reading (one-time use)
    if "_debug_cause" in session_state:
        del session_state["_debug_cause"]
    return cause


def set_cause_tag(session_state: dict, cause: str) -> None:
    """
    Set a cause tag before a state-changing action.
    
    Should be called BEFORE st.rerun() to explain why the state is changing.
    
    Args:
        session_state: Session state dict
        cause: Short cause string (e.g., "login", "restore", "dev_plan_change")
    """
    session_state["_debug_cause"] = cause


def track_event(session_state: dict, event_name: str, details: Optional[Dict[str, Any]] = None) -> None:
    """
    Append an event to the session event timeline.
    
    Args:
        session_state: Streamlit session_state dict
        event_name: Short descriptive name (e.g., "login_success", "deferred_keys_applied")
        details: Optional dict of additional context (will be redacted)
    """
    if "_dev_events" not in session_state:
        session_state["_dev_events"] = []
    
    event = {
        "ts": now_iso(),
        "name": event_name,
    }
    
    if details:
        # Redact sensitive details
        redacted_details = {k: redact_value(k, v) for k, v in details.items()}
        event["details"] = redacted_details
    
    session_state["_dev_events"].append(event)
    
    # Keep only last 100 events to prevent memory bloat
    if len(session_state["_dev_events"]) > 100:
        session_state["_dev_events"] = session_state["_dev_events"][-100:]


def mark_key_set(session_state: dict, key: str, source: str) -> None:
    """
    Record metadata about when a key was set and by whom.
    
    Args:
        session_state: Streamlit session_state dict
        key: The session_state key being set
        source: Short tag describing the origin (e.g., "login_success", "preset_selection")
    """
    if "_dev_key_meta" not in session_state:
        session_state["_dev_key_meta"] = {}
    
    session_state["_dev_key_meta"][key] = {
        "source": source,
        "ts": now_iso(),
    }


def snapshot_state(session_state: dict, keys_of_interest: List[str]) -> Dict[str, Any]:
    """
    Create a redacted snapshot of current session state for debugging.
    
    Args:
        session_state: Streamlit session_state dict
        keys_of_interest: List of keys to include in snapshot
    
    Returns:
        Dict with redacted values and metadata
    """
    snapshot = {}
    key_meta = session_state.get("_dev_key_meta", {})
    
    for key in keys_of_interest:
        if key in session_state:
            value = session_state[key]
            redacted = redact_value(key, value)
            
            entry = {
                "value": redacted,
                "exists": True,
            }
            
            # Add metadata if available
            if key in key_meta:
                entry["meta"] = key_meta[key]
            
            snapshot[key] = entry
        else:
            snapshot[key] = {"exists": False}
    
    return snapshot


def get_recent_events(session_state: dict, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Get the most recent events from the timeline.
    
    Args:
        session_state: Streamlit session_state dict
        limit: Maximum number of events to return
    
    Returns:
        List of event dicts (most recent first)
    """
    events = session_state.get("_dev_events", [])
    return list(reversed(events[-limit:]))


def clear_debug_history(session_state: dict) -> None:
    """
    Clear debug history (events and key metadata) without affecting app state.
    
    Args:
        session_state: Streamlit session_state dict
    """
    if "_dev_events" in session_state:
        session_state["_dev_events"] = []
    if "_dev_key_meta" in session_state:
        session_state["_dev_key_meta"] = {}


def export_snapshot_json(session_state: dict, keys_of_interest: List[str]) -> str:
    """
    Export a full diagnostic snapshot as formatted JSON string.
    
    Args:
        session_state: Streamlit session_state dict
        keys_of_interest: Keys to include in state snapshot
    
    Returns:
        JSON string with snapshot and recent events
    """
    snapshot = snapshot_state(session_state, keys_of_interest)
    events = get_recent_events(session_state, limit=50)
    
    # Add change detection metadata
    changed, old_fp, new_fp = detect_state_changes(session_state)
    last_change_time = session_state.get("_debug_last_change_time")
    # Peek at cause without consuming (display only - will be consumed on next state_changed event)
    pending_cause = session_state.get("_debug_cause", "none")
    
    export = {
        "timestamp": now_iso(),
        "state": snapshot,
        "recent_events": events,
        "change_detection": {
            "changed_since_last": changed,
            "old_fingerprint": old_fp,
            "new_fingerprint": new_fp,
            "last_change_time": last_change_time,
            "pending_cause": pending_cause,
        }
    }
    
    return json.dumps(export, indent=2)
