# Phase 3: RBAC + Entitlements - Manual Test Plan

**Purpose:** Verify role-based access control (RBAC) and plan-based entitlements are properly enforced at the backend level.

**Test Environment:** DEV mode (IS_DEV=true) with admin endpoints enabled

**Prerequisites:**
- Backend running: `uvicorn backend.main:app --reload`
- Frontend running: `streamlit run frontend/app.py`
- SQLite database initialized with accounts and users tables
- JWT authentication working

---

## Test 1: Role-Based Access Control - Write Operations

**Goal:** Verify that only member role or higher can save/delete/restore deals.

### Setup
1. Create two users in the same account:
   - User A: role="owner"
   - User B: role="read_only"

```bash
# Create test account and users (run in Python or via backend)
sqlite3 brinkadata.db

-- Create test account
INSERT INTO accounts (name, plan) VALUES ('Test Account RBAC', 'free');
-- Note the account ID (e.g., 2)

-- Create owner user
INSERT INTO users (email, password_hash, role, account_id, is_active) 
VALUES ('owner@test.com', 'dummy_hash', 'owner', 2, 1);

-- Create read_only user
INSERT INTO users (email, password_hash, role, account_id, is_active) 
VALUES ('readonly@test.com', 'dummy_hash', 'read_only', 2, 1);
```

### Test Steps

#### 1.1 - Owner can save deals
1. Login as `owner@test.com`
2. Navigate to Analyzer
3. Run analysis on a test property
4. Click "Save this deal to portfolio"
5. **Expected:** ✅ Deal saved successfully (HTTP 200)

#### 1.2 - Read-only user CANNOT save deals
1. Logout and login as `readonly@test.com`
2. Navigate to Analyzer
3. Run analysis on a test property
4. Click "Save this deal to portfolio"
5. **Expected:** ❌ HTTP 403 "Insufficient permissions - member role required"
6. **Expected:** Frontend shows "🔒 Permission Denied" message

#### 1.3 - Read-only user CANNOT delete deals
1. Still logged in as `readonly@test.com`
2. Navigate to Portfolio page
3. Select a deal and click "Move to trash"
4. **Expected:** ❌ HTTP 403 "Insufficient permissions - member role required"
5. **Expected:** Frontend shows "🔒 Permission Denied" message

#### 1.4 - Read-only user CANNOT restore deals
1. Still logged in as `readonly@test.com`
2. Navigate to Portfolio page, scroll to Trash section
3. Select a trashed deal and click "Restore from trash"
4. **Expected:** ❌ HTTP 403 "Insufficient permissions - member role required"
5. **Expected:** Frontend shows "🔒 Permission Denied" message

---

## Test 2: Plan-Based Limits - Saved Deals Quota

**Goal:** Verify saved deal limits are enforced by plan at the backend level.

### Setup
1. Use the owner user from Test 1 (account on 'free' plan)
2. Free plan limit: 25 saved deals

### Test Steps

#### 2.1 - Save up to limit (25 deals)
1. Login as `owner@test.com`
2. Save 24 deals (if none exist yet)
3. Check current count: 
```bash
sqlite3 brinkadata.db "SELECT COUNT(*) FROM saved_properties WHERE account_id = 2;"
```
4. Save the 25th deal
5. **Expected:** ✅ Deal saved successfully (HTTP 200)

#### 2.2 - Attempt to save 26th deal (over limit)
1. Still logged in, run another analysis
2. Click "Save this deal to portfolio"
3. **Expected:** ❌ HTTP 402 "Plan limit reached: 25/25 max_saved_deals. Upgrade to continue."
4. **Expected:** Frontend shows "💳 Upgrade Required" message with plan details

#### 2.3 - Upgrade plan and verify limit increase
1. In DEV mode, navigate to Account page or use admin endpoint:
```bash
curl -X POST http://localhost:8000/admin/set_plan \
  -H "Content-Type: application/json" \
  -d '{"account_id": 2, "new_plan": "pro"}'
```
2. Verify plan updated:
```bash
sqlite3 brinkadata.db "SELECT plan FROM accounts WHERE id = 2;"
```
3. Attempt to save the 26th deal again
4. **Expected:** ✅ Deal saved successfully (HTTP 200)
5. **Expected:** Pro plan allows up to 250 deals

