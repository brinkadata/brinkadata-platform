# Manual Verification - Cause Tag Accuracy

## Goal
Verify that debug cause tags are:
1. **Specific** - Show accurate reason for state change (login, restore, preset, etc.)
2. **Single-use** - Cleared after being consumed into logs
3. **Stable** - Don't leak into future state snapshots

---

## Test Environment
- Backend running: `uvicorn backend.main:app --reload`
- Frontend running: `streamlit run frontend/app.py`
- DEV mode: Verify "Debug UI: enabled" in terminal output

---

## Test 14: Immediate Backend Status Detection (UX Fix)

### Goal
Verify that backend connection status updates **immediately** when clicking Portfolio with backend down, without needing to navigate away and back.

### Setup
1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `streamlit run frontend/app.py`
3. Login with valid credentials

### Steps
1. Backend is running, navigate to any page (e.g., Analyzer)
2. Verify sidebar shows: ✅ Connected
3. **STOP the backend** (Ctrl+C in backend terminal)
4. **Click "Portfolio"** in sidebar (single click)
5. Observe sidebar immediately

### Expected Results
- ✅ Sidebar **immediately** shows: ⚠️ Backend unreachable
- ✅ "🔄 Retry Connection" button appears in sidebar
- ✅ Error banner shown: "Cannot reach backend..."
- ✅ No need to click away and back
- ✅ Status updates on first click

### Part B: Retry Button Works
1. Backend still stopped, Portfolio showing error
2. **RESTART backend**: `uvicorn backend.main:app --reload`
3. **Click "🔄 Retry Connection" button** in sidebar
4. Observe behavior

### Expected Results
- ✅ Success message: "✅ Backend reconnected!"
- ✅ Sidebar shows: ✅ Connected
- ✅ Portfolio lists load successfully
- ✅ Error banner disappears

### Pass Criteria
- Backend status updates **immediately** on Portfolio click (no delayed detection)
- Retry button appears without navigation away/back
- Retry button successfully reconnects and loads data

---

## Test 1: Login Cause Tag

### Steps
1. Start app (logged out)
2. Open sidebar → "🔎 State Debug (DEV)" expander
3. Note: "Pending cause: none"
4. Close expander
5. Login with valid credentials (test@example.com / password123 or create account)
6. After redirect to Analyzer, open "🔎 State Debug (DEV)"

### Expected Results
- ✅ Recent Events shows `state_changed` with `cause: "login"`
- ✅ Change Detection shows "Pending cause: none" (cause was consumed)
- ❌ NOT "Pending cause: login" (would indicate leak)

### Pass Criteria
Cause tag "login" appears ONCE in recent events, then clears.

---

## Test 2: Restore from Trash Cause Tag

### Prerequisites
- Must have at least one deal in trash (delete a saved deal first)

### Steps
1. Go to "Portfolio" page
2. Scroll to Trash section
3. Open "🔎 State Debug (DEV)" expander
4. Note current "Pending cause"
5. Click "Restore" button on a trashed deal
6. After page reload, check State Debug

### Expected Results
- ✅ Recent Events shows:
  - `deal_restored` event (from restore action)
  - `deferred_keys_applied` event (from _refresh_portfolio_lists)
  - `state_changed` event with `cause: "restore"`
- ✅ Change Detection shows "Pending cause: none"
- ✅ Restored deal now appears in Active Deals table
- ❌ NOT "Pending cause: restore" persisting across multiple views

### Pass Criteria
Cause tag "restore" appears in state_changed event, then clears.

---

## Test 3: Preset Selection Cause Tag

### Steps
1. Go to "Analyzer" page
2. Open "🔎 State Debug (DEV)"
3. Click preset button (e.g., "SFR Flip")
4. After page reload, check State Debug

### Expected Results
- ✅ Recent Events shows `state_changed` with `cause: "preset"`
- ✅ Change Detection shows "Pending cause: none"
- ✅ Form fields populated with preset values

### Pass Criteria
Cause tag "preset" appears once, then clears.

---

## Test 4: Navigation Without State Change

