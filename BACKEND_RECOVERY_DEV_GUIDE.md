# Backend Recovery Auto-Refresh - Developer Guide

## Quick Start

### Testing Recovery Locally
```bash
# Terminal 1: Start backend
uvicorn backend.main:app --reload

# Terminal 2: Start frontend
streamlit run frontend/app.py

# Terminal 3: Monitor logs (optional)
tail -f frontend_logs.log
```

### Trigger Recovery Flow
1. Navigate to Portfolio page
2. Stop backend (Ctrl+C in Terminal 1)
3. Wait 5s, refresh page → see "Error loading saved deals"
4. Restart backend → `uvicorn backend.main:app --reload`
5. **Observe**: Within 10s, lists auto-populate WITHOUT navigation

## How It Works

### 1. Status Tracking
Every API call via `call_backend_tracked()` updates health registry:
```python
_api_health_set(ss, "/property/saved", "ok", http_status=200, err=None)
```

### 2. Transition Detection
When status changes, `handle_api_health_transition()` is called:
```python
if old_status in ("no_response", "error") and new_status == "ok":
    # Recovery detected! Trigger page-aware refresh
```

### 3. Deferred Refresh
Recovery handler sets ONE-SHOT flags:
```python
ss["_refresh_portfolio_lists"] = True  # Clear cached data
ss["_post_recovery_rerun"] = True      # Trigger safe rerun
```

### 4. Safe Rerun
`apply_pending_actions()` consumes flags BEFORE widgets:
```python
if ss.get("_post_recovery_rerun"):
    ss.pop("_post_recovery_rerun")  # ONE-SHOT
    return True  # Caller does st.rerun()
```

## Adding Recovery for New Endpoints

### Step 1: Use Tracked Wrapper
Replace `call_backend()` with `call_backend_tracked()`:
```python
# Before
resp = call_backend("GET", "/my/endpoint", ...)

# After
resp = call_backend_tracked("GET", "/my/endpoint", 
                             tracked_name="/my/endpoint",
                             expects_auth=True)
```

### Step 2: Add Recovery Logic
Edit `handle_api_health_transition()` in `frontend/app.py`:
```python
# Add your page-aware logic
elif nav_page == "MyPage" and endpoint == "/my/endpoint":
    ss["_refresh_my_page_data"] = True
    ss["_post_recovery_rerun"] = True
    if IS_DEV:
        print(f"[RECOVERY] MyPage auto-refresh triggered for {endpoint}")
```

### Step 3: Handle Deferred Flag
Add to `apply_pending_actions()`:
```python
# After step 4, before normalize_auth_context
if ss.get("_refresh_my_page_data"):
    ss.pop("_refresh_my_page_data")
    # Clear cached data here
    applied_any = True
    applied_keys.append("_refresh_my_page_data")
```

### Step 4: Add Manual Test
Update `MANUAL_CAUSE_TAG_VERIFICATION.md`:
```markdown
### Test 13: MyPage Recovery

#### Steps
1. Navigate to MyPage
2. Stop backend
3. Trigger action → error shown
4. Restart backend
5. Wait 5-10s

#### Expected Results
- ✅ MyPage data auto-refreshes
- ✅ `backend_recovered` event in Recent Events
```

## Debugging

### Console Output (DEV mode)
```
[RECOVERY] Portfolio auto-refresh triggered for /property/saved
[DEFERRED] Backend recovery rerun
[DEFERRED] Portfolio lists will refresh
```

### State Debug UI
1. Open sidebar → "🔎 State Debug (DEV)"
2. Check **API Health** section:
   - Before: `🔌 no_response`
   - After: `✅ ok`
3. Check **Recent Events**:
   - Should show `backend_recovered` with `endpoint`, `old_status`, `new_status`

### Common Issues

#### Recovery Not Triggering
- **Symptom**: Backend restarts, but page doesn't refresh
- **Fix**: Ensure endpoint is tracked via `call_backend_tracked()`
- **Debug**: Check State Debug → API Health → verify status changes

#### Infinite Rerun Loop
- **Symptom**: Page keeps refreshing forever
- **Fix**: Ensure deferred flags are popped (consumed) in `apply_pending_actions()`
- **Debug**: Add `print()` statements in deferred flag handlers

#### Multiple Recovery Events
- **Symptom**: Same `backend_recovered` event appears multiple times
- **Fix**: Ensure `handle_api_health_transition()` only triggers on transition (not every "ok")
- **Debug**: Check `prev_status` tracking in `_api_health_set()`

