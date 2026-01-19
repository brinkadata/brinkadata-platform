# Property Search + Assets MVP - Manual Test Checklist

**Date:** 2026-01-17  
**Features:** Property Search (MVP) + Assets (MVP)  
**Backend Endpoints:** `/search/properties`, `/assets/list`, `/assets/get`, `/assets/create`, `/assets/update`, `/assets/delete`  
**Frontend Pages:** Property Search, Assets  

---

## Prerequisites

1. ✅ Backend running: `uvicorn backend.main:app --reload` (port 8000)
2. ✅ Frontend running: `streamlit run frontend/app.py` (port 8501)
3. ✅ Database initialized (brinkadata.db with new tables: `assets`, `search_properties_cache`)
4. ✅ Test user with Pro+ plan (for `search:advanced` and `asset:manage` capabilities)

---

## Test 1: Navigation to New Pages

### Property Search Navigation
1. Login with Pro+ user
2. Open sidebar navigation
3. ✅ **EXPECTED:** "🔹 Property Search" appears (unlocked, no 🔒)
4. Click "Property Search"
5. ✅ **EXPECTED:** Property Search page renders
6. ✅ **EXPECTED:** No regressions on Analyzer, Portfolio, Plans pages

### Assets Navigation
1. Open sidebar navigation
2. ✅ **EXPECTED:** "🔹 Assets" appears (unlocked)
3. Click "Assets"
4. ✅ **EXPECTED:** Assets page renders
5. ✅ **EXPECTED:** No regressions on other pages

### Locked State (Free Plan User)
1. Logout, login with Free plan user
2. Open sidebar
3. ✅ **EXPECTED:** "🔒 Property Search (Coming Soon)" appears (locked)
4. ✅ **EXPECTED:** "🔒 Assets (Coming Soon)" appears (locked)
5. Click locked items
6. ✅ **EXPECTED:** Info message about upgrade/permissions requirement

---

## Test 2: Property Search - Basic Flow

### Search Form
1. Navigate to Property Search page
2. ✅ **EXPECTED:** Search form renders with fields: Address/Keyword, City, State, ZIP, Limit slider
3. ✅ **EXPECTED:** "Search Properties" button appears

### Search Execution
1. Enter search criteria (e.g., City: "Atlanta", State: "GA")
2. Click "Search Properties"
3. ✅ **EXPECTED:** Loading spinner appears
4. ✅ **EXPECTED:** Results table displays (DataFrame with columns: ID, Address, City, State, ZIP, Beds, Baths, Sq Ft, Est. Price)
5. ✅ **EXPECTED:** Success message shows result count

### Empty Results
1. Search with non-matching criteria (e.g., City: "NonExistent")
2. ✅ **EXPECTED:** "No properties found" info message

### Search Filters
1. Test each filter independently:
   - City filter only
   - State filter only
   - ZIP filter only
   - Query string (address keyword) only
   - Combined filters (City + State + ZIP)
2. ✅ **EXPECTED:** Results filtered correctly

---

## Test 3: Property Search - Property Detail

### Selection
1. Execute a search that returns results
2. Select a property from "Select property to view details" dropdown
3. ✅ **EXPECTED:** Detail panel appears below results
4. ✅ **EXPECTED:** Metrics display: Address, City/State, ZIP, Beds/Baths, Sq Ft, Est. Price

### "Analyze this Property" Button
1. With property selected, click "📊 Analyze this Property"
2. ✅ **EXPECTED:** Navigate to Analyzer page
3. ✅ **EXPECTED:** Address fields prefilled from selected property (property_name, city, state, zip_code)
4. ✅ **EXPECTED:** No errors in console
5. Navigate back to Property Search
6. ✅ **EXPECTED:** Property Search state preserved (results still visible)

### "Save as Asset" Button (Pro+ User)
1. With property selected, click "💾 Save as Asset"
2. ✅ **EXPECTED:** Success message "Asset #{id} created successfully!"
3. Navigate to Assets page
4. ✅ **EXPECTED:** New asset appears in list with correct data

### "Save as Asset" Button (Free Plan User)
1. Logout, login with Free user
2. Navigate to Property Search (if capability check fails, test skipped - expected)
3. ✅ **EXPECTED:** "Save as Asset" button disabled (🔒)
4. ✅ **EXPECTED:** Warning message about permissions/upgrade

---

## Test 4: Assets - List View

### Load Assets
1. Navigate to Assets page (as Pro+ user)
2. ✅ **EXPECTED:** "Your Assets (N)" header shows count
3. ✅ **EXPECTED:** Table displays assets with columns: ID, Name, Address, City, State, ZIP, Created
4. ✅ **EXPECTED:** No assets case: "No assets yet" info message

