# ==============================================================================
# Module: database.py
# Author: Yunzhe Yu (Backend & DevOps)
# Description: Persistent SQLite storage layer for user accounts, hashed 
#              credentials, bearer session tokens, and saved search history.
# ==============================================================================

import os
import secrets
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sneaker_compare.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                lowest_price REAL,
                platform TEXT,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)


def create_user(username: str, password: str) -> bool:
    pw_hash = generate_password_hash(password)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username.strip(), pw_hash)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def authenticate_user(username: str, password: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),)
        ).fetchone()

        if not row or not check_password_hash(row["password_hash"], password):
            return None

        token = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
            (token, row["id"])
        )
        return {"id": row["id"], "username": row["username"], "token": token}


def get_user_by_token(token: str):
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute("""
            SELECT u.id, u.username
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
        """, (token,)).fetchone()
        return dict(row) if row else None


def revoke_token(token: str):
    if not token:
        return
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def save_search(user_id: int, query: str, lowest_price=None, platform=None):
    clean_query = query.strip()
    if not clean_query:
        return
    with get_connection() as conn:
        # Remove older duplicate of the same query so recent history stays clean
        conn.execute(
            "DELETE FROM search_history WHERE user_id = ? AND LOWER(query) = LOWER(?)",
            (user_id, clean_query)
        )
        conn.execute(
            "INSERT INTO search_history (user_id, query, lowest_price, platform) VALUES (?, ?, ?, ?)",
            (user_id, clean_query, lowest_price, platform)
        )


def get_search_history(user_id: int, limit: int = 8):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT query, lowest_price, platform, searched_at
            FROM search_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def clear_search_history(user_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM search_history WHERE user_id = ?", (user_id,))