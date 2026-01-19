# Quick Start - Property Search + Assets Testing

## Prerequisites
1. Backend running: `uvicorn backend.main:app --reload`
2. Frontend running: `streamlit run frontend/app.py`
3. User account with Pro+ plan (for capabilities)

---

## Quick Test Flow (5 minutes)

### 1. Login & Verify Navigation (1 min)
```
✅ Login with Pro+ user
✅ Check sidebar: "🔹 Property Search" and "🔹 Assets" appear (unlocked)
✅ Click each nav item → verify pages load
```

### 2. Property Search (2 min)
```
✅ Navigate to Property Search
✅ Enter: City="Atlanta", State="GA"
✅ Click "Search Properties"
✅ Verify results table displays (3 mock properties)
✅ Select "Property #1" from dropdown
✅ Verify detail panel shows address, beds/baths, price
✅ Click "📊 Analyze this Property"
✅ Verify Analyzer page loads with address prefilled
```

### 3. Assets (2 min)
```
✅ Navigate to Assets page
✅ Expand "➕ Create Asset"
✅ Fill: Address="123 Test St", City="Atlanta", State="GA", ZIP="30301"
✅ Click "Create Asset"
✅ Verify success message and asset appears in list
✅ Select asset from dropdown
✅ Verify detail panel shows asset info
✅ Click "📊 Analyze this Asset" (NEW)
✅ Verify Analyzer page loads with address prefilled
✅ Navigate back to Assets
✅ Expand "✏️ Edit Asset"
✅ Change Name to "Updated Test"
✅ Click "Save Changes"
✅ Verify name updated
✅ Click "🗑️ Delete Asset"
✅ Check confirmation box
✅ Verify asset removed from list
```

---

## Quick Smoke Test Commands

### Backend Health Check
```bash
# Check backend is running
curl http://localhost:8000/health

# Check database tables exist
sqlite3 brinkadata.db "SELECT name FROM sqlite_master WHERE type='table' AND (name='assets' OR name='search_properties_cache');"
```

### Backend API Test (Manual)
```bash
# Login to get token
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@brinkadata.com","password":"test123"}' \
  | jq -r '.access_token')

# Test search endpoint
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/search/properties?city=Atlanta&limit=10"

# Test assets list
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/assets/list"

# Create test asset
curl -X POST http://localhost:8000/assets/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"address":"123 API Test St","city":"Atlanta","state":"GA","zip_code":"30301"}'
```

### Run Backend Tests
```bash
# Run automated tests
pytest backend/test_search_assets.py -v

# Expected: All tests pass (16 tests)
```

---

## Common Issues & Fixes

### Issue: Navigation items are locked (🔒)
**Cause:** User doesn't have required capabilities  
**Fix:**
```bash
# Check capabilities
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/auth/capabilities

# Grant capabilities (dev admin endpoint)
curl -X POST http://localhost:8000/admin/set_plan \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"plan":"pro"}'
```

### Issue: Search returns empty results
**Expected:** MVP returns 3 mock properties  
**Fix:** No fix needed - this is expected behavior

### Issue: "Save as Asset" button disabled
**Cause:** Missing `asset:manage` capability  
**Fix:** Upgrade to Pro+ plan (see above)

---

## Regression Check (1 minute)

Test existing features still work:
```
✅ Analyzer: Run analysis on a rental deal
✅ Portfolio: Save deal, load from portfolio
✅ Portfolio: Delete to trash, restore from trash
✅ Plans: View plans page (no errors)
```

---

## Pass Criteria

### Must Pass
- ✅ Property Search page loads
- ✅ Search returns results (mock data)
- ✅ "Analyze this Property" navigates correctly
- ✅ Assets page loads
- ✅ Create/Edit/Delete asset works
- ✅ No errors in browser console
- ✅ No regressions on existing features

### Nice to Have
- ✅ Backend tests pass (16/16)
- ✅ Capability gating works (locked for Free users)
- ✅ Multi-tenant isolation (test with 2 accounts)

---

## Minimal Test User Setup

### Create Test User with Capabilities
```sql
-- Insert test user
INSERT INTO users (email, password_hash, account_id, role, is_active)
VALUES ('test@brinkadata.com', 
        'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3', -- "test123"
        1, 
        'owner', 
        1);

-- Set account to Pro plan
UPDATE accounts SET plan = 'pro' WHERE id = 1;

-- Ensure subscription exists
INSERT OR REPLACE INTO subscriptions 
  (account_id, plan_id, status, plan_name, provider, current_period_start, current_period_end)
VALUES 
  (1, 2, 'active', 'pro', 'manual', datetime('now'), datetime('now', '+1 year'));
```

Then capabilities will be auto-computed based on plan.

---

## Full Manual Test Checklist

For comprehensive testing, see: [`MANUAL_TEST_SEARCH_ASSETS.md`](./MANUAL_TEST_SEARCH_ASSETS.md)

---

**Estimated Time:** 5-10 minutes for quick smoke test, 30-60 minutes for full manual checklist