### Asset Selection
1. Select an asset from "Select asset to view/manage" dropdown
2. ✅ **EXPECTED:** Asset detail panel appears
3. ✅ **EXPECTED:** Metrics display correctly
4. ✅ **EXPECTED:** Related deals section appears (may be empty)

---

## Test 5: Assets - Create Asset

### Create Form
1. On Assets page, expand "➕ Create Asset"
2. ✅ **EXPECTED:** Form fields appear: Name, Address, City, State, ZIP, Notes (optional)

### Valid Creation
1. Fill all required fields (Address, City, State)
2. Click "➕ Create Asset"
3. ✅ **EXPECTED:** Success message "Asset #{id} created successfully!"
4. ✅ **EXPECTED:** Page reruns and new asset appears in list
5. ✅ **EXPECTED:** Asset count increments

### Invalid Creation
1. Leave required fields blank
2. Click "Create Asset"
3. ✅ **EXPECTED:** Warning message "Please provide at least Address, City, and State"

---

## Test 6: Assets - Edit Asset

### Edit Form
1. Select an asset from list
2. Expand "✏️ Edit Asset"
3. ✅ **EXPECTED:** Form prefilled with current asset data

### Update Asset
1. Change Name to "Updated Name"
2. Change Notes to "Updated notes"
3. Click "💾 Save Changes"
4. ✅ **EXPECTED:** Success message "Asset updated successfully!"
5. ✅ **EXPECTED:** Page reruns with updated data displayed

### Update Validation
1. Verify updated fields persist after rerun
2. Navigate away and back to Assets page
3. ✅ **EXPECTED:** Updated asset data still shows

---

## Test 7: Assets - Delete Asset

### Delete Flow
1. Select an asset
2. Click "🗑️ Delete Asset"
3. ✅ **EXPECTED:** Confirm checkbox appears
4. Check "Confirm deletion of Asset #{id}"
5. Click "Delete Asset" again (or observe button behavior)
6. ✅ **EXPECTED:** Success message "Asset deleted successfully!"
7. ✅ **EXPECTED:** Asset removed from list
8. ✅ **EXPECTED:** Asset count decrements

### Delete Validation
1. Try to get deleted asset detail via dropdown
2. ✅ **EXPECTED:** Asset no longer appears in selection dropdown

---

## Test 8: Multi-Tenant Isolation

### Account Scoping
1. Login as User A (Account A)
2. Create Asset X
3. ✅ **EXPECTED:** Asset X appears in User A's assets list
4. Logout, login as User B (Account B)
5. Navigate to Assets page
6. ✅ **EXPECTED:** Asset X does NOT appear in User B's assets list
7. ✅ **EXPECTED:** User B cannot access Asset X via direct API call (404)

