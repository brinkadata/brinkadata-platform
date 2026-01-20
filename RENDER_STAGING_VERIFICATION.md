# Render Staging Verification Guide

**Idiot-proof copy/paste commands for verifying your Render deployment.**

---

## 1. Find Your Service URLs

1. Log into [Render Dashboard](https://dashboard.render.com/)
2. Navigate to your services:
   - **Backend**: `brinkadata-backend` → Copy the `.onrender.com` URL (e.g., `https://brinkadata-backend.onrender.com`)
   - **Frontend**: `brinkadata-frontend` → Copy the `.onrender.com` URL (e.g., `https://brinkadata-frontend.onrender.com`)
   - **Database**: `brinkadata-db` → Status should show "Available"

---

## 2. Verify Backend Health (PowerShell-Friendly)

Replace `<BACKEND_URL>` with your actual backend URL (no trailing slash).

### a) Health Check (Unauthenticated)

```powershell
curl -Uri "<BACKEND_URL>/health" -Method GET
```

**Expected Output:**
```json
{"status":"ok"}
```

**Expected HTTP Status:** `200 OK`

---

### b) API Documentation (Unauthenticated)

```powershell
curl -Uri "<BACKEND_URL>/docs" -Method GET
```

**Expected Output:** HTML content (FastAPI Swagger UI)

**Expected HTTP Status:** `200 OK`

**Alternative**: Open `<BACKEND_URL>/docs` in your browser to see interactive docs.

---

### c) Version Info (Unauthenticated)

```powershell
curl -Uri "<BACKEND_URL>/version" -Method GET
```

**Expected Output (if commit SHA available):**
```json
{"status":"ok","commit":"a1b2c3d"}
```

**Expected Output (if commit SHA not available):**
```json
{"status":"ok"}
```

**Expected HTTP Status:** `200 OK`

---

### d) Protected Endpoint (Confirm Auth Gate)

Try to access a protected endpoint without authentication:

```powershell
curl -Uri "<BACKEND_URL>/property/saved" -Method GET
```

**Expected HTTP Status:** `401 Unauthorized` or `403 Forbidden`

**Expected Output (example):**
```json
{"detail":"Not authenticated"}
```

If you get `200 OK` here, **STOP** — authentication is not working correctly.

---

## 3. Run Database Migration (First-Time Setup)

**IMPORTANT:** Run this **ONCE** after your first deployment or when schema changes are deployed.

### Steps:

1. Go to Render Dashboard → **brinkadata-backend** service
2. Click **"Shell"** tab (opens a terminal in the running container)
3. Run:

```bash
python -m backend.migrate
```

### Expected Success Output:

```
[MIGRATE] Starting database migrations...
[MIGRATE] Running PostgreSQL migrations...
[MIGRATE] Created table: users
[MIGRATE] Created table: accounts
[MIGRATE] Created table: plans
[MIGRATE] Created table: subscriptions
[MIGRATE] Created table: affiliates
[MIGRATE] Created table: referrals
[MIGRATE] Created table: saved_properties
[MIGRATE] Created table: property_search_assets
[MIGRATE] Created table: scenarios
[MIGRATE] Created table: trash_items
[MIGRATE] Added column saved_properties.cause_tag
[MIGRATE] Added column saved_properties.last_viewed_at
[MIGRATE] All migrations complete!
```

### What If I Run It Again?

**Safe!** The migration is idempotent. Re-running it will output:

```
[MIGRATE] Table users already exists
[MIGRATE] Table accounts already exists
...
[MIGRATE] Column saved_properties.cause_tag already exists
[MIGRATE] All migrations complete!
```

---

## 4. Verify Frontend

Open your frontend URL in a browser:

```
https://brinkadata-frontend.onrender.com
```

**Expected:** Streamlit app loads with the Brinkadata landing page.

**If it doesn't load:** Check the "Logs" tab in Render Dashboard for errors.

---

## 5. Troubleshooting

### ❌ Issue: `/health` returns 404 or 503

**Cause:** Backend service is not running or still deploying.

**Fix:**
1. Check Render Dashboard → **brinkadata-backend** → Status should be "Live" (green).
2. If "Building" or "Deploying", wait for completion.
3. Check "Logs" tab for errors during startup.

---

### ❌ Issue: `/health` returns 200 but `/docs` returns CORS error in browser

**Cause:** CORS_ORIGINS misconfigured.

**Fix:**
1. Go to Render Dashboard → **brinkadata-backend** → "Environment" tab
2. Ensure `CORS_ORIGINS` includes your frontend URL:
   ```
   https://brinkadata-frontend.onrender.com
   ```
3. If missing or incorrect, update and **Redeploy** the service.

**Note:** If testing from `localhost`, add `http://localhost:8501` to CORS_ORIGINS (comma-separated):
```
https://brinkadata-frontend.onrender.com,http://localhost:8501
```

---

### ❌ Issue: `/property/saved` returns 200 without auth (should be 401/403)

**Cause:** Auth middleware not applied or SECRET_KEY missing.

**Fix:**
1. Go to Render Dashboard → **brinkadata-backend** → "Environment" tab
2. Ensure `SECRET_KEY` exists and has a value (Render auto-generates this if you used `generateValue: true` in render.yaml).
3. If missing, add it with a secure random value:
   ```bash
   openssl rand -hex 32
   ```
4. **Redeploy** the service.

---

### ❌ Issue: Migration fails with "connection refused" or "database does not exist"

**Cause:** Database not connected or DATABASE_URL misconfigured.

**Fix:**
1. Go to Render Dashboard → **brinkadata-db** → Status should be "Available" (green).
2. Go to **brinkadata-backend** → "Environment" tab
3. Ensure `DATABASE_URL` is set and has format:
   ```
   postgresql://user:pass@host:port/dbname
   ```
   (This should auto-populate if you set `fromDatabase` in render.yaml)
4. If missing, manually copy the **Internal Database URL** from brinkadata-db and paste into DATABASE_URL.
5. **Redeploy** the backend service.

---

### ❌ Issue: Frontend loads but says "API connection failed"

**Cause:** Frontend can't reach backend or API_BASE_URL is wrong.

**Fix:**
1. Go to Render Dashboard → **brinkadata-frontend** → "Environment" tab
2. Ensure `API_BASE_URL` matches your backend URL:
   ```
   https://brinkadata-backend.onrender.com
   ```
   (No trailing slash)
3. If wrong, update and **Redeploy** the frontend service.

---

### ❌ Issue: Migration output shows "duplicate column" warnings

**Cause:** Migration ran before on an older schema.

**Fix:** **This is expected and harmless.** The migration is idempotent and skips columns that already exist. As long as you see:

```
[MIGRATE] All migrations complete!
```

at the end, you're good.

---

## 6. Next Steps After Verification

✅ **All checks passed?** Congrats! Your staging environment is live.

### What to do next:

1. **Register a test account:**
   - Open frontend → Sign Up
   - Use a real email (for testing) or a throwaway
   - Verify account creation in backend logs

2. **Run a test analysis:**
   - Enter property details → Click "Analyze"
   - Verify metrics display (NOI, ROI, IRR)
   - Click "Save to Portfolio"
   - Go to Portfolio → Verify saved deal appears

3. **Test plan limits:**
   - Free plan: 25 saved deals
   - Pro plan: 250 saved deals
   - Verify limits enforce correctly

4. **Check security:**
   - Log out → Try accessing `/property/saved` → Should get 401/403
   - Log in again → Verify you can access your own deals
   - Create a second account → Verify tenant isolation (can't see each other's deals)

---

## 7. Quick Reference: All Verification Commands

```powershell
# Set your backend URL
$BACKEND_URL = "https://brinkadata-backend.onrender.com"

# Health check
curl -Uri "$BACKEND_URL/health" -Method GET

# API docs (open in browser or curl)
curl -Uri "$BACKEND_URL/docs" -Method GET

# Version info
curl -Uri "$BACKEND_URL/version" -Method GET

# Confirm auth gate (should fail with 401/403)
curl -Uri "$BACKEND_URL/property/saved" -Method GET
```

**Migration (in Render Shell):**
```bash
python -m backend.migrate
```

---

## 8. When to Re-Run Migration

Run migration again if:
- ✅ You deploy schema changes (new tables, columns, indexes)
- ✅ You restore the database from backup
- ✅ You create a new Render environment (prod, staging-2, etc.)

**Do NOT re-run** for:
- ❌ Code-only changes (no schema changes)
- ❌ Routine redeployments (Render auto-restarts on push)

---

## 9. Production Readiness Checklist

Before going to production:
- [ ] Change plan from `starter` to `standard` or `pro` in render.yaml
- [ ] Change ENV from `staging` to `production` in backend environment
- [ ] Update CORS_ORIGINS to production frontend domain
- [ ] Enable custom domain in Render Dashboard (see RENDER_DEPLOY_GUIDE.md)
- [ ] Set up monitoring/alerts (Render Dashboard → Alerts)
- [ ] Run full regression test suite
- [ ] Verify backups are enabled for brinkadata-db

---

**Questions or issues?** Check RENDER_DEPLOY_GUIDE.md or PRODUCTION_READINESS.md for more details.
