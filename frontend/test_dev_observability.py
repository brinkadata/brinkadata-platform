# frontend/test_dev_observability.py
# Unit tests for DEV state observability module

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from frontend.dev_observability import (
    redact_value,
    track_event,
    mark_key_set,
    snapshot_state,
    get_recent_events,
    clear_debug_history,
    export_snapshot_json,
    compute_state_fingerprint,
    detect_state_changes,
    update_fingerprint,
    get_cause_tag,
    set_cause_tag,
)


def test_redact_sensitive_keys():
    """Sensitive keys should be fully redacted."""
    assert redact_value("auth_token", "abc123") == "[REDACTED]"
    assert redact_value("refresh_token", "xyz789") == "[REDACTED]"
    assert redact_value("password", "secret123") == "[REDACTED]"
    assert redact_value("login_password", "hunter2") == "[REDACTED]"
    assert redact_value("resume_code", "R123456") == "[REDACTED]"
    assert redact_value("session_id", "s12345") == "[REDACTED]"


def test_redact_id_fields():
    """ID fields should show last 4 chars only."""
    # Note: session_id is in SENSITIVE_KEYS, so it gets full redaction
    # But other id fields should get partial redaction
    result = redact_value("user_id", "user_123456789")
    assert result == "…6789"
    
    result = redact_value("account_id", "acct_abcdefgh")
    assert result == "…efgh"


def test_non_sensitive_keys():
    """Non-sensitive keys should pass through unchanged."""
    assert redact_value("nav_page", "Analyzer") == "Analyzer"
    assert redact_value("plan", "free") == "free"
    assert redact_value("role", "owner") == "owner"
    assert redact_value("current_user", {"email": "test@example.com"}) == {"email": "test@example.com"}


def test_track_event_basic():
    """track_event should append to _dev_events list."""
    ss = {}
    track_event(ss, "test_event")
    
    assert "_dev_events" in ss
    assert len(ss["_dev_events"]) == 1
    assert ss["_dev_events"][0]["name"] == "test_event"
    assert "ts" in ss["_dev_events"][0]


def test_track_event_with_details():
    """track_event should redact sensitive details."""
    ss = {}
    track_event(ss, "login_success", {"user": "alice@example.com", "auth_token": "secret123"})
    
    event = ss["_dev_events"][0]
    assert event["name"] == "login_success"
    assert event["details"]["user"] == "alice@example.com"
    assert event["details"]["auth_token"] == "[REDACTED]"


def test_track_event_truncation():
    """Event list should truncate to last 100 events."""
    ss = {}
    
    # Add 150 events
    for i in range(150):
        track_event(ss, f"event_{i}")
    
    # Should only keep last 100
    assert len(ss["_dev_events"]) == 100
    assert ss["_dev_events"][0]["name"] == "event_50"  # First event should be #50
    assert ss["_dev_events"][-1]["name"] == "event_149"  # Last event should be #149


def test_mark_key_set():
    """mark_key_set should record key metadata."""
    ss = {}
    mark_key_set(ss, "_apply_payload", "login_success")
    
    assert "_dev_key_meta" in ss
    assert "_apply_payload" in ss["_dev_key_meta"]
    assert ss["_dev_key_meta"]["_apply_payload"]["source"] == "login_success"
    assert "ts" in ss["_dev_key_meta"]["_apply_payload"]


def test_snapshot_state_with_values():
    """snapshot_state should create redacted snapshot of specified keys."""
    ss = {
        "nav_page": "Analyzer",
        "auth_token": "secret123",
        "plan": "free",
        "_dev_key_meta": {
            "nav_page": {"source": "login_success", "ts": "2026-01-16T10:00:00.000Z"},
        },
    }
    
    keys = ["nav_page", "auth_token", "plan", "nonexistent_key"]
    snapshot = snapshot_state(ss, keys)
    
    # Check existing keys
    assert snapshot["nav_page"]["exists"] is True
    assert snapshot["nav_page"]["value"] == "Analyzer"
    assert snapshot["nav_page"]["meta"]["source"] == "login_success"
    
    assert snapshot["auth_token"]["exists"] is True
    assert snapshot["auth_token"]["value"] == "[REDACTED]"
    
    assert snapshot["plan"]["exists"] is True
    assert snapshot["plan"]["value"] == "free"
    
    # Check nonexistent key
    assert snapshot["nonexistent_key"]["exists"] is False


