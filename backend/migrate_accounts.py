#!/usr/bin/env python3
"""
Migration script to add account_id and user_id to existing saved_properties.
Run this once after updating the backend.

TASK 4: Demo user creation is DEV-ONLY.
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = "brinkadata.db"

# TASK 4: Environment detection
IS_DEV = os.environ.get("ENV", "dev") == "dev"

def init_db():
    """Initialize the new tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Account management tables
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            stripe_customer_id TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            stripe_id TEXT,
            features TEXT,  -- JSON string
            limits TEXT,    -- JSON string
            price_monthly REAL DEFAULT 0.0
        )
        """
    )

    # Insert default plans if not exist
    cur.execute("INSERT OR IGNORE INTO plans (name, features, limits) VALUES (?, ?, ?)",
                ("free", '{"can_export_csv": false, "can_use_irr": false}', '{"max_saved_deals": 5}'))
    cur.execute("INSERT OR IGNORE INTO plans (name, features, limits) VALUES (?, ?, ?)",
                ("pro", '{"can_export_csv": true, "can_use_irr": true}', '{"max_saved_deals": 50}'))

    conn.commit()
    conn.close()

def migrate_existing_data():
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Check if saved_properties table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='saved_properties'")
    if not cur.fetchone():
        print("saved_properties table doesn't exist. Creating it...")
        # Create the table (copied from main.py)
        cur.execute(
            """
            CREATE TABLE saved_properties (
                property_name TEXT,
                city TEXT,
                state TEXT,
                zip_code TEXT,
                deal_grade TEXT,
                estimated_roi REAL,
                cashflow_per_month REAL,
                strategy TEXT,
                investor_profile TEXT,
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
                created_at TEXT,
                account_id INTEGER,
                user_id INTEGER
            )
            """
        )
        print("Created saved_properties table")
    
    # TASK 4: Create default account and user ONLY in DEV
    if IS_DEV:
        cur.execute("SELECT id FROM accounts WHERE id = 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO accounts (id, name, plan) VALUES (1, 'Default Account', 'free')")
            print("[DEV-ONLY] Created default account")
        
        cur.execute("SELECT id FROM users WHERE id = 1")
        if not cur.fetchone():
            import hashlib
            password_hash = hashlib.sha256("password".encode()).hexdigest()  # default password
            cur.execute("INSERT INTO users (id, email, password_hash, account_id, role) VALUES (1, 'demo@example.com', ?, 1, 'owner')", (password_hash,))
            print("[DEV-ONLY] Created default user (email: demo@example.com, password: password)")
    else:
        print("[PROD/STAGING] Skipping demo account creation (not allowed outside dev)")
    
    # Update existing saved_properties with default account_id and user_id
    cur.execute("UPDATE saved_properties SET account_id = 1, user_id = 1 WHERE account_id IS NULL OR user_id IS NULL")
    updated_count = cur.rowcount
    print(f"Updated {updated_count} existing deals with account/user IDs")
    
    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate_existing_data()