### Steps
1. Login (if not already)
2. Go to "Analyzer" page
3. Open "🔎 State Debug (DEV)"
4. Note fingerprint and event count
5. Click "Portfolio" in sidebar navigation
6. Check State Debug again

### Expected Results
- ✅ If portfolio state is same as before:
  - Change Detection: "Changed since last: ❌ No"
  - Fingerprint unchanged
  - NO new `state_changed` event
  - Pending cause: "none"

- ✅ If portfolio state changed (e.g., first load):
  - Change Detection: "Changed since last: ✅ Yes"
  - New fingerprint
  - ONE `state_changed` event with `cause: "navigation"`
  - After viewing, "Pending cause: none"

### Pass Criteria
Navigation cause only appears when state actually changes, then clears.

---

## Test 5: DEV Controls (Plan Change)

### Steps
1. Open sidebar → "DEV Controls" expander
2. Change "Override Plan" from current to different (e.g., free → pro)
3. Click "Apply"
4. After page reload, open "🔎 State Debug (DEV)"

### Expected Results
- ✅ Recent Events shows `state_changed` with `cause: "plan_change"`
- ✅ Change Detection shows "Pending cause: none"
- ✅ Plan indicator updated

### Pass Criteria
Cause tag appears once for plan change, then clears.

---

## Test 6: DEV Controls (Role Change)

### Steps
1. Open "DEV Controls"
2. Change "Override Role" (e.g., owner → member)
3. Click "Apply"
4. Check State Debug

### Expected Results
- ✅ `state_changed` with `cause: "role_change"`
- ✅ "Pending cause: none" after consumption

### Pass Criteria
Cause tag appears once, then clears.

---

## Test 7: Resume Session

### Steps
1. Login normally
2. Navigate to Login page (in sidebar)
3. Check Resume Code section for your 12-char code
4. Copy resume code
5. Logout (or use incognito/private browser)
6. Start app, go to Login page
7. Paste resume code in "Resume Code" field
8. Click "🔁 Resume"
9. After redirect, check State Debug

### Expected Results
- ✅ `state_changed` with `cause: "resume"`
- ✅ "Pending cause: none"
- ✅ Logged in successfully

### Pass Criteria
Resume cause appears once, then clears.

---

## Test 8: Scenario Load

### Steps
1. Go to Analyzer
2. Run an analysis
3. Save to Scenario Slot A
4. Change some inputs
5. Open State Debug
6. Click "📂 Load from Slot" (select Slot A, click button)
7. Check State Debug after reload

### Expected Results
- ✅ `state_changed` with `cause: "scenario_load"`
- ✅ "Pending cause: none"
- ✅ Form restored to saved values

### Pass Criteria
Scenario load cause appears once, then clears.

---

## Test 9: Export Snapshot Verification

### Steps
1. Login
2. Do any action with a cause (e.g., select preset)
3. Immediately open State Debug
4. Click "📥 Export Snapshot JSON"
5. Check downloaded JSON file

### Expected Structure
```json
{
  "timestamp": "2026-01-16T...",
  "state": { ... },
  "recent_events": [
    {
      "name": "state_changed",
      "details": {
        "cause": "preset"  // ← Should match recent action
      }
    }
  ],
  "change_detection": {
    "pending_cause": "none"  // ← Should be "none" (consumed)
  }
}
```

### Expected Results
- ✅ `recent_events` shows cause in last `state_changed` event
- ✅ `change_detection.pending_cause` is "none" (not persisting)

### Pass Criteria
Exported snapshot shows cause was already consumed.

---

## Common Issues & Fixes

### Issue: Cause persists as "restore" after multiple page views
**Root Cause**: Cause not being cleared after consumption
**Fix**: Verify `get_cause_tag()` is called in `main()` and properly deletes `_debug_cause`

### Issue: Cause shows "unknown" instead of specific value
**Root Cause**: `set_debug_cause()` not called before action
**Fix**: Check that `set_debug_cause("specific_cause")` is called before `st.rerun()`

### Issue: Multiple "state_changed" events with same cause
**Root Cause**: Cause set multiple times in same flow
**Fix**: Only call `set_debug_cause()` once per user action