### Search Scoping
1. User A searches properties
2. ✅ **EXPECTED:** Search results returned (no cross-tenant data leak)
3. User B searches properties
4. ✅ **EXPECTED:** Independent results (no visibility into User A's search history)

---

## Test 9: RBAC Enforcement

### Asset:Manage Capability (Backend)
1. Use API client (curl/Postman) with token for user WITHOUT `asset:manage`
2. Attempt POST `/assets/create`
3. ✅ **EXPECTED:** 403 Forbidden or capability error
4. Attempt POST `/assets/update`
5. ✅ **EXPECTED:** 403 Forbidden
6. Attempt POST `/assets/delete`
7. ✅ **EXPECTED:** 403 Forbidden
8. Attempt GET `/assets/list` (read-only)
9. ✅ **EXPECTED:** May succeed (depending on read capability) OR fail gracefully

### Search:Advanced Capability
1. User with `search:basic` but not `search:advanced`
2. Navigate to Property Search
3. ✅ **EXPECTED:** Page locked or basic search only (depends on implementation)

---

## Test 10: Related Deals (Assets Detail)

### Related Deals Display
1. Create an asset with address "123 Main St", city "Atlanta", state "GA", zip "30301"
2. Navigate to Analyzer, analyze a deal with same address/city/state/zip
3. Save deal to portfolio
4. Navigate to Assets, select the asset
5. ✅ **EXPECTED:** Related deals section shows saved deal
6. ✅ **EXPECTED:** Deal fields display correctly (ID, name, city, state, strategy, grade, created_at)

### Analyze Asset Flow (NEW)
1. Navigate to Assets page
2. Select an asset from the list
3. ✅ **EXPECTED:** "📊 Analyze this Asset" button appears in Actions section
4. Click "Analyze this Asset"
5. ✅ **EXPECTED:** Navigate to Analyzer page
6. ✅ **EXPECTED:** Address fields prefilled from asset (property_name, city, state, zip_code)
7. ✅ **EXPECTED:** No errors in console
8. Enter remaining analysis fields (purchase_price, rent, etc.)
9. Click "Run Analysis"
10. ✅ **EXPECTED:** Analysis runs normally with prefilled address

### Analyze Asset Capability Gating (NEW)
1. Logout, login with user WITHOUT `analysis:single_property` capability
2. Navigate to Assets page, select an asset
3. ✅ **EXPECTED:** "🔒 Analyze this Asset" button disabled
4. ✅ **EXPECTED:** Warning caption about permissions
5. Login with user WITH capability
6. ✅ **EXPECTED:** Button enabled and functional

---

## Test 11: Regression Testing

### Existing Flows Unaffected
1. Analyzer page:
   - ✅ Analyze a deal (Rental/Flip/BRRRR)
   - ✅ Save to portfolio
   - ✅ Scenarios A/B/C work
2. Portfolio page:
   - ✅ Load saved deals
   - ✅ Delete to trash
   - ✅ Restore from trash
   - ✅ CSV export (Pro+ users)
3. Plans & Billing page:
   - ✅ View plans
   - ✅ Upgrade (if implemented)
4. Login/Logout:
   - ✅ Login flow works
   - ✅ Logout clears session
   - ✅ Resume session works

---

## Test 12: Edge Cases

### Empty State Handling
1. New account with no assets
2. ✅ **EXPECTED:** "No assets yet" message
3. Search with no results
4. ✅ **EXPECTED:** "No properties found" message

### Large Datasets
1. Create 50+ assets
2. ✅ **EXPECTED:** Assets list renders without performance issues
3. Search returns 100+ results (if test data exists)
4. ✅ **EXPECTED:** DataFrame displays correctly, pagination or scrolling works

### Invalid Input
1. Search with empty form
2. ✅ **EXPECTED:** Returns all results (or safe default behavior)
3. Enter SQL injection attempt in search query (e.g., `' OR '1'='1`)
4. ✅ **EXPECTED:** No error, safe query handling (parameterized queries)

---

## Test 13: UI/UX Checks

### Consistency
1. ✅ Navigation items use consistent icons and labels
2. ✅ Capability gating messages are clear ("Upgrade your plan", "Contact admin")
3. ✅ Success messages are green, warnings are yellow, errors are red
4. ✅ Buttons use consistent styling (primary/secondary/disabled)

### Responsiveness
1. Resize browser window
2. ✅ **EXPECTED:** DataFrames and forms adapt to width
3. ✅ **EXPECTED:** No horizontal scroll (unless intentional)

### Error Handling
1. Stop backend, attempt to search
2. ✅ **EXPECTED:** Clear error message ("Failed to load", not raw exception)
3. Restart backend
4. ✅ **EXPECTED:** Subsequent requests succeed (no stale state)

---

## Test 14: Backend Automated Tests

### Run Tests
```bash
pytest backend/test_search_assets.py -v
```

### Expected Results
1. ✅ All tests pass
2. ✅ Test coverage includes:
   - Search endpoint (with/without filters)
   - Assets CRUD (create, read, update, delete)
   - Multi-tenant isolation
   - RBAC enforcement (capability gating)

---

## Summary

**Total Tests:** 14 categories, ~60 individual checks  
**Critical Paths:**
- Property Search → Analyze
- Property Search → Save as Asset → Assets page
- Assets CRUD full lifecycle
- Multi-tenant isolation (no cross-account data leaks)
- RBAC enforcement (capability gating works)

**Pass Criteria:**
- ✅ All critical paths work end-to-end
- ✅ No regressions on existing features
- ✅ Capability gating prevents unauthorized actions
- ✅ Multi-tenant isolation verified
- ✅ Backend tests pass

---

## Notes for Developers

1. **Deferred Pattern:** "Analyze this Property" uses `ss["_apply_address_payload"]` + `st.rerun()` to avoid widget key conflicts.
2. **Capability Helpers:** Use `can('asset:manage')` and `can('search:advanced')` for frontend gating.
3. **Backend Security:** All endpoints use `require_auth_context` and `require_account_id` for tenant scoping.
4. **RBAC:** `asset:manage` capability required for create/update/delete operations.
5. **Database:** New tables `assets` and `search_properties_cache` created on init.

---

**Tester:** _____________  
**Date:** _____________  
**Status:** [ ] Pass  [ ] Fail  
**Issues Found:** _____________