---

## Test 3: Plan-Based Features - IRR/NPV Gating

**Goal:** Verify IRR/NPV analysis is gated behind pro plan at the backend level.

### Setup
1. Create a new account on 'free' plan
2. Create a user with 'member' role (to pass write checks)

```bash
sqlite3 brinkadata.db

-- Create test account
INSERT INTO accounts (name, plan) VALUES ('Test Account Free Plan', 'free');
-- Note the account ID (e.g., 3)

-- Create member user
INSERT INTO users (email, password_hash, role, account_id, is_active) 
VALUES ('member@free.com', 'dummy_hash', 'member', 3, 1);
```

### Test Steps

#### 3.1 - Free plan: Core analysis works, IRR/NPV blocked
1. Login as `member@free.com`
2. Navigate to Analyzer
3. Fill in property details and run analysis
4. **Expected:** ✅ Basic analysis returns (ROI, cashflow, cap rate, etc.)
5. **Expected:** IRR/NPV fields are null or not shown (backend doesn't compute them)
6. Check backend logs for:
```
[AUTHZ] Feature not available: plan=free, feature=can_use_irr_npv
```

#### 3.2 - Upgrade to pro plan
1. Use admin endpoint to upgrade account:
```bash
curl -X POST http://localhost:8000/admin/set_plan \
  -H "Content-Type: application/json" \
  -d '{"account_id": 3, "new_plan": "pro"}'
```
2. Verify plan updated:
```bash
sqlite3 brinkadata.db "SELECT plan FROM accounts WHERE id = 3;"
```

#### 3.3 - Pro plan: IRR/NPV enabled
1. Still logged in as `member@free.com`, run analysis again
2. **Expected:** ✅ IRR/NPV fields are computed and returned
3. Check backend logs for:
```
[AUTHZ] Feature access granted: plan=pro, feature=can_use_irr_npv
```

---

## Test 4: Multi-Tenant Isolation (Regression Test)

**Goal:** Confirm Phase 2 tenant guardrails are not regressed by Phase 3 changes.

### Setup
1. Use accounts from Test 1 and Test 3 (account_id=2 and account_id=3)
2. Both accounts have saved deals

### Test Steps

#### 4.1 - User A cannot see User B's deals
1. Login as `owner@test.com` (account_id=2)
2. Navigate to Portfolio page
3. **Expected:** Only see deals from account_id=2
4. Attempt to access deal from account_id=3 via API:
```bash
# Get a deal ID from account 3
sqlite3 brinkadata.db "SELECT rowid FROM saved_properties WHERE account_id = 3 LIMIT 1;"

# Try to delete it as account 2 user (should fail)
curl -X POST http://localhost:8000/property/delete \
  -H "Authorization: Bearer <ACCOUNT_2_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"id": <ACCOUNT_3_DEAL_ID>}'
```
5. **Expected:** ❌ HTTP 404 "Not found" (tenant isolation enforced)

#### 4.2 - Backend logs show tenant guard warnings (DEV mode)
1. Check backend logs for Phase 2 tenant guard messages:
```
[TENANT] Validating account_id for /property/delete
[SECURITY] Row access denied: table=saved_properties, rowid=X, account_id=2
```

---

## Test 5: Admin Endpoints - DEV-Only Access

**Goal:** Verify admin endpoints are only accessible in DEV mode.

### Test Steps

#### 5.1 - Admin endpoints work in DEV mode
1. Set `ENV=dev` in config
2. Test plan change endpoint:
```bash
curl -X POST http://localhost:8000/admin/set_plan \
  -H "Content-Type: application/json" \
  -d '{"account_id": 2, "new_plan": "team"}'
```
3. **Expected:** ✅ HTTP 200, plan changed successfully

#### 5.2 - Admin endpoints blocked in PROD mode
1. Set `ENV=prod` in config and restart backend
2. Test plan change endpoint:
```bash
curl -X POST http://localhost:8000/admin/set_plan \
  -H "Content-Type: application/json" \
  -d '{"account_id": 2, "new_plan": "team"}'
```
3. **Expected:** ❌ HTTP 403 "Admin endpoints are DEV-only"

---

## Test 6: Frontend Error Handling

**Goal:** Verify frontend displays user-friendly messages for 402/403 errors.

### Test Steps

#### 6.1 - Plan upgrade message (402)
1. Login as user on free plan with 25 deals saved
2. Attempt to save 26th deal
3. **Expected:** Frontend shows:
   - "💳 Upgrade Required: Plan limit reached..."
   - "💡 Upgrade your plan to access this feature..."

#### 6.2 - Permission denied message (403)
1. Login as user with read_only role
2. Attempt to save a deal
3. **Expected:** Frontend shows:
   - "🔒 Permission Denied: Insufficient permissions - member role required"
   - "💡 You need a higher role (member, admin, or owner)..."

---

## Test 7: Role Hierarchy Validation

**Goal:** Verify role hierarchy works correctly (owner > admin > member > read_only).

### Setup
1. Create users with different roles in the same account

```bash
sqlite3 brinkadata.db

INSERT INTO users (email, password_hash, role, account_id, is_active) 
VALUES 
  ('admin@test.com', 'dummy_hash', 'admin', 2, 1),
  ('member@test.com', 'dummy_hash', 'member', 2, 1);
```

### Test Steps

#### 7.1 - Member can write, not admin
1. Login as `member@test.com`
2. Save a deal
3. **Expected:** ✅ Success (member meets "member" requirement)

#### 7.2 - Admin can write (higher than member)
1. Login as `admin@test.com`
2. Save a deal
3. **Expected:** ✅ Success (admin > member in hierarchy)

#### 7.3 - Admin can delete deals (higher than member)
1. Still logged in as `admin@test.com`
2. Delete a deal
3. **Expected:** ✅ Success (admin has write access)

---

## Test 8: Comprehensive Plan Limits Check

**Goal:** Verify all plan limits are correctly configured and enforced.

### Reference Table

| Plan       | Max Deals | Can Export CSV | Can Use IRR/NPV | Can Use API |
|------------|-----------|----------------|-----------------|-------------|
| Free       | 25        | ❌             | ❌              | ❌          |
| Pro        | 250       | ✅             | ✅              | ❌          |
| Team       | 1000      | ✅             | ✅              | ✅          |
| Enterprise | 10000     | ✅             | ✅              | ✅          |

### Test Steps

#### 8.1 - Verify plan limits in code
1. Check `backend/authz.py` PLAN_LIMITS dictionary
2. **Expected:** All values match reference table above

#### 8.2 - Test each plan's saved deal limit
1. For each plan (free, pro, team, enterprise):
   - Create account with that plan
   - Save deals up to limit
   - Verify limit enforced at correct threshold
   - Check HTTP 402 response with correct message

---

## Success Criteria

✅ **All tests must pass:**

1. ✅ Read-only users cannot save/delete/restore (403)
2. ✅ Member/admin/owner users can save/delete/restore (200)
3. ✅ Free plan limited to 25 saved deals (402 on 26th)
4. ✅ Pro plan allows 250 saved deals
5. ✅ Free plan blocks IRR/NPV (null/not computed)
6. ✅ Pro plan enables IRR/NPV (computed and returned)
7. ✅ Multi-tenant isolation still enforced (404 for cross-tenant)
8. ✅ Admin endpoints only work in DEV mode
9. ✅ Frontend shows user-friendly 402/403 messages
10. ✅ Role hierarchy works correctly (owner > admin > member > read_only)

---

## Rollback Plan

If any critical failures:

1. **Revert backend/main.py:**
   - Comment out authz imports and enforcement calls
   - Fallback to Phase 2 implementation

2. **Revert frontend/app.py:**
   - Remove handle_api_error() function
   - Restore old error handling code

3. **Keep backend/authz.py:**
   - Module is standalone, can remain for future use

---

## Notes

- All tests should be run in DEV mode first
- Monitor backend logs for [AUTHZ] messages
- Verify no regression in existing Phase 1/2 features
- Document any edge cases or unexpected behaviors
- Test with real JWT tokens, not mock users

---

**Last Updated:** Phase 3 Implementation - RBAC + Entitlements
**Test Status:** 🟡 Pending execution
