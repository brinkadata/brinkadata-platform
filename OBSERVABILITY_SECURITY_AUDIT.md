# Brinkadata Assets MVP — Observability & Security Audit

**Tag:** `brinkadata-assets-mvp`  
**Audit Date:** January 19, 2026  
**Status:** ⚠️ Action Items Identified

---

## Executive Summary

✅ **PASS:** No JWT tokens or request bodies logged  
⚠️ **WARNING:** Development print statements present in production code  
✅ **PASS:** RBAC enforcement in place  
✅ **PASS:** Tenant isolation guards active  

**Action Required:** Remove debug print statements before production deployment.

---

## A) Logging Security Audit

### Print Statements Found (⚠️ Remove Before Prod)

| File | Line | Statement | Risk | Action |
|------|------|-----------|------|--------|
| `backend/config.py` | 40-42 | Prints token lifetimes | Low | Remove or gate with `if IS_DEV` |
| `backend/main.py` | 904 | `print(f"[REGISTER] Creating user...")` | Medium | Remove or use logger with INFO level |
| `backend/main.py` | 958 | `print(f"[LOGIN] User found...")` | Medium | Remove or use logger with INFO level |
| `backend/main.py` | 961 | `print(f"[LOGIN] Password verification...")` | Low | Remove or use logger with INFO level |
| `backend/auth_context.py` | 177 | `print("[AUTH] Missing user_id...")` | Low | Remove or use logger with WARNING level |
| `backend/migrate_accounts.py` | 130 | `print("[DEV-ONLY] Created default user...")` | Medium | Gate with `if IS_DEV` |

### Recommendations

1. **Replace print() with logging**
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   # Instead of:
   print("[LOGIN] User found")
   
   # Use:
   logger.info("[LOGIN] User authentication initiated", extra={
       "account_id": account_id,
       "event": "auth.login"
   })
   ```

2. **Gate debug output with environment check**
   ```python
   from backend.config import IS_DEV
   
   if IS_DEV:
       print("[DEBUG] Detailed debug info here")
   ```

3. **Never log:**
   - JWT tokens (raw or decoded)
   - Request bodies (may contain passwords, sensitive data)
   - Password hashes
   - Secret keys
   - API keys

---

## B) Error Handling Verification

### RBAC Enforcement ✅

**Property Search Capability**
- File: `backend/routes_property_search.py`
- Enforcement: `@require_capability("property_search")`
- Response: 403 Forbidden if capability missing
- Message: Clear error message returned

**Assets Capability**
- File: `backend/routes_assets.py`
- Enforcement: `@require_capability("manage_assets")`
- Response: 403 Forbidden if capability missing
- Message: Clear error message returned

### Tenant Isolation ✅

**Property Search**
- All queries filter by `account_id`
- Cross-tenant access returns 404 (not 403, to avoid enumeration)

**Assets**
- All queries filter by `account_id`
- Direct access to other tenant's asset returns 404

### HTTP Status Codes

| Scenario | Expected Status | Verified |
|----------|----------------|----------|
| Missing capability | 403 Forbidden | ✅ |
| Cross-tenant access | 404 Not Found | ✅ |
| Invalid input | 422 Unprocessable Entity | ✅ |
| Server error | 500 Internal Server Error | ✅ |
| Unauthenticated | 401 Unauthorized | ✅ |

---

## C) Database Query Safety

### Parameterized Queries ✅

All database queries use SQLAlchemy ORM or parameterized statements:

```python
# ✅ SAFE (parameterized)
cursor.execute(
    "SELECT * FROM assets WHERE account_id = ?",
    (account_id,)
)

# ✅ SAFE (ORM)
db.query(Asset).filter(Asset.account_id == account_id).all()

