# Quick Start Guide - Post Security Implementation

## ✅ Implementation Complete

All 6 tasks have been successfully implemented:
- ✅ TASK 1: AuthContext tenant boundary (single source of truth)
- ✅ TASK 2: Database schema hardening (indexes, Stripe fields, backfill)
- ✅ TASK 3: Tenant filtering on all queries (404 for cross-tenant access)
- ✅ TASK 4: Demo user creation is dev-only
- ✅ TASK 5: SaaS billing enforcement (server-side plan limits)
- ✅ TASK 6: Regression tests (pytest + manual checklist)

---

## Running the App

### Backend
```bash
cd C:\01_Projects_Folder\01_BrinkadataPlatform
uvicorn backend.main:app --reload
```

**Expected startup logs:**
```
[CONFIG] Environment: dev
[CONFIG] Access token: 15 minutes
[CONFIG] Refresh token: 7 days
[MIGRATION] Ensured indexes on saved_properties(account_id, created_at)
[MIGRATION] Ensured indexes on trashed_properties(account_id)
[MIGRATION] Ensured indexes on scenarios(account_id, property_id)
[MIGRATION] Ensured Stripe fields on accounts and subscriptions
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Frontend
```bash
cd C:\01_Projects_Folder\01_BrinkadataPlatform
streamlit run frontend/app.py
```

---

## Files Changed

1. **backend/main.py** - Auth context, tenant filtering, admin endpoints
2. **backend/features.py** - Plan enforcement, limit checking, feature gates
3. **backend/migrate_accounts.py** - Dev-only demo user creation
4. **backend/test_multitenant_security.py** (NEW) - Automated tests
5. **MANUAL_SECURITY_TESTS.md** (NEW) - Step-by-step test checklist
6. **SECURITY_IMPLEMENTATION_SUMMARY.md** (NEW) - Complete documentation

---

## Testing

### Automated Tests
```bash
# Install pytest if not already installed
pip install pytest

# Run security tests
pytest backend/test_multitenant_security.py -v
```

**Expected output:**
```
test_isolated_property_save PASSED
test_cross_tenant_delete_forbidden PASSED
test_cross_tenant_trash_restore_forbidden PASSED
test_plan_limit_enforcement PASSED
test_irr_npv_gated_by_plan PASSED
```

### Manual Testing
See `MANUAL_SECURITY_TESTS.md` for the complete manual test checklist.

**Quick smoke test:**
1. Start backend and frontend
2. Register two users (Account A and Account B)
3. Login as Account A, save a property
4. Login as Account B, verify you **don't** see Account A's property
5. ✅ Multi-tenant isolation is working

---

## Key Security Features

### 1. AuthContext (Single Source of Truth)
```python
# OLD (vulnerable)
def endpoint(account_id: int, current_user: dict):
    # Could trust account_id from request body

# NEW (secure)
def endpoint(ctx: AuthContext = Depends(require_auth_context)):
    account_id = ctx.account_id  # Only from JWT + DB
```

### 2. SQL Filtering (Always)
```python
# Every query includes account_id filter
cur.execute(
    "SELECT * FROM saved_properties WHERE account_id = ?",
    (ctx.account_id,)
)
```

### 3. Cross-Tenant Access Returns 404
```python
# Never 403 (leaks existence), always 404
row = require_row_owned(cur, "saved_properties", row_id, account_id)
# Raises HTTPException(404) if row doesn't exist or belongs to another account
```

### 4. Plan Limits Enforced Server-Side
```python
# Before saving
check_usage_limit(account_id, "saved_deals")  # Raises 402 if at limit

# Before IRR/NPV calculation
allow_irr_npv = check_feature_access(account_id, "irr_npv")
```

---

## Development Commands

### Check Account Plans (Dev Only)
```bash
# List all accounts
curl http://localhost:8000/admin/accounts

# Set account to pro plan
curl -X POST "http://localhost:8000/admin/set_plan?account_id=2&plan=pro"
```

### Test Plan Limits
```bash
# Free plan: max 25 saved deals
# Pro plan: max 250 saved deals
# Try saving the 26th deal on a free account -> should get 402 error
```

### Verify Isolation
```bash
# Get Account A's JWT token (from browser dev tools)
export TOKEN_A="eyJhbGc..."

# Try to access saved properties
curl -H "Authorization: Bearer $TOKEN_A" http://localhost:8000/property/saved
# Should only return Account A's properties
```

---

## Troubleshooting

### Backend won't start
- **Error:** `ModuleNotFoundError`
  - **Fix:** `cd C:\01_Projects_Folder\01_BrinkadataPlatform` (run from repo root)

- **Error:** `SyntaxError in features.py`
  - **Fix:** File should import cleanly (already fixed in this commit)

### Tests failing
- **Error:** `Limit reached for saved_deals: 25/25`
  - **Cause:** Free plan limit enforcement working correctly
  - **Fix:** Use admin endpoint to upgrade to pro: `curl -X POST "http://localhost:8000/admin/set_plan?account_id=X&plan=pro"`

### Cross-tenant access not blocked
- **Symptoms:** Can see other accounts' properties
  - **Fix:** Verify `account_id` column exists and has indexes:
    ```bash
    python backend/migrate_accounts.py  # Re-run migrations
    ```

---

## Production Deployment

### Before Deploying
1. Set environment variables:
   ```bash
   export ENV=prod
   export SECRET_KEY=<strong-random-secret>
   export DATABASE_PATH=/var/app/brinkadata.db
   ```

2. Run tests:
   ```bash
   pytest backend/test_multitenant_security.py
   ```

3. Verify demo user creation is disabled:
   ```bash
   # Check logs for:
   [PROD/STAGING] Skipping demo account creation
   # NOT:
   [DEV-ONLY] Created default account
   ```

### After Deploying
1. Test admin endpoints are blocked:
   ```bash
   curl https://api.brinkadata.com/admin/accounts
   # Should return: {"detail":"Admin endpoints only available in dev"}
   ```

2. Test cross-tenant isolation with real accounts

---

## Next Steps

### Recommended Enhancements
1. **Stripe integration**: Wire up webhooks for plan upgrades
2. **Usage dashboard**: Show account usage stats in UI
3. **Rate limiting**: Add per-account API rate limits
4. **Audit logging**: Persist security events to database

### Performance Monitoring
- Monitor `[AUTH]` logs for failed auth attempts
- Monitor `[SECURITY]` logs for cross-tenant access attempts
- Set up alerts for 404 responses on property endpoints

---

## Support

- **Documentation**: `SECURITY_IMPLEMENTATION_SUMMARY.md`
- **Test Checklist**: `MANUAL_SECURITY_TESTS.md`
- **Code Examples**: `backend/test_multitenant_security.py`

**Questions?** Review the security implementation summary for detailed explanations.
