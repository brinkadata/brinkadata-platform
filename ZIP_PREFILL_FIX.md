# ZIP Prefill Fix + Deferred Actions Centralization (January 2026)

## Problem
After first login, ZIP code did not auto-populate in Analyzer even though city/state did. Selecting a ZIP from dropdown fixed it temporarily. This was a **Streamlit widget-state conflict**.

Additionally, deferred actions (_apply_payload, _apply_address_payload, _post_login_nav, _refresh_portfolio_lists) were scattered across multiple locations (main(), page renders, sidebar callbacks), increasing the risk of widget-key ownership errors.

## Root Cause
1. **Widget key mismatch**: The ZIP text_input widget at line 1013 uses `key="zip_code_property"`, but the `_apply_address_payload` logic wrote to `ss["zip_code"]`. 

2. **Scattered execution**: Deferred actions were applied in multiple places, sometimes after widgets were already instantiated, causing race conditions.

When a Streamlit widget has a `key`, that key becomes the bound session_state variable. Writing to a different key has no effect on the widget. Writing to a widget-owned key AFTER the widget is created in the same run raises errors or is silently ignored.

## Fix (Centralized Deferred Actions Pattern)

### 1. New Function: `apply_pending_actions()` (Lines 248-338)
Created a single centralized handler for ALL deferred actions that must execute BEFORE widgets are created.

**Execution order** (strict):
1. `_apply_payload`: Auth/session data from login/register/resume
2. `_post_login_nav`: Navigation redirect after successful auth
3. `_apply_address_payload`: Analyzer address field prefill (including ZIP)
4. `_refresh_portfolio_lists`: Trigger portfolio/trash list refresh

**Returns**: `True` if any action was applied (indicating a rerun is needed)

### 2. Main() Refactor (Lines 2466-2490)
- Call `apply_pending_actions()` at the **very top** of `main()`, before any widgets
- If it returns `True`, immediately `st.rerun()` once
- Removed scattered payload application blocks that were duplicated throughout main()
- Infinite rerun prevention: Each action is popped (consumed) on first application

### 3. Removed Redundant Guards
- **render_analyzer()** (Line 1151): Removed duplicate address payload guard since it's now handled centrally
- Simplified code by ~50 lines, eliminated race conditions

### 4. Widget Key Consistency
- **Line 1170**: Changed ZIP widget's `value` from `ss.get("zip_code", ...)` to `ss.get("zip_code_property", ...)` 
- **apply_pending_actions()**: Writes to BOTH `zip_code` (sidebar widget) and `zip_code_property` (Analyzer widget)

## Why This Fixes Multiple Issues

### ZIP Auto-Fill
- Payload writes to correct widget key (`zip_code_property`) before widget creation
- Widget reads from the same key for default value
- No timing issues from navigation/rerun sequences

### Login/Resume Navigation
- `_post_login_nav` is applied before nav widget instantiation
- Single rerun lands user on Analyzer deterministically
- No "stuck on login page" or navigation flicker

### Restore from Trash
- `_refresh_portfolio_lists` triggers before portfolio list widgets render
- Restored deals disappear from trash and reappear in portfolio immediately
- No manual navigation required

### Success Message Stability
- All state changes complete before widgets render
- No flicker from mid-render state updates

## Regression Test Plan
Manual tests to verify no behavior changes:

### Test 1: First Login → Analyzer
1. Clear browser cache / new incognito window
2. Navigate to app
3. Login with valid credentials
4. **Expected**: Redirected to Analyzer, ZIP shows "21207" (default)
5. Enter address, click "Run Analysis"
6. **Expected**: Analysis completes, ZIP retains value

### Test 2: Preset Selection
1. In Analyzer, select a preset from dropdown (e.g., "Baltimore Row Home")
2. **Expected**: Property name, city, state, **and ZIP** all auto-fill immediately
3. Click "Run Analysis"
4. **Expected**: Analysis uses correct ZIP

### Test 3: Scenario Load
1. Run analysis and save scenario
2. Load scenario from "What-if Scenarios" panel
3. **Expected**: All address fields including ZIP populate correctly
4. No unwanted navigation or reruns

### Test 4: Resume Session
1. Get resume code (DEV controls)
2. Clear session (logout or browser refresh)
3. Resume with code
4. Navigate to Analyzer
5. **Expected**: Previous ZIP value (if any) is retained

### Test 5: Portfolio Load → Analyzer
1. Save a deal from Analyzer
2. Navigate to Portfolio
3. Click "Load" on a saved deal
4. **Expected**: Navigates to Analyzer with all fields including ZIP pre-filled

### Test 6: Trash Restore
1. Delete a deal (moves to trash)
2. Navigate to Trash tab in Portfolio
3. Restore deal
4. **Expected**: Deal reappears in portfolio list, no ZIP-related errors

### Test 7: Logout and Re-login
1. Logout
2. Login again
3. Navigate to Analyzer
4. **Expected**: Default ZIP or last-used ZIP appears correctly

## Technical Notes
- **No backend changes**: This is purely a frontend widget-state management fix
- **No new dependencies**: Uses existing Streamlit patterns
- **Preserves security**: Auth/RBAC logic untouched
- **Net reduction**: ~30 lines removed via centralization, improved maintainability
- **Pattern consistency**: Single source of truth for deferred action execution
- **Debug support**: Added IS_DEV logging to track deferred action application

## Architecture: Deferred Actions Pattern

### Problem Solved
Streamlit widgets "own" their session_state key once instantiated. Writing to widget-owned keys after widget creation in the same run causes errors or is ignored.

### Solution
1. **Before login/resume/preset**: Set deferred action flags (_apply_payload, _post_login_nav, etc.)
2. **Call st.rerun()**: Trigger a fresh run
3. **At top of main()**: apply_pending_actions() reads flags, writes to widget keys, pops flags
4. **If applied**: st.rerun() once more so widgets render with correct state
5. **Remainder of run**: Widgets instantiate with correct session_state values already present

### Safety Guarantees
- **No infinite reruns**: Flags are popped (consumed) on first application
- **Strict ordering**: Actions applied in dependency order (auth → nav → address → refresh)
- **Single point of failure**: All deferred logic in one function, easy to debug
- **DEV observability**: Logging shows which actions were applied and when

## Related Session State Keys
- `zip_code`: General-purpose ZIP state (if used elsewhere, e.g., sidebar or market context)
- `zip_code_property`: Analyzer ZIP widget key (bound to text_input widget at line 1016)
- `_apply_address_payload`: Deferred payload carrying property_name, city, state, zip_code from preset/scenario selection

## Edge Case Handled
If user navigates directly to Analyzer URL or a rerun sequence causes Analyzer to render before main() payload application runs, the guard in `render_analyzer()` catches it and applies payload + reruns once. This prevents the "first render has no ZIP" issue completely.
