import pymysql
import pymysql.cursors
import os
from flask import g

DB_CONFIG = {
    'host':        os.environ.get('DB_HOST', 'localhost'),
    'port':        int(os.environ.get('DB_PORT', 3307)),
    'user':        os.environ.get('DB_USER', 'root'),
    'password':    os.environ.get('DB_PASSWORD', ''),
    'database':    os.environ.get('DB_NAME', 'cal_ai'),
    'cursorclass': pymysql.cursors.DictCursor,
    'charset':     'utf8mb4',
    'autocommit':  True, # Changed to True so changes save automatically like SQLite
}

class DBWrapper:
    """Wraps PyMySQL connection to support .execute() like SQLite."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, args=None):
        cur = self._conn.cursor()
        cur.execute(sql, args or ())
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

def get_db():
    # Crucial fix: Check if 'db' exists AND is actually an instance of DBWrapper
    if 'db' not in g or not isinstance(g.db, DBWrapper):
        conn = pymysql.connect(**DB_CONFIG)
        g.db = DBWrapper(conn)
    return g.db

def close_db(e=None):
    # Retrieve the wrapper from g and safely pop it
    db = g.pop('db', None)
    if db is not None and isinstance(db, DBWrapper):
        db.close()

def init_db():
    try:
        # Connect WITHOUT specifying database first, so we can create it if needed
        cfg_no_db = {k: v for k, v in DB_CONFIG.items() if k != 'database'}
        conn = pymysql.connect(**cfg_no_db)
        with conn.cursor() as cur:
            db_name = DB_CONFIG['database']
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"USE `{db_name}`")
        conn.commit()
        conn.close()
        print(f'[DB] Database `{DB_CONFIG["database"]}` ensured.')
    except Exception as e:
        print(f'[DB] ERROR: Cannot connect -- {e}')
        print('[DB] Steps: 1) Start XAMPP MySQL  2) Import cal_ai.sql in phpMyAdmin')
        raise

    # Now connect normally and ensure push-related tables exist
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # push_subscriptions — stores Web Push endpoint per user
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `push_subscriptions` (
                    `id`                INT AUTO_INCREMENT PRIMARY KEY,
                    `user_id`           INT NOT NULL UNIQUE,
                    `subscription_json` TEXT NOT NULL,
                    `created_at`        DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # user_settings — stores per-user reminder times (JSON)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `user_settings` (
                    `user_id`        INT PRIMARY KEY,
                    `reminder_times` TEXT DEFAULT NULL,
                    `updated_at`     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
        conn.close()
        print('[DB] push_subscriptions + user_settings tables ensured.')
    except Exception as e:
        # Non-fatal: tables might already exist with FK constraints from manual SQL import
        print(f'[DB] Table ensure warning (non-fatal): {e}')

    print('[DB] Connected to MySQL successfully.')