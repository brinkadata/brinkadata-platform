# Manual Multi-Tenant Security Test Checklist

## Prerequisites
- Backend running: `uvicorn backend.main:app --reload` (port 8000)
- Frontend running: `streamlit run frontend/app.py` (port 8501)
- Clean dev database or willingness to create new test accounts

## Test Account Setup

### Create Test Account A (Free Plan)
1. Navigate to registration page
2. Register with:
   - Email: `test_a@example.com`
   - Password: `password123`
   - Account Name: `Test Account A`
3. Note the account_id (check browser console or backend logs)

### Create Test Account B (Pro Plan)
1. **Logout from Account A**
2. Register with:
   - Email: `test_b@example.com`
   - Password: `password123`
   - Account Name: `Test Account B`
3. Note the account_id
4. **Using curl or Postman**, upgrade Account B to Pro:
   ```bash
   curl -X POST http://localhost:8000/admin/set_plan?account_id=<B_ID>&plan=pro
   ```

---

## Test 1: Saved Properties Isolation

### Steps
1. **Login as Account A**
2. Create and save a deal:
   - Property Name: `Account A Property 1`
   - City: `Los Angeles`, State: `CA`
   - Purchase Price: `200000`, Rehab: `50000`, Rent: `2000`, Hold: `5`
   - Click **Analyze**, then **Save**
3. Go to **Portfolio** page
4. Verify you see `Account A Property 1`
5. Note the property ID from the table

6. **Logout and Login as Account B**
7. Go to **Portfolio** page
8. **Expected**: Portfolio is empty (no Account A properties visible)

9. **Attempt manual cross-tenant access** (using curl):
   ```bash
   # Get Account B's JWT token from browser dev tools (localStorage or session)
   curl -X GET http://localhost:8000/property/saved \
     -H "Authorization: Bearer <ACCOUNT_B_TOKEN>"
   ```
   **Expected**: Empty list or only Account B properties

10. **Attempt to delete Account A's property using Account B's token**:
    ```bash
    curl -X POST http://localhost:8000/property/delete \
      -H "Authorization: Bearer <ACCOUNT_B_TOKEN>" \
      -H "Content-Type: application/json" \
      -d '{"id": <ACCOUNT_A_PROPERTY_ID>}'
    ```
    **Expected**: `404 Not Found` (not 403, to avoid leaking existence)

**Result**: ☐ PASS / ☐ FAIL

---

## Test 2: Trash Isolation

### Steps
1. **Login as Account A**
2. Create and save a property: `Account A Trash Test`
3. Delete it (moves to Trash)
4. Go to **Trash** page
5. Verify `Account A Trash Test` appears
6. Note the `trash_id`

7. **Logout and Login as Account B**
8. Go to **Trash** page
9. **Expected**: Empty trash (no Account A items)

10. **Attempt cross-tenant restore** (using curl):
    ```bash
    curl -X POST http://localhost:8000/property/trash/restore \
      -H "Authorization: Bearer <ACCOUNT_B_TOKEN>" \
      -H "Content-Type: application/json" \
      -d '{"trash_id": <ACCOUNT_A_TRASH_ID>}'
    ```
    **Expected**: `404 Not Found`

**Result**: ☐ PASS / ☐ FAIL

---

## Test 3: Scenario Isolation

### Steps
1. **Login as Account A**
2. Save a property and note its ID: `property_id_a`
3. Create a scenario for Slot A (if UI supports it, or use curl):
   ```bash
   curl -X POST http://localhost:8000/scenario/save \
     -H "Authorization: Bearer <ACCOUNT_A_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"property_id": <property_id_a>, "slot": "A", "label": "Scenario A", "metrics": {}}'
   ```
4. List scenarios:
   ```bash
   curl -X GET http://localhost:8000/scenario/list/<property_id_a> \
     -H "Authorization: Bearer <ACCOUNT_A_TOKEN>"
   ```
   **Expected**: Returns Scenario A