---

## Test 10: Capabilities Fetch Status & Throttling

### Goal
Verify that capabilities fetch errors are throttled and status is observable.

### Part A: Backend Unreachable

#### Steps
1. Login normally with backend running
2. Open "🔎 State Debug (DEV)" → check "Capabilities Fetch" section
3. Note: Status should be "✅ ok"
4. Stop the backend (Ctrl+C in backend terminal)
5. Refresh browser or trigger capabilities fetch (e.g., navigate, open DEV controls)
6. Check terminal output and State Debug

#### Expected Results
- ✅ Terminal shows ONE warning: "[CAPABILITIES] No response from backend" (or similar)
- ✅ State Debug shows:
  - Status: "🔌 backend_unreachable"
  - Last error: "No response" (or "Connection failed")
  - Warnings logged: 1/3
- ✅ Wait 15+ seconds, trigger another fetch → second warning appears
- ✅ After 3rd warning, no more console spam (even if fetch continues failing)

#### Pass Criteria
- Max 3 warnings total per session
- Min 15 seconds between warnings
- Status correctly shows "backend_unreachable"

### Part B: Backend Recovery

#### Steps
1. With backend still stopped, verify status = "🔌 backend_unreachable"
2. Restart backend: `uvicorn backend.main:app --reload`
3. Trigger capabilities fetch (navigate, reload page, etc.)
4. Check State Debug

#### Expected Results
- ✅ Status changes to "✅ ok"
- ✅ Recent Events shows `capabilities_fetch_status` with `status: "ok"` and `changed: true`
- ✅ Last error: None (or cleared)
- ✅ No more warnings in console

#### Pass Criteria
Status automatically updates to "ok" when backend recovers.

### Part C: Not Authenticated

#### Steps
1. Logout
2. Open State Debug (should still be accessible on Login page)
3. Check Capabilities Fetch section

#### Expected Results
- ✅ Status: "🔒 not_authenticated"
- ✅ Last error: "No auth token"
- ✅ No console warnings (no fetch attempted)

#### Pass Criteria
No fetch attempts when not logged in, status shows "not_authenticated".

---

## Test 11: API Observability - Phase 2 (Backend Unreachable)

### Goal
Verify that API calls are tracked, errors are throttled, and status is observable in State Debug UI.

### Part A: Stop Backend and Check API Health

#### Steps
1. Login normally with backend running
2. Open "🔎 State Debug (DEV)" → scroll to "API Health" section
3. Note current statuses (should show several endpoints with "✅ ok")
4. Stop the backend (Ctrl+C in backend terminal)
5. Go to Portfolio page (triggers /property/saved and /property/trash calls)
6. Check State Debug → API Health section

#### Expected Results
- ✅ API Health shows:
  - `/property/saved`: Status "🔌 no_response", age recent, err_count incremented
  - `/property/trash`: Status "🔌 no_response", age recent, err_count incremented
  - Last error: "No response from backend" or "Connection failed"
- ✅ Terminal shows throttled warnings (max one per endpoint per 15s)
- ✅ Portfolio page shows empty/no deals (graceful degradation)

#### Pass Criteria
- API health status accurately reflects backend state
- Errors throttled (not spamming console)
- UI doesn't crash, shows graceful fallback

### Part B: Restart Backend and Verify Recovery

#### Steps
1. With backend still stopped, verify API Health shows "no_response"
2. Restart backend: `uvicorn backend.main:app --reload`
3. Refresh Portfolio page or navigate away and back
4. Check State Debug → API Health section

#### Expected Results
- ✅ `/property/saved`: Status changes to "✅ ok"
- ✅ `/property/trash`: Status changes to "✅ ok"
- ✅ ok_count incremented, no new errors
- ✅ Portfolio displays deals normally

#### Pass Criteria
Status automatically updates to "ok" when backend recovers.

### Part C: Restore from Trash (Deferred Key + API Tracking)

#### Prerequisites
- Backend running, at least one deal in trash

