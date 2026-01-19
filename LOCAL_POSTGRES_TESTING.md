# Local PostgreSQL Testing - Brinkadata

## Overview
Test your Brinkadata backend against PostgreSQL locally before deploying to Render. This ensures migrations, queries, and data models work correctly with Postgres.

---

## Option 1: Docker (Recommended)

### Prerequisites
- Docker Desktop installed (https://www.docker.com/products/docker-desktop/)

### Steps

1. **Start PostgreSQL Container**
   ```powershell
   docker run --name brinkadata-postgres `
     -e POSTGRES_PASSWORD=devpassword `
     -e POSTGRES_USER=devuser `
     -e POSTGRES_DB=brinkadata_dev `
     -p 5432:5432 `
     -d postgres:15
   ```

2. **Set Environment Variable**
   ```powershell
   $env:DATABASE_URL = "postgresql://devuser:devpassword@localhost:5432/brinkadata_dev"
   ```

3. **Run Migrations**
   ```powershell
   python -m backend.migrate
   ```

4. **Start Backend**
   ```powershell
   uvicorn backend.main:app --reload
   ```

5. **Test API**
   - Open browser: http://localhost:8000/docs
   - Test endpoints (analyze, save, portfolio)

6. **Stop Container (when done)**
   ```powershell
   docker stop brinkadata-postgres
   docker rm brinkadata-postgres
   ```

---

## Option 2: Native PostgreSQL (Windows)

### Prerequisites
- PostgreSQL 15+ installed (https://www.postgresql.org/download/windows/)
- `psql` in PATH

### Steps

1. **Create Database**
   ```powershell
   psql -U postgres
   ```
   Then in psql:
   ```sql
   CREATE DATABASE brinkadata_dev;
   CREATE USER devuser WITH PASSWORD 'devpassword';
   GRANT ALL PRIVILEGES ON DATABASE brinkadata_dev TO devuser;
   \q
   ```

2. **Set Environment Variable**
   ```powershell
   $env:DATABASE_URL = "postgresql://devuser:devpassword@localhost:5432/brinkadata_dev"
   ```

3. **Run Migrations**
   ```powershell
   python -m backend.migrate
   ```

4. **Start Backend**
   ```powershell
   uvicorn backend.main:app --reload
   ```

5. **Verify Tables**
   ```powershell
   psql -U devuser -d brinkadata_dev
   ```
   Then in psql:
   ```sql
   \dt
   SELECT * FROM accounts LIMIT 5;
   \q
   ```

---

## Option 3: Cloud Database (Render Free Tier)

Render offers free PostgreSQL databases (limited capacity, good for testing).

### Steps

1. **Create Free Database**
   - Go to https://dashboard.render.com
   - Click "New +" → "PostgreSQL"
   - Select "Free" plan
   - Name: `brinkadata-dev-test`
   - Create database

2. **Copy External Connection String**
   - Go to database → "Info" tab
   - Copy "External Database URL"

3. **Set Environment Variable**
   ```powershell
   $env:DATABASE_URL = "postgresql://user:password@host.render.com/dbname"
   ```

4. **Run Migrations**
   ```powershell
   python -m backend.migrate
   ```

5. **Start Backend**
   ```powershell
   uvicorn backend.main:app --reload
   ```

---

## Switching Between SQLite and PostgreSQL

### Use SQLite (default for local dev)
```powershell
Remove-Item Env:\DATABASE_URL
uvicorn backend.main:app --reload
```

### Use PostgreSQL
```powershell
$env:DATABASE_URL = "postgresql://devuser:devpassword@localhost:5432/brinkadata_dev"
uvicorn backend.main:app --reload
```

The backend automatically detects which database to use based on `DATABASE_URL` environment variable.

---

## Verifying PostgreSQL Mode

When starting backend, check console output:

**PostgreSQL mode:**
```
[DB] Using PostgreSQL (localhost)
[MIGRATE] Running PostgreSQL migrations...
```

**SQLite mode:**
```
[DB] Using SQLite (local dev mode)
[MIGRATE] Running SQLite migrations...
```

---

## Common Issues

### "psycopg2" not installed
```powershell
pip install psycopg2-binary
```

### Connection refused (Docker)
- Verify container is running: `docker ps`
- Check port 5432 is not in use: `netstat -an | Select-String 5432`

### Permission denied
- Grant privileges in psql:
  ```sql
  GRANT ALL PRIVILEGES ON DATABASE brinkadata_dev TO devuser;
  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO devuser;
  ```

### Migrations fail
- Drop and recreate database:
  ```sql
  DROP DATABASE brinkadata_dev;
  CREATE DATABASE brinkadata_dev;
  ```
- Re-run migrations: `python -m backend.migrate`

---

## Manual Testing Checklist

After connecting to Postgres:

- [ ] Run migrations successfully
- [ ] Start backend without errors
- [ ] Create test account via API
- [ ] Analyze a deal (rental/flip/BRRRR)
- [ ] Save deal to portfolio
- [ ] Load portfolio (verify count)
- [ ] Delete deal to trash
- [ ] View trash
- [ ] Restore from trash
- [ ] Test scenario compare (A/B/C)
- [ ] Export portfolio CSV (Pro+ feature)

---

## Performance Notes

**PostgreSQL advantages:**
- Better concurrent writes (multi-user scenarios)
- Full-text search (future features)
- JSON operators (native JSONB support)
- Production-ready scaling

**SQLite advantages:**
- Zero configuration
- Single file database
- Perfect for local dev
- No external dependencies

**Recommendation:**
- Use SQLite for solo development
- Use PostgreSQL when testing multi-tenant features
- Always test against Postgres before deploying to Render

---

## Database Inspection (GUI Tools)

**pgAdmin (Free, Windows/Mac/Linux):**
- Download: https://www.pgadmin.org/
- Connect with credentials from DATABASE_URL

**DBeaver (Free, cross-platform):**
- Download: https://dbeaver.io/
- Supports PostgreSQL, SQLite, and more

**TablePlus (Paid, Mac/Windows):**
- Download: https://tableplus.com/
- Clean UI, good for quick queries

---

## Clean Up

### Docker
```powershell
docker stop brinkadata-postgres
docker rm brinkadata-postgres
docker volume prune  # Remove unused volumes
```

### Native PostgreSQL
```sql
DROP DATABASE brinkadata_dev;
DROP USER devuser;
```

### Render Free Database
- Go to Render dashboard → Database → "Settings"
- Click "Delete Database"

---

## Next Steps

Once local Postgres testing is successful:
1. Commit code changes
2. Push to GitHub
3. Deploy to Render staging (see `RENDER_DEPLOY_GUIDE.md`)
4. Run migrations on Render via Shell
5. Test staging deployment
6. Promote to production

---

## Support

- PostgreSQL Docs: https://www.postgresql.org/docs/
- Docker PostgreSQL: https://hub.docker.com/_/postgres
- SQLAlchemy Docs: https://docs.sqlalchemy.org/
