# State Observability v2 - Quick Reference Card

## 🎯 What Changed?
**Before**: Every `main()` logged events, even when nothing changed (NOISY)  
**After**: Only logs when state actually changes + cause tag explains why (SIGNAL)

---

## 📊 Key Metrics

| Metric | v1 | v2 |
|--------|----|----|
| **Events per navigation** | 1-3 | 0 (if no change) |
| **Events per login** | 2-4 | 1 |
| **False positives** | High | Zero |
| **Cause tracking** | None | 8 scenarios |

---

## 🔧 Core Functions

### Fingerprinting
```python
from frontend.dev_observability import (
    compute_state_fingerprint,  # Hash critical state
    detect_state_changes,       # Compare old/new
    update_fingerprint,         # Store current
)

# Usage in main()
changed, old_fp, new_fp = detect_state_changes(st.session_state)
if changed:
    track_event(ss, "state_changed", details={"cause": cause, ...})
    update_fingerprint(ss)
```

### Cause Tags
```python
from frontend.dev_observability import set_cause_tag, get_cause_tag

# Before rerun
set_cause_tag(st.session_state, "login")
st.rerun()

# After rerun
cause = get_cause_tag(st.session_state, default="navigation")
# -> "login" (then cleared)
```

---

## 📍 Integration Points

### 8 Cause Tag Locations in app.py

| Location | Line | Cause | Trigger |
|----------|------|-------|---------|
| Login | ~2400 | `login` | Auth success |
| Register | ~2466 | `register` | New account |
| Resume | ~2529 | `resume` | Resume code |
| Restore | ~2157 | `restore` | From trash |
| Preset | ~632 | `preset` | Preset button |
| Scenario | ~1578 | `scenario_load` | Load scenario |
| Plan | ~892 | `dev_plan_change` | DEV controls |
| Role | ~924 | `dev_role_change` | DEV controls |

---

## 🧪 Testing

### Unit Tests
```bash
python -m pytest frontend/test_dev_observability.py frontend/test_normalize_auth.py -v
```
**Expected**: 20 passed, 1 skipped

### Manual Tests
```bash
# Start app
streamlit run frontend/app.py

# Check: NO logs for navigation (Analyzer → Portfolio → Analyzer)
# Check: ONE log with cause="login" after login
```

---

## 🐛 State Debug UI

### New "Change Detection" Section
```
Changed since last: ✅ Yes / ❌ No
Old fingerprint: a3f8e9b2c1d4 (or "None")
New fingerprint: f7d6c5b4a3e2
Last change: 2026-01-16T21:10:00Z
Pending cause: login (or "None")
```

### Snapshot Export
```json
{
  "change_detection": {
    "last_fingerprint": "a3f8e9b2c1d4",
    "last_change_time": "2026-01-16T21:10:00Z",
    "pending_cause": null
  }
}
```

---

## 🔒 Security

### Excluded from Fingerprint
- Auth tokens (auth_token, refresh_token, session_id)
- Timestamps (_last_*, *_time)
- Metadata (_dev_*, _debug_*)

### Still Redacted in Logs
- Sensitive keys: `[REDACTED]`
- ID fields: `***1234` (last 4 chars)

---

## ✅ Expected Behavior

### DO Log "state_changed":
- ✅ First app load (no previous fingerprint)
- ✅ Login/register (auth state changes)
- ✅ Restore/preset/scenario (action state changes)
- ✅ DEV plan/role change (manual override)

### DO NOT Log "state_changed":
- ❌ Navigation between tabs (nav_page excluded from critical state)
- ❌ Token refresh (tokens excluded from fingerprint)
- ❌ Repeated normalization (only logs when actually setting)
- ❌ Timestamp updates (excluded from fingerprint)

---

## 🚨 Troubleshooting

### Problem: Navigation logs "state_changed"
**Debug**:
1. Check State Debug UI → Current State → Look for unexpected key changes
2. Add print in `compute_state_fingerprint()` to see what's hashed
3. Verify `nav_page` NOT included in critical state keys

### Problem: Cause tags always "navigation"
**Debug**:
1. Verify `set_cause_tag()` called BEFORE `st.rerun()`
2. Check `get_cause_tag()` called in `main()` with correct default
3. Add print in `set_cause_tag()` to confirm it's called

### Problem: Still seeing auth_context_normalized spam
**Debug**:
1. Check `normalize_auth_context()` line ~282
2. Verify `actually_set` list only populated when keys don't exist
3. Confirm event logged ONLY when `actually_set` is non-empty

---

## 📚 Documentation

| Doc | Purpose |
|-----|---------|
| [STATE_OBSERVABILITY_V2_SUMMARY.md](STATE_OBSERVABILITY_V2_SUMMARY.md) | Full implementation guide |
| [MANUAL_STATE_OBSERVABILITY_V2_TESTS.md](MANUAL_STATE_OBSERVABILITY_V2_TESTS.md) | 11-test checklist |
| [STATE_OBSERVABILITY_V2_CHECKLIST.md](STATE_OBSERVABILITY_V2_CHECKLIST.md) | Implementation status |
| [DEV_OBSERVABILITY_QUICK_REF.md](DEV_OBSERVABILITY_QUICK_REF.md) | v1 quick ref |

---

## 🎓 Key Concepts

### Fingerprint
12-character SHA256 hash of critical state keys (account_id, role, plan, deferred keys). Excludes tokens and timestamps.

### Cause Tag
One-time label explaining why state changed. Set before `st.rerun()`, consumed by `get_cause_tag()` in next run, then cleared.

### Critical State
Keys that matter for app behavior: auth (account_id, role, plan), navigation (nav_page), deferred actions. NOT tokens or timestamps.

### Diff-Based Logging
Compare current fingerprint with previous. Log ONLY if different. Reduces noise from repeated normalization and navigation.

---

## 🚀 Quick Start

1. **Start app**: `streamlit run frontend/app.py`
2. **Open State Debug**: Sidebar → "🐛 DEV State Debug"
3. **Navigate**: Click tabs, verify NO new events
4. **Login**: Verify ONE event with `cause="login"`
5. **Check UI**: "Changed since last: ✅ Yes"

---

## 📞 Support

**Issue?** Check:
1. [MANUAL_STATE_OBSERVABILITY_V2_TESTS.md](MANUAL_STATE_OBSERVABILITY_V2_TESTS.md) - Test scenarios
2. [STATE_OBSERVABILITY_V2_SUMMARY.md](STATE_OBSERVABILITY_V2_SUMMARY.md) - Implementation details
3. State Debug UI → Export snapshot for debugging

**Still stuck?** Review:
- Unit tests: `pytest frontend/test_dev_observability.py -v`
- Syntax: `python -m py_compile frontend/app.py`
- Logs: Check Streamlit terminal output