#### Steps
1. Go to Portfolio → Trash section
2. Open State Debug
3. Note current API Health for `/property/trash` and `/property/saved`
4. Click "Restore" on a trashed deal
5. After page reload, check:
   - Deal moved from Trash to Active Deals
   - State Debug → API Health section

#### Expected Results
- ✅ `/property/trash/restore`: Shows in API Health with "✅ ok"
- ✅ `/property/trash`: Refreshed, ok_count incremented
- ✅ `/property/saved`: Refreshed, ok_count incremented
- ✅ Recent Events shows `api_health_update` events
- ✅ Deferred key `_refresh_portfolio_lists` was applied (not broken by tracking)

#### Pass Criteria
- Restore works normally (no regression)
- API calls tracked in health registry
- Deferred pattern still functional

### Part D: DEV Controls /account/info Tracking

#### Steps
1. Login
2. Open sidebar → "🧪 DEV Test Controls" expander
3. Check State Debug → API Health section
4. Look for `/account/info` endpoint

#### Expected Results
- ✅ `/account/info`: Status "✅ ok" (loaded for DEV controls)
- ✅ Shows ok_count, age, HTTP status 200
- ✅ No errors

#### Pass Criteria
/account/info call is tracked and status visible.

### Part E: Address Lookup Failure (Graceful Degradation)

**Note**: This test assumes address/zip autocomplete exists. If not implemented, skip.

#### Steps
1. Go to Analyzer page
2. Stop backend
3. Type in address or zip field (if autocomplete implemented)
4. Check State Debug → API Health

#### Expected Results
- ✅ Address lookup endpoint shows "🔌 no_response" or "not_authenticated"
- ✅ UI doesn't crash or force logout
- ✅ Manual entry still possible (graceful fallback)

#### Pass Criteria
Address lookup failures don't break navigation or login flow.

---

## Test 12: Backend Recovery Auto-Refresh

### Goal
Verify that when backend transitions from unreachable to reachable, the current page automatically refreshes its data WITHOUT requiring navigation away/back.

### Part A: Portfolio Recovery (Key Feature)

#### Setup
1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `streamlit run frontend/app.py`
3. Login with valid credentials
4. Navigate to "Portfolio" page
5. Ensure you have at least one saved deal visible

#### Steps
1. Open "🔎 State Debug (DEV)" expander
2. Note API Health shows "/property/saved" with status "✅ ok"
3. **STOP the backend** (Ctrl+C in backend terminal)
4. Wait 5 seconds, then refresh Portfolio page (or click sidebar "Portfolio" again)
5. Observe error banner: "Error loading saved deals"
6. Check State Debug → API Health → "/property/saved" shows "🔌 no_response"
7. **RESTART backend**: `uvicorn backend.main:app --reload`
8. Wait ~3-5 seconds (backend starts)
9. **Without navigating away**, observe page behavior

#### Expected Results
- ✅ After backend restart (within 5-10s), Portfolio lists auto-refresh and appear
- ✅ Error banner disappears naturally (no manual navigation needed)
- ✅ State Debug → Recent Events shows `backend_recovered` event with:
  - `endpoint: "/property/saved"`
  - `old_status: "no_response"`
  - `new_status: "ok"`
- ✅ State Debug → Change Detection shows "Pending cause: none" (ONE-SHOT consumption)
- ✅ Console shows: `[RECOVERY] Portfolio auto-refresh triggered for /property/saved`
- ✅ API Health shows "/property/saved" status "✅ ok"

#### Pass Criteria
- Portfolio data appears WITHOUT clicking away and back
- Exactly ONE `backend_recovered` event in recent events
- No infinite rerun loop (page stabilizes after 1-2 reruns)

---

### Part B: Trash Recovery

#### Setup
1. Backend running, Portfolio page open
2. Ensure you have at least one deal in Trash section

#### Steps
1. Stop backend (Ctrl+C)
2. Scroll to Trash section
3. Click "Restore" on any trashed deal → error shown
4. Check State Debug → API Health → "/property/trash" shows "🔌 no_response"
5. Restart backend
6. Wait 5-10 seconds (without navigation)

