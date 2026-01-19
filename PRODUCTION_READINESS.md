# Brinkadata Assets MVP — Production Readiness Checklist

**Git Tag:** `brinkadata-assets-mvp`  
**Date:** January 19, 2026  
**Status:** ✅ Locked for deployment

---

## A) Git Hygiene — ✅ COMPLETE

### Commit History
```
7057cb0 (tag: brinkadata-assets-mvp) feat(ui): property search and assets pages with RBAC gating
bf28a44 feat(assets): tenant-safe assets + property search backend (MVP)
```

### Two Atomic Commits
- **Commit 1 (bf28a44):** DB migration + backend routes + schemas + tests
- **Commit 2 (7057cb0):** Frontend pages + nav wiring + API client wrappers

### Tag Created
```bash
git tag brinkadata-assets-mvp
# Push to remote when ready:
# git push origin main --tags
```

---

## B) Production Config Validation — REQUIRED

### Environment Variables (Documented)

| Variable | Purpose | Required | Example |
|----------|---------|----------|---------|
| `DATABASE_URL` | PostgreSQL/SQLite connection string | ✅ | `sqlite:///brinkadata.db` or `postgresql://user:pass@host/db` |
| `JWT_SECRET` | Signing key for auth tokens | ✅ | `your-256-bit-secret-key` |
| `ENV` | Environment identifier | ✅ | `prod` or `production` |
| `LOG_LEVEL` | Logging verbosity | ✅ | `INFO` or `WARNING` (NOT `DEBUG` in prod) |
| `CORS_ORIGINS` | Allowed frontend origins | ✅ | `https://app.brinkadata.com` |

### Security Requirements
- [ ] `JWT_SECRET` is randomly generated (min 32 bytes)
- [ ] `LOG_LEVEL` is set to `INFO` or `WARNING` (NOT `DEBUG`)
- [ ] Request bodies are NOT logged
- [ ] JWT tokens are NOT logged
- [ ] `.env` file is excluded from version control (in `.gitignore`)

### Database User Permissions
- [ ] Can read/write to `assets` table
- [ ] Can read/write to `property_index` table
- [ ] Cannot access tables belonging to other tenants (if using schema-per-tenant)
- [ ] Has `account_id` column indexed on both tables

---

## C) Production Migration Dry-Run — MANDATORY

### Pre-Migration Checklist
1. **Backup Database**
   ```bash
   # SQLite
   cp brinkadata.db brinkadata.db.backup-$(date +%Y%m%d)
   
   # PostgreSQL
   pg_dump -U user -d brinkadata > backup-$(date +%Y%m%d).sql
   ```

2. **Review Migration SQL**
   - File: `backend/migrate_property_search_assets.py`
   - Tables created:
     - `assets` (account_id, property_id, address, city, state, saved_at)
     - `property_index` (account_id, property_id, address, city, state, indexed_at)
   - Indexes created:
     - `idx_assets_account_id` on `assets(account_id)`
     - `idx_property_index_account_id` on `property_index(account_id)`

3. **Dry-Run Steps (Staging/Replica)**
   ```bash
   # Test migration on staging database first
   python backend/migrate_property_search_assets.py --dry-run
   
   # Inspect generated SQL for:
   # - No DROP TABLE statements
   # - No unbounded UPDATE statements
   # - Proper account_id isolation
   ```

4. **Apply Migration (After Validation)**
   ```bash
   python backend/migrate_property_search_assets.py
   ```

5. **Post-Migration Verification**
   ```bash
   # Verify tables exist
   sqlite3 brinkadata.db ".tables"
   # Should show: assets, property_index
   
   # Verify indexes
   sqlite3 brinkadata.db ".schema assets"
   # Should show: idx_assets_account_id
   ```

---

## D) Smoke Tests — Post-Deploy Manual Validation

### Test Account Setup
- Account 1: `test_account_1` (with `property_search` capability)
- Account 2: `test_account_2` (without capability OR different tenant)

### Test Cases

#### 1. Dashboard Load
- [ ] Login as test_account_1
- [ ] Dashboard loads without errors
- [ ] No 500 errors in backend logs

#### 2. Property Search Visibility
- [ ] "Property Search" appears in sidebar (account_1 with capability)
- [ ] "Property Search" does NOT appear for account without capability

#### 3. Property Search Functionality
- [ ] Navigate to Property Search page
- [ ] Enter search query (e.g., "Austin, TX")
- [ ] Click "Search Properties"
- [ ] Results appear OR clean empty state displays
- [ ] No errors in browser console or backend logs

