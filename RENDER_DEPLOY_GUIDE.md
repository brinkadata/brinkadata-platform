# Render Deployment Guide - Brinkadata

## Overview
This guide covers deploying Brinkadata to Render's managed platform with PostgreSQL database, custom domains, and DNS configuration (GoDaddy-safe for Google Workspace mail).

---

## Phase 1: Initial Render Deployment (Staging)

### Prerequisites
- GitHub repo pushed with `render.yaml` in root
- Render account (sign up at https://render.com)

### Steps

1. **Connect Repository to Render**
   - Go to Render Dashboard: https://dashboard.render.com
   - Click "New +" → "Blueprint"
   - Connect your GitHub account
   - Select `Brinkadata` repository
   - Render will detect `render.yaml` automatically

2. **Review and Deploy**
   - Render will show 3 resources:
     - `brinkadata-backend` (Web Service)
     - `brinkadata-frontend` (Web Service)
     - `brinkadata-db` (PostgreSQL Database)
   - Click "Apply" to create all resources
   - Wait 5-10 minutes for initial build and deploy

3. **Run Database Migrations**
   - After backend service is live, open Render Shell:
     - Go to `brinkadata-backend` service in dashboard
     - Click "Shell" tab
     - Run: `python -m backend.migrate`
   - Verify migration success (tables created)

4. **Test Staging Deployment**
   - Backend URL: `https://brinkadata-backend.onrender.com`
   - Frontend URL: `https://brinkadata-frontend.onrender.com`
   - Test basic functionality:
     - Load frontend
     - Analyze a deal (rental/flip/BRRRR)
     - Save to portfolio
     - View portfolio

5. **Update CORS Origins**
   - After first deploy, note actual frontend URL
   - Update backend env var in Render dashboard:
     - Go to `brinkadata-backend` → "Environment"
     - Update `CORS_ORIGINS` to include frontend URL
     - Click "Save Changes" (triggers redeploy)

---

## Phase 2: Custom Domains (Optional)

### Prerequisites
- Domain registered (e.g., `brinkadata.com` via GoDaddy)
- Render services deployed and stable

### Add Custom Domains in Render

1. **Backend Domain**
   - Go to `brinkadata-backend` service → "Settings"
   - Scroll to "Custom Domain"
   - Add: `api.brinkadata.com`
   - Render will provide CNAME target (e.g., `brinkadata-backend.onrender.com`)

2. **Frontend Domain**
   - Go to `brinkadata-frontend` service → "Settings"
   - Add: `app.brinkadata.com`
   - Render will provide CNAME target (e.g., `brinkadata-frontend.onrender.com`)

### Configure DNS in GoDaddy

**CRITICAL: Do NOT change MX records (Google Workspace mail will break)**

Add ONLY these records in GoDaddy DNS Management:

| Type  | Name  | Target                                  | TTL  |
|-------|-------|-----------------------------------------|------|
| CNAME | api   | brinkadata-backend.onrender.com         | 600  |
| CNAME | app   | brinkadata-frontend.onrender.com        | 600  |

**What to AVOID:**
- ❌ Do NOT modify existing MX records
- ❌ Do NOT modify existing TXT records (SPF/DKIM)
- ❌ Do NOT modify A records for root domain
- ✅ ONLY add CNAME records for subdomains

### SSL/TLS Certificate

- Render automatically provisions Let's Encrypt SSL certificates
- Wait 5-10 minutes after DNS propagation
- Verify HTTPS works: `https://api.brinkadata.com`

### Update Backend Environment

After custom domains are active:

1. Go to `brinkadata-backend` → "Environment"
2. Update `CORS_ORIGINS`:
   ```
   https://app.brinkadata.com
   ```
3. Save (triggers redeploy)

4. Go to `brinkadata-frontend` → "Environment"
5. Update `API_BASE_URL`:
   ```
   https://api.brinkadata.com
   ```
6. Save (triggers redeploy)

---

## Phase 3: Production Deployment

### Upgrade Plans (Recommended)
- Database: `starter` → `standard` (better performance, backups)
- Services: `starter` → `standard` (zero-downtime deploys)

### Production Environment Variables

Update backend env vars:

```bash
ENV=prod
SECRET_KEY=<use-render-generated-value>
CORS_ORIGINS=https://app.brinkadata.com,https://www.brinkadata.com
DATABASE_URL=<provided-by-render-database>
```

Update frontend env vars:

```bash
ENV=prod
API_BASE_URL=https://api.brinkadata.com
```

### Enable Auto-Deploy

- Go to each service → "Settings" → "Build & Deploy"
- Enable "Auto-Deploy" for `main` branch
- Every push to `main` will trigger automatic deployment

### Monitoring

- View logs: Service dashboard → "Logs" tab
- Set up alerts: "Settings" → "Notifications"
- Add Render status badge to README (optional)

---

## Phase 4: Rollback and Debugging

### Rollback to Previous Deploy

1. Go to service → "Events" tab
2. Find previous successful deploy
3. Click "Rollback" button
4. Confirm rollback

### Access Database Directly

1. Go to `brinkadata-db` → "Info" tab
2. Copy "External Database URL"
3. Connect via `psql` or GUI client:
   ```bash
   psql <DATABASE_URL>
   ```

### Common Issues

**Migration fails:**
- Run migration manually via Shell: `python -m backend.migrate`
- Check logs for errors

**CORS errors:**
- Verify `CORS_ORIGINS` includes frontend URL
- Check for trailing slashes (avoid them)

**Database connection errors:**
- Verify `DATABASE_URL` env var is set
- Check database is active in Render dashboard

**Custom domain not working:**
- Verify CNAME record in GoDaddy
- Wait 10-15 minutes for DNS propagation
- Check SSL provisioning status in Render

---

## Security Checklist

Before going to production:

- [ ] Rotate `SECRET_KEY` (use Render-generated value)
- [ ] Verify `DATABASE_URL` uses SSL (`?sslmode=require`)
- [ ] Enable "Auto-Deploy" only for `main` branch
- [ ] Set up branch protection rules on GitHub
- [ ] Enable 2FA on Render account
- [ ] Review environment variables (no hardcoded secrets)
- [ ] Test RBAC/auth flows in staging first
- [ ] Set up monitoring alerts (Render notifications)

---

## Cost Estimates (Render Pricing as of 2024)

**Starter Plan (Staging):**
- Database: $7/month
- Backend service: $7/month
- Frontend service: $7/month
- **Total: ~$21/month**

**Standard Plan (Production):**
- Database: $15/month (daily backups, better perf)
- Backend service: $25/month (zero-downtime deploys)
- Frontend service: $25/month
- **Total: ~$65/month**

**Note:** Render has a free tier (750 hours/month), but databases and persistent services require paid plans.

---

## Local Development with PostgreSQL

See `LOCAL_POSTGRES_TESTING.md` for testing against Postgres locally before deploying.

---

## Support

- Render Docs: https://render.com/docs
- Render Support: https://render.com/support
- Brinkadata Issues: [GitHub Issues](https://github.com/your-org/brinkadata/issues)
