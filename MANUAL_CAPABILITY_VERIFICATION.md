# Manual Verification Checklist: Capability Gating

**Purpose:** Verify that capability-based authorization works correctly across roles, plans, and UI states.

**Setup:**
1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `streamlit run frontend/app.py`
3. Use different test accounts (see test data below)

---

## Test Data

### Account 1: Free Plan
- **Owner:** email=owner@free.com, password=(set during registration)
- **Member:** email=member@free.com
- **Read-only:** email=readonly@free.com

### Account 2: Pro Plan
- **Owner:** email=owner@pro.com

### Account 3: Team Plan  
- **Member:** email=member@team.com

---

## Test Cases

### ✅ Test 1: Login & Capability Loading

**Scenario:** Verify capabilities load automatically after login

**Steps:**
1. Navigate to Login page
2. Login as `owner@free.com`
3. Check sidebar (with Debug UI enabled)

**Expected Results:**
- [ ] Sidebar shows "Plan: free | Role: owner"
- [ ] Sidebar shows "Capabilities: X cached" (not "not cached")
- [ ] Sidebar shows "can('asset:manage'): True"
- [ ] No "⏳ Loading permissions..." message after page loads

**Notes:** Capabilities should load once immediately after login, without requiring page refresh.

---

### ✅ Test 2: Free Plan + Member Role - Save Within Limits

**Scenario:** Verify free plan member can save deals up to plan limit

**Steps:**
1. Login as `member@free.com` (free plan, member role)
2. Navigate to Analyzer
3. Enter property details and click "Analyze"
4. Verify "💾 Save this deal to portfolio" button appears
5. Click Save button

**Expected Results:**
- [ ] Save button is visible (has `asset:manage` capability)
- [ ] Deal saves successfully (status 200)
- [ ] Success message appears
- [ ] Deal appears in Portfolio tab
- [ ] After reaching 25 saved deals (free limit), backend returns 402 with clear message

**Notes:** Free plan allows up to 25 saved deals. Member role has `asset:manage` capability.

---

### ✅ Test 3: Free Plan + Read-only Role - Save Blocked

**Scenario:** Verify read-only role cannot save deals regardless of plan

**Steps:**
1. Login as `readonly@free.com` (free plan, read_only role)
2. Navigate to Analyzer
3. Enter property details and click "Analyze"
4. Check for Save button

**Expected Results:**
- [ ] Save button is NOT visible
- [ ] Message shown: "💡 Saving deals requires additional permissions..."
- [ ] Can still view analysis results
- [ ] Can navigate to Portfolio (view-only)

**Notes:** Read-only role lacks `asset:manage` capability. UI should prevent save action.

---

### ✅ Test 4: Pro Plan + Owner - Premium Features

**Scenario:** Verify pro plan owner has access to premium capabilities

**Steps:**
1. Login as `owner@pro.com` (pro plan, owner role)
2. Navigate to Analyzer
3. Analyze a property
4. Check sidebar capabilities (Debug UI)
5. Try to export CSV (when implemented)

**Expected Results:**
- [ ] Sidebar shows "Plan: pro | Role: owner"
- [ ] Capabilities include `export:csv`
- [ ] Capabilities include `analysis:portfolio`
- [ ] IRR/NPV calculations visible (pro plan feature)
- [ ] Save button appears (has `asset:manage`)
- [ ] Can save up to 250 deals (pro limit)

**Notes:** Pro plan unlocks premium features like CSV export and portfolio analysis.

---

### ✅ Test 5: Delete & Restore Actions

**Scenario:** Verify delete/restore respects capability gating

**Steps:**
1. Login as `member@free.com`
2. Navigate to Portfolio
3. Find a saved deal and click Delete
4. Navigate to Trash
5. Click Restore on the deleted deal

**Expected Results:**
- [ ] Delete button visible (has `asset:manage`)
- [ ] Delete succeeds (item moves to Trash)
- [ ] Restore button visible in Trash
- [ ] Restore succeeds (item returns to Portfolio)
- [ ] If logged in as read-only, delete/restore not available

**Notes:** Delete and restore require `asset:manage` capability.

---

### ✅ Test 6: Backend Enforces Tenant Isolation

**Scenario:** Verify backend blocks cross-tenant actions (404/403)

**Steps:**
1. Login as `owner@free.com` (Account 1)
2. Note a property_id from Portfolio
3. Logout
4. Login as `owner@pro.com` (Account 2)
5. Try to delete the property_id from Account 1 using browser DevTools or API client

