# Brinkadata System Rules (Do Not Break)

You are working on the Brinkadata codebase.

## Non-negotiables
- Do NOT regress existing working features.
- Prefer minimal diffs over rewriting files.
- Never remove endpoints or UI features unless explicitly requested.
- Preserve feature gating logic.
- Preserve auth/account boundaries (account_id scoping).

## Streamlit safety rules
- Never assign to st.session_state for a widget key after that widget renders.
- Use an "apply_on_next_run" pattern:
  - set ss["_apply_payload"] = {...} on click
  - st.rerun()
  - at top of page, if ss["_apply_payload"]: apply values BEFORE widgets

## Output format
- Provide a short plan
- Then provide exact code diffs OR full file only if requested
- List files changed
- List manual test steps


# Brinkadata — Workspace Chat Instructions

You are an expert senior software engineer working on the Brinkadata Platform.

## Core Rules
- Never remove existing functionality unless explicitly instructed.
- Never regress previously working features.
- Prefer additive changes over refactors.
- Preserve Streamlit widget keys exactly once per widget.
- Never set st.session_state values after a widget with the same key is instantiated.
- Do not use deprecated Streamlit APIs (e.g., st.experimental_rerun).
- Assume FastAPI backend and Streamlit frontend are already live and integrated.

## Code Generation Rules
- Default to full-file outputs only when explicitly requested.
- Otherwise, provide minimal diffs with exact line references.
- Validate that all referenced columns exist before using them (pandas safety).
- Use defensive coding for optional fields (zip_code, noi_year, irr, npv).

## Architecture Awareness
- Backend: FastAPI (backend/main.py)
- Frontend: Streamlit (frontend/app.py)
- Database: SQLite (brinkadata.db)
- Auth: JWT-based multi-account system
- Plans & gating must be respected

## UX Principles
- Counts must start at 1, never 0.
- Portfolio tables must not duplicate index columns.
- Deleted items go to Trash (7-day retention).
- Save buttons must always appear after successful analysis.

If instructions conflict, prioritize stability and backward compatibility.

## Full-File Generation Safety Rules (Critical)

These rules apply whenever a full file (e.g., frontend/app.py or backend/main.py)
is regenerated or heavily modified.

### Mandatory Preservation Checklist
A full-file output MUST preserve all existing working functionality, including:
- Deal analysis execution
- Save deal button after analysis
- Portfolio view with filters
- Delete → Trash workflow
- Trash restore functionality
- Comparison / Scenario UI (even if partially implemented)
- Presets and exports (if present)
- Account / plan gating logic
- Branding (logo, colors, layout intent)
- User-friendly numbering (counts start at 1, never 0)

### Regeneration Rules
- Full-file regeneration is allowed ONLY when explicitly requested.
- Otherwise, apply minimal diffs.
- If a full file is regenerated, the author must mentally validate against:
  prompts/30_regression_checklist.md

### Streamlit-Specific Safeguards
- Never remove widget keys once introduced.
- Never change widget keys for existing UI elements.
- Never reassign st.session_state values tied to widgets after render.
- Apply “load then rerun” patterns for programmatic state updates.

If there is uncertainty, default to preserving behavior over refactoring.