## Architecture Patterns

### Deferred Key Pattern
```python
# WRONG (widget key violation)
def on_button_click():
    ss["widget_key"] = "new_value"  # Error! Widget already instantiated
    st.rerun()

# RIGHT (deferred pattern)
def on_button_click():
    ss["_deferred_update"] = {"widget_key": "new_value"}  # Safe temporary flag
    st.rerun()

# In main(), BEFORE widgets:
if ss.get("_deferred_update"):
    payload = ss.pop("_deferred_update")  # Consume flag
    ss["widget_key"] = payload["widget_key"]  # Write before widget creation
    return True  # Triggers st.rerun()
```

### ONE-SHOT Flags
```python
# Always pop() to ensure single execution
if ss.get("_one_shot_flag"):
    ss.pop("_one_shot_flag")  # Remove immediately
    do_action()
    # Flag is gone, won't trigger again
```

### Page-Aware Logic
```python
nav_page = ss.get("nav_page", "")

if nav_page == "Portfolio":
    # Portfolio-specific recovery actions
    ss["_refresh_portfolio_lists"] = True
elif nav_page == "Analyzer":
    # Analyzer-specific recovery actions
    pass  # Analyzer has no persistent data
```

## Performance Considerations

### Throttling
- API errors throttled: **15 seconds per endpoint**
- Capabilities fetch: **max 3 warnings, 15s interval**
- Recovery detection: **ONE-SHOT per transition** (no repeated events)

### Cache Invalidation
```python
# Portfolio recovery clears cached data
if ss.get("_refresh_portfolio_lists"):
    ss.pop("_refresh_portfolio_lists")
    # Next render will re-fetch from backend automatically
    # (No explicit cache clear needed - fetch functions check timestamp)
```

## Testing Checklist

### Unit Tests (TODO)
- [ ] Test `handle_api_health_transition()` with various status transitions
- [ ] Test ONE-SHOT flag consumption
- [ ] Test page-aware logic for each page

### Integration Tests (TODO)
- [ ] Test multi-endpoint recovery
- [ ] Test recovery during active user session
- [ ] Test recovery with cached data

### Manual Tests (REQUIRED)
- [x] Test 12A: Portfolio recovery ✅
- [x] Test 12B: Trash recovery ✅
- [x] Test 12C: Analyzer recovery ✅
- [x] Test 12D: No spam ✅
- [x] Test 12E: Cross-page recovery ✅

## Monitoring

### Metrics to Track (Future)
- Recovery event count per endpoint
- Average time to recovery (backend down → data visible)
- Failed recovery attempts (transition detected but refresh failed)
- User navigation after recovery (did they manually refresh?)

### Logging
```python
# DEV mode only
if IS_DEV:
    print(f"[RECOVERY] {nav_page} auto-refresh triggered for {endpoint}")
    print(f"[DEFERRED] Backend recovery rerun")
```

### State Debug UI Snapshot
```json
{
  "_api_health": {
    "/property/saved": {
      "status": "ok",
      "prev_status": "no_response",
      "last_ts": 1705500000.123,
      "count_ok": 5,
      "count_err": 2
    }
  },
  "_dev_events": [
    {
      "name": "backend_recovered",
      "data": {
        "endpoint": "/property/saved",
        "old_status": "no_response",
        "new_status": "ok"
      }
    }
  ]
}
```

## FAQs

### Q: Why not auto-retry failed requests?
**A**: Auto-retry could cause duplicate operations (e.g., double-charge). We detect recovery on NEXT user-initiated request instead.

### Q: Why separate `_refresh_portfolio_lists` and `_post_recovery_rerun`?
**A**: `_refresh_portfolio_lists` clears cached data (Portfolio-specific). `_post_recovery_rerun` triggers safe rerun (generic). Separation allows flexibility.

### Q: What if user navigates away before recovery?
**A**: Recovery detection is page-aware. If nav_page changes before recovery, no refresh is triggered (correct: user already left).

### Q: Can I disable recovery for a specific endpoint?
**A**: Yes, don't add logic for that endpoint in `handle_api_health_transition()`. It will still track status but won't trigger refresh.

---

**Last Updated**: January 17, 2026
**Maintainer**: GitHub Copilot (Claude Sonnet 4.5)
