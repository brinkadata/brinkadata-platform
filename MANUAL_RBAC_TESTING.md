# MANUAL RBAC TESTING GUIDE

## Overview
This guide describes how to test Role-Based Access Control (RBAC) and plan-based capabilities using DEV-only test controls. These controls allow you to dynamically change a user's plan and role to verify permission boundaries without weakening production security.

## CRITICAL REGRESSION TESTS

### Widget State Clearing (Streamlit)
**Test**: Login form clearing does not cause StreamlitAPIException
- Go to Login page
- Enter email/password → Click Login
- **EXPECT**: No `StreamlitAPIException` about modifying session_state
- **EXPECT**: After login succeeds and UI reruns, email/password fields are BLANK
- Return to Login page later → Fields should remain blank (no lingering credentials)

### Plan Change Immediacy (No Stale Cache)
**Test**: Plan changes take effect WITHOUT re-login
1. Login as user on free plan
2. Navigate to Analyzer → Run analysis on a property
3. **VERIFY**: Save button is hidden/disabled (free plan lacks asset:manage)
4. Open DEV Test Controls → Change plan to "pro" → Click "Apply Plan"
5. **EXPECT**: Success message shows "Capabilities updated"
6. Return to Analyzer (with same session/token)
7. **VERIFY**: Save button is NOW visible/enabled (pro plan grants asset:manage)
8. Click Save → **EXPECT**: Save succeeds (no 403 error)

**Test**: Plan downgrades immediately revoke access (SECURITY CRITICAL)
1. Start on pro plan → Save works
2. Downgrade to free via DEV Test Controls
3. **EXPECT**: Save button immediately disappears or becomes disabled
4. Try to save (if button somehow still visible) → **EXPECT**: 403 error

### Role Change Immediacy
**Test**: Role changes take effect WITHOUT re-login
1. Login as owner on pro plan → Save works
2. Change role to "read_only" via DEV Test Controls
3. **EXPECT**: Save button immediately disappears (role overrides plan)
4. Try to save → **EXPECT**: 403 error
5. Change role back to "owner" → Save button reappears

## DEV-Only Controls

### Where to Find Them
In the **Streamlit frontend sidebar**, when running in DEV environment:
1. Log in as any user
2. Look for the **"🧪 DEV Test Controls"** expander (appears only when `IS_DEV=true` or `ENABLE_DEBUG_UI=true`)
3. This panel will show:
   - Current User ID
   - Current Account ID
   - Plan selector (free/pro/team/enterprise)
   - Role selector (owner/admin/member/read_only)
   - "Apply Plan" and "Apply Role" buttons

### How to Use
1. **Select a plan** from the dropdown (e.g., "free" or "pro")
2. **Click "Apply Plan"** - this updates the account's plan in the database
3. **Select a role** from the dropdown (e.g., "owner" or "read_only")
4. **Click "Apply Role"** - this updates the user's role in the database
5. The UI will **automatically reload** and cached capabilities will be cleared
6. All permission-gated features will immediately reflect the new plan/role combination

## Security Guarantees

### Production Safety
- All test control endpoints (`/admin/set_plan`, `/admin/set_role`) are **gated by `IS_DEV` check**
- In staging/production (`ENV=staging` or `ENV=prod`), these endpoints return **403 Forbidden**
- The DEV Test Controls panel is **completely hidden** in staging/production
- No UI trigger exists to expose these controls outside of dev environment
- Existing Session Management tools remain unchanged and unaffected

### Authentication Requirements
- Test endpoints still require valid JWT authentication (they are NOT exempt from auth)
- Users must be logged in to access the test controls
- Tenant isolation remains intact (account_id scoping is preserved)

## Test Scenarios

### Scenario 1: Free Plan + Owner Role
**Setup:**
- Plan: `free`
- Role: `owner`