#### 4. Save as Asset
- [ ] Click "Save as Asset" on a search result
- [ ] Success toast/message appears
- [ ] Asset appears in Assets list

#### 5. Assets List
- [ ] Navigate to "Assets" page
- [ ] Saved asset appears in list
- [ ] "Analyze" button is visible and enabled

#### 6. Analyze Asset
- [ ] Click "Analyze" on saved asset
- [ ] Analyzer page opens
- [ ] Address is prefilled in analyzer form
- [ ] City and state are prefilled (if available)

#### 7. Cross-Tenant Isolation ⚠️ CRITICAL
- [ ] Login as test_account_2 (different tenant)
- [ ] Navigate to Assets page
- [ ] Assets from test_account_1 are NOT visible
- [ ] Direct API call to account_1's asset returns 404 or 403
   ```bash
   # Example test:
   curl -H "Authorization: Bearer <account2_token>" \
        http://localhost:8000/api/v1/assets/<account1_asset_id>
   # Expected: 404 or 403, NOT 200
   ```

---

## E) Observability & Security Sanity Check

### Backend Logging Review
- [ ] No JWT tokens printed in logs
- [ ] No request bodies logged (may contain sensitive data)
- [ ] No password or secret values logged
- [ ] User actions logged with `account_id` for audit trail

### Error Handling Verification
- [ ] Missing capability → 403 Forbidden (with clear message)
- [ ] Cross-tenant access → 404 Not Found (or 403)
- [ ] Invalid input → 422 Unprocessable Entity (with validation errors)
- [ ] Server errors → 500 Internal Server Error (no stack traces exposed in prod)

### RBAC Enforcement
- [ ] `/api/v1/property/search` requires `property_search` capability
- [ ] `/api/v1/assets/*` requires `manage_assets` capability
- [ ] Missing capability returns 403, not 500

### Tenant Isolation
- [ ] All queries include `account_id` filter
- [ ] No cross-tenant data leakage possible
- [ ] Database queries use parameterized statements (no SQL injection)

---

## F) Rollback Plan

### If Issues Arise Post-Deploy

1. **Quick Rollback (Git)**
   ```bash
   # Revert to previous stable tag
   git checkout <previous-stable-tag>
   # Restart services
   ```

2. **Database Rollback**
   ```bash
   # If migration is reversible:
   python backend/migrate_property_search_assets.py --rollback
   
   # Or restore from backup:
   cp brinkadata.db.backup-YYYYMMDD brinkadata.db
   ```

3. **Feature Flag Disable (Future)**
   - Disable `property_search` and `manage_assets` capabilities at plan level
   - Users lose access without code changes

---

## G) Deployment Steps (Production)

1. **Pre-Deploy**
   - [ ] Backup production database
   - [ ] Verify environment variables are set
   - [ ] Test migration on staging replica

2. **Deploy**
   - [ ] Pull `brinkadata-assets-mvp` tag
   - [ ] Run database migration
   - [ ] Restart backend service
   - [ ] Restart frontend service

3. **Post-Deploy**
   - [ ] Run smoke tests (Section D)
   - [ ] Monitor logs for errors
   - [ ] Verify no 500 errors in first 10 minutes
   - [ ] Test cross-tenant isolation

4. **Monitoring**
   - [ ] Watch error rates (should not spike)
   - [ ] Check API response times (should remain consistent)
   - [ ] Monitor database query performance

---

## H) Next Steps (DO NOT IMPLEMENT YET)

After MVP is locked and deployed, the next approved roadmap item is:

**Assets v1 Enhancements (Design-first)**
- Asset pagination
- Asset bulk actions (future)
- Advanced property filters (beds/baths/price) — requires data source decision
- CSV export (capability-gated)

**Action Required:** Design doc ONLY when requested (no code yet).

---

## Status Summary

| Phase | Status | Notes |
|-------|--------|-------|
| A) Git Hygiene | ✅ Complete | Two atomic commits + tag |
| B) Config Validation | ⚠️ Manual | Review env vars before deploy |
| C) Migration Dry-Run | ⚠️ Manual | Test on staging first |
| D) Smoke Tests | ⚠️ Manual | Run post-deploy |
| E) Observability | ⚠️ Manual | Review logs |
| F) Rollback Plan | ✅ Documented | Ready if needed |
| G) Deployment Steps | ⚠️ Ready | Execute when validated |

**Overall Status:** 🔒 Locked for production deployment (pending manual validations)

---

## Contact

For deployment questions or issues:
- Review this checklist
- Check backend logs: `tail -f logs/backend.log`
- Check frontend logs: Streamlit console output
- Run smoke tests to isolate issues
