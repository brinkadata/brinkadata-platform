# Manual Test Checklist for Environment-Based Auth/Resume

## Setup

### Test in DEV environment (default):
```powershell
# No ENV variable set (defaults to dev)
uvicorn backend.main:app --reload
streamlit run frontend/app.py
```

### Test in STAGING environment:
```powershell
$env:ENV="staging"
uvicorn backend.main:app --reload

# In another terminal:
$env:ENV="staging"
streamlit run frontend/app.py
```

### Test in PROD environment:
```powershell
$env:ENV="prod"
uvicorn backend.main:app --reload

# In another terminal:
$env:ENV="prod"
streamlit run frontend/app.py
```

---

## Test Cases

### 1. Environment Detection (All Envs)

**Backend:**
- [ ] On startup, backend prints `[CONFIG] Environment: dev|staging|prod`
- [ ] Backend prints token lifetimes from config
- [ ] CORS origins are restricted in prod (not `["*"]`)

**Frontend:**
- [ ] On startup, frontend prints `[CONFIG] Environment: dev|staging|prod`
- [ ] Frontend prints Backend URL
- [ ] Frontend prints Debug UI status

---

### 2. DEBUG UI Visibility

**DEV Environment:**
- [ ] Login successfully
- [ ] Sidebar shows "Session Management" section
- [ ] "🔑 Get Resume Code" button is visible
- [ ] "🔄 Simulate Refresh (DEBUG)" button is **VISIBLE**
- [ ] "🚪 Logout" button is visible
- [ ] Sidebar shows "Auth token present: Yes" caption

**STAGING Environment:**
- [ ] Login successfully
- [ ] "🔑 Get Resume Code" button is visible
- [ ] "🔄 Simulate Refresh (DEBUG)" button is **NOT VISIBLE**
- [ ] "🚪 Logout" button is visible
- [ ] "Auth token present" caption is **NOT VISIBLE**

**PROD Environment:**
- [ ] Login successfully
- [ ] "🔑 Get Resume Code" button is visible
- [ ] "🔄 Simulate Refresh (DEBUG)" button is **NOT VISIBLE**
- [ ] "🚪 Logout" button is visible
- [ ] "Auth token present" caption is **NOT VISIBLE**

---

### 3. Session Rehydration Guard (All Envs)

**Cold Start:**
- [ ] Open fresh browser/clear cache
- [ ] Navigate to app
- [ ] On first load, `session_rehydrated` is False
- [ ] After rehydration check, `session_rehydrated` becomes True
- [ ] No protected API calls (e.g., `/account/info`) made before rehydration completes
- [ ] No infinite rerun loops
- [ ] Login page renders correctly

**After Login:**
- [ ] Login successfully
- [ ] `session_rehydrated` is True
- [ ] `/account/info` is called successfully
- [ ] Usage stats display in sidebar
- [ ] No errors in console

---

### 4. Resume Flow (DEV only - with Simulate Refresh)

**Successful Resume:**
- [ ] Login with credentials
- [ ] Click "🔑 Get Resume Code"
- [ ] Resume code displays (e.g., "ABCD-EFGH1234")
- [ ] Caption shows expiration time from config (e.g., "10 minutes")
- [ ] Copy the resume code
- [ ] Click "🔄 Simulate Refresh (DEBUG)"
- [ ] App redirects to Login page
- [ ] Paste resume code into "Resume Session" form
- [ ] Click "Resume" button
- [ ] ✅ Session restored successfully
- [ ] Redirects to Analyzer page
- [ ] Can perform analysis, save deals, access portfolio

**Resume After Logout (Must Fail):**
- [ ] Login with credentials
- [ ] Click "🔑 Get Resume Code"
- [ ] Copy the resume code
- [ ] Click "🚪 Logout"
- [ ] Backend prints session revoked
- [ ] Paste resume code into "Resume Session" form
- [ ] Click "Resume" button
- [ ] ❌ Error: "Session revoked" (401)
- [ ] Must login again with credentials

---

### 5. Resume Flow (STAGING/PROD - without Simulate Refresh)

**Note:** In staging/prod, "Simulate Refresh" button is hidden.
To test resume flow, use actual browser refresh (Ctrl+R / F5):

**Resume After Browser Refresh:**
- [ ] Login with credentials
- [ ] Click "🔑 Get Resume Code"
- [ ] Copy the resume code
- [ ] Perform actual browser refresh (Ctrl+R)
- [ ] Session state cleared (tokens lost)
- [ ] Login page shows
- [ ] Paste resume code into "Resume Session" form
- [ ] Click "Resume" button
- [ ] ✅ Session restored successfully

**Resume After Logout (Must Fail):**
- [ ] Login with credentials
- [ ] Click "🔑 Get Resume Code"
- [ ] Copy the resume code
- [ ] Click "🚪 Logout"
- [ ] Paste resume code into "Resume Session" form
- [ ] Click "Resume" button
- [ ] ❌ Error: "Session revoked"

---

### 6. Token Lifetimes (All Envs)

