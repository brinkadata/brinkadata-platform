"""
backend/migrate_property_search_assets.py

Database migration for Property Search + Assets feature hardening.

This migration ensures:
1. assets table has created_by column and proper tenant indexes
2. property_index table exists with tenant isolation (account_id)
3. All queries are tenant-scoped for security

Run: python -m backend.migrate_property_search_assets
"""

from __future__ import annotations

import sqlite3
from pathlib import Path as FsPath

# Import config
try:
    from backend.config import DATABASE_PATH
except ModuleNotFoundError:
    from config import DATABASE_PATH


def get_db_path() -> str:
    """Get absolute path to database."""
    return str(FsPath(__file__).resolve().parent / DATABASE_PATH)


def migrate() -> None:
    """Apply migration for Property Search + Assets hardening."""
    db_path = get_db_path()
    print(f"[MIGRATION] Connecting to: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("[MIGRATION] Starting Property Search + Assets migration...")
    
    # ========================================================================
    # STEP 1: Ensure assets table has proper schema
    # ========================================================================
    print("[MIGRATION] Checking assets table schema...")
    
    # Check existing columns
    cur.execute("PRAGMA table_info(assets)")
    existing_cols = {row[1] for row in cur.fetchall()}
    
    # Add created_by column if missing
    if "created_by" not in existing_cols:
        print("[MIGRATION] Adding created_by column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN created_by INTEGER")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.created_by")
    else:
        print("[MIGRATION] ✅ assets.created_by already exists")
    
    # Add address_line1, address_line2 if missing (for structured addresses)
    if "address_line1" not in existing_cols:
        print("[MIGRATION] Adding address_line1 column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN address_line1 TEXT")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.address_line1")
    
    if "address_line2" not in existing_cols:
        print("[MIGRATION] Adding address_line2 column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN address_line2 TEXT")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.address_line2")
    
    # Add postal_code if missing (standardized name)
    if "postal_code" not in existing_cols:
        print("[MIGRATION] Adding postal_code column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN postal_code TEXT")
        # Backfill from zip_code if it exists
        if "zip_code" in existing_cols:
            cur.execute("UPDATE assets SET postal_code = zip_code WHERE postal_code IS NULL")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.postal_code")
    
    # Add country column if missing
    if "country" not in existing_cols:
        print("[MIGRATION] Adding country column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN country TEXT DEFAULT 'US'")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.country")
    
    # Add source columns if missing
    if "source" not in existing_cols:
        print("[MIGRATION] Adding source column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN source TEXT DEFAULT 'property_search'")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.source")
    
    if "source_ref" not in existing_cols:
        print("[MIGRATION] Adding source_ref column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN source_ref TEXT")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.source_ref")
    
    # Add property_data column if missing
    if "property_data" not in existing_cols:
        print("[MIGRATION] Adding property_data column to assets...")
        cur.execute("ALTER TABLE assets ADD COLUMN property_data TEXT DEFAULT '{}'")
        conn.commit()
        print("[MIGRATION] ✅ Added assets.property_data")
    
    # Ensure indexes for tenant filtering
    print("[MIGRATION] Creating indexes for assets...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_account_created ON assets(account_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_account_name ON assets(account_id, name COLLATE NOCASE)")
    conn.commit()
    print("[MIGRATION] ✅ Created assets indexes")
    
    # ========================================================================
    # STEP 2: Create or update property_index table (tenant-scoped search cache)
    # ========================================================================
    print("[MIGRATION] Checking property_index table...")
    
    # Check if table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='property_index'")
    table_exists = cur.fetchone() is not None
    
    if not table_exists:
        print("[MIGRATION] Creating property_index table...")
        cur.execute("""
            CREATE TABLE property_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                address_line1 TEXT,
                city TEXT,
                state TEXT,
                postal_code TEXT,
                country TEXT DEFAULT 'US',
                display_address TEXT,
                data TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("[MIGRATION] ✅ Created property_index table")
    else:
        print("[MIGRATION] ✅ property_index table already exists")
        
        # Ensure account_id column exists
        cur.execute("PRAGMA table_info(property_index)")
        property_index_cols = {row[1] for row in cur.fetchall()}
        
        if "account_id" not in property_index_cols:
            print("[MIGRATION] Adding account_id column to property_index...")
            cur.execute("ALTER TABLE property_index ADD COLUMN account_id INTEGER NOT NULL DEFAULT 1")
            conn.commit()
            print("[MIGRATION] ✅ Added property_index.account_id")
    
    # Create indexes for property_index
    print("[MIGRATION] Creating indexes for property_index...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_index_account_address ON property_index(account_id, display_address COLLATE NOCASE)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_index_account_city ON property_index(account_id, city COLLATE NOCASE)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_property_index_account_postal ON property_index(account_id, postal_code)")
    conn.commit()
    print("[MIGRATION] ✅ Created property_index indexes")
    
    # ========================================================================
    # STEP 3: Backfill account_id for legacy data (DEV ONLY)
    # ========================================================================
    print("[MIGRATION] Checking for legacy data to backfill...")
    
    # Backfill assets.account_id if NULL (set to 1 for dev)
    cur.execute("SELECT COUNT(*) FROM assets WHERE account_id IS NULL")
    null_account_count = cur.fetchone()[0]
    if null_account_count > 0:
        print(f"[MIGRATION] Backfilling {null_account_count} assets with account_id=1...")
        cur.execute("UPDATE assets SET account_id = 1 WHERE account_id IS NULL")
        conn.commit()
        print(f"[MIGRATION] ✅ Backfilled {null_account_count} assets")
    
    # Backfill property_index.account_id if NULL (set to 1 for dev)
    cur.execute("SELECT COUNT(*) FROM property_index WHERE account_id IS NULL")
    null_property_index_count = cur.fetchone()[0]
    if null_property_index_count > 0:
        print(f"[MIGRATION] Backfilling {null_property_index_count} property_index rows with account_id=1...")
        cur.execute("UPDATE property_index SET account_id = 1 WHERE account_id IS NULL")
        conn.commit()
        print(f"[MIGRATION] ✅ Backfilled {null_property_index_count} property_index rows")
    
    # ========================================================================
    # STEP 4: Seed property_index with sample data for testing (if empty)
    # ========================================================================
    cur.execute("SELECT COUNT(*) FROM property_index")
    property_index_count = cur.fetchone()[0]
    
    if property_index_count == 0:
        print("[MIGRATION] Seeding property_index with sample data...")
        sample_properties = [
            (1, "123 Main St", "Atlanta", "GA", "30301", "US", "123 Main St, Atlanta, GA 30301", '{"beds": 3, "baths": 2.0, "sqft": 1500, "est_price": 250000}'),
            (1, "456 Oak Ave", "Atlanta", "GA", "30302", "US", "456 Oak Ave, Atlanta, GA 30302", '{"beds": 4, "baths": 2.5, "sqft": 2000, "est_price": 325000}'),
            (1, "789 Pine Rd", "Decatur", "GA", "30030", "US", "789 Pine Rd, Decatur, GA 30030", '{"beds": 2, "baths": 1.0, "sqft": 1100, "est_price": 175000}'),
            (1, "321 Elm St", "Atlanta", "GA", "30303", "US", "321 Elm St, Atlanta, GA 30303", '{"beds": 3, "baths": 2.0, "sqft": 1600, "est_price": 280000}'),
            (1, "654 Maple Dr", "Marietta", "GA", "30060", "US", "654 Maple Dr, Marietta, GA 30060", '{"beds": 4, "baths": 3.0, "sqft": 2200, "est_price": 375000}'),
        ]
        
        for prop in sample_properties:
            cur.execute("""
                INSERT INTO property_index (account_id, address_line1, city, state, postal_code, country, display_address, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, prop)
        
        conn.commit()
        print(f"[MIGRATION] ✅ Seeded {len(sample_properties)} sample properties")
    
    # ========================================================================
    # DONE
    # ========================================================================
    conn.close()
    print("[MIGRATION] ✅ Migration completed successfully!")
    print("[MIGRATION] Summary:")
    print("[MIGRATION]   - assets table: hardened with created_by, structured addresses, tenant indexes")
    print("[MIGRATION]   - property_index table: created/updated with tenant isolation")
    print("[MIGRATION]   - Legacy data: backfilled with account_id=1 (dev)")
    print("[MIGRATION]   - Sample data: seeded if property_index was empty")


if __name__ == "__main__":
    migrate()
