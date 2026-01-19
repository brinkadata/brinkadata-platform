# Manual Verification Checklist - State Observability v2

## Pre-flight
- [ ] Backend running: `uvicorn backend.main:app --reload`
- [ ] Frontend running: `streamlit run frontend/app.py`
- [ ] DEV mode enabled: Check config shows "Debug UI: enabled"

---

## Test 1: Noise Reduction (No False Positives)

### Scenario: Navigate without state changes
1. [ ] Open app, login if needed
2. [ ] Open sidebar → "🐛 DEV State Debug"
3. [ ] Note current event count
4. [ ] Click "Portfolio" tab
5. [ ] Click "Analyzer" tab
6. [ ] Click "Portfolio" tab again
7. [ ] Check event timeline

**Expected**:
- [ ] ❌ NO new "state_changed" events (count unchanged)
- [ ] Change Detection shows: "Changed since last: ❌ No"
- [ ] Old fingerprint == New fingerprint

**Why**: Navigation alone doesn't change critical state (account_id, role, plan, nav_page)

---

## Test 2: Signal Preservation (Login)

### Scenario: Login changes auth state
1. [ ] Logout if logged in
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Login with valid credentials
4. [ ] Check event timeline after redirect

**Expected**:
- [ ] ✅ ONE new "state_changed" event
- [ ] Event details show: `"cause": "login"`
- [ ] Old fingerprint: `None` or different from new
- [ ] New fingerprint: 12-character hash
- [ ] Change Detection: "Changed since last: ✅ Yes"

---

## Test 3: Preset Selection

### Scenario: Selecting preset changes input state
1. [ ] Go to Analyzer tab
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Click "SFR Flip" preset button
4. [ ] Wait for page reload
5. [ ] Check event timeline

**Expected**:
- [ ] ✅ ONE "state_changed" event with `"cause": "preset"`
- [ ] Change Detection shows fingerprint changed

---

## Test 4: Restore from Trash

### Scenario: Restore changes portfolio state
1. [ ] Save an analysis
2. [ ] Go to Portfolio, delete the deal (moves to Trash)
3. [ ] Go to Trash tab
4. [ ] Open "🐛 DEV State Debug"
5. [ ] Click "Restore" on the deal
6. [ ] Check event timeline after redirect

**Expected**:
- [ ] ✅ ONE "state_changed" event with `"cause": "restore"`

---

## Test 5: DEV Controls (Plan Change)

### Scenario: Changing plan in DEV controls
1. [ ] Open sidebar → "DEV Controls" expander
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Change "Override Plan" to "pro"
4. [ ] Click "Apply"
5. [ ] Check event timeline

**Expected**:
- [ ] ✅ ONE "state_changed" event with `"cause": "dev_plan_change"`
- [ ] State snapshot shows `"plan": "pro"`

---

## Test 6: DEV Controls (Role Change)

### Scenario: Changing role in DEV controls
1. [ ] Open "DEV Controls"
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Change "Override Role" to "member"
4. [ ] Click "Apply"
5. [ ] Check event timeline

**Expected**:
- [ ] ✅ ONE "state_changed" event with `"cause": "dev_role_change"`
- [ ] State snapshot shows `"role": "member"`

---

## Test 7: Normalization Noise Reduction

### Scenario: Normalization doesn't spam logs
1. [ ] Login (sets account_id, role, plan)
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Navigate to Portfolio
4. [ ] Navigate to Analyzer
5. [ ] Check for "auth_context_normalized" events

**Expected**:
- [ ] ❌ NO "auth_context_normalized" events in timeline
- [ ] OR only ONE when keys were first set (on login)

**Why**: normalize_auth_context() only logs when actually setting new values, not on every call.

---

## Test 8: State Debug UI Display

### Scenario: Verify UI shows change detection info
1. [ ] Open "🐛 DEV State Debug"
2. [ ] Check "Change Detection" section

**Expected fields**:
- [ ] "Changed since last:" (✅ Yes or ❌ No)
- [ ] "Old fingerprint:" (hash or "None")
- [ ] "New fingerprint:" (12-char hash)
- [ ] "Last change:" (timestamp)
- [ ] "Pending cause:" (cause string or "None")

---

## Test 9: Snapshot Export

### Scenario: Verify export includes v2 metadata
1. [ ] Open "🐛 DEV State Debug"
2. [ ] Click "📥 Export Snapshot JSON"
3. [ ] Check downloaded JSON file

**Expected structure**:
```json
{
  "timestamp": "...",
  "state": { ... },
  "recent_events": [ ... ],
  "change_detection": {
    "last_fingerprint": "...",
    "last_change_time": "...",
    "pending_cause": null
  }
}
```
- [ ] `change_detection` object exists
- [ ] Contains `last_fingerprint`, `last_change_time`, `pending_cause`

---

## Test 10: Sensitive Data Redaction

### Scenario: Verify tokens not in logs
1. [ ] Login
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Check state snapshot

**Expected**:
- [ ] `auth_token`: `"[REDACTED]"`
- [ ] `refresh_token`: `"[REDACTED]"`
- [ ] `account_id`: `"***1234"` (partial redaction)
- [ ] `session_id`: `"[REDACTED]"`

---

## Test 11: Fingerprint Stability

### Scenario: Same state produces same fingerprint
1. [ ] Login
2. [ ] Open "🐛 DEV State Debug"
3. [ ] Note "New fingerprint" value
4. [ ] Navigate to Portfolio (no state change)
5. [ ] Check fingerprint again

**Expected**:
- [ ] Fingerprint unchanged
- [ ] "Changed since last: ❌ No"

---

## Pass Criteria

**All tests MUST pass**:
- [ ] Noise: No false positives (navigation without changes)
- [ ] Signal: Cause tags appear correctly for 6 scenarios
- [ ] UI: Change Detection section displays correctly
- [ ] Export: JSON includes change_detection metadata
- [ ] Security: Sensitive keys redacted

**Optional (nice-to-have)**:
- [ ] Performance: No noticeable lag from fingerprinting
- [ ] UX: State Debug UI is readable and useful

---

## Failure Scenarios

### If navigation logs "state_changed":
1. Check if `nav_page` is actually changing in state snapshot
2. Verify fingerprint includes only critical keys (not volatile data)
3. Debug: Add print statements in `compute_state_fingerprint()`

### If cause tags missing:
1. Verify `set_cause_tag()` called BEFORE `st.rerun()`
2. Check `get_cause_tag()` in `main()` clears the key
3. Debug: Add print in `set_cause_tag()` and `get_cause_tag()`

### If normalization still spammy:
1. Check `normalize_auth_context()` only logs when `actually_set` list is non-empty
2. Verify `setdefault()` replaced with explicit checks

---

## Sign-off

**Tester**: _______________  
**Date**: _______________  
**Status**: ⬜ PASS  ⬜ FAIL  
**Notes**:
