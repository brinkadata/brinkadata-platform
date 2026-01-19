# backend/db.py
# Database abstraction layer supporting PostgreSQL (production) and SQLite (dev)

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Union, Any
from urllib.parse import urlparse

try:
    from sqlalchemy import create_engine, text, pool
    from sqlalchemy.engine import Engine, Connection
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    Engine = None
    Connection = None

from backend.config import DATABASE_PATH

# Database URL from environment (Render provides this for managed Postgres)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Detect database type
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
IS_SQLITE = not IS_POSTGRES

# Global engine (SQLAlchemy) or None for SQLite
_engine: Union[Engine, None] = None


def init_engine() -> None:
    """Initialize SQLAlchemy engine for PostgreSQL if DATABASE_URL is set."""
    global _engine
    
    if not IS_POSTGRES:
        # SQLite mode - no engine needed
        _engine = None
        print("[DB] Using SQLite (local dev mode)")
        return
    
    if not SQLALCHEMY_AVAILABLE:
        raise RuntimeError(
            "PostgreSQL mode requires SQLAlchemy. Install: pip install sqlalchemy psycopg2-binary"
        )
    
    # Parse and validate URL
    parsed = urlparse(DATABASE_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid DATABASE_URL: {DATABASE_URL[:20]}...")
    
    # Create engine with connection pooling
    _engine = create_engine(
        DATABASE_URL,
        poolclass=pool.QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before use
        echo=False,  # Set True for SQL debugging
    )
    
    print(f"[DB] Using PostgreSQL ({parsed.hostname})")


@contextmanager
def get_db_connection() -> Generator[Union[sqlite3.Connection, Connection], None, None]:
    """
    Context manager for database connections.
    Returns sqlite3.Connection for SQLite or sqlalchemy.Connection for Postgres.
    """
    if IS_POSTGRES:
        if _engine is None:
            init_engine()
        
        # SQLAlchemy connection
        with _engine.connect() as conn:
            yield conn
    else:
        # SQLite connection
        from pathlib import Path as FsPath
        db_path = str(FsPath(__file__).resolve().parent / DATABASE_PATH)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def execute_query(
    conn: Union[sqlite3.Connection, Connection],
    query: str,
    params: Union[tuple, dict, None] = None,
) -> Any:
    """
    Execute a query with parameters.
    Handles differences between SQLite and PostgreSQL parameter styles.
    
    Args:
        conn: Database connection
        query: SQL query (use ? for SQLite, :param for named params)
        params: Query parameters (tuple for positional, dict for named)
    
    Returns:
        Cursor (SQLite) or ResultProxy (PostgreSQL)
    """
    if IS_POSTGRES:
        # Convert SQLite ? placeholders to PostgreSQL $1, $2, etc.
        if "?" in query and isinstance(params, (tuple, list)):
            # Replace ? with $1, $2, etc.
            parts = query.split("?")
            pg_query = parts[0]
            for i in range(1, len(parts)):
                pg_query += f"${i}" + parts[i]
            query = pg_query
        
        # Execute with SQLAlchemy
        return conn.execute(text(query), params or {})
    else:
        # Execute with sqlite3
        cur = conn.cursor()
        if params:
            return cur.execute(query, params)
        else:
            return cur.execute(query)


def commit(conn: Union[sqlite3.Connection, Connection]) -> None:
    """Commit transaction (handles SQLite and Postgres differences)."""
    if IS_POSTGRES:
        conn.commit()
    else:
        conn.commit()


def rollback(conn: Union[sqlite3.Connection, Connection]) -> None:
    """Rollback transaction (handles SQLite and Postgres differences)."""
    if IS_POSTGRES:
        conn.rollback()
    else:
        conn.rollback()


def get_cursor(conn: Union[sqlite3.Connection, Connection]) -> Any:
    """Get cursor for raw SQL execution (compatibility layer)."""
    if IS_POSTGRES:
        # Return connection itself (SQLAlchemy pattern)
        return conn
    else:
        return conn.cursor()


# Initialize engine on module import if Postgres mode
if IS_POSTGRES and _engine is None:
    init_engine()
