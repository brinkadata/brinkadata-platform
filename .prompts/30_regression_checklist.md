# Regression Checklist (must pass before commit)

## Backend
- /health returns ok
- register/login works
- analyze returns metrics
- save deal works
- list saved deals works
- delete -> trash works
- trash restore works

## Frontend
- Analyzer runs
- Save button appears after analysis
- Portfolio loads and filters work
- Delete moves to trash
- Restore works
- No Streamlit session_state mutation warnings
- No duplicate widget keys
