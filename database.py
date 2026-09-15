"""
Database layer for Expense Tracker.
Uses a local SQLite file (expense_tracker.db) - no external service needed.
Every function is careful to only touch the data belonging to the given
username, so multiple people can safely share one deployment.
"""

import sqlite3
import bcrypt
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "expense_tracker.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # Migration: add a currency column for accounts created before this
        # feature existed. Safe to run every time - it's a no-op once added.
        try:
            conn.execute("ALTER TABLE users ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                occurred_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                month TEXT NOT NULL,
                budget REAL NOT NULL CHECK (budget > 0),
                savings REAL NOT NULL DEFAULT 0 CHECK (savings >= 0),
                PRIMARY KEY (username, month)
            )
        """)


# ---------------------------------------------------------------------------
# Users / auth
# ---------------------------------------------------------------------------

def username_exists(username):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)
        ).fetchone()
        return row is not None


def create_user(username, password, currency="INR"):
    username = username.strip()
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    if username_exists(username):
        raise ValueError("That username is already taken.")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at, currency) VALUES (?, ?, ?, ?)",
            (username, password_hash, datetime.now().isoformat(), currency),
        )


def get_currency(username):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT currency FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row["currency"] if row else "INR"


def set_currency(username, currency):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET currency = ? WHERE username = ?", (currency, username)
        )


def verify_login(username, password):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT username, password_hash FROM users WHERE lower(username) = lower(?)",
            (username.strip(),),
        ).fetchone()
    if row is None:
        raise ValueError("Incorrect username or password.")
    if not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        raise ValueError("Incorrect username or password.")
    return row["username"]  # canonical stored casing


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

def add_expense(username, description, category, amount):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO expenses (username, description, category, amount, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, description.strip(), category, round(float(amount), 2), datetime.now().isoformat()),
        )


def get_expenses(username):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, description, category, amount, occurred_at "
            "FROM expenses WHERE username = ? ORDER BY occurred_at DESC",
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

def get_budget(username, month):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT budget, savings FROM budgets WHERE username = ? AND month = ?",
            (username, month),
        ).fetchone()
    return dict(row) if row else None


def set_budget(username, month, budget, savings):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO budgets (username, month, budget, savings) VALUES (?, ?, ?, ?)
            ON CONFLICT(username, month) DO UPDATE SET budget = excluded.budget, savings = excluded.savings
            """,
            (username, month, budget, savings),
        )
