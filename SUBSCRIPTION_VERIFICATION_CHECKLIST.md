# Subscription System Verification Checklist

## Pre-Flight Checks

### 1. Syntax Validation ✅
```bash
python -m py_compile backend/entitlements.py
python -m py_compile backend/auth_context.py
python -m py_compile backend/dependencies.py
python -m py_compile backend/main.py
```
**Status:** All files compile without errors

### 2. Manual Tests ✅
```bash
python backend/manual_test_subscriptions.py
```
**Status:** All 6 tests passed
- ✅ Active pro subscription grants capabilities
- ✅ Past_due subscription downgrades to free
- ✅ Canceled subscription loses pro features
- ✅ Read-only role blocks writes (even on pro)
- ✅ Trialing subscription grants full access
- ✅ Plan upgrades add capabilities immediately

## Runtime Verification

### Step 1: Start Backend
```bash
uvicorn backend.main:app --reload
```

**Expected:**
- Server starts on port 8000
- Migration runs: "Ensured subscription entitlement fields"
- No errors in console

### Step 2: Test Migration (Check DB)
```bash
sqlite3 backend/brinkadata.db "SELECT * FROM subscriptions LIMIT 1;"
```

**Expected Output:**
```
id|account_id|plan_id|status|plan_name|provider|provider_customer_id|...
1|1|0|active|free|manual|NULL|...
```

**Verify:**
- ✅ `status` column exists
- ✅ `plan_name` column exists
- ✅ `provider` column exists
- ✅ `cancel_at_period_end` column exists

### Step 3: Test /account/info Endpoint

**Login and get token:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpass"}'
```

**Get account info:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/account/info
```

**Expected Response:**
```json
{
  "account_id": 1,
  "plan": "free",
  "subscription": {
    "status": "active",
    "plan": "free",
    "effective_plan": "free",
    "cancel_at_period_end": false,
    "current_period_end": "..."
  },
  "capabilities": [
    "project:view",
    "asset:view",
    "search:basic",
    "analysis:single_property"
  ],
  "usage": {...},
  "limits": {...}
}
```

**Verify:**
- ✅ `subscription` object present
- ✅ `capabilities` array present
- ✅ Free plan has 4 basic capabilities
- ✅ No pro capabilities (export:csv, asset:manage, etc.)

### Step 4: Test Admin Upgrade Endpoint

```bash
curl -X POST "http://localhost:8000/admin/set_plan?account_id=1&plan=pro"
```

**Expected Response:**
```json
{
  "status": "ok",
  "account_id": 1,
  "plan": "pro",
  "subscription_status": "active"
}
```

**Verify:**
- ✅ Returns success
- ✅ Includes subscription_status

**Re-check /account/info:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/account/info
```

**Expected:**
- ✅ `plan` is now "pro"
- ✅ `subscription.plan` is "pro"
- ✅ `capabilities` includes "export:csv", "asset:manage"
- ✅ Changes took effect immediately

### Step 5: Test Past Due Downgrade

```bash
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=past_due"
```

**Expected Response:**
```json
{
  "status": "ok",
  "account_id": 1,
  "subscription_status": "past_due"
}
```

**Re-check /account/info:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/account/info
```

**Expected:**
- ✅ `subscription.status` is "past_due"
- ✅ `subscription.plan` is still "pro"
- ✅ `subscription.effective_plan` is "free"
- ✅ `capabilities` no longer includes "export:csv"
- ✅ Downgrade took effect immediately

### Step 6: Test Canceled Subscription

```bash
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=canceled"
```

**Re-check /account/info:**

**Expected:**
- ✅ `subscription.status` is "canceled"
- ✅ `subscription.effective_plan` is "free"
- ✅ Pro capabilities revoked

### Step 7: Test Restoration

```bash
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=active"
```

**Re-check /account/info:**

**Expected:**
- ✅ `subscription.status` is "active"
- ✅ `subscription.effective_plan` is "pro"
- ✅ Pro capabilities restored immediately

### Step 8: Test Frontend

