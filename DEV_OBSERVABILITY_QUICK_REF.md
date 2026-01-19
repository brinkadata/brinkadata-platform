# DEV State Observability - Quick Reference

## Quick Access
1. Set `ENV=dev` in environment
2. Run: `streamlit run frontend/app.py`
3. Open sidebar → Expand "🔎 State Debug (DEV)"

## What You'll See

### Tracked Keys (12 total)
```
nav_page                    - Current page
_post_login_nav             - Deferred navigation target
_apply_payload              - Pending auth data
_apply_address_payload      - Pending address data
_refresh_portfolio_lists    - List refresh flag
session_rehydrated          - Session init status
current_user                - User data
account_id                  - Account ID
plan                        - User plan
role                        - User role
capabilities                - Permission list
auth_token                  - Auth token (REDACTED)
session_id                  - Session ID (REDACTED)
```

### Event Sources (10 types)
```
main_start                  - Start of main() run
login_success               - After successful login
register_success            - After registration
resume_success              - After resume code
token_refresh               - After auto token renewal
token_refresh_failed        - After failed refresh
preset_selection            - When preset applied
scenario_load               - When scenario loaded
restore_from_trash          - When deal restored
deferred_keys_applied       - After deferred processing
```

## Quick Debug Workflow

### Check Current State
```
1. Expand State Debug UI
2. Look for your key in the table
3. Check value (redacted if sensitive)
4. Check source + timestamp
```

### Track a Flow
```
1. Clear history (optional)
2. Perform action (e.g., login)
3. Check Recent Events
4. Verify expected events appear
5. Check state changes
```

### Export Diagnostics
```
1. Click "📋 Copy Snapshot"
2. Copy JSON from text area
3. Search for sensitive data (should be "[REDACTED]")
4. Share with team
```

### Clear Debug Data
```
1. Click "🗑️ Clear History"
2. Confirms: "Debug history cleared"
3. Only clears _dev_events and _dev_key_meta
4. Does NOT affect auth_token, session_id, etc.
```

## Security Checklist

**MUST Be Redacted**:
- ❌ auth_token → "[REDACTED]"
- ❌ refresh_token → "[REDACTED]"
- ❌ resume_code → "[REDACTED]"
- ❌ password → "[REDACTED]"

**Partial Redaction OK**:
- ✅ session_id → "…a9f2"
- ✅ account_id → "…1234"

**Fully Visible OK**:
- ✅ nav_page → "Analyzer"
- ✅ plan → "free"
- ✅ role → "owner"
- ✅ current_user → {"email": "..."}

## Common Issues

**UI Not Visible**
→ Check `ENV=dev` or `ENABLE_DEBUG_UI=True`

**Events Not Recording**
→ Check `IS_DEV=True` in console logs

**Token Visible**
→ CRITICAL: Add to SENSITIVE_KEYS immediately

**State Missing**
→ OK if not set yet; check after triggering action

## Test Commands

```bash
# Run unit tests
cd frontend
python -m pytest test_dev_observability.py -v

# Check syntax
python -m py_compile frontend/app.py
python -m py_compile frontend/dev_observability.py

# Start app (dev mode)
ENV=dev streamlit run frontend/app.py
```

## Files to Check

```
frontend/dev_observability.py   - Core module
frontend/app.py                  - Integration hooks
frontend/test_dev_observability.py - Unit tests
MANUAL_DEV_STATE_DEBUG.md        - Full testing guide
DEV_OBSERVABILITY_IMPLEMENTATION.md - Implementation summary
```

## Key Code Patterns

### Track an Event
```python
if IS_DEV and 'track_event' in globals():
    track_event(ss, "event_name", {"detail_key": "value"})
```

### Mark Key Set
```python
if IS_DEV and 'mark_key_set' in globals():
    mark_key_set(ss, "key_name", "source_tag")
```

### Both Together
```python
ss["_apply_payload"] = {
    "auth_token": token,
    "current_user": user,
}
if IS_DEV and 'mark_key_set' in globals():
    mark_key_set(ss, "_apply_payload", "login_success")
    track_event(ss, "login_success", {"user": user.get("email")})
```

---

**Need Help?** See [MANUAL_DEV_STATE_DEBUG.md](MANUAL_DEV_STATE_DEBUG.md) for detailed scenarios.