5. **Login as Account B** (or use Account B token)
6. Attempt to list Account A's scenarios:
   ```bash
   curl -X GET http://localhost:8000/scenario/list/<property_id_a> \
     -H "Authorization: Bearer <ACCOUNT_B_TOKEN>"
   ```
   **Expected**: Empty list (no access to Account A's scenarios)

**Result**: ☐ PASS / ☐ FAIL

---

## Test 4: Plan Limit Enforcement (Free Plan - 25 Deals)

### Steps
1. **Login as Account A (Free Plan)**
2. Check current saved deal count in Portfolio
3. **Save deals until limit is reached**:
   - If already have 25+ deals, delete some first to test limit
   - Save deals until you have exactly 25 (Free plan limit)
4. **Attempt to save the 26th deal**:
   - Fill out analysis form
   - Click Analyze, then Save
   **Expected**: Error message: `"Limit reached for saved_deals: 25/25 (free plan)"` or similar
   - Status code: `402 Payment Required`

5. **Verify in backend logs**:
   - Should see: `[SAVE_PROPERTY] Limit reached` or `UsageLimitError`

**Result**: ☐ PASS / ☐ FAIL

---

## Test 5: IRR/NPV Feature Gating

### Steps
1. **Login as Account A (Free Plan)**
2. Analyze a property:
   - Purchase: `200000`, Rehab: `50000`, Rent: `2000`, Hold: `5`
3. **Expected**: Results should **NOT** show IRR or NPV fields (or show `null`)
4. Check the response JSON (browser dev tools):
   ```json
   {
     "irr_unlevered": null,
     "npv_unlevered": null
   }
   ```

5. **Logout and Login as Account B (Pro Plan)**
6. Analyze the same property
7. **Expected**: Results **SHOULD** include IRR and NPV (computed values, not `null`)
8. Check the response JSON:
   ```json
   {
     "irr_unlevered": 0.123,  // some computed value
     "npv_unlevered": 45000   // some computed value
   }
   ```

**Result**: ☐ PASS / ☐ FAIL

---

## Test 6: Admin Endpoints (Dev-Only)

### Steps
1. **In DEV mode** (ENV=dev):
   ```bash
   curl http://localhost:8000/admin/accounts
   ```
   **Expected**: Returns list of accounts

2. **Set Account A to Pro plan**:
   ```bash
   curl -X POST "http://localhost:8000/admin/set_plan?account_id=<A_ID>&plan=pro"
   ```
   **Expected**: `{"status": "ok", "account_id": <A_ID>, "plan": "pro"}`

3. **Verify plan change**:
   - Login as Account A
   - Go to account settings (or call `/account/info`)
   - **Expected**: Plan is now `pro`

4. **Set ENV=prod** (change environment variable):
   ```bash
   $env:ENV="prod"  # PowerShell
   # Restart backend
   ```
   
5. **Attempt admin endpoint in prod**:
   ```bash
   curl http://localhost:8000/admin/accounts
   ```
   **Expected**: `403 Forbidden` (admin endpoints disabled in prod)

**Result**: ☐ PASS / ☐ FAIL

---

## Test 7: Session/Token Security

### Steps
1. **Login as Account A**
2. Copy the JWT access token from browser localStorage or session
3. **Decode the token** (use jwt.io):
   - Verify it contains: `sub` (user_id), `account_id`
4. **Manually edit the token**:
   - Change `account_id` to another account's ID
   - Attempt to use the modified token in a request:
     ```bash
     curl -X GET http://localhost:8000/property/saved \
       -H "Authorization: Bearer <MODIFIED_TOKEN>"
     ```
   **Expected**: `401 Unauthorized` (signature invalid) or `401 Invalid token`

5. **Use a valid token but with an inactive user**:
   - In DB, set `users.is_active = 0` for Account A's user
   - Attempt to access `/property/saved` with Account A's token
   **Expected**: `403 Account inactive`

**Result**: ☐ PASS / ☐ FAIL

---

## Test 8: Account/User ID Never Trusted from Request Body

### Steps
1. **Login as Account A**
2. **Attempt to inject account_id in save request**:
   ```bash
   curl -X POST http://localhost:8000/property/save \
     -H "Authorization: Bearer <ACCOUNT_A_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{
       "property_name": "Injected Property",
       "city": "NYC",
       "state": "NY",
       "account_id": <ACCOUNT_B_ID>,  // Attempt to save to Account B
       "estimated_roi": 0.20,
       "cashflow_per_month": 500
     }'
   ```
   **Expected**: Property is saved to **Account A** (ignores injected `account_id`)
   
3. **Verify in database**:
   ```sql
   SELECT account_id, property_name FROM saved_properties WHERE property_name = 'Injected Property';
   ```
   **Expected**: `account_id` is Account A's ID (not Account B's)

**Result**: ☐ PASS / ☐ FAIL

---

## Summary

| Test | Status |
|------|--------|
| Test 1: Saved Properties Isolation | ☐ PASS / ☐ FAIL |
| Test 2: Trash Isolation | ☐ PASS / ☐ FAIL |
| Test 3: Scenario Isolation | ☐ PASS / ☐ FAIL |
| Test 4: Plan Limit Enforcement | ☐ PASS / ☐ FAIL |
| Test 5: IRR/NPV Feature Gating | ☐ PASS / ☐ FAIL |
| Test 6: Admin Endpoints (Dev-Only) | ☐ PASS / ☐ FAIL |
| Test 7: Session/Token Security | ☐ PASS / ☐ FAIL |
| Test 8: Request Body Injection Prevention | ☐ PASS / ☐ FAIL |

**Overall Result**: ☐ ALL PASS / ☐ SOME FAILURES

---

## Notes
- All cross-tenant access attempts should return **404** (not 403) to avoid information leakage
- Plan limits must be enforced server-side (status code 402)
- Feature gates must be checked in backend (never trust frontend)
- Token claims (account_id, user_id) are the only source of truth