**Config Defaults:**
- [ ] ACCESS_TOKEN_MINUTES = 15 (unless overridden)
- [ ] REFRESH_TOKEN_DAYS = 7 (unless overridden)
- [ ] RESUME_CODE_MINUTES = 10 (unless overridden)

**Custom Config:**
```powershell
$env:ACCESS_TOKEN_MINUTES="5"
$env:REFRESH_TOKEN_DAYS="14"
$env:RESUME_CODE_MINUTES="5"
```
- [ ] Backend prints updated token lifetimes
- [ ] Resume code expires in configured minutes
- [ ] Access token expires in configured minutes (test with long-running session)

---

### 7. No Regressions (All Envs)

**Core Features:**
- [ ] Login works
- [ ] Register new account works
- [ ] Property analysis works
- [ ] Save deal to portfolio works
- [ ] Load deal from portfolio works
- [ ] Delete to trash works
- [ ] Restore from trash works
- [ ] Scenario management works
- [ ] Plans & Billing page loads
- [ ] Logout works (revokes session)
- [ ] Token refresh works (401 → auto-refresh)

**Protected API Calls:**
- [ ] `/account/info` requires auth
- [ ] `/property/save` requires auth
- [ ] `/property/saved` requires auth
- [ ] `/auth/resume/request` requires auth
- [ ] `/auth/logout` requires auth
- [ ] `/auth/login` does NOT require auth
- [ ] `/auth/register` does NOT require auth
- [ ] `/auth/resume` does NOT require auth (uses resume_code)

---

### 8. Security Validation (All Envs)

**Resume Codes:**
- [ ] Resume codes are single-use (marked `used_at` immediately)
- [ ] Resume codes expire after configured minutes
- [ ] Expired codes return 400 "Expired"
- [ ] Used codes return 400 "Already used"
- [ ] Invalid codes return 400 "Invalid code"
- [ ] Revoked sessions return 401 "Session revoked"

**Logout:**
- [ ] Logout calls `/auth/logout` backend endpoint
- [ ] Backend session is revoked (sets `revoked_at`)
- [ ] Resume codes fail after logout
- [ ] Must login again to get new session

**Session State:**
- [ ] No JWT tokens logged to console
- [ ] No refresh tokens logged to console
- [ ] Resume codes are safe to display (not the JWT)
- [ ] Session state properly isolated per user

---

## Environment Variables Reference

### Backend (`backend/config.py`):
- `ENV` - dev|staging|prod (default: dev)
- `SECRET_KEY` - JWT secret (use secure key in prod!)
- `ACCESS_TOKEN_MINUTES` - Access token lifetime (default: 15)
- `REFRESH_TOKEN_DAYS` - Refresh token lifetime (default: 7)
- `RESUME_CODE_MINUTES` - Resume code lifetime (default: 10)
- `DATABASE_PATH` - SQLite database path (default: brinkadata.db)
- `STAGING_FRONTEND_URL` - Staging frontend URL for CORS
- `PROD_FRONTEND_URL` - Production frontend URL for CORS

### Frontend (`frontend/config.py`):
- `ENV` - dev|staging|prod (default: dev)
- `BACKEND_URL` - Backend API URL (default: http://127.0.0.1:8000)
- `ACCESS_TOKEN_MINUTES` - For display only (default: 15)
- `REFRESH_TOKEN_DAYS` - For display only (default: 7)
- `RESUME_CODE_MINUTES` - For display only (default: 10)

---

## Expected Behavior Summary

| Feature | DEV | STAGING | PROD |
|---------|-----|---------|------|
| Simulate Refresh button | ✅ Visible | ❌ Hidden | ❌ Hidden |
| Debug captions | ✅ Visible | ❌ Hidden | ❌ Hidden |
| Get Resume Code | ✅ Visible | ✅ Visible | ✅ Visible |
| Logout button | ✅ Visible | ✅ Visible | ✅ Visible |
| CORS origins | `["*"]` | Restricted | Restricted |
| Verbose logging | ✅ Enabled | ✅ Enabled | ❌ Disabled |
| Resume after refresh | ✅ Works | ✅ Works | ✅ Works |
| Resume after logout | ❌ Fails | ❌ Fails | ❌ Fails |

---

## Troubleshooting

**Issue: "Simulate Refresh" button still visible in prod**
- Check `ENV` environment variable is set to "prod"
- Restart both backend and frontend after setting ENV
- Check frontend console for `[CONFIG] Debug UI: disabled`

**Issue: Protected API calls before auth established**
- Check `session_rehydrated` is True before calling protected endpoints
- Check no infinite rerun loops in console
- Check Login page renders without errors

**Issue: Resume codes not expiring correctly**
- Check `RESUME_CODE_MINUTES` environment variable
- Check backend logs for actual expiration time used
- Verify system time is correct

**Issue: CORS errors in staging/prod**
- Set `STAGING_FRONTEND_URL` or `PROD_FRONTEND_URL` environment variables
- Restart backend after setting environment variables
- Check backend CORS origins in startup logs