#### Expected Results
- ✅ Trash list auto-refreshes when backend recovers
- ✅ Restore operation succeeds automatically if triggered during downtime
- ✅ Recent Events shows `backend_recovered` for "/property/trash"
- ✅ Console shows: `[RECOVERY] Portfolio auto-refresh triggered for /property/trash`

---

### Part C: Analyzer Recovery (Graceful)

#### Setup
1. Backend running, navigate to "Analyzer" page
2. Backend stops during analysis

#### Steps
1. Navigate to Analyzer
2. Enter address/property data
3. Stop backend
4. Click "🔬 Analyze Deal" → error shown
5. Check State Debug → API Health → "/property/analyze" shows "🔌 no_response"
6. Restart backend
7. Wait 5-10 seconds

#### Expected Results
- ✅ Page reruns once to clear error banner
- ✅ Recent Events shows `backend_recovered` for "/property/analyze"
- ✅ Console shows: `[RECOVERY] Analyzer rerun triggered for /property/analyze`
- ✅ No data loss (form fields retain values)
- ⚠️ User must re-click "Analyze" (expected: analyzer has no persistent data to auto-refresh)

---

### Part D: No Spam - One Recovery Event Per Transition

#### Steps
1. Backend running, Portfolio page open
2. Stop backend → wait for "no_response"
3. Restart backend → wait for recovery
4. **Refresh page 3-5 times** (simulate multiple requests)
5. Check State Debug → Recent Events

#### Expected Results
- ✅ Exactly ONE `backend_recovered` event for each endpoint (no duplicates per transition)
- ✅ Subsequent API calls show "ok" status but don't trigger more recovery events
- ✅ No log spam: recovery message appears once per endpoint

#### Pass Criteria
- Recovery detection is ONE-SHOT per transition
- No repeated `backend_recovered` events after status stabilizes at "ok"

---

### Part E: Cross-Page Recovery

