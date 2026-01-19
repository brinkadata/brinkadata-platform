# Manual Testing Guide: DEV State Observability

## Overview
This guide describes how to use the DEV-only state observability feature for debugging session state and deferred navigation behaviors in Brinkadata.

**IMPORTANT**: This feature is only available when `ENABLE_DEBUG_UI = True` (i.e., in development environment).

---

## Accessing State Debug UI

1. **Start the application** in DEV mode:
   ```bash
   # Backend
   uvicorn backend.main:app --reload
   
   # Frontend (in separate terminal)
   streamlit run frontend/app.py
   ```

2. **Open the sidebar** in the Streamlit UI

3. **Locate the "🔎 State Debug (DEV)" expander** at the bottom of the sidebar (below Presets & Market section)

4. **Expand it** to view state diagnostics

---

## What You'll See

### Current State Table
Shows the current value of tracked keys:
- `nav_page` - Current page
- `_post_login_nav` - Deferred navigation target
- `_apply_payload` - Pending auth payload
- `_apply_address_payload` - Pending address data
- `_refresh_portfolio_lists` - List refresh flag
- `session_rehydrated` - Session initialization status
- `current_user` - User data (email redacted)
- `account_id` - Account identifier (partial)
- `plan`, `role`, `capabilities` - User permissions
- `auth_token`, `session_id` - Auth tokens (REDACTED)

Each entry shows:
- **Value**: Current value (sensitive data redacted)
- **Source**: Who set it (e.g., "login_success", "preset_selection")
- **Timestamp**: When it was set (UTC, HH:MM:SS format)

### Recent Events Timeline
Shows last 10 events (max 30 stored), each with:
- **Timestamp** (HH:MM:SS format)
- **Event name** (e.g., "main_start", "login_success", "deferred_keys_applied")
- **Details** (optional context, redacted if sensitive)

### Action Buttons
- **📋 Copy Snapshot**: Exports full diagnostic JSON (includes state + 50 recent events)
- **🗑️ Clear History**: Clears event timeline and key metadata (does NOT affect app state)

---

## Testing Scenarios

### Scenario 1: Login Navigation Flow
**Purpose**: Verify that login correctly navigates to Analyzer page

1. Start on Login page (logged out)
2. Open State Debug expander
3. Enter credentials and click "Login"
4. **Observe**:
   - Event: "login_success" should appear
   - State: `_apply_payload` set with source="login_success"
   - State: `_post_login_nav` set to "Analyzer"
   - Event: "main_start" should show deferred keys present
   - Event: "deferred_keys_applied" should show keys=["_apply_payload", "_post_login_nav"]
   - State: `nav_page` changes to "Analyzer"
5. **Verify**:
   - You are now on Analyzer page
   - `_apply_payload` and `_post_login_nav` are no longer in state (consumed)
   - `auth_token` shows "[REDACTED]"
   - `session_id` shows "…XXXX" (last 4 chars)

### Scenario 2: Preset Selection
**Purpose**: Verify ZIP code and address fields populate correctly

1. Navigate to Analyzer page (logged in)
2. Open State Debug expander
3. In sidebar, select preset "Balanced rental (baseline)"
4. Click "Apply preset"
5. **Observe**:
   - Event: "preset_applied" with preset name
   - State: `_apply_address_payload` set with source="preset_selection"
   - After rerun, address fields should be populated
   - `_apply_address_payload` consumed (no longer in state)
6. **Verify**:
   - Property name, city, state, ZIP are all filled
   - No secrets are visible in debug UI

### Scenario 3: Restore from Trash
**Purpose**: Verify portfolio list refresh works correctly

1. Navigate to Portfolio & Trash page (logged in)
2. Delete a deal (moves to trash)
3. Open State Debug expander
4. Click "Restore from trash" button
5. **Observe**:
   - Event: "deal_restored" with trash_id
   - State: `_refresh_portfolio_lists` set with source="restore_from_trash"
   - After rerun, deal reappears in portfolio
   - `_refresh_portfolio_lists` consumed
6. **Verify**:
   - Deal is back in portfolio list
   - Deal is gone from trash list
   - No duplicate entries

### Scenario 4: Token Refresh
**Purpose**: Verify automatic token refresh on 401

