# Frontend: Scenario Comparison UX

Implement scenario save/load in Streamlit without session_state widget errors.

## Requirements
- Scenario section in Analyzer:
  - dropdown slot A/B/C to save current analysis
  - show table of saved scenarios
  - "Load A/B/C into analyzer"
  - "Clear slot"
- Uses apply-on-next-run pattern to avoid Streamlit key exceptions.
- Must respect feature gating (if plan restricts scenarios, show upgrade UI)
- No duplicate numbering columns; all displayed row numbers start at 1

## Deliverables
- Update frontend/app.py (or page modules)
- Manual test steps list
