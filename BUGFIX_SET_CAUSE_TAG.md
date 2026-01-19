# Bug Fix Verification - set_cause_tag NameError

## Issue
Frontend crashed on login with:
```
NameError: name 'set_cause_tag' is not defined
```

## Root Cause
`set_cause_tag()` was defined in `dev_observability.py` but imported conditionally (only when `IS_DEV=True`). However, calls to it throughout `app.py` were unconditional, causing crashes in production mode or when imports failed.

## Fix Applied
**Minimal single-file patch** to `frontend/app.py`:

### 1. Added helper function (line ~198)
```python
def set_debug_cause(cause: str) -> None:
    """Set one-time cause tag for state change debugging."""
    st.session_state["_debug_cause"] = cause
```

### 2. Replaced all 8 calls
| Location | Old | New | Scenario |
|----------|-----|-----|----------|
| Line ~643 | `set_cause_tag(ss, "preset")` | `set_debug_cause("preset")` | Preset selection |
| Line ~902 | `set_cause_tag(ss, "dev_plan_change")` | `set_debug_cause("dev_plan_change")` | DEV plan override |
| Line ~935 | `set_cause_tag(ss, "dev_role_change")` | `set_debug_cause("dev_role_change")` | DEV role override |
| Line ~1606 | `set_cause_tag(ss, "scenario_load")` | `set_debug_cause("scenario_load")` | Load scenario |
| Line ~2187 | `set_cause_tag(ss, "restore")` | `set_debug_cause("restore")` | Restore from trash |
| Line ~2432 | `set_cause_tag(ss, "login")` | `set_debug_cause("login")` | Login success |
| Line ~2498 | `set_cause_tag(ss, "register")` | `set_debug_cause("register")` | Register success |
| Line ~2561 | `set_cause_tag(ss, "resume")` | `set_debug_cause("resume")` | Resume session |

### 3. Removed conditional guards
**Before**:
```python
if IS_DEV and 'set_cause_tag' in globals():
    set_cause_tag(ss, "login")
```

**After**:
```python
set_debug_cause("login")
```

Now unconditional and always safe (no import dependency).

---

## Verification Steps

### ✅ Syntax Check
```bash
python -m py_compile frontend/app.py
```
**Result**: Compiles without errors

### ⏳ Smoke Test (Manual)
1. **Start app**: `streamlit run frontend/app.py`
2. **Login** with valid credentials
3. **Expected**:
   - ✅ No NameError
   - ✅ Login succeeds, redirects to Analyzer
   - ✅ If DEV mode enabled: State Debug UI shows `_debug_cause: "login"` immediately after login, then clears on next run

4. **Other scenarios** (optional):
   - Select preset → verify no crash, cause tag set if DEV mode
   - Restore from trash → verify no crash
   - DEV controls (plan/role) → verify no crash

---

## Impact Analysis

### Changed
- ✅ `set_cause_tag()` calls replaced with `set_debug_cause()`
- ✅ Removed conditional checks (`if IS_DEV and 'set_cause_tag' in globals()`)
- ✅ Added simple helper directly in `app.py` (no import dependency)

### Unchanged
- ❌ Auth logic (login/register/resume flows)
- ❌ Navigation behavior (deferred pattern still used)
- ❌ State observability v2 design (cause tags still work)
- ❌ DEV mode observability (still logs if `track_event()` available)

### Risk Assessment
**Low risk**:
- Single-line helper function (trivial logic)
- Drop-in replacement (same interface: `set_debug_cause(cause: str)`)
- No external dependencies
- Unconditional = works in all modes (DEV and prod)

---

## Files Modified
1. **frontend/app.py** (2740 lines)
   - Added `set_debug_cause()` helper (line ~198)
   - Replaced 8 calls to `set_cause_tag()`
   - Removed 2 conditional guards in DEV controls

**Total**: 1 file modified, ~10 lines changed

---

## Related Issues
- **State Observability v2**: This fix ensures cause tagging works without import failures
- **DEV mode**: Observability features still work when `IS_DEV=True`
- **Production**: No crashes when observability imports unavailable

---

## Rollback
If this causes issues:
1. Revert `frontend/app.py` to previous version
2. OR: Comment out the 8 `set_debug_cause()` calls (non-critical feature)

**No data loss risk** - cause tags are debug-only metadata.

---

## Success Criteria
- [x] ✅ Code compiles without errors
- [ ] ⏳ Login works without NameError
- [ ] ⏳ Cause tag appears in DEV state logs (if enabled)
- [ ] ⏳ No regressions in auth or navigation

**Status**: Code complete, awaiting manual smoke test
