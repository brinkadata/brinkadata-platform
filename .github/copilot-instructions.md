# Brinkadata System Rules (Do Not Break)

## Project Overview
Brinkadata is a SaaS platform for real estate property intelligence. It analyzes rental/flip deals using metrics like NOI, ROI, IRR/NPV, and provides AI-enhanced insights. Architecture: FastAPI backend (SQLite), Streamlit frontend, modular domains (e.g., `domains/property/`).

## Non-negotiables
- Do NOT regress existing working features (analysis, save, portfolio, trash/restore).
- Prefer minimal diffs over rewriting files.
- Never remove endpoints, UI features, or data fields unless explicitly requested.
- Preserve feature gating logic (plans: free/pro/team/enterprise) and account_id scoping.
- Maintain backward compatibility; assume legacy/incomplete records exist.

## Architecture Patterns
- **Backend**: FastAPI with Pydantic models (`backend/models.py`), endpoints in `backend/main.py`. Use `account_id` for multi-tenancy.
- **Frontend**: Streamlit with session state safety. Never assign `st.session_state` after widget render; use "apply_on_next_run" pattern.
- **Domains**: Modular structure under `domains/` (e.g., `domains/property/models/` for `PropertyInput`, `AnalysisResult`).
- **Data**: SQLite (`brinkadata.db`), tables like `saved_properties` with `account_id` column.
- **Agents**: Role-based development (architect: design; backend: APIs/data; frontend: UI).

## Critical Workflows
- **Run Backend**: `uvicorn backend.main:app --reload` (port 8000)
- **Run Frontend**: `streamlit run frontend/app.py` (connects to localhost:8000)
- **Database**: Auto-init via `init_db()` in `backend/main.py`; migrations via SQL scripts.
- **Testing**: No formal tests yet; validate manually (analyze deal, save/load, export CSV).

## Project-Specific Conventions
- **Plan Limits**: Enforced via `backend/features.py` (e.g., free: 25 saved deals; pro: 250).
- **Auth**: JWT-based; mock for dev until real login.
- **UI Counts**: Start at 1, never 0 (e.g., "Deal 1" not "Deal 0").
- **Deal Grades**: A-F scale; risk levels: low/medium/high.
- **Trash**: 7-day retention; restore via `/property/trash/restore`.
- **Exports**: CSV gated by plan; use pandas for generation.

## Streamlit Safety Rules
- Never assign to `st.session_state` for a widget key after that widget renders.
- Use "apply_on_next_run" pattern: set `ss["_apply_payload"] = {...}` on click, `st.rerun()`, apply at top of page if payload exists.
- Never reuse widget keys; never change keys for existing UI elements.

## Output Format
- Provide a short plan
- Then provide exact code diffs OR full file only if requested
- List files changed
- List manual test steps

## UX Principles
- Counts must start at 1, never 0.
- Portfolio tables must not duplicate index columns.
- Deleted items go to Trash (7-day retention).
- Save buttons must always appear after successful analysis.

If instructions conflict, prioritize stability and backward compatibility.