**Expected Behavior:**
- `asset:manage` capability = `false` (free plan doesn't allow save/delete)
- Save/delete buttons should be **hidden or disabled**
- Portfolio operations should be **blocked**
- Analysis still works (single property analysis is usually free)

### Scenario 2: Pro Plan + Owner Role
**Setup:**
- Plan: `pro`
- Role: `owner`

**Expected Behavior:**
- `asset:manage` capability = `true` (pro plan allows save/delete)
- Save/delete buttons should be **visible and enabled**
- Portfolio operations should be **allowed**
- All analysis features available
- Export CSV available (if gated by plan)

### Scenario 3: Pro Plan + Read-Only Role
**Setup:**
- Plan: `pro`
- Role: `read_only`

**Expected Behavior:**
- `asset:manage` capability = `false` (role restriction overrides plan)
- Save/delete buttons should be **hidden or disabled**
- Portfolio operations should be **blocked**
- User can only view existing data, cannot create/update/delete

### Scenario 4: Pro Plan + Member Role
**Setup:**
- Plan: `pro`
- Role: `member`

**Expected Behavior:**
- `asset:manage` capability = `true` (member has full operations on pro plan)
- Save/delete buttons should be **visible and enabled**
- Portfolio operations should be **allowed**
- Same behavior as owner for most operational tasks

## Permission Matrix

| Plan | Role | asset:manage | Expected Save/Delete | Export CSV |
|------|------|-------------|---------------------|-----------|
| free | owner | ❌ | Blocked | ❌ |
| free | admin | ❌ | Blocked | ❌ |
| free | member | ❌ | Blocked | ❌ |
| free | read_only | ❌ | Blocked | ❌ |
| pro | owner | ✅ | Allowed | ✅ |
| pro | admin | ✅ | Allowed | ✅ |
| pro | member | ✅ | Allowed | ✅ |
| pro | read_only | ❌ | Blocked | ❌ |
| team | owner | ✅ | Allowed | ✅ |
| team | admin | ✅ | Allowed | ✅ |
| team | member | ✅ | Allowed | ✅ |
| team | read_only | ❌ | Blocked | ❌ |
| enterprise | owner | ✅ | Allowed | ✅ |
| enterprise | admin | ✅ | Allowed | ✅ |
| enterprise | member | ✅ | Allowed | ✅ |
| enterprise | read_only | ❌ | Blocked | ❌ |

## API Endpoints (DEV-Only)

### POST /admin/set_plan
**Purpose:** Change account plan for testing

**Request:**
```
POST /admin/set_plan?account_id=1&plan=pro
```

**Response:**
```json
{
  "status": "ok",
  "account_id": 1,
  "plan": "pro"
}
```

**Errors:**
- `403` - Not in DEV environment
- `400` - Invalid plan name (valid: free/pro/team/enterprise)
- `404` - Account not found

### POST /admin/set_role
**Purpose:** Change user role for testing

**Request:**
```
POST /admin/set_role?user_id=1&role=read_only
```

**Response:**
```json
{
  "status": "ok",
  "user_id": 1,
  "role": "read_only"
}
```

**Errors:**
- `403` - Not in DEV environment
- `400` - Invalid role name (valid: owner/admin/member/read_only/affiliate)
- `404` - User not found

## Testing Workflow

### Quick Test Cycle
1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `streamlit run frontend/app.py`
3. Log in with any test user
4. Open "🧪 DEV Test Controls" expander in sidebar
5. Change plan to "free", apply → verify save buttons disappear
6. Change plan to "pro", apply → verify save buttons appear
7. Change role to "read_only", apply → verify save buttons disappear again
8. Change role back to "owner", apply → verify save buttons reappear

### Verification Checklist
- [ ] Free plan blocks save/delete regardless of role
- [ ] Pro plan allows save/delete for owner/admin/member roles
- [ ] Read-only role blocks save/delete regardless of plan
- [ ] Capability changes take effect immediately after applying
- [ ] UI reloads and cached capabilities are cleared
- [ ] No errors in console/logs during plan/role changes
- [ ] Test controls do NOT appear when `ENV=prod` or `ENV=staging`

## Environment Variables

To ensure test controls work correctly:

```bash
# DEV environment (test controls enabled)
ENV=dev

# Staging/Production (test controls disabled)
ENV=staging  # or ENV=prod
```

## Debugging

### Test Controls Not Appearing
- Check `ENV` variable is set to `dev`
- Verify `ENABLE_DEBUG_UI` is `True` in frontend config
- Ensure you are logged in (controls only show with auth token)

### Buttons Not Working
- Check browser console for errors
- Verify backend is running on correct port (8000)
- Check backend logs for 403/400 errors
- Ensure JWT token is valid

### Permissions Not Updating
- Verify database was updated (check SQLite directly if needed)
- Clear browser cache/session state
- Restart Streamlit to ensure clean state
- Check capability caching logic in `can()` helper

## Related Files

- Backend endpoints: [backend/main.py](backend/main.py) (lines ~1366-1430)
- Frontend panel: [frontend/app.py](frontend/app.py) (lines ~603-680)
- Capability logic: [backend/authz.py](backend/authz.py)
- RBAC definitions: [backend/rbac.py](backend/rbac.py)
- Environment config: [backend/config.py](backend/config.py), [frontend/config.py](frontend/config.py)

## Notes

- **No regression risk**: Existing auth and tenant isolation remain unchanged
- **Plan limits**: Even with test controls, plan limits (e.g., max saved deals) are still enforced
- **Refresh required**: After changing plan/role, the UI performs a full rerun to refresh capabilities
- **Database changes**: Changes are persisted to SQLite (not session-only)
- **Multi-user testing**: You can log in as different users and test their permissions independently