**Expected Results:**
- [ ] Backend returns 404 (property not found) or 403 (forbidden)
- [ ] Property remains in Account 1's portfolio
- [ ] No data leakage across accounts

**Notes:** Backend must enforce tenant boundaries regardless of frontend UI.

---

### ✅ Test 7: Capability Cache Persistence

**Scenario:** Verify capabilities persist across page navigations

**Steps:**
1. Login as `member@free.com`
2. Verify capabilities are cached (check sidebar)
3. Navigate from Analyzer → Portfolio → Analyzer
4. Check sidebar capabilities again

**Expected Results:**
- [ ] Capabilities remain cached across navigation
- [ ] No additional backend calls to `/account/capabilities`
- [ ] UI gating remains consistent
- [ ] No "Loading permissions..." flicker

**Notes:** Capabilities are fetched once per session and cached.

---

### ✅ Test 8: Session Refresh with Token Rotation

**Scenario:** Verify capabilities remain valid after token refresh

**Steps:**
1. Login as `owner@free.com`
2. Wait for access token to expire (or manually trigger refresh)
3. Perform an authenticated action (e.g., save a deal)
4. Verify capabilities still work

**Expected Results:**
- [ ] Token refresh succeeds automatically
- [ ] Capabilities remain cached
- [ ] Actions continue to work without re-login
- [ ] No capability re-fetch needed

**Notes:** Capabilities are tied to role/plan, which don't change during refresh.

---

### ✅ Test 9: Error Messaging (403 vs 402)

**Scenario:** Verify clear error messages for gating failures

**Steps:**
1. Login as `member@free.com`
2. Save 25 deals (free plan limit)
3. Try to save the 26th deal
4. Login as `readonly@free.com`
5. Try to perform a write action via API (if exposed)

**Expected Results:**
- [ ] 26th deal returns 402 with message: "Plan upgrade required - pro plan or higher needed..."
- [ ] Read-only write attempt returns 403 with message: "Insufficient permissions..."
- [ ] Frontend shows user-friendly error messages
- [ ] Errors don't expose sensitive info (no tokens, no PII)

**Notes:** 402 = plan restriction, 403 = role restriction.

---

### ✅ Test 10: Logout Clears Capabilities

**Scenario:** Verify capabilities are cleared on logout

**Steps:**
1. Login as `owner@free.com`
2. Verify capabilities are cached
3. Logout
4. Check session state (DevTools if needed)

**Expected Results:**
- [ ] `st.session_state["capabilities"]` is cleared
- [ ] `st.session_state["auth_token"]` is cleared
- [ ] Navigates to Login page
- [ ] No stale capability data remains

**Notes:** Security: old capabilities must not persist after logout.

---

## Summary Checklist

After completing all tests, verify:

- [ ] Capabilities load automatically after login/resume
- [ ] UI gating is accurate (no false positives/negatives)
- [ ] Backend remains authoritative (UI is convenience only)
- [ ] Error messages are clear and user-friendly
- [ ] Tenant isolation is enforced (no cross-account access)
- [ ] Capabilities persist across navigation
- [ ] Logout clears capability cache
- [ ] Read-only role correctly limits write actions
- [ ] Plan upgrades unlock new capabilities
- [ ] Tests pass: `pytest backend/test_capabilities.py -v`

---

## Troubleshooting

### Issue: "Capabilities: not cached" persists after login
**Solution:** Check browser console for errors. Verify `/account/capabilities` endpoint returns 200. Check `fetch_and_cache_capabilities()` is called after login.

### Issue: Save button hidden even for owner/member
**Solution:** Check sidebar "can('asset:manage')" shows True. Verify role and plan in capabilities response. Check backend logs for auth context.

### Issue: 500 errors after login
**Solution:** Check for `sqlite3.Row.get()` errors in logs. Verify `row_to_dict()` is used or bracket notation only. Run `pytest backend/test_analyze_regression.py`.

### Issue: Cross-tenant data visible
**Solution:** Check backend logs for tenant isolation violations. Verify all queries include `account_id` filter. Review tenant guardrail logs.

---

## Related Files

- **Backend:** `backend/main.py` (`/account/capabilities` endpoint)
- **Frontend:** `frontend/app.py` (`fetch_and_cache_capabilities()`, `can()`)
- **RBAC Logic:** `backend/rbac.py` (`effective_capabilities()`)
- **Tests:** `backend/test_capabilities.py`, `backend/test_analyze_regression.py`
- **Docs:** This file

---

**Last Updated:** January 15, 2026  
**Maintainer:** Brinkadata Team
