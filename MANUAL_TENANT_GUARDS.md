# Manual Tenant Guardrails Testing Checklist

## Overview
Phase 2 tenant guardrails add defense-in-depth protections to prevent accidental data leakage.

**In DEV:** Warnings are logged when tenant scope is missing or results contain mismatched account_ids  
**In STAGING/PROD:** Fast-fail with HTTP 500 to prevent data leakage

---

## Prerequisites
- Backend running: `uvicorn backend.main:app --reload`
- Frontend running: `streamlit run frontend/app.py`
- Environment: `ENV=dev` (for warning detection tests)

---

## Test 1: Basic Tenant Isolation (Functional Verification)

### Steps
1. **Create Account A**
   - Register user: `account_a@test.com`
   - Save a property: "Account A Property 1"
   - Note the property ID

2. **Create Account B**
   - Register user: `account_b@test.com`
   - Verify portfolio is empty (should NOT see Account A's property)

### Expected Result
✅ Account B cannot see Account A's saved properties

**Result:** ☐ PASS / ☐ FAIL

---

## Test 2: Cross-Tenant Delete Protection

### Steps
1. **Login as Account A**
   - Save a property, note its ID: `property_id_a`

2. **Login as Account B**
   - Attempt to delete Account A's property via API:
     ```bash
     curl -X POST http://localhost:8000/property/delete \
       -H "Authorization: Bearer <ACCOUNT_B_TOKEN>" \
       -H "Content-Type: application/json" \
       -d '{"id": <property_id_a>}'
     ```

### Expected Result
✅ Returns `404 Not Found` (tenant guard blocks access)  
✅ Backend logs: `[TENANT] Row access denied` (if in dev)

**Result:** ☐ PASS / ☐ FAIL

---

## Test 3: Trash Isolation

### Steps
1. **Login as Account A**
   - Save and delete a property (moves to trash)
   - Verify it appears in trash

2. **Login as Account B**
   - View trash page

### Expected Result
✅ Account B's trash is empty (cannot see Account A's trash)

**Result:** ☐ PASS / ☐ FAIL

---

## Test 4: Restore Isolation

### Steps
1. **Login as Account A**
   - Delete a property (moves to trash)
   - Note the `trash_id`

2. **Login as Account B**
   - Attempt to restore Account A's trash item:
     ```bash
     curl -X POST http://localhost:8000/property/trash/restore \
       -H "Authorization: Bearer <ACCOUNT_B_TOKEN>" \
       -H "Content-Type: application/json" \
       -d '{"trash_id": <trash_id_from_A>}'
     ```

### Expected Result
✅ Returns `404 Not Found`  
✅ Backend logs: `[TENANT] Tenant isolation violation` (if row was somehow returned)

**Result:** ☐ PASS / ☐ FAIL

---

## Test 5: Scenario Isolation

### Steps
1. **Login as Account A**
   - Save a property with ID `property_id_a`
   - Create a scenario for it (Slot A)

2. **Login as Account B**
   - Attempt to list scenarios for Account A's property:
     ```bash
     curl -X GET http://localhost:8000/scenario/list/<property_id_a> \
       -H "Authorization: Bearer <ACCOUNT_B_TOKEN>"
     ```

### Expected Result
✅ Returns empty list `[]` (tenant guard filters by account_id)  
✅ Backend logs show `[TENANT]` assertion passed (no violations)

**Result:** ☐ PASS / ☐ FAIL

---

## Test 6: DEV-Only Warnings (Developer Experiment)

**⚠️ Only perform this test in DEV environment**

### Steps
1. **Temporarily break tenant scoping** (in a test branch):
   - Comment out `WHERE account_id = ?` in `/property/saved` endpoint
   - Or remove the `account_id` parameter from `execute_scoped()`

2. **Call the endpoint:**
   ```bash
   curl -X GET http://localhost:8000/property/saved \
     -H "Authorization: Bearer <TOKEN>"
   ```

### Expected Result (DEV)
✅ Backend logs warning:
```
[TENANT][DEV] Query missing 'account_id' filter in /property/saved
[TENANT][DEV] SQL: SELECT rowid, * FROM saved_properties...
```
✅ Request still succeeds (dev mode is forgiving)

