# Backend: Scenario Saving (A/B/C)

Implement persistent scenario saving.

## Requirements
- Store scenarios per account_id and user_id (at least account_id).
- Each scenario slot is one of: "A", "B", "C".
- Save should upsert slot for that account.
- Scenario contains:
  - label/name
  - strategy
  - grade
  - key metrics (roi, cashflow, noi, cap_rate, coc, irr, npv)
  - input snapshot (the analyzer inputs)
  - created_at / updated_at

## Endpoints
- POST /scenario/save
- GET /scenario/list
- POST /scenario/clear
- POST /scenario/load (optional)

## Plan gating
- Free: allow A/B/C but limit saves per day or total scenarios (define simple rule)
- Pro+: unlimited

## Deliverables
- DB model + migrations (sqlite)
- router endpoints
- service functions
- tests if available
