import mysql.connector
from mysql.connector import Error, pooling
import os
from dotenv import load_dotenv

load_dotenv(override=True)
# ── Connection pool (created once at import time) ────────────
_pool: pooling.MySQLConnectionPool | None = None


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name='kairaflow_pool',
            pool_size=10,
            pool_reset_session=True,
            host=os.getenv('DB_HOST') or os.getenv('MYSQLHOST', 'localhost'),
            port=int(os.getenv('DB_PORT') or os.getenv('MYSQLPORT', 3306)),
            user=os.getenv('DB_USER') or os.getenv('MYSQLUSER', 'root'),
            password=os.getenv('DB_PASSWORD') or os.getenv('MYSQLPASSWORD', ''),
            database=os.getenv('DB_NAME') or os.getenv('MYSQLDATABASE', 'agencyflow'),
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci',
            autocommit=False,
        )
    return _pool


def get_db_connection():
    """Return a pooled connection. Caller must close() it to return to pool."""
    try:
        return _get_pool().get_connection()
    except Error as e:
        print(f"[DB] Pool connection error: {e}")
        # Fallback: direct connection
        return mysql.connector.connect(
            host=os.getenv('DB_HOST') or os.getenv('MYSQLHOST', 'localhost'),
            port=int(os.getenv('DB_PORT') or os.getenv('MYSQLPORT', 3306)),
            user=os.getenv('DB_USER') or os.getenv('MYSQLUSER', 'root'),
            password=os.getenv('DB_PASSWORD') or os.getenv('MYSQLPASSWORD', ''),
            database=os.getenv('DB_NAME') or os.getenv('MYSQLDATABASE', 'agencyflow'),
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci',
        )