### Expected Result (PROD)
❌ Backend returns `HTTP 500` with:
```json
{"detail": "Unsafe tenant query detected - missing account_id filter"}
```

**Result:** ☐ PASS / ☐ FAIL

---

## Test 7: Result Set Validation (assert_rows_scoped)

### Steps
1. **Artificially create a mixed result set** (in test):
   - Manually insert a row with `account_id=999` in DB
   - Call `/property/saved` as Account A

2. **Observe behavior:**

### Expected Result (DEV)
✅ Backend logs warning:
```
[TENANT] Tenant isolation violation in /property/saved
[TENANT][DEV] Expected account_id=1, found mismatches: [{'index': 5, 'expected': 1, 'found': 999}]
```
✅ Request still returns data (dev mode)

### Expected Result (PROD)
❌ Backend returns `HTTP 500`:
```json
{"detail": "Tenant isolation violation detected - this is a server error"}
```

**Result:** ☐ PASS / ☐ FAIL

---

## Test 8: require_account_id() Guard

### Steps
1. **Artificially set account_id to None** (in test):
   - Modify `AuthContext` to return `None` for `account_id`
   - Call any protected endpoint

### Expected Result (DEV)
✅ Backend logs warning:
```
[TENANT] Missing or invalid account_id: None (DEV warning - continuing)
```
✅ Request may fail with other errors (0 is invalid) but doesn't crash server

### Expected Result (PROD)
❌ Backend returns `HTTP 500`:
```json
{"detail": "Tenant scope missing - this is a server error"}
```

**Result:** ☐ PASS / ☐ FAIL

---

## Summary

| Test | Status |
|------|--------|
| Test 1: Basic Tenant Isolation | ☐ PASS / ☐ FAIL |
| Test 2: Cross-Tenant Delete Protection | ☐ PASS / ☐ FAIL |
| Test 3: Trash Isolation | ☐ PASS / ☐ FAIL |
| Test 4: Restore Isolation | ☐ PASS / ☐ FAIL |
| Test 5: Scenario Isolation | ☐ PASS / ☐ FAIL |
| Test 6: DEV-Only Warnings | ☐ PASS / ☐ FAIL |
| Test 7: Result Set Validation | ☐ PASS / ☐ FAIL |
| Test 8: require_account_id() Guard | ☐ PASS / ☐ FAIL |

**Overall Result:** ☐ ALL PASS / ☐ SOME FAILURES

---

## Interpreting Results

### DEV Mode Behavior
- **Warnings logged** but requests succeed
- Helps developers catch mistakes during development
- Safe to iterate without breaking the app

### PROD Mode Behavior
- **Fast-fail with HTTP 500** on violations
- Prevents data leakage at the cost of error responses
- Assumes developers have tested in DEV first

### When to Investigate
- ❌ **Test 1-5 fail**: Core tenant isolation is broken (critical)
- ❌ **Test 6-8 fail in DEV**: Guards not working (needs debugging)
- ⚠️ **Warnings in PROD logs**: Should never happen (investigate immediately)

---

## Common Issues

### "Missing account_id filter" warnings in DEV
- **Cause:** Query doesn't include `account_id` in WHERE clause
- **Fix:** Add `WHERE account_id = ?` to the SQL query
- **Example:** `SELECT * FROM saved_properties WHERE account_id = ?`

### "Tenant isolation violation" errors
- **Cause:** Query returned rows from multiple accounts
- **Fix:** Ensure `WHERE account_id = ?` is in the query
- **Check:** Verify `execute_scoped()` is being used

### Guards not triggering in DEV
- **Cause:** `ENV` variable not set to "dev"
- **Fix:** Set `export ENV=dev` or check `backend/config.py`
- **Verify:** Backend startup logs should show `[CONFIG] Environment: dev`

---

## Post-Testing Cleanup

After completing tests:
1. Remove any test accounts created
2. Clean up test properties from database
3. Revert any intentional tenant scope violations (Test 6-8)
4. Verify all guards are active and passing

**Notes:**
- All tests should pass in both DEV and PROD modes
- DEV shows warnings; PROD fails fast
- Phase 2 guardrails are defense-in-depth (assume Phase 1 is correct)