1. Wait for access token to expire (~15 min) OR manually invalidate token in backend
2. Make any protected API call (e.g., save a deal)
3. Open State Debug expander
4. **Observe**:
   - Event: "token_refresh" or similar
   - State: `_apply_payload` set with source="token_refresh"
   - New tokens applied automatically
5. **Verify**:
   - Operation succeeded (no logout)
   - `auth_token` remains "[REDACTED]"
   - No raw tokens visible

### Scenario 5: Resume Code
**Purpose**: Verify resume flow sets session correctly

1. Logout (if logged in)
2. Navigate to Login page
3. Expand "Resume Session" section
4. Enter a valid resume code
5. Click "Resume"
6. Open State Debug expander
7. **Observe**:
   - Event: "resume_success"
   - State: `_apply_payload` with source="resume_success"
   - State: `_post_login_nav` set
   - Navigation to Analyzer
8. **Verify**:
   - Resume code is NOT visible in state (never stored)
   - Auth tokens are redacted
   - Session is fully restored

---

## Security Verification

**CRITICAL**: Confirm no secrets are leaked

### What MUST Be Redacted
- `auth_token` → "[REDACTED]"
- `refresh_token` → "[REDACTED]"
- `resume_code` → "[REDACTED]" (if ever stored, which it shouldn't be)
- `password` → "[REDACTED]"
- Any key with "token", "secret", "password", "jwt" in name

### What Can Be Partially Visible
- `session_id` → "…a9f2" (last 4 chars only)
- `account_id` → "…1234" (last 4 chars only)

### What Can Be Fully Visible
- `nav_page`, `plan`, `role`
- `current_user` → Email and non-sensitive fields OK
- `capabilities` → List of capability strings OK
- Deferred key names (not their auth token values)

### Manual Check Steps
1. Open State Debug expander
2. Click "Copy Snapshot" button
3. Review the JSON output in text area
4. **Search for** (should NOT find exact matches):
   - Your actual auth token
   - Your actual refresh token
   - Your password
5. **Verify** you only see:
   - "[REDACTED]" for sensitive keys
   - "…XXXX" for IDs
   - Actual values for safe keys

---

## Troubleshooting

### Debug UI Not Visible
- **Check**: `ENABLE_DEBUG_UI` in [frontend/config.py](frontend/config.py)
- **Check**: `ENV` environment variable (should be "dev")
- **Fix**: Set `ENV=dev` or ensure `IS_DEV = True` in config

### Events Not Recording
- **Check**: `IS_DEV` is True
- **Check**: `track_event` and `mark_key_set` functions are imported
- **Check**: Browser console for JavaScript errors
- **Fix**: Restart Streamlit app

### Snapshot Shows Errors
- **Check**: All KEYS_OF_INTEREST exist in session_state (OK if missing)
- **Check**: `_dev_events` and `_dev_key_meta` are lists/dicts
- **Fix**: Click "Clear History" button

### Sensitive Data Visible
- **STOP**: This is a security issue
- **Check**: Key name is in `SENSITIVE_KEYS` set in [dev_observability.py](frontend/dev_observability.py)
- **Fix**: Add key to `SENSITIVE_KEYS` set
- **Test**: Verify redaction works

---

## Cleanup After Testing

1. **Clear debug history** using "🗑️ Clear History" button (optional)
2. **Logout** to clear session
3. **Verify** no sensitive data persists in browser DevTools → Application → Session Storage

---

## Integration with Existing Tests

This DEV observability is complementary to:
- [MANUAL_CAPABILITY_VERIFICATION.md](MANUAL_CAPABILITY_VERIFICATION.md) - RBAC testing
- [MANUAL_SECURITY_TESTS.md](MANUAL_SECURITY_TESTS.md) - Auth/authz testing
- [MANUAL_TENANT_GUARDS.md](MANUAL_TENANT_GUARDS.md) - Multi-tenancy testing

Use State Debug to:
- Diagnose navigation issues during manual tests
- Verify deferred key consumption
- Confirm token refresh behaviors
- Debug session state corruption

---

## Future Enhancements

Potential improvements (not currently implemented):
- Export to file instead of text area
- Filter events by type
- Search/filter state keys
- Diff between snapshots
- Persist event log to backend (DEV only)