# ❌ NEVER DO THIS (SQL injection risk)
cursor.execute(f"SELECT * FROM assets WHERE account_id = {account_id}")
```

**Audit Result:** No SQL injection vulnerabilities found.

---

## D) Environment-Specific Configuration

### Current Settings (backend/config.py)

| Setting | Dev | Staging | Prod | Notes |
|---------|-----|---------|------|-------|
| `ENV` | `dev` | `staging` | `prod` | Set via environment variable |
| `SECRET_KEY` | Default fallback | ⚠️ Must set | ⚠️ Must set | Use 32+ byte random key |
| `ACCESS_TOKEN_MINUTES` | 15 | 15 | 15 | Reasonable default |
| `REFRESH_TOKEN_DAYS` | 7 | 7 | 7 | Reasonable default |
| `CORS_ORIGINS` | localhost | + staging URL | + prod URL | ✅ Environment-aware |

### Production Environment Variables (Required)

```bash
# .env (for production)
ENV=prod
SECRET_KEY=<generate-with-openssl-rand-hex-32>
DATABASE_URL=postgresql://user:pass@host:5432/brinkadata
CORS_ORIGINS=https://app.brinkadata.com
LOG_LEVEL=INFO  # NOT DEBUG
```

---

## E) RBAC & Capability Matrix

### Current Capabilities

| Capability | Purpose | Enforced On | Gated By |
|------------|---------|-------------|----------|
| `property_search` | Search property index | `/api/v1/property/search` | `@require_capability` |
| `manage_assets` | CRUD on assets | `/api/v1/assets/*` | `@require_capability` |
| `analyze_property` | (Existing) Run analyzer | `/api/v1/property/analyze` | `@require_capability` |

### Plan-Level Gating

| Plan | `property_search` | `manage_assets` | Notes |
|------|-------------------|-----------------|-------|
| Free | ❌ | ❌ | Not available |
| Pro | ✅ | ✅ | Full access |
| Team | ✅ | ✅ | Full access |
| Enterprise | ✅ | ✅ | Full access |

*(Verify in `backend/features.py` or plan configuration)*

---

## F) Tenant Isolation Checklist

### Backend Routes

| Endpoint | Tenant Filter | Verified |
|----------|---------------|----------|
| `GET /api/v1/property/search` | ✅ `account_id` in query | ✅ |
| `GET /api/v1/assets` | ✅ `account_id` filter | ✅ |
| `POST /api/v1/assets` | ✅ `account_id` from auth | ✅ |
| `GET /api/v1/assets/{id}` | ✅ `account_id` filter | ✅ |
| `DELETE /api/v1/assets/{id}` | ✅ `account_id` filter | ✅ |

### Database Tables

| Table | Tenant Column | Indexed | Verified |
|-------|---------------|---------|----------|
| `assets` | `account_id` | ✅ | ✅ |
| `property_index` | `account_id` | ✅ | ✅ |

---

## G) Frontend Security

### Session State Safety ✅

No direct `st.session_state` assignments after widget render in:
- Property Search page
- Assets page

### API Client ✅

- All requests include auth token
- CORS enabled for frontend origins
- No sensitive data in URLs (uses request bodies)

---

## H) Immediate Action Items (Before Prod Deploy)

### Critical (Must Fix)
1. **Remove debug print statements OR gate with `IS_DEV`**
   - Files: `backend/main.py`, `backend/config.py`, `backend/auth_context.py`
   - Risk: Information leakage, verbose logs in production

2. **Set production environment variables**
   - `ENV=prod`
   - `SECRET_KEY=<secure-random-key>`
   - `LOG_LEVEL=INFO` (NOT `DEBUG`)

### High Priority (Recommended)
3. **Replace print() with logging**
   - Use `logging.getLogger(__name__)` in all modules
   - Configure log level via environment variable
   - Structured logging with JSON format (for log aggregation)

4. **Add request ID middleware** (Future Enhancement)
   - Track requests across logs
   - Helps with debugging in production

### Medium Priority (Nice-to-Have)
5. **Add APM/Observability**
   - Sentry for error tracking
   - Prometheus metrics for API performance
   - Grafana dashboards for monitoring

---

## I) Post-Deploy Monitoring

### What to Watch

| Metric | Alert Threshold | Action |
|--------|----------------|--------|
| Error rate (5xx) | > 1% | Investigate immediately |
| Response time (p95) | > 2 seconds | Check database query performance |
| 403 errors | Spike | Verify RBAC config |
| 404 errors (assets) | Unexpected spike | Check tenant isolation |
| Database connection errors | Any | Check DB health |

### Log Monitoring Queries

```bash
# Watch for 500 errors
tail -f logs/backend.log | grep "500"

# Watch for failed auth
tail -f logs/backend.log | grep "401\|403"

# Watch for database errors
tail -f logs/backend.log | grep "database\|sql"
```

---

## J) Security Best Practices (Ongoing)

### Development
- [ ] Never commit secrets to git (use `.env` and `.gitignore`)
- [ ] Use `pre-commit` hooks to prevent secret leaks
- [ ] Review all print statements before merging

### Deployment
- [ ] Rotate `SECRET_KEY` every 90 days
- [ ] Monitor failed login attempts (rate limiting future enhancement)
- [ ] Keep dependencies updated (run `pip-audit` monthly)

### Operations
- [ ] Backup database daily
- [ ] Test restore process quarterly
- [ ] Review access logs weekly for anomalies

---

## Status Summary

| Area | Status | Blocking? |
|------|--------|-----------|
| JWT/Token Logging | ✅ Pass | No |
| Request Body Logging | ✅ Pass | No |
| RBAC Enforcement | ✅ Pass | No |
| Tenant Isolation | ✅ Pass | No |
| Debug Print Statements | ⚠️ Found | **Yes** (remove before prod) |
| Environment Config | ⚠️ Review | **Yes** (set prod env vars) |
| SQL Injection Safety | ✅ Pass | No |

**Overall Status:** ⚠️ Ready for production AFTER removing debug statements and setting environment variables.

---

## Approval Checklist

- [ ] Debug print statements removed or gated with `IS_DEV`
- [ ] Production environment variables configured
- [ ] `LOG_LEVEL=INFO` (not DEBUG)
- [ ] `SECRET_KEY` is secure random value (32+ bytes)
- [ ] CORS origins include production frontend URL
- [ ] Database backup taken before migration
- [ ] Migration tested on staging replica
- [ ] Smoke tests passed (see PRODUCTION_READINESS.md)

**Sign-off:** _____________ Date: _______
