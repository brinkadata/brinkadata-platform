# ---------------------------------------------------------
# backend/main.py
# Brinkadata - Property Intelligence Backend
#
# Run: uvicorn backend.main:app --reload (from repo root)
#
# - FastAPI + SQLite
# - /property/analyze : compute deal metrics + IRR / NPV (unlevered)
#   + flip metrics (ARV, flip profit, profit per month)
# - /property/save    : save deal to portfolio
# - /property/saved   : list saved deals
# - /property/delete  : delete to Trash
# - /property/trash   : view Trash
# - /property/trash/restore : restore from Trash
# ---------------------------------------------------------

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path as FsPath
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Path, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# New imports for auth and models
import base64
import hashlib
import jwt
import secrets
import uuid

# Import local modules (robust fallback for different run contexts)
try:
    from backend.models import (
        User,
        Account,
        Plan,
        Subscription,
        Affiliate,
        Referral,
        Scenario,
        UserRole,
        PlanName,
    )
    from backend.features import check_usage_limit, get_account_plan, get_usage_stats, check_feature_access, get_limit, UsageLimitError, FeatureNotAllowedError, require_feature, get_plan_features
    from backend.config import (
        SECRET_KEY,
        ALGORITHM,
        DATABASE_PATH,
        ACCESS_TOKEN_MINUTES,
        REFRESH_TOKEN_DAYS,
        RESUME_CODE_MINUTES,
        CORS_ORIGINS,
        IS_DEV,
        IS_PROD,
    )
    # Import auth context primitives (breaks circular import with dependencies.py)
    from backend.auth_context import AuthContext, require_auth_context, get_db, security, verify_token
    # Phase 2: Tenant Guardrails
    from backend.tenant import require_account_id, assert_rows_scoped, assert_row_scoped, execute_scoped
    # Phase 3: RBAC + Entitlements
    from backend.authz import (
        require_write_access,
        require_admin,
        require_owner,
        require_pro_plan,
        get_plan_limits,
        check_usage_against_limit,
        require_feature_access,
        Capability,
    )
    # Phase 3: Capability enforcement
    from backend.dependencies import require_capability
    # Phase 3: RBAC capability introspection
    from backend.rbac import effective_capabilities
except ModuleNotFoundError:
    from models import (
        User,
        Account,
        Plan,
        Subscription,
        Affiliate,
        Referral,
        Scenario,
        UserRole,
        PlanName,
    )
    from features import check_usage_limit, get_account_plan, get_usage_stats, check_feature_access, get_limit, UsageLimitError, FeatureNotAllowedError, require_feature, get_plan_features
    from config import (
        SECRET_KEY,
        ALGORITHM,
        DATABASE_PATH,
        ACCESS_TOKEN_MINUTES,
        REFRESH_TOKEN_DAYS,
        RESUME_CODE_MINUTES,
        CORS_ORIGINS,
        IS_DEV,
        IS_PROD,
    )
    # Import auth context primitives (breaks circular import with dependencies.py)
    from auth_context import AuthContext, require_auth_context, get_db, security, verify_token
    # Phase 2: Tenant Guardrails
    from tenant import require_account_id, assert_rows_scoped, assert_row_scoped, execute_scoped
    # Phase 3: RBAC + Entitlements
    from authz import (
        require_write_access,
        require_admin,
        require_owner,
        require_pro_plan,
        get_plan_limits,
        check_usage_against_limit,
        require_feature_access,
        Capability,
    )
    # Phase 3: Capability enforcement
    from dependencies import require_capability
    # Phase 3: RBAC capability introspection
    from rbac import effective_capabilities

# --------------------------------------------------------------------
# Token Utilities (for refresh tokens)
# --------------------------------------------------------------------

def generate_refresh_token() -> str:
    """Generate a high-entropy refresh token (not logged)."""
    return secrets.token_urlsafe(48)

def hash_token(token: str) -> str:
    """Hash a token for secure storage (SHA-256)."""
    return hashlib.sha256(token.encode()).hexdigest()

def verify_token_hash(token: str, token_hash: str) -> bool:
    """Verify a token against its hash."""
    return hash_token(token) == token_hash

def generate_resume_code() -> str:
    """Generate a short, human-readable resume code (8-10 chars base32)."""
    # Generate 6 random bytes (48 bits) -> base32 encodes to ~10 chars
    random_bytes = secrets.token_bytes(6)
    code = base64.b32encode(random_bytes).decode('ascii').rstrip('=')  # Remove padding
    # Insert hyphen for readability (e.g., ABCD-EFGH)
    if len(code) >= 8:
        return f"{code[:4]}-{code[4:]}"
    return code

# Plan configuration helper (used by /account/plans)
def get_plan_config(plan: PlanName) -> Dict[str, Any]:
    """Return display config for a plan tier.

    NOTE: Limits are sourced from features.get_limit so they stay consistent
    with enforcement elsewhere. This function only supports the UI/API payload.
    """
    price_map = {
        PlanName.free: 0.0,
        PlanName.pro: 29.99,
        PlanName.team: 99.99,
        PlanName.enterprise: 299.99,
    }

    # Feature bullets are intentionally human-readable for the Plans UI.
    base_features = [
        "Deal analysis (Rental / Flip / BRRRR)",
        "Portfolio + filtering",
        "Trash (7-day retention) + restore",
    ]

    pro_features = base_features + [
        "IRR / NPV metrics",
        "CSV export",
        "Presets",
        "Scenario compare (A/B/C)",
    ]

    team_features = pro_features + [
        "Team accounts + roles",
        "Usage tracking",
    ]

    enterprise_features = team_features + [
        "Enterprise support",
        "Advanced API access (as enabled)",
    ]

    feature_map = {
        PlanName.free: base_features,
        PlanName.pro: pro_features,
        PlanName.team: team_features,
        PlanName.enterprise: enterprise_features,
    }

    return {
        "price_monthly": float(price_map.get(plan, 0.0)),
        "features": feature_map.get(plan, base_features),
        "limits": {
            "saved_deals": get_plan_features(1).get("max_saved_deals", 25),  # Use dummy account_id for plan config
            "scenarios": get_plan_features(1).get("max_scenarios", 3),
        },
    }


# Use canonical absolute path for database (from config)
DB_PATH = str(FsPath(__file__).resolve().parent / DATABASE_PATH)

# Note: security, get_db, verify_token, AuthContext, and require_auth_context
# are now imported from backend.auth_context to break circular import

# ---------------------------------------------------------
# DB helpers
# ---------------------------------------------------------

def get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return set of column names for a table using PRAGMA table_info."""
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in cur.fetchall()}
    except Exception:
        return set()


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl_fragment: str) -> bool:
    """Add column to table if missing. Returns True if migration applied, False if already exists.
    
    Args:
        conn: SQLite connection
        table_name: Name of table to alter
        column_name: Name of column to add
        ddl_fragment: Column definition (e.g., 'INTEGER', 'TEXT DEFAULT NULL')
    
    Returns:
        True if column was added, False if it already existed
    """
    columns = get_table_columns(conn, table_name)
    if column_name in columns:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_fragment}")
        conn.commit()
        print(f"[MIGRATION] Added column {table_name}.{column_name} ({ddl_fragment})")
        return True
    except sqlite3.OperationalError as e:
        # Column might exist in a race condition, or table doesn't exist
        if "duplicate column" not in str(e).lower():
            print(f"[MIGRATION] Warning: Could not add {table_name}.{column_name}: {e}")
        return False


def ensure_users_columns(conn, cur) -> None:
    """Ensure users table has account_id and is_active columns for migration safety."""
    ensure_column(conn, "users", "account_id", "INTEGER")
    ensure_column(conn, "users", "is_active", "BOOLEAN DEFAULT 1")


def ensure_saved_properties_columns(conn, cur) -> None:
    """Ensure saved_properties table has user_id column for migration safety."""
    ensure_column(conn, "saved_properties", "user_id", "INTEGER")
    
    # TASK 2: Multi-tenancy hardening
    # Ensure account_id is NOT NULL (backfill legacy rows to account 1 in dev)
    columns = get_table_columns(conn, "saved_properties")
    if "account_id" in columns:
        try:
            # Backfill NULL account_id to default account (dev-only pattern)
            cur.execute("UPDATE saved_properties SET account_id = 1 WHERE account_id IS NULL")
            if cur.rowcount > 0:
                print(f"[MIGRATION] Backfilled {cur.rowcount} saved_properties rows with account_id=1 (dev data)")
            conn.commit()
        except Exception as e:
            print(f"[MIGRATION] Warning: Could not backfill saved_properties.account_id: {e}")
    
    # Create indexes for efficient tenant filtering
    cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_properties_account_id ON saved_properties(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_properties_account_created ON saved_properties(account_id, created_at)")
    print("[MIGRATION] Ensured indexes on saved_properties(account_id, created_at)")


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()

    # Saved properties table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_properties (
            account_id INTEGER DEFAULT 1,
            property_name TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            strategy TEXT,
            investor_profile TEXT,

            purchase_price REAL,
            rehab_budget REAL,
            monthly_rent REAL,
            hold_years REAL,

            estimated_roi REAL,
            cashflow_per_month REAL,
            cap_rate REAL,
            coc_return REAL,
            noi REAL,
            dscr REAL,
            total_investment REAL,

            irr_unlevered REAL,
            npv_unlevered REAL,

            arv REAL,
            rehab_months REAL,
            holding_months REAL,
            holding_costs_monthly REAL,
            selling_costs_pct REAL,
            flip_profit REAL,
            profit_per_month REAL,

            deal_grade TEXT,
            risk_level TEXT,
            tags_json TEXT,

            created_at TEXT
        )
        """
    )

    # Ensure saved_properties has user_id column for legacy DB compatibility
    ensure_saved_properties_columns(conn, cur)

    # Trash table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trashed_properties (
            trash_id INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_row_json TEXT,
            deleted_at TEXT
        )
        """
    )

    # Migration: Add account_id to trashed_properties for efficient filtering (idempotent)
    ensure_column(conn, "trashed_properties", "account_id", "INTEGER")
    
    # TASK 2: Multi-tenancy hardening for trashed_properties
    # Backfill account_id from JSON for legacy rows (dev-only)
    cur.execute("SELECT trash_id, saved_row_json FROM trashed_properties WHERE account_id IS NULL")
    legacy_trash = cur.fetchall()
    for row in legacy_trash:
        trash_id = row["trash_id"]
        saved_json = row["saved_row_json"] or "{}"
        try:
            saved = json.loads(saved_json)
            account_id = saved.get("account_id", 1)  # Default to account 1 for dev
            cur.execute("UPDATE trashed_properties SET account_id = ? WHERE trash_id = ?", (account_id, trash_id))
        except Exception:
            cur.execute("UPDATE trashed_properties SET account_id = 1 WHERE trash_id = ?", (trash_id,))
    if legacy_trash:
        print(f"[MIGRATION] Backfilled {len(legacy_trash)} trashed_properties rows with account_id")
        conn.commit()
    
    # Create indexes for efficient tenant filtering
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trashed_properties_account_id ON trashed_properties(account_id)")
    print("[MIGRATION] Ensured indexes on trashed_properties(account_id)")

    # Scenarios table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            slot TEXT NOT NULL CHECK (slot IN ('A', 'B', 'C')),
            label TEXT,
            metrics_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, property_id, slot)
        )
        """
    )
    
    # TASK 2: Multi-tenancy indexes for scenarios
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_account_property ON scenarios(account_id, property_id)")
    print("[MIGRATION] Ensured indexes on scenarios(account_id, property_id)")

    # Auth sessions table (for refresh token rotation)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT NULL,
            user_agent TEXT NULL,
            ip TEXT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    # Indexes for auth_sessions (idempotent)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_account_id ON auth_sessions(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)")

    # Resume codes table (for secure session resumption without browser JWT persistence)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS resume_codes (
            code TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT NULL,
            FOREIGN KEY (session_id) REFERENCES auth_sessions (id)
        )
        """
    )

    # Index for resume_codes (idempotent)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_resume_codes_expires_at ON resume_codes(expires_at)")

    # Account management tables
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            account_id INTEGER,
            role TEXT DEFAULT 'member',
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    ensure_users_columns(conn, cur)

    # Ensure unique index on email (idempotent migration)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS account_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(account_id, user_id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price_monthly REAL NOT NULL,
            max_saved_deals INTEGER DEFAULT 10,
            max_scenarios INTEGER DEFAULT 3,
            features_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            stripe_subscription_id TEXT,
            current_period_start TEXT,
            current_period_end TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (plan_id) REFERENCES plans (id)
        )
        """
    )
    
    # Create unique index on account_id to ensure one subscription per account
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_account_unique ON subscriptions(account_id)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS affiliates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            referral_code TEXT UNIQUE NOT NULL,
            commission_rate REAL DEFAULT 0.1,
            total_earned REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            affiliate_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL,
            referred_account_id INTEGER NOT NULL,
            commission_amount REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (affiliate_id) REFERENCES affiliates (id),
            FOREIGN KEY (referred_user_id) REFERENCES users (id),
            FOREIGN KEY (referred_account_id) REFERENCES accounts (id)
        )
        """
    )

    # Ensure critical columns for plan management and feature gating
    ensure_column(conn, "accounts", "plan", "TEXT DEFAULT 'free'")
    ensure_column(conn, "subscriptions", "plan_name", "TEXT DEFAULT 'free'")
    
    # TASK 2 & TASK 5: Stripe subscription fields for SaaS billing
    ensure_column(conn, "accounts", "stripe_customer_id", "TEXT")
    ensure_column(conn, "accounts", "stripe_subscription_id", "TEXT")
    ensure_column(conn, "subscriptions", "stripe_subscription_id", "TEXT")
    print("[MIGRATION] Ensured Stripe fields on accounts and subscriptions")
    
    # Subscription-aware entitlements: add new fields to subscriptions table
    ensure_column(conn, "subscriptions", "provider", "TEXT DEFAULT 'manual'")
    ensure_column(conn, "subscriptions", "provider_customer_id", "TEXT")
    ensure_column(conn, "subscriptions", "provider_subscription_id", "TEXT")
    ensure_column(conn, "subscriptions", "cancel_at_period_end", "INTEGER DEFAULT 0")
    ensure_column(conn, "subscriptions", "updated_at", "TEXT")
    print("[MIGRATION] Ensured subscription entitlement fields")
    
    # Ensure every account has exactly one subscription row (idempotent)
    cur.execute("""
        INSERT OR IGNORE INTO subscriptions (
            account_id, plan_id, status, plan_name, provider, 
            current_period_start, current_period_end, created_at
        )
        SELECT 
            a.id,
            0 AS plan_id,  -- Placeholder (can be updated to real plan_id later)
            'active' AS status,
            COALESCE(a.plan, 'free') AS plan_name,
            'manual' AS provider,
            datetime('now') AS current_period_start,
            datetime('now', '+1 year') AS current_period_end,
            datetime('now') AS created_at
        FROM accounts a
        WHERE NOT EXISTS (
            SELECT 1 FROM subscriptions s WHERE s.account_id = a.id
        )
    """)
    
    if cur.rowcount > 0:
        print(f"[MIGRATION] Created {cur.rowcount} default subscription(s) for existing accounts")
        conn.commit()

    # Assets table for Property Search + Assets features
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            name TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_account_id ON assets(account_id)")
    print("[MIGRATION] Ensured assets table and indexes")

    # Search properties cache (for MVP: stores property search results)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS search_properties_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            beds INTEGER,
            baths REAL,
            sqft INTEGER,
            est_price REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_search_cache_city_state ON search_properties_cache(city, state)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_search_cache_zip ON search_properties_cache(zip_code)")
    print("[MIGRATION] Ensured search_properties_cache table and indexes")

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------
app = FastAPI(title="Brinkadata Backend", version="0.1")

# CORS configuration from config module
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if IS_PROD else ["*"],  # Restrict origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ---------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------
def safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def to_percent(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return x * 100.0


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_access_token(data: dict) -> str:
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


# Note: verify_token is imported from backend.auth_context


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    # Get user and account info from database
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, email, role, account_id FROM users WHERE id = ?", (user_id,))
    user_row = cur.fetchone()
    conn.close()
    
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {
        "user_id": user_row["id"],
        "email": user_row["email"],
        "role": user_row["role"],
        "account_id": user_row["account_id"],
        "session_id": payload.get("session_id")  # May be None for older tokens
    }


# Note: AuthContext and require_auth_context are imported from backend.auth_context


# ---------------------------------------------------------
# TASK 3: Row-level tenant isolation helper
# ---------------------------------------------------------
def require_row_owned(cur: sqlite3.Cursor, table: str, row_id: int, account_id: int) -> sqlite3.Row:
    """
    Fetch a row and enforce tenant ownership.
    Returns the row if owned by account_id, raises 404 otherwise.
    This prevents cross-tenant access and information leakage.
    """
    cur.execute(f"SELECT * FROM {table} WHERE rowid = ? AND account_id = ?", (row_id, account_id))
    row = cur.fetchone()
    if not row:
        print(f"[SECURITY] Row access denied: table={table}, rowid={row_id}, account_id={account_id}")
        raise HTTPException(status_code=404, detail="Not found")
    return row


# ---------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------
class AnalyzeRequest(BaseModel):
    property_name: str
    city: str
    state: str
    zip_code: Optional[str] = None

    purchase_price: float
    rehab_budget: float
    monthly_rent: float
    hold_years: float

    strategy: str = "rental"
    investor_profile: str = "balanced"
    notes: Optional[str] = None

    # Operating assumptions
    vacancy_rate: Optional[float] = 0.05
    op_ex_pct_of_rent: Optional[float] = 0.35
    op_ex_fixed_monthly: Optional[float] = 0.0
    capex_reserves_pct: Optional[float] = 0.05

    # Financing (optional)
    down_payment_pct: Optional[float] = None
    interest_rate_annual: Optional[float] = None
    loan_term_years: Optional[float] = None


class AnalyzeResponse(BaseModel):
    deal_grade: str
    risk_level: str
    summary: str

    estimated_roi: float
    cashflow_per_month: float
    cap_rate: Optional[float] = None
    coc_return: Optional[float] = None
    payback_years: Optional[float] = None
    projected_total_profit: Optional[float] = None
    total_investment: Optional[float] = None

    noi_annual: Optional[float] = None
    op_ex_annual: Optional[float] = None
    vacancy_loss_annual: Optional[float] = None
    capex_reserves_annual: Optional[float] = None
    break_even_occupancy: Optional[float] = None
    dscr: Optional[float] = None
    debt_service_annual: Optional[float] = None

    irr_unlevered: Optional[float] = None
    npv_unlevered: Optional[float] = None

    arv: Optional[float] = None
    rehab_months: Optional[float] = None
    holding_months: Optional[float] = None
    holding_costs_monthly: Optional[float] = None
    selling_costs_pct: Optional[float] = None
    flip_profit: Optional[float] = None
    profit_per_month: Optional[float] = None

    tags: Optional[List[str]] = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    account_name: str = "My Account"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    user: Dict[str, Any]


class ScenarioSaveRequest(BaseModel):
    property_id: int
    slot: str  # "A", "B", "C"
    label: Optional[str] = None
    metrics: Dict[str, Any]


class ScenarioClearRequest(BaseModel):
    property_id: int
    slot: str  # "A", "B", "C"


# ============================================================================
# API ENDPOINT CLASSIFICATION & SECURITY MODEL
# ============================================================================
#
# All endpoints are classified into three security tiers:
#
# [PUBLIC] - No authentication required
#   • /health - Health check
#   • /auth/register - User registration
#   • /auth/login - User login
#   • /auth/refresh - Token refresh (uses refresh token, not access token)
#   • /auth/resume - Session resume (uses resume code, not access token)
#   • /account/plans - Public plan information (no auth needed)
#
# [AUTH_ONLY] - Requires authentication but not tenant-scoped
#   • /auth/logout - Revoke session
#   • /auth/resume/request - Request resume code
#   • /auth/capabilities - Get user's effective capabilities
#   • /account/info - Get account info for current user
#   • /account/upgrade - Upgrade plan for current account
#
# [TENANT_SCOPED] - Requires authentication AND tenant isolation
#   All operations must filter by account_id (and user_id where applicable).
#   IDs from client MUST be verified against current account before use.
#   Return 404 (not 403) when ID doesn't exist for account (prevents enumeration).
#
#   Property operations (require asset:manage capability for mutations):
#     • /property/analyze - Analyze deal (read-only, but account-scoped for IRR/NPV gating)
#     • /property/save - Save property to portfolio [RBAC: asset:manage]
#     • /property/saved - List saved properties for account
#     • /property/delete - Move property to trash [RBAC: asset:manage]
#     • /property/trash - List trashed properties for account
#     • /property/trash/restore - Restore from trash [RBAC: asset:manage]
#
#   Scenario operations (require asset:manage capability):
#     • /scenario/save - Save scenario comparison [RBAC: asset:manage]
#     • /scenario/list/{property_id} - List scenarios for property
#     • /scenario/clear - Clear scenario slot [RBAC: asset:manage]
#
#   Admin operations (DEV-only, require authentication):
#     • /admin/set_plan - Set plan for any account [DEV-only, gated by IS_DEV]
#     • /admin/set_role - Set role for any user [DEV-only, gated by IS_DEV]
#     • /admin/accounts - List all accounts [DEV-only, gated by IS_DEV]
#
# ENFORCEMENT RULES:
# 1. All TENANT_SCOPED endpoints MUST use AuthContext from require_auth_context()
# 2. Never trust account_id from request payload for writes
# 3. All DB queries MUST include "WHERE account_id = ?" for tenant isolation
# 4. When client provides entity ID, verify it exists for current account (404 if not)
# 5. Mutations require appropriate capability (enforced via require_capability() dependency)
# 6. Read-only users (role=read_only) cannot perform mutations even on Pro plan
#
# ============================================================================

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# Auth endpoints
@app.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    conn = get_db()
    cur = conn.cursor()

    # Capture and normalize email
    raw_email = req.email
    email_norm = raw_email.strip().lower()
    print(f"[REGISTER] raw_email={repr(raw_email)}, email_norm={repr(email_norm)}")

    # Create account FIRST (before user, so we have account_id to set on user)
    print(f"[REGISTER] Creating account: {repr(req.account_name)}")
    cur.execute("INSERT INTO accounts (name) VALUES (?)", (req.account_name,))
    account_id = cur.lastrowid
    print(f"[REGISTER] Account created with id={account_id}")

    # Now create user with account_id set
    pw_hash = hash_password(req.password)
    print(f"[REGISTER] Creating user with hashed password (length={len(pw_hash)})")
    print(f"[REGISTER] About to INSERT user with email={repr(email_norm)}, account_id={account_id}")
    try:
        cur.execute(
            "INSERT INTO users (email, password_hash, role, account_id) VALUES (?, ?, ?, ?)",
            (email_norm, pw_hash, str(UserRole.owner.value), account_id),
        )
        user_id = cur.lastrowid
        print(f"[REGISTER] User created with id={user_id}")
    except sqlite3.IntegrityError as e:
        error_msg = str(e).lower()
        print(f"[REGISTER] IntegrityError caught: {e}, email={repr(email_norm)}")
        conn.close()
        # Distinguish between email duplicate and other integrity errors
        if "email" in error_msg or "unique" in error_msg:
            raise HTTPException(status_code=400, detail="Email already registered")
        else:
            raise HTTPException(status_code=500, detail="Registration failed due to server configuration error")

    # Update account owner_id now that we have user_id
    print(f"[REGISTER] Updating account {account_id} with owner_id={user_id}")
    cur.execute("UPDATE accounts SET owner_id = ? WHERE id = ?", (user_id, account_id))

    # Link membership
    cur.execute(
        "INSERT INTO account_memberships (account_id, user_id, role) VALUES (?, ?, ?)",
        (account_id, user_id, str(UserRole.owner.value)),
    )

    conn.commit()
    conn.close()

    access_token = create_access_token({"sub": str(user_id), "email": email_norm, "account_id": account_id})
    return TokenResponse(access_token=access_token, user={"id": user_id, "email": email_norm, "role": str(UserRole.owner.value), "account_id": account_id})


@app.post("/auth/login")
def login(req: LoginRequest):
    # Normalize email
    email_norm = req.email.strip().lower()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email_norm,))
    row = cur.fetchone()

    # Debug logging (non-sensitive)
    if not row:
        conn.close()
        print("[LOGIN] User not found by email")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Safe access to row data
    row_dict = dict(row)
    print(f"[LOGIN] User found: id={row_dict.get('id', 'unknown')}, has_password_hash={bool(row_dict.get('password_hash'))}")
    
    password_valid = verify_password(req.password, row["password_hash"])
    print(f"[LOGIN] Password verification result: {password_valid}")
    
    if not password_valid:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = User(**row_dict)
    
    # Create refresh token and session
    session_id = str(uuid.uuid4())
    refresh_token = generate_refresh_token()
    refresh_token_hash = hash_token(refresh_token)
    
    # Create access token (short-lived) with session_id
    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "account_id": user.account_id,
        "session_id": session_id
    })
    
    now = datetime.utcnow()
    expires_at = now + timedelta(days=REFRESH_TOKEN_DAYS)
    
    # Store session in DB
    cur.execute(
        """
        INSERT INTO auth_sessions (id, user_id, account_id, refresh_token_hash, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, user.id, user.account_id, refresh_token_hash, now.isoformat(), expires_at.isoformat())
    )
    conn.commit()
    conn.close()
    
    print(f"[LOGIN] Session created successfully: user_id={user.id}, account_id={user.account_id}, session_id={session_id}")
    
    # Safely extract role value (handles both Enum and string)
    role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
    
    return {
        "access_token": access_token,
        "user": {"id": user.id, "email": user.email, "role": role_value, "account_id": user.account_id},
        "session_id": session_id,
        "refresh_token": refresh_token
    }


@app.post("/auth/refresh")
def refresh_token(req: dict):
    """Refresh access token using refresh token with rotation."""
    session_id = req.get("session_id")
    refresh_token = req.get("refresh_token")
    
    if not session_id or not refresh_token:
        raise HTTPException(status_code=400, detail="Missing session_id or refresh_token")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get session
    cur.execute("SELECT * FROM auth_sessions WHERE id = ?", (session_id,))
    session = cur.fetchone()
    
    if not session:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid session")
    
    session_dict = dict(session)
    
    # Check if session is revoked
    if session_dict.get("revoked_at"):
        conn.close()
        raise HTTPException(status_code=401, detail="Session revoked")
    
    # Check if session is expired
    expires_at = datetime.fromisoformat(session_dict["expires_at"])
    if datetime.utcnow() > expires_at:
        conn.close()
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Verify refresh token hash
    if not verify_token_hash(refresh_token, session_dict["refresh_token_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # Get user info
    user_id = session_dict["user_id"]
    account_id = session_dict["account_id"]
    
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_row = cur.fetchone()
    
    if not user_row:
        conn.close()
        raise HTTPException(status_code=401, detail="User not found")
    
    user_dict = dict(user_row)
    
    # Rotate refresh token (generate new one)
    new_refresh_token = generate_refresh_token()
    new_refresh_token_hash = hash_token(new_refresh_token)
    
    # Update session with new refresh token hash
    cur.execute(
        "UPDATE auth_sessions SET refresh_token_hash = ? WHERE id = ?",
        (new_refresh_token_hash, session_id)
    )
    conn.commit()
    conn.close()
    
    # Create new access token
    new_access_token = create_access_token({
        "sub": str(user_id),
        "email": user_dict["email"],
        "account_id": account_id
    })
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "user": {
            "id": user_id,
            "email": user_dict["email"],
            "account_id": account_id
        }
    }


@app.post("/auth/logout")
def logout(req: dict):
    """Revoke a session (idempotent)."""
    session_id = req.get("session_id")
    refresh_token = req.get("refresh_token")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get session
    cur.execute("SELECT * FROM auth_sessions WHERE id = ?", (session_id,))
    session = cur.fetchone()
    
    if session:
        session_dict = dict(session)
        
        # Verify refresh token if provided (optional for logout)
        if refresh_token and not verify_token_hash(refresh_token, session_dict["refresh_token_hash"]):
            conn.close()
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Revoke session (idempotent)
        if not session_dict.get("revoked_at"):
            now = datetime.utcnow()
            cur.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE id = ?",
                (now.isoformat(), session_id)
            )
            conn.commit()
    
    conn.close()
    return {"status": "ok"}


@app.post("/auth/resume/request")
def request_resume_code(current_user: dict = Depends(get_current_user)):
    """Generate a short-lived resume code for current session.
    
    Requires valid Bearer token. Returns a resume code that can be used
    to recreate the session after browser refresh (without storing JWT).
    """
    user_id = current_user.get("user_id")
    account_id = current_user.get("account_id")
    session_id = current_user.get("session_id")
    
    conn = get_db()
    cur = conn.cursor()
    
    # If session_id not in token (older tokens), look up active session from DB
    if not session_id:
        cur.execute(
            """
            SELECT * FROM auth_sessions 
            WHERE user_id = ? AND account_id = ? AND revoked_at IS NULL 
            ORDER BY created_at DESC 
            LIMIT 1
            """,
            (user_id, account_id)
        )
        session = cur.fetchone()
        if session:
            session_id = session["id"]
            print(f"[RESUME] Found active session via DB lookup: user_id={user_id}, account_id={account_id}, session_id={session_id}")
        else:
            conn.close()
            print(f"[RESUME] No active session found: user_id={user_id}, account_id={account_id}")
            raise HTTPException(status_code=409, detail="No active session; please login again")
    
    # Verify session exists and get refresh token hash
    cur.execute("SELECT * FROM auth_sessions WHERE id = ?", (session_id,))
    session = cur.fetchone()
    
    if not session:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid session")
    
    session_dict = dict(session)
    
    # Check if session is revoked or expired
    if session_dict.get("revoked_at"):
        conn.close()
        raise HTTPException(status_code=401, detail="Session revoked")
    
    expires_at = datetime.fromisoformat(session_dict["expires_at"])
    if datetime.utcnow() > expires_at:
        conn.close()
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Generate unique resume code
    max_attempts = 5
    code = None
    for _ in range(max_attempts):
        candidate = generate_resume_code()
        cur.execute("SELECT code FROM resume_codes WHERE code = ?", (candidate,))
        if not cur.fetchone():
            code = candidate
            break
    
    if not code:
        conn.close()
        raise HTTPException(status_code=500, detail="Failed to generate unique code")
    
    # Store resume code (expires in configured minutes)
    now = datetime.utcnow()
    expires = now + timedelta(minutes=RESUME_CODE_MINUTES)
    
    cur.execute(
        """
        INSERT INTO resume_codes (code, session_id, refresh_token_hash, created_at, expires_at, used_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (code, session_id, session_dict["refresh_token_hash"], now.isoformat(), expires.isoformat())
    )
    conn.commit()
    conn.close()
    
    print(f"[RESUME] Resume code generated successfully: user_id={current_user.get('user_id')}, account_id={current_user.get('account_id')}, session_id={session_id}")
    
    return {"resume_code": code}


@app.post("/auth/resume")
def resume_session(req: dict):
    """Resume session using a resume code.
    
    Validates the code, marks it as used, and issues new tokens for the session.
    Rotates refresh token for security.
    """
    resume_code = req.get("resume_code")
    
    if not resume_code:
        raise HTTPException(status_code=400, detail="Missing resume_code")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get resume code record
    cur.execute("SELECT * FROM resume_codes WHERE code = ?", (resume_code,))
    code_record = cur.fetchone()
    
    if not code_record:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid code")
    
    code_dict = dict(code_record)
    
    # Check if already used
    if code_dict.get("used_at"):
        conn.close()
        raise HTTPException(status_code=400, detail="Already used")
    
    # Check if expired
    expires_at = datetime.fromisoformat(code_dict["expires_at"])
    if datetime.utcnow() > expires_at:
        conn.close()
        raise HTTPException(status_code=400, detail="Expired")
    
    # Mark code as used immediately
    now = datetime.utcnow()
    cur.execute(
        "UPDATE resume_codes SET used_at = ? WHERE code = ?",
        (now.isoformat(), resume_code)
    )
    conn.commit()
    
    # Get the session
    session_id = code_dict["session_id"]
    cur.execute("SELECT * FROM auth_sessions WHERE id = ?", (session_id,))
    session = cur.fetchone()
    
    if not session:
        conn.close()
        raise HTTPException(status_code=401, detail="Session not found")
    
    session_dict = dict(session)
    
    # Check if session is revoked
    if session_dict.get("revoked_at"):
        conn.close()
        raise HTTPException(status_code=401, detail="Session revoked")
    
    # Check if session is expired
    session_expires = datetime.fromisoformat(session_dict["expires_at"])
    if datetime.utcnow() > session_expires:
        conn.close()
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Verify refresh token hash matches (security check)
    if code_dict["refresh_token_hash"] != session_dict["refresh_token_hash"]:
        conn.close()
        raise HTTPException(status_code=401, detail="Session mismatch")
    
    # Get user info
    user_id = session_dict["user_id"]
    account_id = session_dict["account_id"]
    
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_row = cur.fetchone()
    
    if not user_row:
        conn.close()
        raise HTTPException(status_code=401, detail="User not found")
    
    user_dict = dict(user_row)
    
    # Generate NEW refresh token (rotation for security)
    new_refresh_token = generate_refresh_token()
    new_refresh_token_hash = hash_token(new_refresh_token)
    
    # Update session with new refresh token hash
    cur.execute(
        "UPDATE auth_sessions SET refresh_token_hash = ? WHERE id = ?",
        (new_refresh_token_hash, session_id)
    )
    conn.commit()
    conn.close()
    
    # Create new access token
    new_access_token = create_access_token({
        "sub": str(user_id),
        "email": user_dict["email"],
        "account_id": account_id,
        "session_id": session_id
    })
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "session_id": session_id,
        "user": {
            "id": user_id,
            "email": user_dict["email"],
            "account_id": account_id
        }
    }


# ---------------------------------------------------------
# Auth & Capability Introspection
# ---------------------------------------------------------
@app.get("/auth/capabilities")
@app.get("/account/capabilities")  # Alias for consistency with /account/* endpoints
def get_account_capabilities(ctx: AuthContext = Depends(require_auth_context)):
    """
    Expose effective capabilities to frontend for UI guardrails.
    
    Returns the authenticated user's plan, role, and list of effective capabilities.
    Capabilities are computed as intersection of plan AND role.
    
    This is read-only introspection - no tokens, no auth changes.
    Available at both /auth/capabilities and /account/capabilities for convenience.
    """
    # Fetch account plan from database (backend is source of truth)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT plan FROM accounts WHERE id = ?", (ctx.account_id,))
    account_row = cur.fetchone()
    conn.close()
    
    if not account_row:
        raise HTTPException(
            status_code=500,
            detail="Account not found - this is a server error"
        )
    
    account_plan = account_row["plan"] or "free"
    user_role = ctx.role
    
    # Get effective capabilities (intersection of plan + role)
    caps = effective_capabilities(account_plan, user_role)
    
    return {
        "plan": account_plan,
        "role": user_role,
        "capabilities": sorted(list(caps))  # Return as sorted list for consistency
    }


# Account & Plan endpoints
@app.get("/account/info")
def get_account_info(ctx: AuthContext = Depends(require_auth_context)):
    try:
        # TASK 3: Use AuthContext for tenant boundary
        # Phase 2: Apply tenant guardrails
        account_id = require_account_id(ctx.account_id)
        
        # Get usage stats from existing helper
        usage_stats = get_usage_stats(account_id)

        # Subscription state is already in AuthContext
        print(f"[ACCOUNT_INFO] account_id={account_id}, "
              f"sub_plan={ctx.subscription_plan}, effective_plan={ctx.effective_plan}, "
              f"status={ctx.subscription_status}")

        return {
            "account_id": account_id,
            "plan": ctx.effective_plan,  # Use effective plan (respects subscription status)
            "subscription": {
                "status": ctx.subscription_status,
                "plan": ctx.subscription_plan,
                "effective_plan": ctx.effective_plan,
                "cancel_at_period_end": ctx.cancel_at_period_end,
                "current_period_end": ctx.current_period_end,
            },
            "capabilities": list(ctx.capabilities),  # Convert set to list for JSON
            "usage": usage_stats,
            "limits": {
                "saved_deals": get_limit(account_id, "saved_deals"),
                "scenarios": get_limit(account_id, "scenarios"),
            },
        }
    except Exception as e:
        print(f"[ACCOUNT_INFO] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve account information")


@app.get("/account/plans")
def get_available_plans():
    plans = []
    plan_names = ["free", "pro", "team", "enterprise"]
    for plan_name_str in plan_names:
        plan_name = PlanName(plan_name_str)
        config = get_plan_config(plan_name)
        # Safely extract plan name value (handles both Enum and string)
        name_value = plan_name.value if hasattr(plan_name, 'value') else str(plan_name)
        plans.append(
            {
                "name": name_value,
                "price_monthly": config["price_monthly"],
                "features": config["features"],
                "limits": config["limits"],
            }
        )
    return {"plans": plans}


@app.post("/account/upgrade")
def upgrade_plan(new_plan: str, ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary
    account_id = ctx.account_id
    user_role = ctx.role

    # Only owners can upgrade plans
    if user_role != "owner":
        raise HTTPException(status_code=403, detail="Only account owners can upgrade plans")

    try:
        plan_enum = PlanName(new_plan)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plan name")

    # In real implementation, this would update the account's plan in DB
    # and handle billing with Stripe
    # Safely extract plan value (handles both Enum and string)
    plan_value = plan_enum.value if hasattr(plan_enum, 'value') else str(plan_enum)
    return {"status": "upgraded", "new_plan": plan_value, "message": f"Successfully upgraded to {plan_value} plan"}


# ---------------------------------------------------------
# TASK 5: Admin endpoints (dev-only) for subscription testing
# ---------------------------------------------------------
@app.post("/admin/set_plan")
def admin_set_plan(account_id: int, plan: str):
    """
    TASK 5: Admin endpoint to change account subscription plan (dev/testing only).
    Updates subscription row, not legacy accounts.plan.
    In production, this would be called by Stripe webhooks or admin dashboard.
    """
    if not IS_DEV:
        raise HTTPException(status_code=403, detail="Admin endpoints only available in dev")
    
    try:
        plan_enum = PlanName(plan)
    except ValueError:
        valid_plans = [p.value for p in PlanName]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan name. Valid options: {valid_plans}"
        )
    
    conn = get_db()
    cur = conn.cursor()
    
    # Update subscription plan and set status to active
    cur.execute(
        """
        UPDATE subscriptions 
        SET plan_name = ?, status = 'active', updated_at = datetime('now')
        WHERE account_id = ?
        """,
        (plan, account_id)
    )
    
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Subscription not found for account")
    
    # Also update legacy accounts.plan for backward compatibility
    cur.execute("UPDATE accounts SET plan = ? WHERE id = ?", (plan, account_id))
    
    conn.commit()
    conn.close()
    
    print(f"[ADMIN] Set account {account_id} subscription plan to {plan} (status=active)")
    return {"status": "ok", "account_id": account_id, "plan": plan, "subscription_status": "active"}


@app.post("/admin/set_role")
def admin_set_role(user_id: int, role: str):
    """
    DEV-only endpoint to change user role for RBAC testing.
    Allows testing permission boundaries without weakening production security.
    """
    if not IS_DEV:
        raise HTTPException(status_code=403, detail="Admin endpoints only available in dev")
    
    try:
        role_enum = UserRole(role)
    except ValueError:
        valid_roles = [r.value for r in UserRole]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role name. Valid options: {valid_roles}"
        )
    
    conn = get_db()
    cur = conn.cursor()
    
    # Update user role
    cur.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    conn.commit()
    conn.close()
    
    print(f"[ADMIN] Set user {user_id} role to {role}")
    return {"status": "ok", "user_id": user_id, "role": role}


@app.post("/admin/set_subscription_status")
def admin_set_subscription_status(account_id: int, status: str):
    """
    DEV-only endpoint to change subscription status for testing.
    Allows testing payment failures, cancellations, and grace periods.
    
    Valid statuses: trialing, active, past_due, canceled
    """
    if not IS_DEV:
        raise HTTPException(status_code=403, detail="Admin endpoints only available in dev")
    
    valid_statuses = ["trialing", "active", "past_due", "canceled"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Valid options: {valid_statuses}"
        )
    
    conn = get_db()
    cur = conn.cursor()
    
    # Update subscription status
    cur.execute(
        """
        UPDATE subscriptions 
        SET status = ?, updated_at = datetime('now')
        WHERE account_id = ?
        """,
        (status, account_id)
    )
    
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Subscription not found for account")
    
    conn.commit()
    conn.close()
    
    print(f"[ADMIN] Set account {account_id} subscription status to {status}")
    return {"status": "ok", "account_id": account_id, "subscription_status": status}


@app.get("/admin/accounts")
def admin_list_accounts():
    """TASK 5: Admin endpoint to list all accounts (dev-only)."""
    if not IS_DEV:
        raise HTTPException(status_code=403, detail="Admin endpoints only available in dev")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, plan, created_at FROM accounts ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    
    accounts = [dict(row) for row in rows]
    return {"accounts": accounts}


@app.post("/property/analyze", response_model=AnalyzeResponse)
def analyze_property(req: AnalyzeRequest, ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary (never trust request body)
    account_id = ctx.account_id

    # Phase 3: Get account for authorization checks
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, plan FROM accounts WHERE id = ?", (account_id,))
    account = cur.fetchone()
    cur.execute("SELECT id, role, is_active FROM users WHERE id = ?", (ctx.user_id,))
    user = cur.fetchone()
    conn.close()

    if not account:
        raise HTTPException(status_code=500, detail="Account not found")
    if not user:
        raise HTTPException(status_code=500, detail="User not found")

    # TASK 5: Check plan access for IRR/NPV; Free gets basic analysis without IRR/NPV
    # Phase 3: Use authz module for plan feature checking
    allow_irr_npv = check_feature_access(account_id, "irr_npv")

    # Core values
    purchase_price = max(0.0, safe_float(req.purchase_price))
    rehab_budget = max(0.0, safe_float(req.rehab_budget))
    monthly_rent = max(0.0, safe_float(req.monthly_rent))
    hold_years = max(0.0, safe_float(req.hold_years))

    strategy = (req.strategy or "rental").lower()

    total_investment = purchase_price + rehab_budget

    # Operating assumptions
    vacancy_rate = min(max(safe_float(req.vacancy_rate), 0.0), 0.5)
    op_ex_pct = min(max(safe_float(req.op_ex_pct_of_rent), 0.0), 0.95)
    op_ex_fixed_monthly = max(0.0, safe_float(req.op_ex_fixed_monthly))
    capex_reserves_pct = min(max(safe_float(req.capex_reserves_pct), 0.0), 0.5)

    gross_rent_annual = monthly_rent * 12.0
    vacancy_loss_annual = gross_rent_annual * vacancy_rate
    effective_gross_income = gross_rent_annual - vacancy_loss_annual

    op_ex_annual = (effective_gross_income * op_ex_pct) + (op_ex_fixed_monthly * 12.0)
    capex_reserves_annual = gross_rent_annual * capex_reserves_pct

    noi_annual = max(0.0, effective_gross_income - op_ex_annual - capex_reserves_annual)
    noi_monthly = noi_annual / 12.0

    cashflow_per_month = noi_monthly  # before debt

    # Financing (optional)
    debt_service_annual = None
    dscr = None
    break_even_occupancy = None

    if req.down_payment_pct is not None and req.interest_rate_annual is not None and req.loan_term_years is not None:
        down_payment_pct = min(max(safe_float(req.down_payment_pct), 0.0), 1.0)
        interest_rate_annual = max(0.0, safe_float(req.interest_rate_annual))
        loan_term_years = max(1.0, safe_float(req.loan_term_years))

        loan_amount = max(0.0, purchase_price * (1.0 - down_payment_pct))
        monthly_rate = (interest_rate_annual / 100.0) / 12.0
        n = int(loan_term_years * 12)

        if loan_amount > 0 and n > 0:
            if monthly_rate > 0:
                payment = loan_amount * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)
            else:
                payment = loan_amount / n
            debt_service_annual = payment * 12.0
            cashflow_per_month = noi_monthly - payment

            if debt_service_annual > 0:
                dscr = noi_annual / debt_service_annual

            # Break-even occupancy: solve for occupancy that makes NOI = debt service
            # Using effective gross = gross * occ - vacancy modeled already; keep simple:
            if gross_rent_annual > 0 and debt_service_annual is not None:
                # Approx: NOI ≈ (gross * occ) - op_ex(occ) - capex - debt
                # We'll estimate with linear model:
                variable_op_ex = (gross_rent_annual * op_ex_pct)
                fixed_op_ex = (op_ex_fixed_monthly * 12.0)
                fixed_costs = fixed_op_ex + capex_reserves_annual + debt_service_annual
                denom = gross_rent_annual - variable_op_ex
                if denom > 0:
                    break_even_occupancy = min(max(fixed_costs / denom, 0.0), 1.5)

    # Cap rate (year 1)
    cap_rate = (noi_annual / purchase_price) if purchase_price > 0 else None

    # CoC (approx) - using total investment (purchase+rehab) as equity proxy for MVP
    annual_cashflow = cashflow_per_month * 12.0
    coc_return = (annual_cashflow / total_investment) if total_investment > 0 else None

    # Simple ROI projection: (annual cashflow * hold + appreciation) / investment
    annual_appreciation = 0.04
    future_value = total_investment * ((1 + annual_appreciation) ** hold_years) if hold_years > 0 else total_investment
    total_profit = (future_value - total_investment) + (annual_cashflow * hold_years)
    estimated_roi = (total_profit / total_investment) if total_investment > 0 else 0.0

    payback_years = (total_investment / annual_cashflow) if annual_cashflow > 0 else None

    # Unlevered IRR/NPV (simplified) — gated by plan
    irr_unlevered = None
    npv_unlevered = None
    if allow_irr_npv:
        try:
            # cashflows: t0 = -investment, then annual cashflow for hold_years, then sale at end
            n_years = int(round(hold_years))
            if n_years >= 1 and total_investment > 0:
                cashflows = [-total_investment] + [annual_cashflow] * n_years
                cashflows[-1] += future_value  # sale proceeds at end

                # Simple IRR via Newton
                def npv(rate: float) -> float:
                    return sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cashflows))

                rate = 0.1
                for _ in range(50):
                    f = npv(rate)
                    # derivative
                    df = sum(-t * cf / ((1 + rate) ** (t + 1)) for t, cf in enumerate(cashflows) if t > 0)
                    if abs(df) < 1e-9:
                        break
                    new_rate = rate - f / df
                    if abs(new_rate - rate) < 1e-7:
                        rate = new_rate
                        break
                    rate = new_rate
                if -0.99 < rate < 10:
                    irr_unlevered = rate

                discount_rate = 0.10
                npv_unlevered = npv(discount_rate)
        except Exception:
            irr_unlevered = None
            npv_unlevered = None

    # Flip metrics placeholders (if strategy flip/brrrr)
    arv = None
    rehab_months = None
    holding_months = None
    holding_costs_monthly = None
    selling_costs_pct = None
    flip_profit = None
    profit_per_month = None

    if strategy in ["flip", "brrrr", "brrrrr", "brrrrr?"]:
        # Basic defaults for MVP; frontend may override later
        arv = total_investment * 1.25 if total_investment > 0 else None
        rehab_months = 4.0
        holding_months = 6.0
        holding_costs_monthly = 600.0
        selling_costs_pct = 0.08
        if arv and total_investment:
            selling_costs = arv * selling_costs_pct
            holding_costs = holding_costs_monthly * holding_months
            flip_profit = arv - total_investment - selling_costs - holding_costs
            profit_per_month = flip_profit / max(1.0, holding_months)

    # Grade & risk (simple)
    risk_level = "Low"
    grade = "C"
    if estimated_roi >= 0.25 and (cashflow_per_month >= 200):
        grade = "A"
    elif estimated_roi >= 0.18:
        grade = "B"
    elif estimated_roi >= 0.12:
        grade = "C"
    elif estimated_roi >= 0.08:
        grade = "D"
        risk_level = "Medium"
    else:
        grade = "F"
        risk_level = "High"

    tags: List[str] = []
    if cashflow_per_month < 0:
        tags.append("Negative cashflow")
        risk_level = "High"
    if strategy in ["flip", "brrrr"]:
        if flip_profit is not None and flip_profit < 0:
            tags.append("Flip loss risk")
            risk_level = "High"

    summary = f"{grade} grade deal with {risk_level.lower()} risk. Estimated ROI {estimated_roi*100:.1f}%, cashflow ${cashflow_per_month:,.0f}/mo."

    return AnalyzeResponse(
        deal_grade=grade,
        risk_level=risk_level,
        summary=summary,
        estimated_roi=estimated_roi,
        cashflow_per_month=cashflow_per_month,
        cap_rate=cap_rate,
        coc_return=coc_return,
        payback_years=payback_years,
        projected_total_profit=total_profit,
        total_investment=total_investment,
        noi_annual=noi_annual,
        op_ex_annual=op_ex_annual,
        vacancy_loss_annual=vacancy_loss_annual,
        capex_reserves_annual=capex_reserves_annual,
        break_even_occupancy=break_even_occupancy,
        dscr=dscr,
        debt_service_annual=debt_service_annual,
        irr_unlevered=irr_unlevered,
        npv_unlevered=npv_unlevered,
        arv=arv,
        rehab_months=rehab_months,
        holding_months=holding_months,
        holding_costs_monthly=holding_costs_monthly,
        selling_costs_pct=selling_costs_pct,
        flip_profit=flip_profit,
        profit_per_month=profit_per_month,
        tags=tags,
    )


# ---------------------------------------------------------
# RBAC Enforcement: /property/save
# ---------------------------------------------------------
# This endpoint requires "asset:manage" capability, which enforces BOTH role AND plan.
#
# MANUAL TEST for RBAC enforcement:
#
# 1. Setup: Create test users with different roles in the same account
#    - read_only user (role="read_only")
#    - member user (role="member")
#    - admin user (role="admin")
#    - owner user (role="owner")
#
# 2. Expected Behavior (on any plan):
#    - read_only → 403 Forbidden ("Insufficient permissions")
#      Reason: read_only role does NOT have "asset:manage" capability
#    - member → SUCCESS (saves property normally, within plan limits)
#    - admin → SUCCESS (saves property normally, within plan limits)
#    - owner → SUCCESS (saves property normally, within plan limits)
#
# 3. Plan Interaction:
#    - Free plan + member role: Gets intersection of free plan + member capabilities
#    - Pro plan + read_only role: Gets intersection of pro plan + read_only capabilities
#      (read_only still cannot save even on pro plan!)
#
# 4. Test Commands (using JWT tokens for each user):
#    curl -X POST http://localhost:8000/property/save \
#      -H "Authorization: Bearer <TOKEN>" \
#      -H "Content-Type: application/json" \
#      -d '{"property_name": "Test", "city": "Austin", ...}'
#
# 5. Success Criteria:
#    - read_only users blocked with 403
#    - member/admin/owner can save (within plan limits)
#    - Logs show: [AUTHZ] Capability denied: capability=asset:manage, role=read_only, plan=...
#    - No regressions on existing saved property functionality
# ---------------------------------------------------------
@app.post("/property/save", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def save_property(payload: Dict[str, Any], ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary (never trust request body for account_id)
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)
    user_id = ctx.user_id

    # Phase 3: Get user and account for RBAC
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, plan FROM accounts WHERE id = ?", (account_id,))
    account = cur.fetchone()
    cur.execute("SELECT id, role, is_active FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    
    # Phase 3: Require write access (member role or higher)
    require_write_access(dict(user) if user else None, dict(account) if account else None)
    
    # Phase 3: Check saved deal limit by plan
    cur.execute("SELECT COUNT(*) as count FROM saved_properties WHERE account_id = ?", (account_id,))
    current_count = cur.fetchone()["count"]
    conn.close()
    
    plan = account["plan"] if account else "free"
    check_usage_against_limit(current_count, plan, "max_saved_deals")

    # Legacy enforcement (can be removed if redundant)
    # try:
    #     check_usage_limit(account_id, "saved_deals")
    # except UsageLimitError as e:
    #     raise HTTPException(status_code=402, detail=str(e))

    conn = get_db()
    cur = conn.cursor()

    created_at = now_iso()

    # Minimal defensive gets
    prop_name = payload.get("property_name")
    city = payload.get("city")
    state = payload.get("state")
    zip_code = payload.get("zip_code")

    strategy = payload.get("strategy")
    investor_profile = payload.get("investor_profile")

    estimated_roi = safe_float(payload.get("estimated_roi"))
    cashflow_per_month = safe_float(payload.get("cashflow_per_month"))
    cap_rate = payload.get("cap_rate")
    coc_return = payload.get("coc_return")
    noi = payload.get("noi")
    dscr = payload.get("dscr")
    total_investment = payload.get("total_investment")

    irr_unlevered = payload.get("irr_unlevered")
    npv_unlevered = payload.get("npv_unlevered")

    arv = payload.get("arv")
    rehab_months = payload.get("rehab_months")
    holding_months = payload.get("holding_months")
    holding_costs_monthly = payload.get("holding_costs_monthly")
    selling_costs_pct = payload.get("selling_costs_pct")
    flip_profit = payload.get("flip_profit")
    profit_per_month = payload.get("profit_per_month")

    deal_grade = payload.get("deal_grade")

    # Build column/value lists matching actual DB schema (self-consistent INSERT)
    # Columns match saved_properties table schema exactly
    cols = [
        "property_name", "city", "state", "zip_code", "deal_grade",
        "estimated_roi", "cashflow_per_month", "strategy", "investor_profile",
        "cap_rate", "coc_return", "noi", "dscr", "total_investment",
        "irr_unlevered", "npv_unlevered", "created_at",
        "arv", "rehab_months", "holding_months", "holding_costs_monthly", "selling_costs_pct",
        "flip_profit", "profit_per_month",
        "account_id", "user_id",
    ]

    values = [
        prop_name,
        city,
        state,
        zip_code,
        deal_grade,
        estimated_roi,
        cashflow_per_month,
        strategy,
        investor_profile,
        cap_rate,
        coc_return,
        noi,
        dscr,
        total_investment,
        irr_unlevered,
        npv_unlevered,
        created_at,
        arv,
        rehab_months,
        holding_months,
        holding_costs_monthly,
        selling_costs_pct,
        flip_profit,
        profit_per_month,
        account_id,
        user_id,  # TASK 3: Set from AuthContext (never from request body)
    ]

    # Sanity check: columns and values must match (dev safety)
    assert len(cols) == len(values), f"Column/value length mismatch: cols={len(cols)} values={len(values)}"

    try:
        placeholders = ",".join(["?"] * len(cols))
        sql = f"INSERT INTO saved_properties ({','.join(cols)}) VALUES ({placeholders})"
        cur.execute(sql, values)
        saved_id = cur.lastrowid

        conn.commit()
        conn.close()
        print(f"[SAVE_PROPERTY] Saved deal id={saved_id} for account_id={account_id}, property={repr(prop_name)}")
        return {"status": "saved", "id": saved_id}
    
    except sqlite3.IntegrityError as e:
        conn.close()
        print(f"[SAVE_PROPERTY] Integrity error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to save deal: integrity constraint violation")
    
    except sqlite3.OperationalError as e:
        conn.close()
        print(f"[SAVE_PROPERTY] Operational error (schema mismatch?): {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    except Exception as e:
        conn.close()
        print(f"[SAVE_PROPERTY] Unexpected error saving deal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save deal: {str(e)}")


@app.get("/property/saved")
def list_saved_properties(ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Always filter by account_id from AuthContext
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)

    conn = get_db()
    cur = execute_scoped(
        conn,
        "SELECT rowid, * FROM saved_properties WHERE account_id = ? ORDER BY rowid DESC",
        (account_id,),
        account_id,
        label="/property/saved"
    )
    rows = cur.fetchall()
    conn.close()

    # Phase 2: Assert all rows belong to this tenant
    assert_rows_scoped(rows, account_id, label="/property/saved")

    results: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["id"] = d.get("rowid")
        d.pop("rowid", None)

        # tags_json -> list
        try:
            d["tags"] = json.loads(d.get("tags_json") or "[]")
        except Exception:
            d["tags"] = []
        d.pop("tags_json", None)

        results.append(d)

    return results


@app.post("/property/delete", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def delete_property(payload: Dict[str, Any], ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary (enforced)
    # RBAC: Requires asset:manage capability (role + plan intersection)
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)

    # Phase 3: Require write access (member role or higher)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, plan FROM accounts WHERE id = ?", (account_id,))
    account = cur.fetchone()
    cur.execute("SELECT id, role, is_active FROM users WHERE id = ?", (ctx.user_id,))
    user = cur.fetchone()
    conn.close()
    
    require_write_access(dict(user) if user else None, dict(account) if account else None)

    row_id = int(payload.get("id", 0))
    if row_id < 1:
        raise HTTPException(status_code=400, detail="Invalid id")

    conn = get_db()
    cur = conn.cursor()

    # TASK 3: Enforce tenant isolation - row must belong to account
    row = require_row_owned(cur, "saved_properties", row_id, account_id)
    # Phase 2: Validate the row belongs to this tenant
    assert_row_scoped(row, account_id, label="/property/delete")

    saved = dict(row)
    saved["rowid"] = saved.get("rowid") or row_id
    saved_json = json.dumps(saved)

    cur.execute("DELETE FROM saved_properties WHERE rowid = ? AND account_id = ?", (row_id, account_id))
    cur.execute(
        "INSERT INTO trashed_properties (saved_row_json, deleted_at, account_id) VALUES (?, ?, ?)",
        (saved_json, now_iso(), account_id)
    )
    trash_id = cur.lastrowid  # Capture the autoincremented trash_id

    conn.commit()
    conn.close()

    return {"status": "deleted", "id": row_id, "trash_id": trash_id}


@app.get("/property/trash")
def get_trash(ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Filter by account_id from AuthContext only
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)

    conn = get_db()
    # TASK 3: Strict WHERE filter - no cross-tenant access
    cur = execute_scoped(
        conn,
        """SELECT trash_id, saved_row_json, deleted_at, account_id 
           FROM trashed_properties 
           WHERE account_id = ?
           ORDER BY trash_id DESC""",
        (account_id,),
        account_id,
        label="/property/trash"
    )
    rows = cur.fetchall()
    conn.close()

    # Phase 2: Assert all rows belong to this tenant
    assert_rows_scoped(rows, account_id, label="/property/trash")

    trash_list: List[Dict[str, Any]] = []
    for row in rows:
        base = dict(row)
        saved_json = base.get("saved_row_json") or "{}"
        try:
            saved = json.loads(saved_json)
        except Exception:
            saved = {}

        trash_list.append(
            {
                "trash_id": base.get("trash_id"),
                "property_name": saved.get("property_name"),
                "city": saved.get("city"),
                "state": saved.get("state"),
                "deal_grade": saved.get("deal_grade"),
                "strategy": saved.get("strategy"),
                "deleted_at": base.get("deleted_at"),
            }
        )

    return trash_list


@app.post("/property/trash/restore", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def restore_from_trash(payload: Dict[str, Any], ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary (enforced)
    # RBAC: Requires asset:manage capability (role + plan intersection)
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)

    # Phase 3: Require write access (member role or higher)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, plan FROM accounts WHERE id = ?", (account_id,))
    account = cur.fetchone()
    cur.execute("SELECT id, role, is_active FROM users WHERE id = ?", (ctx.user_id,))
    user = cur.fetchone()
    conn.close()
    
    require_write_access(dict(user) if user else None, dict(account) if account else None)

    trash_id = int(payload.get("trash_id", 0))
    if trash_id < 1:
        raise HTTPException(status_code=400, detail="Invalid trash_id")

    conn = get_db()
    cur = conn.cursor()
    # TASK 3: Enforce account scoping - only return rows owned by this account
    cur.execute(
        """SELECT trash_id, saved_row_json, account_id 
           FROM trashed_properties 
           WHERE trash_id = ? AND account_id = ?""",
        (trash_id, account_id)
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        # TASK 3: Return 404 for cross-tenant attempts (don't leak existence)
        raise HTTPException(status_code=404, detail="Not found")
    
    # Phase 2: Validate the row belongs to this tenant
    assert_row_scoped(row, account_id, label="/property/trash/restore")

    saved_json = row["saved_row_json"] or "{}"
    try:
        saved = json.loads(saved_json)
    except Exception:
        saved = {}

    # TASK 3: Row already validated by SQL WHERE clause (no need to double-check)

    # Reinsert into saved_properties matching actual DB schema (26 columns)
    cur.execute(
        """
        INSERT INTO saved_properties (
            property_name, city, state, zip_code, deal_grade,
            estimated_roi, cashflow_per_month, strategy, investor_profile,
            cap_rate, coc_return, noi, dscr, total_investment,
            irr_unlevered, npv_unlevered, created_at,
            arv, rehab_months, holding_months, holding_costs_monthly, selling_costs_pct,
            flip_profit, profit_per_month,
            account_id, user_id
        ) VALUES (
            ?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,?,
            ?,?,?,
            ?,?,?,?,?,
            ?,?,
            ?,?
        )
        """,
        (
            saved.get("property_name"),
            saved.get("city"),
            saved.get("state"),
            saved.get("zip_code"),
            saved.get("deal_grade"),
            saved.get("estimated_roi"),
            saved.get("cashflow_per_month"),
            saved.get("strategy"),
            saved.get("investor_profile"),
            saved.get("cap_rate"),
            saved.get("coc_return"),
            saved.get("noi"),
            saved.get("dscr"),
            saved.get("total_investment"),
            saved.get("irr_unlevered"),
            saved.get("npv_unlevered"),
            saved.get("created_at") or now_iso(),
            saved.get("arv"),
            saved.get("rehab_months"),
            saved.get("holding_months"),
            saved.get("holding_costs_monthly"),
            saved.get("selling_costs_pct"),
            saved.get("flip_profit"),
            saved.get("profit_per_month"),
            account_id,
            None,  # user_id
        ),
    )

    # Remove from trash
    cur.execute("DELETE FROM trashed_properties WHERE trash_id = ?", (trash_id,))
    conn.commit()
    conn.close()

    return {"status": "restored", "trash_id": trash_id}


# ---------------------------------------------------------


@app.post("/scenario/save", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def save_scenario(req: ScenarioSaveRequest, ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary (enforced)
    # RBAC: Requires asset:manage capability (scenarios belong to assets)
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)
    
    if req.slot not in ["A", "B", "C"]:
        raise HTTPException(status_code=400, detail="Invalid slot. Must be A, B, or C")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Security: Verify property belongs to current account (prevent cross-tenant scenario creation)
    cur.execute("SELECT id FROM saved_properties WHERE id = ? AND account_id = ?", (req.property_id, account_id))
    property_row = cur.fetchone()
    if not property_row:
        conn.close()
        # Return 404 to prevent cross-tenant enumeration
        raise HTTPException(status_code=404, detail="Property not found")
    
    metrics_json = json.dumps(req.metrics)
    
    # Upsert: insert or replace
    cur.execute(
        """
        INSERT OR REPLACE INTO scenarios (account_id, property_id, slot, label, metrics_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (account_id, req.property_id, req.slot, req.label, metrics_json, now_iso())
    )
    
    conn.commit()
    conn.close()
    
    return {"success": True}


@app.get("/scenario/list/{property_id}")
def list_scenarios(property_id: int, ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Filter by account_id from AuthContext
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)
    
    conn = get_db()
    cur = execute_scoped(
        conn,
        "SELECT id, slot, label, metrics_json, created_at FROM scenarios WHERE account_id = ? AND property_id = ? ORDER BY slot",
        (account_id, property_id),
        account_id,
        label="/scenario/list"
    )
    rows = cur.fetchall()
    conn.close()
    
    # Phase 2: Assert all rows belong to this tenant
    assert_rows_scoped(rows, account_id, label="/scenario/list")
    
    scenarios = []
    for row in rows:
        scenarios.append({
            "id": row["id"],
            "slot": row["slot"],
            "label": row["label"],
            "metrics": json.loads(row["metrics_json"]),
            "created_at": row["created_at"]
        })
    
    return scenarios


@app.post("/scenario/clear", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def clear_scenario(req: ScenarioClearRequest, ctx: AuthContext = Depends(require_auth_context)):
    # TASK 3: Use AuthContext for tenant boundary (enforced)
    # RBAC: Requires asset:manage capability (scenarios belong to assets)
    # Phase 2: Apply tenant guardrails
    account_id = require_account_id(ctx.account_id)
    
    if req.slot not in ["A", "B", "C"]:
        raise HTTPException(status_code=400, detail="Invalid slot. Must be A, B, or C")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Security: Verify property belongs to current account (prevent cross-tenant scenario deletion)
    cur.execute("SELECT id FROM saved_properties WHERE id = ? AND account_id = ?", (req.property_id, account_id))
    property_row = cur.fetchone()
    if not property_row:
        conn.close()
        # Return 404 to prevent cross-tenant enumeration
        raise HTTPException(status_code=404, detail="Property not found")
    
    cur.execute(
        "DELETE FROM scenarios WHERE account_id = ? AND property_id = ? AND slot = ?",
        (account_id, req.property_id, req.slot)
    )
    conn.commit()
    conn.close()
    
    return {"success": True}

# ---------------------------------------------------------
# Property Search endpoints
# ---------------------------------------------------------

@app.get("/search/properties")
def search_properties(
    q: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip: Optional[str] = None,
    limit: int = 50,
    ctx: AuthContext = Depends(require_auth_context)
):
    """
    Search properties from cache or return sample data.
    Gated by search:basic capability (Pro+ plans).
    Advanced filters (zip + city/state + q) require search:advanced.
    """
    account_id = require_account_id(ctx.account_id)
    
    # For MVP: Return mock data if search_properties_cache is empty
    # In production, this would query a real property data source
    conn = get_db()
    cur = conn.cursor()
    
    # Check if we have any cached data
    cur.execute("SELECT COUNT(*) as count FROM search_properties_cache")
    row = cur.fetchone()
    has_cache = row["count"] > 0
    
    if not has_cache:
        # Return sample data for MVP
        conn.close()
        sample_properties = [
            {
                "property_id": 1,
                "address": "123 Main St",
                "city": "Atlanta",
                "state": "GA",
                "zip": "30301",
                "beds": 3,
                "baths": 2.0,
                "sqft": 1500,
                "est_price": 250000
            },
            {
                "property_id": 2,
                "address": "456 Oak Ave",
                "city": "Atlanta",
                "state": "GA",
                "zip": "30302",
                "beds": 4,
                "baths": 2.5,
                "sqft": 2000,
                "est_price": 325000
            },
            {
                "property_id": 3,
                "address": "789 Pine Rd",
                "city": "Decatur",
                "state": "GA",
                "zip": "30030",
                "beds": 2,
                "baths": 1.0,
                "sqft": 1100,
                "est_price": 175000
            },
        ]
        
        # Filter based on query params
        results = sample_properties
        if city:
            results = [p for p in results if p["city"].lower() == city.lower()]
        if state:
            results = [p for p in results if p["state"].lower() == state.lower()]
        if zip:
            results = [p for p in results if p["zip"] == zip]
        if q:
            q_lower = q.lower()
            results = [p for p in results if q_lower in p["address"].lower() or q_lower in p["city"].lower()]
        
        return results[:limit]
    
    # Build query from cache
    query = "SELECT id as property_id, address, city, state, zip_code as zip, beds, baths, sqft, est_price FROM search_properties_cache WHERE 1=1"
    params = []
    
    if q:
        query += " AND (address LIKE ? OR city LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if city:
        query += " AND city = ?"
        params.append(city)
    if state:
        query += " AND state = ?"
        params.append(state)
    if zip:
        query += " AND zip_code = ?"
        params.append(zip)
    
    query += f" LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append({
            "property_id": row["property_id"],
            "address": row["address"],
            "city": row["city"],
            "state": row["state"],
            "zip": row["zip"],
            "beds": row["beds"],
            "baths": row["baths"],
            "sqft": row["sqft"],
            "est_price": row["est_price"]
        })
    
    return results


# ---------------------------------------------------------
# Assets endpoints
# ---------------------------------------------------------

class AssetCreateRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None


class AssetUpdateRequest(BaseModel):
    asset_id: int
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None


class AssetDeleteRequest(BaseModel):
    asset_id: int


@app.get("/assets/list")
def list_assets(ctx: AuthContext = Depends(require_auth_context)):
    """List all assets for current account."""
    account_id = require_account_id(ctx.account_id)
    
    conn = get_db()
    cur = execute_scoped(
        conn,
        "SELECT id, account_id, name, address, city, state, zip_code, notes, created_at, updated_at FROM assets WHERE account_id = ? ORDER BY created_at DESC",
        (account_id,),
        account_id,
        label="/assets/list"
    )
    rows = cur.fetchall()
    conn.close()
    
    assert_rows_scoped(rows, account_id, label="/assets/list")
    
    assets = []
    for row in rows:
        assets.append({
            "asset_id": row["id"],
            "name": row["name"],
            "address": row["address"],
            "city": row["city"],
            "state": row["state"],
            "zip_code": row["zip_code"],
            "notes": row["notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })
    
    return assets


@app.get("/assets/get")
def get_asset(asset_id: int, ctx: AuthContext = Depends(require_auth_context)):
    """Get single asset detail."""
    account_id = require_account_id(ctx.account_id)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, address, city, state, zip_code, notes, created_at, updated_at FROM assets WHERE id = ? AND account_id = ?",
        (asset_id, account_id)
    )
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    assert_row_scoped(row, account_id, label="/assets/get")
    
    # Optionally, fetch related saved deals
    conn2 = get_db()
    cur2 = conn2.cursor()
    cur2.execute(
        """
        SELECT id, property_name, city, state, zip_code, strategy, deal_grade, created_at
        FROM saved_properties
        WHERE account_id = ?
          AND (address = ? OR (city = ? AND state = ? AND zip_code = ?))
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (account_id, row["address"], row["city"], row["state"], row["zip_code"])
    )
    related_deals = cur2.fetchall()
    conn2.close()
    
    return {
        "asset_id": row["id"],
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "zip_code": row["zip_code"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "related_deals": [dict(d) for d in related_deals]
    }


@app.post("/assets/create", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def create_asset(req: AssetCreateRequest, ctx: AuthContext = Depends(require_auth_context)):
    """Create new asset. Requires asset:manage capability."""
    account_id = require_account_id(ctx.account_id)
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO assets (account_id, name, address, city, state, zip_code, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, req.name, req.address, req.city, req.state, req.zip_code, req.notes, now_iso(), now_iso())
    )
    asset_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    return {"success": True, "asset_id": asset_id}


@app.post("/assets/update", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def update_asset(req: AssetUpdateRequest, ctx: AuthContext = Depends(require_auth_context)):
    """Update existing asset. Requires asset:manage capability."""
    account_id = require_account_id(ctx.account_id)
    
    conn = get_db()
    cur = conn.cursor()
    
    # Verify ownership
    cur.execute("SELECT id FROM assets WHERE id = ? AND account_id = ?", (req.asset_id, account_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Build update query dynamically for only provided fields
    fields = []
    params = []
    if req.name is not None:
        fields.append("name = ?")
        params.append(req.name)
    if req.address is not None:
        fields.append("address = ?")
        params.append(req.address)
    if req.city is not None:
        fields.append("city = ?")
        params.append(req.city)
    if req.state is not None:
        fields.append("state = ?")
        params.append(req.state)
    if req.zip_code is not None:
        fields.append("zip_code = ?")
        params.append(req.zip_code)
    if req.notes is not None:
        fields.append("notes = ?")
        params.append(req.notes)
    
    if not fields:
        conn.close()
        return {"success": True, "message": "No fields to update"}
    
    fields.append("updated_at = ?")
    params.append(now_iso())
    params.extend([req.asset_id, account_id])
    
    query = f"UPDATE assets SET {', '.join(fields)} WHERE id = ? AND account_id = ?"
    cur.execute(query, params)
    conn.commit()
    conn.close()
    
    return {"success": True}


@app.post("/assets/delete", dependencies=[Depends(require_capability(Capability.ASSET_MANAGE))])
def delete_asset(req: AssetDeleteRequest, ctx: AuthContext = Depends(require_auth_context)):
    """Delete asset. Requires asset:manage capability."""
    account_id = require_account_id(ctx.account_id)
    
    conn = get_db()
    cur = conn.cursor()
    
    # Verify ownership
    cur.execute("SELECT id FROM assets WHERE id = ? AND account_id = ?", (req.asset_id, account_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found")
    
    cur.execute("DELETE FROM assets WHERE id = ? AND account_id = ?", (req.asset_id, account_id))
    conn.commit()
    conn.close()
    
    return {"success": True}