def test_get_recent_events():
    """get_recent_events should return limited list in reverse order."""
    ss = {}
    
    for i in range(10):
        track_event(ss, f"event_{i}")
    
    recent = get_recent_events(ss, limit=5)
    
    assert len(recent) == 5
    # Should be most recent first
    assert recent[0]["name"] == "event_9"
    assert recent[-1]["name"] == "event_5"


def test_clear_debug_history():
    """clear_debug_history should remove only debug data."""
    ss = {
        "nav_page": "Analyzer",
        "auth_token": "secret123",
        "_dev_events": [{"name": "test"}],
        "_dev_key_meta": {"nav_page": {"source": "test"}},
    }
    
    clear_debug_history(ss)
    
    # Debug data should be cleared
    assert ss["_dev_events"] == []
    assert ss["_dev_key_meta"] == {}
    
    # App data should remain
    assert ss["nav_page"] == "Analyzer"
    assert ss["auth_token"] == "secret123"


def test_export_snapshot_json():
    """export_snapshot_json should produce valid JSON."""
    ss = {
        "nav_page": "Analyzer",
        "auth_token": "secret123",
        "_dev_events": [{"name": "test_event", "ts": "2026-01-16T10:00:00.000Z"}],
        "_dev_key_meta": {
            "nav_page": {"source": "test", "ts": "2026-01-16T10:00:00.000Z"},
        },
    }
    
    keys = ["nav_page", "auth_token"]
    json_str = export_snapshot_json(ss, keys)
    
    # Should be valid JSON
    import json
    data = json.loads(json_str)
    
    assert "timestamp" in data
    assert "state" in data
    assert "recent_events" in data
    assert "change_detection" in data
    
    # Verify redaction
    assert data["state"]["auth_token"]["value"] == "[REDACTED]"
    assert data["state"]["nav_page"]["value"] == "Analyzer"


def test_compute_state_fingerprint():
    """compute_state_fingerprint should create stable hash."""
    ss1 = {
        "nav_page": "Analyzer",
        "account_id": 123,
        "role": "owner",
        "plan": "free",
    }
    
    ss2 = {
        "nav_page": "Analyzer",
        "account_id": 123,
        "role": "owner",
        "plan": "free",
    }
    
    fp1 = compute_state_fingerprint(ss1)
    fp2 = compute_state_fingerprint(ss2)
    
    # Same state should produce same fingerprint
    assert fp1 == fp2
    assert len(fp1) == 12  # Short hash
    
    # Different state should produce different fingerprint
    ss3 = ss2.copy()
    ss3["plan"] = "pro"
    fp3 = compute_state_fingerprint(ss3)
    assert fp3 != fp1


def test_detect_state_changes():
    """detect_state_changes should detect when state changes."""
    ss = {"nav_page": "Analyzer"}
    
    # First check - no previous fingerprint
    changed, old_fp, new_fp = detect_state_changes(ss)
    assert changed is True
    assert old_fp is None
    assert new_fp is not None
    
    # Update fingerprint
    update_fingerprint(ss)
    
    # Second check - no change
    changed, old_fp, new_fp = detect_state_changes(ss)
    assert changed is False
    assert old_fp == new_fp
    
    # Change state
    ss["nav_page"] = "Portfolio"
    changed, old_fp, new_fp = detect_state_changes(ss)
    assert changed is True
    assert old_fp != new_fp


def test_cause_tags():
    """set_cause_tag and get_cause_tag should work correctly."""
    ss = {}
    
    # Set cause
    set_cause_tag(ss, "login")
    assert ss["_debug_cause"] == "login"
    
    # Get cause (should clear it)
    cause = get_cause_tag(ss)
    assert cause == "login"
    assert "_debug_cause" not in ss
    
    # Get default cause
    cause = get_cause_tag(ss, default="navigation")
    assert cause == "navigation"


def test_fingerprint_excludes_sensitive_data():
    """Fingerprint should not include auth tokens or session IDs."""
    ss = {
        "nav_page": "Analyzer",
        "auth_token": "secret_token_123",
        "session_id": "session_abc",
        "account_id": 123,
    }
    
    fp = compute_state_fingerprint(ss)
    
    # Changing tokens should not change fingerprint
    ss["auth_token"] = "different_token_456"
    ss["session_id"] = "different_session_xyz"
    fp2 = compute_state_fingerprint(ss)
    
    assert fp == fp2  # Should be same since tokens not included


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
