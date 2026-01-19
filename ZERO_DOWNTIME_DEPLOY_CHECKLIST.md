# 🚀 Zero-Downtime Production Deploy Checklist — Brinkadata Assets MVP

**Target Release:** `brinkadata-assets-mvp`  
**Deployment Type:** Blue/Green (Backend) + Rolling (Frontend)  
**Expected Duration:** 60–90 minutes  
**Rollback Window:** 60 minutes after completion

---

## Pre-Deploy Information

**What's Deploying:**
- ✅ New tables: `assets`, `property_index` (with `account_id` tenant isolation)
- ✅ New endpoints: `/api/v1/assets/*`, `/api/v1/property/search`
- ✅ New capabilities: `property_search`, `manage_assets`
- ✅ New frontend pages: Property Search, Assets (RBAC-gated)
- ✅ No changes to: Analyzer, Portfolio, Auth, Plans

**Why Zero-Downtime Works:**
- Expand-only migration (new tables don't affect old code)
- Old app instances ignore new tables/endpoints
- Capability-gating prevents premature feature access

---

## A) RELEASE ARTIFACTS & CHANGE CONTROL

### 1. Identify Deployment Artifacts

- [ ] **Git Tag:** `brinkadata-assets-mvp`
- [ ] **Commit Hash:** `7057cb0` (verify with `git log --oneline --decorate`)
- [ ] **Backend Artifact:**
  - [ ] Docker image tag: `brinkadata-backend:assets-mvp` OR
  - [ ] Git SHA for deployment: `7057cb0`
- [ ] **Frontend Artifact:**
  - [ ] Docker image tag: `brinkadata-frontend:assets-mvp` OR
  - [ ] Build output directory prepared

### 2. Document Change Manifest

Record in deployment log:
```
Release: brinkadata-assets-mvp
Date: YYYY-MM-DD HH:MM UTC
Git SHA: 7057cb0
Migration: migrate_property_search_assets.py

NEW ENDPOINTS:
- POST /api/v1/property/search (requires property_search capability)
- GET /api/v1/assets (requires manage_assets capability)
- POST /api/v1/assets (requires manage_assets capability)
- GET /api/v1/assets/{id} (requires manage_assets capability)
- DELETE /api/v1/assets/{id} (requires manage_assets capability)

NEW PAGES:
- Property Search (capability-gated)
- Assets (capability-gated)

SCHEMA CHANGES:
- CREATE TABLE assets (account_id, property_id, address, city, state, saved_at)
- CREATE TABLE property_index (account_id, property_id, address, city, state, indexed_at)
- CREATE INDEX idx_assets_account_id
- CREATE INDEX idx_property_index_account_id
```

---

## B) PRE-DEPLOY SAFETY CHECKS (NO CHANGES YET)

### 1. Monitoring & Alerting

- [ ] **Confirm monitoring is active:**
  - [ ] API error rate (4xx/5xx)
  - [ ] API latency (p50, p95, p99)
  - [ ] Database connection pool utilization
  - [ ] CPU/memory usage
  - [ ] Active sessions
  
- [ ] **Set up deployment alerts:**
  - [ ] Error rate spike (> 1% for 2 minutes)
  - [ ] Latency spike (p95 > 2 seconds)
  - [ ] Database connection exhaustion

### 2. Environment Configuration Validation

- [ ] **Database connection:**
  ```bash
  echo $DATABASE_URL
  # Should be: postgresql://user:***@prod-host:5432/brinkadata
  ```

- [ ] **JWT signing key (DO NOT LOG VALUE):**
  ```bash
  # Verify it exists (length check only):
  echo ${#JWT_SECRET}
  # Should output: 64 or similar (NOT the actual secret)
  ```

- [ ] **Environment flag:**
  ```bash
  echo $ENV
  # Should output: prod or production
  ```

- [ ] **CORS origins:**
  ```bash
  echo $CORS_ORIGINS
  # Should include: https://app.brinkadata.com
  ```

- [ ] **Log level:**
  ```bash
  echo $LOG_LEVEL
  # Should be: INFO or WARNING (NOT DEBUG)
  ```

### 3. Backup & Rollback Readiness

- [ ] **Take fresh database backup:**
  ```bash
  pg_dump -U brinkadata_user -d brinkadata -Fc -f \
    backup_pre_assets_mvp_$(date +%Y%m%d_%H%M%S).dump
  
  # Verify backup size is reasonable:
  ls -lh backup_*.dump
  ```

- [ ] **Storage snapshot (if cloud provider supports):**
  - [ ] AWS RDS: Create snapshot via console/CLI
  - [ ] GCP Cloud SQL: Create snapshot via console/CLI

- [ ] **Confirm old artifacts are available for rollback:**
  - [ ] Previous backend image/tag: `brinkadata-backend:previous`
  - [ ] Previous frontend build available

- [ ] **Test restore process (optional but recommended):**
  ```bash
  # Restore to staging/test DB to confirm backup is valid
  pg_restore -U test_user -d test_db backup_pre_assets_mvp_*.dump --clean
  ```

### 4. Communication

- [ ] **Notify stakeholders:**
  - [ ] Deployment window: [START TIME] to [END TIME]
  - [ ] Expected user impact: None (zero-downtime)
  - [ ] Rollback window: 60 minutes after completion

- [ ] **Prepare status page (if applicable):**
  - [ ] "Maintenance in progress" or "Deployment underway"

---

## C) MIGRATION COMPATIBILITY GATE (CRITICAL FOR ZERO-DOWNTIME)

### 1. Review Migration SQL

- [ ] **Generate migration SQL for review:**
  ```bash
  # If using Alembic:
  alembic upgrade head --sql > migration_review.sql
  
  # If custom script:
  python backend/migrate_property_search_assets.py --dry-run > migration_review.sql
  ```

- [ ] **Inspect SQL for safe operations:**
  - [ ] ✅ Contains ONLY: `CREATE TABLE`, `CREATE INDEX CONCURRENTLY`
  - [ ] ❌ Does NOT contain: `DROP TABLE`, `DROP COLUMN`, `ALTER COLUMN` (type changes)
  - [ ] ❌ Does NOT contain: `CREATE INDEX` (without CONCURRENTLY on large tables)

- [ ] **Verify new tables do not affect old code:**
  - [ ] `assets` table: New table, old code doesn't reference it
  - [ ] `property_index` table: New table, old code doesn't reference it
  - [ ] No changes to existing tables: `users`, `accounts`, `saved_properties`, etc.

### 2. Migration Safety Checklist

- [ ] **Migration is expand-only** (adds new resources, doesn't modify existing)
- [ ] **No long-running locks** (all indexes use CONCURRENTLY)
- [ ] **No data backfills** (or backfills are done in separate background job)
- [ ] **Old app instances can run during migration** (they ignore new tables)
- [ ] **New app instances can run with old schema** (graceful degradation via capability-gating)

### 3. Decision Point: GO / NO-GO for Migration

**GO if:**
- ✅ Migration is expand-only
- ✅ Backup completed successfully
- ✅ Monitoring is active
- ✅ No active incidents

**NO-GO if:**
- ❌ Migration contains destructive operations
- ❌ Active production incident
- ❌ Backup failed or untested
- ❌ High load period (defer to low-traffic window)

**Decision:** ☐ GO  ☐ NO-GO (if NO-GO, reschedule)

---

## D) DATABASE MIGRATION DEPLOY (ZERO-DOWNTIME PATH)

### 1. Apply Migration (Before App Deploy)

**Why first?** Old app instances don't use new tables, so it's safe.

- [ ] **Run migration from dedicated job/admin host (NOT from web worker):**
  ```bash
  # Navigate to project directory:
  cd /path/to/brinkadata
  
  # Activate environment:
  source venv/bin/activate  # or equivalent
  
  # Run migration:
  python backend/migrate_property_search_assets.py
  
  # Expected output: "Migration completed successfully"
  ```

- [ ] **Record migration start time:** `_________` (UTC)
- [ ] **Record migration end time:** `_________` (UTC)
- [ ] **Migration duration:** `_________` (should be < 10 seconds for small tables)

### 2. Verify Migration Success

- [ ] **Check schema version:**
  ```bash
  # If using Alembic:
  alembic current
  
  # Should show: head (or specific revision matching your migration)
  ```

- [ ] **Verify tables exist:**
  ```bash
  psql -U brinkadata_user -d brinkadata -c "\dt assets"
  # Should show: assets table
  
  psql -U brinkadata_user -d brinkadata -c "\dt property_index"
  # Should show: property_index table
  ```

- [ ] **Verify indexes exist:**
  ```bash
  psql -U brinkadata_user -d brinkadata -c "\d assets"
  # Should show: idx_assets_account_id
  
  psql -U brinkadata_user -d brinkadata -c "\d property_index"
  # Should show: idx_property_index_account_id
  ```

- [ ] **Verify table structure:**
  ```sql
  -- Run in psql:
  SELECT column_name, data_type, is_nullable 
  FROM information_schema.columns 
  WHERE table_name = 'assets';
  
  -- Expected columns: id, account_id, property_id, address, city, state, saved_at, metadata (JSONB)
  ```

### 3. Migration Verification Passed

- [ ] ✅ Tables created
- [ ] ✅ Indexes created
- [ ] ✅ No errors in migration log
- [ ] ✅ Old app instances still running and stable

**If migration failed:**
- [ ] Check error logs
- [ ] Rollback migration if script supports it
- [ ] Restore from backup if needed
- [ ] **STOP deployment** and investigate

---

## E) BACKEND DEPLOY (BLUE/GREEN PREFERRED)

### Strategy Selection

**Choose ONE:**
- [ ] **BLUE/GREEN** (recommended) — Deploy new stack alongside old, switch traffic atomically
- [ ] **ROLLING UPDATE** (acceptable) — Update instances in batches

---

### OPTION 1: BLUE/GREEN BACKEND DEPLOY

#### Step 1: Deploy GREEN Backend (New Version)

- [ ] **Stand up GREEN backend instances:**
  ```bash
  # Example for Kubernetes:
  kubectl apply -f backend-deployment-green.yaml
  
  # Example for Docker Compose:
  docker-compose -f docker-compose.green.yml up -d
  
  # Example for Heroku/PaaS:
  # Deploy to new app slug without switching traffic
  ```

- [ ] **Wait for GREEN instances to be healthy:**
  ```bash
  # Check pod status:
  kubectl get pods -l app=backend,version=green
  
  # All pods should show: Running (2/2)
  ```

#### Step 2: Warmup & Smoke Test GREEN (No Traffic Yet)

- [ ] **Health check:**
  ```bash
  curl -f http://green-backend:8000/health
  # Expected: 200 OK
  ```

- [ ] **Auth-protected endpoint test:**
  ```bash
  # Get a valid token (DO NOT LOG TOKEN VALUE):
  TOKEN="<valid-jwt-token>"
  
  # Test existing endpoint (should work on GREEN):
  curl -H "Authorization: Bearer $TOKEN" \
       http://green-backend:8000/api/v1/portfolio
  # Expected: 200 OK with portfolio data
  
  # Test new endpoint (should work on GREEN):
  curl -H "Authorization: Bearer $TOKEN" \
       http://green-backend:8000/api/v1/assets
  # Expected: 200 OK (empty list if no assets) OR 403 if capability missing
  ```

- [ ] **Verify GREEN can connect to database:**
  ```bash
  # Check logs for successful DB connection:
  kubectl logs -l app=backend,version=green | grep "Database connected"
  # or equivalent for your deployment
  ```

- [ ] **Smoke test results:**
  - [ ] ✅ Health endpoint responding
  - [ ] ✅ Auth working (token validation)
  - [ ] ✅ Database connected
  - [ ] ✅ Old endpoints working
  - [ ] ✅ New endpoints responding (even if 403 due to missing capability)

#### Step 3: Canary Traffic to GREEN (1–5%)

- [ ] **Route 1–5% of traffic to GREEN:**
  ```bash
  # Example for Nginx/load balancer:
  # Update upstream weights: BLUE=95, GREEN=5
  
  # Example for Kubernetes with Istio/service mesh:
  kubectl apply -f backend-traffic-split-canary.yaml
  
  # Example for AWS ALB:
  # Update target group weights via console/CLI
  ```

- [ ] **Monitor canary metrics for 5–10 minutes:**
  - [ ] Error rate: GREEN should match BLUE (within ±0.1%)
  - [ ] Latency: GREEN p95 should be ≤ BLUE p95 (within ±100ms)
  - [ ] No new exceptions in logs

- [ ] **Canary health check:**
  - [ ] ✅ Error rate normal
  - [ ] ✅ Latency normal
  - [ ] ✅ No auth regressions
  - [ ] ❌ ROLLBACK if issues detected

#### Step 4: Gradual Traffic Shift

- [ ] **Shift to 25% GREEN:**
  - [ ] Update traffic split
  - [ ] Monitor for 5 minutes
  - [ ] ✅ Stable OR ❌ Rollback

- [ ] **Shift to 50% GREEN:**
  - [ ] Update traffic split
  - [ ] Monitor for 5 minutes
  - [ ] ✅ Stable OR ❌ Rollback

- [ ] **Shift to 100% GREEN:**
  - [ ] Update traffic split
  - [ ] Monitor for 10 minutes
  - [ ] ✅ Stable OR ❌ Rollback

#### Step 5: Keep BLUE Warm for Rollback Window

- [ ] **Leave BLUE running for 60 minutes** (do NOT terminate instances)
- [ ] **After 60 minutes and verification passed:**
  - [ ] Terminate BLUE instances
  - [ ] Update GREEN to be new BLUE (rename/relabel for next deploy)

---

### OPTION 2: ROLLING UPDATE BACKEND DEPLOY

#### Step 1: Update Instances in Batches

- [ ] **Identify total instance count:** `_____` instances
- [ ] **Calculate batch size:** `_____` instances (10–20% of total, min 1)

#### Step 2: Deploy Batch 1

- [ ] **Update first batch:**
  ```bash
  # Example for Kubernetes:
  kubectl set image deployment/backend backend=brinkadata-backend:assets-mvp
  kubectl rollout pause deployment/backend
  
  # Wait for first batch to be ready:
  kubectl rollout status deployment/backend
  ```

- [ ] **Monitor batch 1 for 5 minutes:**
  - [ ] Error rate: Should match pre-deploy baseline
  - [ ] Latency: Should match pre-deploy baseline
  - [ ] No new exceptions

- [ ] **Batch 1 health:** ☐ ✅ Stable  ☐ ❌ Rollback

#### Step 3: Deploy Remaining Batches

- [ ] **Resume rollout OR deploy next batch:**
  ```bash
  kubectl rollout resume deployment/backend
  # OR deploy next batch manually and repeat monitoring
  ```

- [ ] **Monitor each batch before proceeding**
- [ ] **All batches deployed:** ☐ Yes

---

### Backend Deployment Verification (Either Strategy)

- [ ] **Verify new endpoints respond:**
  ```bash
  # Test with valid token:
  curl -H "Authorization: Bearer $TOKEN" \
       https://api.brinkadata.com/api/v1/assets
  # Expected: 200 OK or 403 (if capability missing)
  
  curl -H "Authorization: Bearer $TOKEN" \
       -X POST https://api.brinkadata.com/api/v1/property/search \
       -H "Content-Type: application/json" \
       -d '{"query": "Austin, TX"}'
  # Expected: 200 OK or 403 (if capability missing)
  ```

- [ ] **Verify existing endpoints unaffected:**
  ```bash
  # Test analyzer endpoint:
  curl -H "Authorization: Bearer $TOKEN" \
       https://api.brinkadata.com/api/v1/property/analyze
  # Expected: Works as before
  
  # Test portfolio endpoint:
  curl -H "Authorization: Bearer $TOKEN" \
       https://api.brinkadata.com/api/v1/portfolio
  # Expected: Works as before
  ```

- [ ] **Backend deployment successful:** ☐ ✅ Yes  ☐ ❌ Rollback

---

## F) FRONTEND DEPLOY (STREAMLIT)

### Why Frontend Second?

- New frontend pages call new backend endpoints (which are now live)
- Capability-gating prevents users from seeing new pages if capabilities not assigned
- Frontend is stateless, so deploy is simpler

### Step 1: Deploy New Frontend

- [ ] **Deploy frontend artifact:**
  ```bash
  # Example for Docker:
  docker pull brinkadata-frontend:assets-mvp
  docker-compose up -d frontend
  
  # Example for Streamlit Cloud:
  # Push to main branch OR deploy via dashboard
  
  # Example for Kubernetes:
  kubectl set image deployment/frontend frontend=brinkadata-frontend:assets-mvp
  kubectl rollout status deployment/frontend
  ```

- [ ] **Wait for frontend instances to be healthy:**
  ```bash
  # Check that frontend is serving:
  curl -f https://app.brinkadata.com/
  # Expected: 200 OK (may redirect to login)
  ```

### Step 2: Frontend Smoke Test

- [ ] **Login test:**
  - [ ] Navigate to `https://app.brinkadata.com`
  - [ ] Login with test account
  - [ ] Dashboard loads without errors
  - [ ] Session persists after refresh

- [ ] **Sidebar visibility (capability-gated):**
  - [ ] **Account WITH capabilities:**
    - [ ] "Property Search" appears in sidebar
    - [ ] "Assets" appears in sidebar
  - [ ] **Account WITHOUT capabilities:**
    - [ ] "Property Search" does NOT appear
    - [ ] "Assets" does NOT appear

- [ ] **Property Search page:**
  - [ ] Navigate to Property Search
  - [ ] Page renders (even if no data)
  - [ ] Search form is functional
  - [ ] No errors in browser console

- [ ] **Assets page:**
  - [ ] Navigate to Assets
  - [ ] Page renders (empty state if no assets)
  - [ ] No errors in browser console

- [ ] **Existing pages unaffected:**
  - [ ] Analyzer page loads
  - [ ] Portfolio page loads
  - [ ] Plans page loads (if applicable)

### Step 3: Frontend Deployment Complete

- [ ] ✅ Frontend deployed
- [ ] ✅ Login works
- [ ] ✅ Capability-gating verified
- [ ] ✅ New pages render
- [ ] ✅ Old pages unaffected

---

## G) POST-DEPLOY DATA & SECURITY VERIFICATION (REQUIRED)

### 1. RBAC Enforcement Tests

#### Test Account Setup
- **Account A:** Has `property_search` and `manage_assets` capabilities
- **Account B:** Does NOT have capabilities (or has different capabilities)

#### RBAC Test Cases

- [ ] **Test 1: Property Search without capability:**
  ```bash
  # Login as Account B (no capability):
  # Navigate to /api/v1/property/search
  # Expected: 403 Forbidden
  ```

- [ ] **Test 2: Assets read without capability:**
  ```bash
  # Login as Account B:
  # Navigate to /api/v1/assets
  # Expected: 403 Forbidden
  ```

- [ ] **Test 3: Asset create without capability:**
  ```bash
  # Login as Account B:
  # POST to /api/v1/assets
  # Expected: 403 Forbidden
  ```

- [ ] **Test 4: Property Search WITH capability:**
  ```bash
  # Login as Account A:
  # POST to /api/v1/property/search
  # Expected: 200 OK (with results or empty)
  ```

- [ ] **Test 5: Assets read WITH capability:**
  ```bash
  # Login as Account A:
  # GET /api/v1/assets
  # Expected: 200 OK (with assets or empty)
  ```

### 2. Tenant Isolation Tests (CRITICAL)

- [ ] **Test 1: Create asset as Account A:**
  ```bash
  # Login as Account A:
  # Save an asset via UI or API
  # Record asset ID: _____________
  ```

- [ ] **Test 2: Account B cannot see Account A's asset:**
  ```bash
  # Login as Account B:
  # GET /api/v1/assets
  # Expected: Asset from Account A is NOT in list
  
  # Direct access to Account A's asset:
  # GET /api/v1/assets/<account_a_asset_id>
  # Expected: 404 Not Found (or 403)
  ```

- [ ] **Test 3: Account A can only see their own assets:**
  ```bash
  # Login as Account A:
  # GET /api/v1/assets
  # Expected: Only Account A's assets appear
  ```

- [ ] **Tenant isolation verified:** ☐ ✅ PASS  ☐ ❌ FAIL (CRITICAL — ROLLBACK)

### 3. End-to-End Flow Test

- [ ] **Flow: Search → Save → List → Analyze:**
  1. [ ] Login as Account A
  2. [ ] Navigate to Property Search
  3. [ ] Search for "Austin, TX" (or any query)
  4. [ ] Click "Save as Asset" on a result
  5. [ ] Success message appears
  6. [ ] Navigate to Assets page
  7. [ ] Saved asset appears in list
  8. [ ] Click "Analyze" on the asset
  9. [ ] Analyzer page opens with address prefilled
  10. [ ] Verify city and state are prefilled (if available)

- [ ] **Flow completed successfully:** ☐ ✅ Yes  ☐ ❌ No

### 4. Logging & Security Audit

- [ ] **Check backend logs for sensitive data:**
  ```bash
  # Tail logs during test:
  kubectl logs -l app=backend --tail=100
  # OR equivalent for your deployment
  
  # Verify:
  # ✅ No JWT tokens logged
  # ✅ No request bodies with sensitive data
  # ✅ No password hashes logged
  ```

- [ ] **Logging audit passed:** ☐ ✅ Yes  ☐ ❌ No

### 5. Database Performance Check

- [ ] **Check index usage for assets queries:**
  ```sql
  -- Run in psql (on a replica if possible):
  EXPLAIN ANALYZE 
  SELECT * FROM assets 
  WHERE account_id = '<test-account-id>' 
  ORDER BY saved_at DESC 
  LIMIT 20;
  
  -- Verify:
  -- ✅ Uses idx_assets_account_id
  -- ✅ Execution time < 10ms
  ```

- [ ] **Check connection pool utilization:**
  ```bash
  # Monitor DB connections:
  # Should not spike significantly from pre-deploy baseline
  ```

- [ ] **DB performance check passed:** ☐ ✅ Yes  ☐ ❌ No

---

## H) ROLLBACK PLAN (ZERO-DOWNTIME)

### Rollback Decision Criteria

**ROLLBACK if:**
- ❌ Error rate spike (> 1% sustained for 2+ minutes)
- ❌ Latency spike (p95 > 2 seconds sustained)
- ❌ Tenant isolation breach (Account B can see Account A's data)
- ❌ RBAC failure (403 errors for valid capabilities OR 200 for missing capabilities)
- ❌ Auth regression (login fails, sessions not persisting)
- ❌ Database connection exhaustion

### Rollback Procedure

#### 1. Frontend Rollback (If UI Issues Only)

- [ ] **Redeploy previous frontend version:**
  ```bash
  # Example for Docker:
  docker pull brinkadata-frontend:previous
  docker-compose up -d frontend
  
  # Example for Kubernetes:
  kubectl rollout undo deployment/frontend
  kubectl rollout status deployment/frontend
  ```

- [ ] **Verify frontend rollback:**
  - [ ] Old UI is visible
  - [ ] No errors on load

#### 2. Backend Rollback (If API Issues)

##### Blue/Green Rollback:
- [ ] **Route traffic back to BLUE (old version):**
  ```bash
  # Update load balancer to send 100% traffic to BLUE
  # Example for Kubernetes:
  kubectl apply -f backend-traffic-blue-only.yaml
  ```

- [ ] **Verify BLUE is serving traffic:**
  ```bash
  curl -H "Authorization: Bearer $TOKEN" \
       https://api.brinkadata.com/api/v1/portfolio
  # Expected: 200 OK
  ```

##### Rolling Update Rollback:
- [ ] **Rollback deployment:**
  ```bash
  kubectl rollout undo deployment/backend
  kubectl rollout status deployment/backend
  ```

#### 3. Database Rollback (LAST RESORT — Causes Downtime)

**Only rollback DB if:**
- Data corruption occurred (highly unlikely for expand-only migration)
- Migration caused catastrophic failure

**DO NOT rollback DB if:**
- App issues only (expand-only migrations are safe to leave in place)

**If DB rollback required:**

- [ ] **Announce downtime** (maintenance page)
- [ ] **Stop all app instances** (backend + frontend)
- [ ] **Restore from backup:**
  ```bash
  # Drop database (CAREFUL):
  dropdb brinkadata
  
  # Restore from backup:
  createdb brinkadata
  pg_restore -U brinkadata_user -d brinkadata backup_pre_assets_mvp_*.dump
  ```
- [ ] **Restart app instances with old artifacts**
- [ ] **Verify restoration:**
  - [ ] Test login
  - [ ] Test analyzer
  - [ ] Test portfolio
- [ ] **Remove maintenance page**

### Rollback Verification

- [ ] **Error rate returned to baseline**
- [ ] **Latency returned to baseline**
- [ ] **Auth working**
- [ ] **Existing features functional**
- [ ] **Rollback complete:** ☐ ✅ Yes

---

## I) SUCCESS CRITERIA (GO/NO-GO FOR COMPLETION)

### Metrics Baseline

Record pre-deploy baseline for comparison:
- **Error rate:** `______%`
- **Latency p95:** `______ ms`
- **DB connections:** `______`
- **Active sessions:** `______`

### Post-Deploy Metrics (After 30 Minutes)

- [ ] **Error rate:** `______%` (within ±0.5% of baseline)
- [ ] **Latency p95:** `______ ms` (within ±200ms of baseline)
- [ ] **DB connections:** `______` (within ±10% of baseline)
- [ ] **Active sessions:** `______` (normal variation)

### Functional Tests

- [ ] ✅ Login works
- [ ] ✅ Auth/session rehydration works
- [ ] ✅ Analyzer unchanged
- [ ] ✅ Portfolio unchanged
- [ ] ✅ Property Search works (for users with capability)
- [ ] ✅ Assets CRUD works (for users with capability)
- [ ] ✅ Cross-tenant isolation verified
- [ ] ✅ RBAC enforcement verified

### Declare Success

- [ ] **All metrics stable for 30+ minutes**
- [ ] **No auth regressions**
- [ ] **New features verified**
- [ ] **Cross-tenant tests passed**
- [ ] **RBAC tests passed**

**Deployment Status:** ☐ ✅ SUCCESS  ☐ ❌ ROLLBACK

**If SUCCESS:**
- [ ] Terminate old BLUE instances (after 60 minutes)
- [ ] Update status page: "Deployment complete"
- [ ] Notify stakeholders
- [ ] Document any issues encountered
- [ ] Schedule post-mortem (if needed)

---

## J) COMMON FAILURE MODES & REMEDIATION

### 1. Migration Takes Too Long / Locks Table

**Symptoms:** Migration hangs, DB connections piling up

**Cause:** Non-concurrent index creation on large table

**Remediation:**
- Kill migration
- Rewrite to use `CREATE INDEX CONCURRENTLY`
- Retry

**Prevention:** Always use CONCURRENTLY for indexes in production

---

### 2. New Endpoints Return 500 Errors

**Symptoms:** `/api/v1/assets` returns 500

**Possible Causes:**
- DB connection issue (migration not applied)
- Missing environment variable
- Code bug in new routes

**Remediation:**
1. Check backend logs for stack trace
2. Verify migration applied: `psql -c "\dt assets"`
3. Verify environment variables present
4. If unresolvable quickly: Rollback backend

---

### 3. Capability-Gating Not Working (403 or 200 Incorrectly)

**Symptoms:** 
- User without capability can access new pages (200 when should be 403)
- User WITH capability gets 403

**Possible Causes:**
- Capability not assigned to user's plan
- RBAC decorator not applied to endpoint
- JWT missing capability claims

**Remediation:**
1. Check user's JWT payload (decode on jwt.io)
2. Verify capabilities in `entitlements` or `features` table
3. Verify `@require_capability("property_search")` on endpoint
4. If broken for all users: Rollback backend

---

### 4. Tenant Isolation Breach (Account B Sees Account A Data)

**Symptoms:** Cross-tenant data visible

**Cause:** Missing `account_id` filter in query

**Remediation:**
- **IMMEDIATELY ROLLBACK BACKEND**
- This is a critical security issue
- Review all queries in new routes
- Add unit tests for tenant isolation
- Redeploy with fix

---

### 5. Frontend Doesn't Show New Pages

**Symptoms:** Property Search / Assets missing from sidebar

**Possible Causes:**
- Frontend not deployed (cached old version)
- Capability-gating too aggressive (hiding pages incorrectly)
- Browser cache

**Remediation:**
1. Hard refresh browser (Ctrl+Shift+R)
2. Check frontend version: View source → look for version comment
3. Verify capabilities in JWT
4. Check frontend logs for errors

---

### 6. Database Connection Pool Exhausted

**Symptoms:** 500 errors, "too many connections" in logs

**Possible Causes:**
- New code has connection leak
- Query taking too long (holding connections)

**Remediation:**
1. Increase connection pool size (temporary):
   ```sql
   ALTER SYSTEM SET max_connections = 200;
   SELECT pg_reload_conf();
   ```
2. Identify slow queries:
   ```sql
   SELECT pid, query, state, query_start 
   FROM pg_stat_activity 
   WHERE state != 'idle';
   ```
3. Kill long-running queries if needed
4. Rollback if issue persists

---

### 7. Session Lost / Auth Regression

**Symptoms:** Users logged out, must re-login frequently

**Possible Causes:**
- JWT signing key changed
- Session storage issue

**Remediation:**
1. Verify JWT_SECRET unchanged
2. Check Redis/session store (if used)
3. If JWT_SECRET changed accidentally: Rollback immediately

---

## K) POST-DEPLOY MONITORING (First 24 Hours)

### Hour 1 (Intensive Monitoring)

- [ ] **Every 5 minutes:** Check error rate, latency
- [ ] **Watch logs:** Tail backend logs for exceptions
- [ ] **Test new features:** Run smoke tests manually

### Hours 2–4 (Active Monitoring)

- [ ] **Every 15 minutes:** Check metrics dashboard
- [ ] **Watch alerts:** Respond to any threshold breaches

### Hours 5–24 (Passive Monitoring)

- [ ] **Hourly:** Glance at dashboard
- [ ] **Alert-driven:** Respond to automated alerts only

### After 24 Hours

- [ ] **Review metrics:** Compare pre/post deploy
- [ ] **Identify anomalies:** Investigate any outliers
- [ ] **Document lessons learned**
- [ ] **Close deployment ticket**

---

## L) DEPLOYMENT SIGN-OFF

**Deployer:** `_____________________`  
**Date/Time:** `_____________________` (UTC)  
**Deployment Duration:** `_____________________`  
**Issues Encountered:** `_____________________`  
**Rollback Required:** ☐ Yes  ☐ No  
**Final Status:** ☐ Success  ☐ Partial  ☐ Failed  

**Approved for Completion:** `_____________________` (Name/Role)

---

## M) APPENDIX: Quick Reference Commands

### Check Deployment Status
```bash
# Backend version:
curl https://api.brinkadata.com/health | jq '.version'

# Frontend version:
curl https://app.brinkadata.com/ | grep "version"

# Git tag deployed:
git describe --tags --exact-match
```

### Check Database Migration Status
```bash
# Current schema version:
alembic current

# List tables:
psql -U brinkadata_user -d brinkadata -c "\dt"

# Check index on assets:
psql -U brinkadata_user -d brinkadata -c "\d assets"
```

### Monitor Metrics
```bash
# Error rate (last 5 minutes):
# Replace with your monitoring tool query

# Latency p95 (last 5 minutes):
# Replace with your monitoring tool query

# Database connections:
psql -U brinkadata_user -d brinkadata -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='brinkadata';"
```

### Quick Rollback
```bash
# Backend (blue/green):
kubectl apply -f backend-traffic-blue-only.yaml

# Backend (rolling):
kubectl rollout undo deployment/backend

# Frontend:
kubectl rollout undo deployment/frontend
```

---

**END OF CHECKLIST**

Use this checklist step-by-step during deployment. Check off each item as completed.  
If any step fails, follow the rollback procedures immediately.

Good luck with the deployment! 🚀