#### Steps
1. Backend running, on Analyzer page
2. Stop backend
3. Click "Portfolio" in sidebar → error shown
4. Check State Debug → API Health shows failures
5. Restart backend
6. Stay on Portfolio (don't navigate away)

#### Expected Results
- ✅ Portfolio lists auto-populate when endpoints recover
- ✅ Recent Events shows `backend_recovered` for multiple endpoints (e.g., "/property/saved", "/property/trash")
- ✅ Page stabilizes after 1-2 reruns (no infinite loop)

#### Pass Criteria
- Multi-endpoint recovery works correctly
- Page-aware refresh logic triggers appropriate actions

---

## Pass/Fail Criteria

### ✅ PASS if:
- All 14 tests show correct behavior
- **Backend status updates immediately on Portfolio click (Test 14)**
- **Retry button appears without navigation away/back (Test 14)**
- **Retry button successfully reconnects (Test 14B)**
- Cause tags appear once then clear (Tests 1-9)
- Capabilities fetch throttled: max 3 warnings, min 15s apart (Test 10A)
- Status observable in State Debug UI (Test 10B-C)
- **API Health section displays tracked endpoints (Test 11)**
- **API errors throttled (max once per endpoint per 15s)**
- **Backend recovery updates status to "ok"**
- **Portfolio auto-refreshes on recovery WITHOUT manual navigation (Test 12)**
- **Recovery triggers exactly ONE event per endpoint per transition (Test 12D)**
- **No infinite rerun loops after recovery (Test 12A-E)**
- **Restore from trash still works (deferred pattern intact) (Test 12B)**
- "Pending cause" shows "none" after being consumed
- No cause leakage across unrelated actions
- Exported snapshots reflect consumed state

---

## Test 13: Portfolio Auto-Refresh with Timer-Based Recovery

### Goal
Verify that Portfolio automatically recovers when backend restarts using a background timer that only runs when the backend is unreachable.

### Setup
1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `streamlit run frontend/app.py`
3. Login with valid credentials
4. Save at least one deal (if not already saved)
5. Navigate to "Portfolio" page

### Part A: Backend Healthy - No Auto-Refresh

#### Steps
1. On Portfolio page, verify deals are visible
2. Check State Debug UI → Portfolio Auto-Recovery section
3. Observe page behavior (no flickering or reruns)

#### Expected Results
- ✅ Portfolio data loads immediately
- ✅ State Debug shows: "Active: ⏸️ NO"
- ✅ No auto-refresh timer running (page is stable)
- ✅ No unnecessary reruns

#### Pass Criteria
Auto-refresh timer is OFF when backend is healthy.

---

### Part B: Backend Down - Timer Activates

#### Steps
1. On Portfolio page with backend running
2. **STOP the backend** (Ctrl+C in backend terminal)
3. Click "Portfolio" in sidebar to refresh page
4. Observe page behavior

#### Expected Results
- ✅ Page shows: "🔄 Attempting to reconnect to backend... (attempt 1/10)"
- ✅ Page automatically reruns every ~2 seconds
- ✅ State Debug shows:
  - "Active: 🔄 YES"
  - "Attempts: 1/10", then "2/10", etc.
  - "Endpoint /property/saved: no_response"
- ✅ Console shows (if DEV mode): `[PORTFOLIO RECOVERY] Activated (backend unreachable)`
- ✅ Console shows (if DEV mode): `[PORTFOLIO RECOVERY] Attempt 1/10`, `Attempt 2/10`, etc.

#### Pass Criteria
Auto-refresh timer activates and increments attempts counter.

---

### Part C: Backend Recovery - Timer Stops (KEY TEST)

#### Steps
1. Portfolio showing reconnection message (backend still stopped)
2. **RESTART backend**: `uvicorn backend.main:app --reload`
3. Wait ~2-10 seconds (do NOT navigate or click anything)
4. Observe page behavior

#### Expected Results
- ✅ Within ~10 seconds, Portfolio lists **automatically populate**
- ✅ Saved deals reappear WITHOUT manual navigation
- ✅ Reconnection message disappears
- ✅ Auto-refresh timer **stops immediately** (no more reruns)
- ✅ State Debug shows:
  - "Active: ⏸️ NO"
  - "Attempts: 0/10" (reset)
  - "Endpoint /property/saved: ok"
- ✅ Console shows (if DEV mode): `[PORTFOLIO RECOVERY] Deactivated (backend recovered)`
- ✅ Page stabilizes (no more automatic reruns)

#### Pass Criteria
- Portfolio auto-recovers within 10 seconds
- Timer stops immediately after success
- No infinite rerun loop

---

### Part D: Retry Limit - Max 10 Attempts

#### Steps
1. On Portfolio page with backend running
2. Stop backend
3. Click "Portfolio" → reconnection message shown
4. **DO NOT restart backend**
5. Wait ~20 seconds, observe behavior

#### Expected Results
- ✅ Console shows (if DEV mode): `[PORTFOLIO RECOVERY] Attempt 1/10`, `2/10`, ..., `10/10`
- ✅ After 10th attempt (~20 seconds), timer **stops automatically**
- ✅ Error message changes to: "⚠️ Unable to connect to backend after 10 attempts. Please check if the backend is running, then click 'Portfolio' to retry."
- ✅ "Reset & Retry" button appears
- ✅ No more automatic reruns (page is stable)
- ✅ State Debug shows: "Attempts: 10/10"

#### Pass Criteria
- Exactly 10 retry attempts
- Timer stops after limit reached
- Clear error message and manual retry option provided

---

### Part E: Manual Reset After Limit

#### Steps
1. Backend stopped, Portfolio hit 10-attempt limit
2. Error shows: "Unable to connect to backend after 10 attempts"
3. Restart backend
4. **Click "Reset & Retry" button** (on error screen)

#### Expected Results
- ✅ Recovery state resets
- ✅ Portfolio data loads successfully
- ✅ State Debug shows:
  - "Active: ⏸️ NO"
  - "Attempts: 0/10"
  - "Endpoint /property/saved: ok"
- ✅ Console shows (if DEV mode): `[PORTFOLIO RECOVERY] Deactivated (backend recovered)`

#### Pass Criteria
Manual reset button works after limit reached.

---

### Part F: Timer Interval - 2 Seconds

#### Steps
1. Backend stopped, Portfolio showing reconnection attempts
2. Observe timing between reruns (watch page flicker or counter updates)
3. Use stopwatch or console timestamps (if DEV mode)

#### Expected Results
- ✅ Approximately 2 seconds between each rerun
- ✅ Counter increments: 1/10 → wait ~2s → 2/10 → wait ~2s → 3/10, etc.
- ✅ No rapid-fire reruns (<1 second apart)

#### Pass Criteria
Timer respects PORTFOLIO_RECOVERY_INTERVAL_MS (2000ms = 2 seconds).

---

### Part G: Navigation Away Stops Timer

#### Steps
1. Backend stopped, Portfolio timer active (reconnection attempts running)
2. Navigate to "Analyzer" page (click in sidebar)
3. Wait 5 seconds
4. Navigate back to "Portfolio"

#### Expected Results
- ✅ Timer stops when navigating away from Portfolio
- ✅ Analyzer page is stable (no reruns)
- ✅ Upon return to Portfolio, timer reactivates (if backend still down)
- ✅ State Debug shows attempts reset to 0 (fresh start)

#### Pass Criteria
Timer only runs on Portfolio page, not other pages.

---

## Pass/Fail Criteria

### ✅ PASS if:
- All 13 tests show correct behavior
- Cause tags appear once then clear (Tests 1-9)
- Capabilities fetch throttled: max 3 warnings, min 15s apart (Test 10A)
- Status observable in State Debug UI (Test 10B-C)
- **API Health section displays tracked endpoints (Test 11)**
- **API errors throttled (max once per endpoint per 15s)**
- **Backend recovery updates status to "ok"**
- **Portfolio auto-refreshes on recovery WITHOUT manual navigation (Test 12)**
- **Recovery triggers exactly ONE event per endpoint per transition (Test 12D)**
- **No infinite rerun loops after recovery (Test 12A-E)**
- **Portfolio auto-refresh with timer-based recovery (Test 13A-G)**
- **Timer OFF when backend healthy (Test 13A)**
- **Timer activates when backend down (Test 13B)**
- **Timer stops immediately after recovery (Test 13C)**
- **Retry limit enforced: max 10 attempts (Test 13D)**
- **Manual reset works after limit (Test 13E)**
- **Timer interval is ~2 seconds (Test 13F)**
- **Timer only runs on Portfolio page (Test 13G)**
- **Restore from trash still works (deferred pattern intact) (Test 12B)**
- "Pending cause" shows "none" after being consumed
- No cause leakage across unrelated actions
- Exported snapshots reflect consumed state

### ❌ FAIL if:
- Cause persists in "Pending cause" after being logged
- Cause shows "unknown" when specific cause expected
- Cause from previous action appears in unrelated action
- Navigation without state changes logs unnecessary events
- Capabilities fetch spams console (>3 warnings or <15s apart)
- Status not updated in State Debug UI
- **API Health section missing or shows wrong status**
- **API errors spam console (not throttled)**
- **Backend recovery doesn't update status**
- **Restore from trash broken (regression)**
- **Portfolio requires manual navigation to refresh after recovery (Test 12A FAIL)**
- **Multiple recovery events for same transition (Test 12D FAIL)**
- **Infinite rerun loop after recovery (Test 12A-E FAIL)**
- **Portfolio does NOT auto-refresh after backend restart (Test 13C FAIL)**
- **Timer causes infinite loop (Test 13C FAIL)**
- **Timer still runs when backend is healthy (Test 13A FAIL)**
- **More than 10 retry attempts (Test 13D FAIL)**
- **Timer doesn't stop after recovery (Test 13C FAIL)**
- **Timer interval is too fast (<1s) or too slow (>3s) (Test 13F FAIL)**
- **Timer runs on non-Portfolio pages (Test 13G FAIL)**

---

## Sign-off

**Tester**: _____________  
**Date**: _____________  
**Environment**: ⬜ Local Dev  ⬜ Staging  
**Result**: ⬜ PASS  ⬜ FAIL  

**Notes**:

