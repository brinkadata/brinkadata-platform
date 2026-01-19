# backend/migrate.py
# Database migration module for PostgreSQL and SQLite
# Run: python -m backend.migrate

import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import IS_POSTGRES, get_db_connection, commit


def run_migrations() -> None:
    """
    Run all database migrations (idempotent).
    Creates tables, adds columns, and creates indexes if missing.
    Safe to run multiple times.
    """
    print("[MIGRATE] Starting database migrations...")
    
    with get_db_connection() as conn:
        if IS_POSTGRES:
            _run_postgres_migrations(conn)
        else:
            _run_sqlite_migrations(conn)
        
        commit(conn)
    
    print("[MIGRATE] All migrations complete!")


def _run_postgres_migrations(conn) -> None:
    """PostgreSQL-specific migrations using SQLAlchemy."""
    from sqlalchemy import text
    
    print("[MIGRATE] Running PostgreSQL migrations...")
    
    # Users table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            account_id INTEGER,
            role TEXT DEFAULT 'member',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email)"))
    
    # Accounts table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            owner_id INTEGER REFERENCES users(id),
            plan TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Account memberships table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS account_memberships (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            role TEXT DEFAULT 'member',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, user_id)
        )
    """))
    
    # Plans table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS plans (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            price_monthly REAL NOT NULL,
            max_saved_deals INTEGER DEFAULT 10,
            max_scenarios INTEGER DEFAULT 3,
            features_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Subscriptions table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            plan_id INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            plan_name TEXT DEFAULT 'free',
            provider TEXT DEFAULT 'manual',
            provider_customer_id TEXT,
            provider_subscription_id TEXT,
            stripe_subscription_id TEXT,
            cancel_at_period_end INTEGER DEFAULT 0,
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    """))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_account_unique ON subscriptions(account_id)"))
    
    # Saved properties table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS saved_properties (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL DEFAULT 1,
            user_id INTEGER,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_saved_properties_account_id ON saved_properties(account_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_saved_properties_account_created ON saved_properties(account_id, created_at)"))
    
    # Trashed properties table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS trashed_properties (
            trash_id SERIAL PRIMARY KEY,
            account_id INTEGER,
            saved_row_json TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trashed_properties_account_id ON trashed_properties(account_id)"))
    
    # Scenarios table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            slot TEXT NOT NULL CHECK (slot IN ('A', 'B', 'C')),
            label TEXT,
            metrics_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, property_id, slot)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scenarios_account_property ON scenarios(account_id, property_id)"))
    
    # Auth sessions table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            account_id INTEGER NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP NULL,
            user_agent TEXT NULL,
            ip TEXT NULL
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auth_sessions_account_id ON auth_sessions(account_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)"))
    
    # Resume codes table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS resume_codes (
            code TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES auth_sessions(id),
            refresh_token_hash TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP NULL
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_resume_codes_expires_at ON resume_codes(expires_at)"))
    
    # Affiliates table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS affiliates (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            referral_code TEXT UNIQUE NOT NULL,
            commission_rate REAL DEFAULT 0.1,
            total_earned REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Referrals table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            affiliate_id INTEGER NOT NULL REFERENCES affiliates(id),
            referred_user_id INTEGER NOT NULL REFERENCES users(id),
            referred_account_id INTEGER NOT NULL REFERENCES accounts(id),
            commission_amount REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Assets table (Property Search + Assets)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            name TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_assets_account_id ON assets(account_id)"))
    
    # Property index table (Property Search)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS property_index (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            asset_id INTEGER REFERENCES assets(id),
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            county TEXT,
            property_type TEXT,
            bedrooms INTEGER,
            bathrooms REAL,
            sqft INTEGER,
            lot_size REAL,
            year_built INTEGER,
            zoning TEXT,
            last_sale_date TEXT,
            last_sale_price REAL,
            assessed_value REAL,
            market_value REAL,
            owner_name TEXT,
            owner_type TEXT,
            occupancy_status TEXT,
            rental_estimate REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_property_index_account_id ON property_index(account_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_property_index_asset_id ON property_index(asset_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_property_index_city_state ON property_index(city, state)"))
    
    print("[MIGRATE] PostgreSQL migrations complete")


def _run_sqlite_migrations(conn) -> None:
    """SQLite-specific migrations using sqlite3."""
    print("[MIGRATE] Running SQLite migrations...")
    
    cur = conn.cursor()
    
    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            account_id INTEGER,
            role TEXT DEFAULT 'member',
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email)")
    
    # Accounts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER,
            plan TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
    """)
    
    # Add plan columns if missing (idempotent)
    _ensure_sqlite_column(cur, conn, "accounts", "plan", "TEXT DEFAULT 'free'")
    _ensure_sqlite_column(cur, conn, "accounts", "stripe_customer_id", "TEXT")
    _ensure_sqlite_column(cur, conn, "accounts", "stripe_subscription_id", "TEXT")
    
    # Account memberships table
    cur.execute("""
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
    """)
    
    # Plans table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price_monthly REAL NOT NULL,
            max_saved_deals INTEGER DEFAULT 10,
            max_scenarios INTEGER DEFAULT 3,
            features_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Subscriptions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            plan_name TEXT DEFAULT 'free',
            provider TEXT DEFAULT 'manual',
            provider_customer_id TEXT,
            provider_subscription_id TEXT,
            stripe_subscription_id TEXT,
            cancel_at_period_end INTEGER DEFAULT 0,
            current_period_start TEXT,
            current_period_end TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (plan_id) REFERENCES plans (id)
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_account_unique ON subscriptions(account_id)")
    
    # Add subscription columns if missing (idempotent)
    _ensure_sqlite_column(cur, conn, "subscriptions", "plan_name", "TEXT DEFAULT 'free'")
    _ensure_sqlite_column(cur, conn, "subscriptions", "provider", "TEXT DEFAULT 'manual'")
    _ensure_sqlite_column(cur, conn, "subscriptions", "provider_customer_id", "TEXT")
    _ensure_sqlite_column(cur, conn, "subscriptions", "provider_subscription_id", "TEXT")
    _ensure_sqlite_column(cur, conn, "subscriptions", "cancel_at_period_end", "INTEGER DEFAULT 0")
    _ensure_sqlite_column(cur, conn, "subscriptions", "updated_at", "TEXT")
    
    # Saved properties table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER DEFAULT 1,
            user_id INTEGER,
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
    """)
    _ensure_sqlite_column(cur, conn, "saved_properties", "user_id", "INTEGER")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_properties_account_id ON saved_properties(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_properties_account_created ON saved_properties(account_id, created_at)")
    
    # Trashed properties table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trashed_properties (
            trash_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            saved_row_json TEXT,
            deleted_at TEXT
        )
    """)
    _ensure_sqlite_column(cur, conn, "trashed_properties", "account_id", "INTEGER")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trashed_properties_account_id ON trashed_properties(account_id)")
    
    # Scenarios table
    cur.execute("""
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
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_account_property ON scenarios(account_id, property_id)")
    
    # Auth sessions table
    cur.execute("""
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
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_account_id ON auth_sessions(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)")
    
    # Resume codes table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resume_codes (
            code TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT NULL,
            FOREIGN KEY (session_id) REFERENCES auth_sessions (id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_resume_codes_expires_at ON resume_codes(expires_at)")
    
    # Affiliates table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS affiliates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            referral_code TEXT UNIQUE NOT NULL,
            commission_rate REAL DEFAULT 0.1,
            total_earned REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # Referrals table
    cur.execute("""
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
    """)
    
    # Assets table
    cur.execute("""
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
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_account_id ON assets(account_id)")
    
    # Property index table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS property_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            asset_id INTEGER,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            county TEXT,
            property_type TEXT,
            bedrooms INTEGER,
            bathrooms REAL,
            sqft INTEGER,
            lot_size REAL,
            year_built INTEGER,
            zoning TEXT,
            last_sale_date TEXT,
            last_sale_price REAL,
            assessed_value REAL,
            market_value REAL,
            owner_name TEXT,
            owner_type TEXT,
            occupancy_status TEXT,
            rental_estimate REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES assets (id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_index_account_id ON property_index(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_index_asset_id ON property_index(asset_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_index_city_state ON property_index(city, state)")
    
    print("[MIGRATE] SQLite migrations complete")


def _ensure_sqlite_column(cur, conn, table: str, column: str, ddl: str) -> None:
    """Add column to SQLite table if missing (idempotent)."""
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    
    if column not in columns:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()
            print(f"[MIGRATE] Added column {table}.{column}")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                print(f"[MIGRATE] Warning: Could not add {table}.{column}: {e}")


if __name__ == "__main__":
    run_migrations()