```bash
streamlit run frontend/app.py
```

**Navigate to "Plans & Billing":**

**Verify:**
- ✅ Page loads without errors
- ✅ Current plan shows "Pro"
- ✅ Status badge shows "✅ Active"
- ✅ Usage stats display correctly

**Test Past Due UI (use admin endpoint first):**

```bash
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=past_due"
```

**Refresh Plans & Billing page:**

**Expected:**
- ✅ Red warning: "⚠️ Payment Required - Your subscription is past due..."
- ✅ Status badge shows "⚠️ Past Due"
- ✅ Shows downgrade notice: "Subscribed to Pro but currently on Free..."

**Test Canceled UI:**

```bash
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=canceled"
```

**Refresh Plans & Billing page:**

**Expected:**
- ✅ Orange warning: "⚠️ Subscription Canceled - Your subscription has been canceled..."
- ✅ Status badge shows "❌ Canceled"

## Regression Tests

### Test 1: Existing Endpoints Still Work
```bash
# Analyzer endpoint
curl -X POST http://localhost:8000/property/analyze \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"purchase_price":100000,"monthly_rent":1000}'
```

**Expected:**
- ✅ Returns analysis result
- ✅ No breaking changes

### Test 2: Save/Load Portfolio
```bash
# Save a property
curl -X POST http://localhost:8000/property/save \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"address":"123 Test St","analysis_result":{...}}'

# Load portfolio
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/property/list
```

**Expected:**
- ✅ Save works
- ✅ Load works
- ✅ Tenant isolation preserved

### Test 3: Role-Based Access Control
```bash
# Set user to read_only
curl -X POST "http://localhost:8000/admin/set_role?user_id=1&role=read_only"

# Try to save (should fail)
curl -X POST http://localhost:8000/property/save \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"address":"123 Test St","analysis_result":{...}}'
```

**Expected:**
- ✅ Returns 403 Forbidden
- ✅ Read-only restrictions still enforced

## Final Checklist

- [ ] Backend starts without errors
- [ ] Migration runs successfully
- [ ] /account/info returns subscription object
- [ ] /account/info returns capabilities array
- [ ] Admin endpoints modify subscription state
- [ ] Active pro subscription grants pro capabilities
- [ ] Past_due subscription downgrades immediately
- [ ] Canceled subscription revokes pro features
- [ ] Changes take effect on next request (no cache)
- [ ] Frontend displays subscription status
- [ ] Frontend shows warnings for past_due/canceled
- [ ] Existing endpoints still work (no regressions)
- [ ] Role restrictions still enforced
- [ ] Tenant boundaries preserved
- [ ] No secrets logged

## Success Criteria

✅ All manual tests pass
✅ All runtime verification steps pass
✅ No regressions in existing features
✅ Frontend reflects subscription state correctly
✅ Admin endpoints work for testing
✅ Changes take effect immediately

## Troubleshooting

### Issue: "Column already exists" error during migration
**Solution:** Migration is idempotent, safe to ignore if columns exist

### Issue: /account/info missing subscription object
**Check:**
1. Backend restarted after code changes?
2. Token is valid and not expired?
3. Check backend logs for errors

### Issue: Capabilities not updating after admin change
**Check:**
1. Login again to get fresh token
2. Check subscription status in database:
   ```bash
   sqlite3 backend/brinkadata.db "SELECT * FROM subscriptions WHERE account_id=1;"
   ```

### Issue: Frontend not showing subscription warnings
**Check:**
1. Backend /account/info returns subscription object?
2. Browser cache cleared?
3. Streamlit app restarted?

## Commands Summary

```bash
# Run manual tests
python backend/manual_test_subscriptions.py

# Start backend
uvicorn backend.main:app --reload

# Start frontend
streamlit run frontend/app.py

# Test upgrade
curl -X POST "http://localhost:8000/admin/set_plan?account_id=1&plan=pro"

# Test past_due
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=past_due"

# Test restore
curl -X POST "http://localhost:8000/admin/set_subscription_status?account_id=1&status=active"
```
