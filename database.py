"""
Database layer for Expense Tracker.
Uses a real, persistent Postgres database (e.g. a free Supabase project's
database) instead of a local file - so data survives app restarts, sleeps,
and redeploys on Streamlit Community Cloud, none of which a local SQLite
file can survive there.

Every function is careful to only touch the data belonging to the given
username, so multiple people can safely share one deployment.
"""

import bcrypt
import streamlit as st
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from datetime import datetime
from contextlib import contextmanager


@st.cache_resource
def _get_pool():
    """One shared connection pool per app instance, reused across reruns."""
    db_url = st.secrets["DATABASE_URL"]
    return ThreadedConnectionPool(minconn=1, maxconn=5, dsn=db_url)


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR'
            )
        """)
        # Safe to run every time - a no-op once the column already exists.
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'INR'")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
                occurred_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                month TEXT NOT NULL,
                budget NUMERIC(12,2) NOT NULL CHECK (budget > 0),
                savings NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (savings >= 0),
                PRIMARY KEY (username, month)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS day_notes (
                username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                day TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (username, day)
            )
        """)
        cur.close()


# ---------------------------------------------------------------------------
# Users / auth
# ---------------------------------------------------------------------------

def username_exists(username):
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute("SELECT 1 FROM users WHERE lower(username) = lower(%s)", (username,))
        row = cur.fetchone()
        cur.close()
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
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at, currency) VALUES (%s, %s, %s, %s)",
            (username, password_hash, datetime.now().isoformat(), currency),
        )
        cur.close()


def get_currency(username):
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute("SELECT currency FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        cur.close()
    return row["currency"] if row else "INR"


def set_currency(username, currency):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET currency = %s WHERE username = %s", (currency, username))
        cur.close()


def verify_login(username, password):
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT username, password_hash FROM users WHERE lower(username) = lower(%s)",
            (username.strip(),),
        )
        row = cur.fetchone()
        cur.close()
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
        cur = _dict_cursor(conn)
        cur.execute(
            "INSERT INTO expenses (username, description, category, amount, occurred_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, description, category, amount, occurred_at",
            (username, description.strip(), category, round(float(amount), 2), datetime.now().isoformat()),
        )
        row = cur.fetchone()
        cur.close()
    return {**dict(row), "amount": float(row["amount"])}


def get_expenses(username):
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, description, category, amount, occurred_at "
            "FROM expenses WHERE username = %s ORDER BY occurred_at DESC",
            (username,),
        )
        rows = cur.fetchall()
        cur.close()
    return [{**dict(r), "amount": float(r["amount"])} for r in rows]


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

def get_budget(username, month):
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT budget, savings FROM budgets WHERE username = %s AND month = %s",
            (username, month),
        )
        row = cur.fetchone()
        cur.close()
    if row is None:
        return None
    return {"budget": float(row["budget"]), "savings": float(row["savings"])}


def set_budget(username, month, budget, savings):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO budgets (username, month, budget, savings) VALUES (%s, %s, %s, %s)
            ON CONFLICT (username, month) DO UPDATE SET budget = excluded.budget, savings = excluded.savings
            """,
            (username, month, budget, savings),
        )
        cur.close()


# ---------------------------------------------------------------------------
# Day notes (e.g. "outing day, that's why spending was high")
# ---------------------------------------------------------------------------

def get_day_note(username, day):
    with get_conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT note FROM day_notes WHERE username = %s AND day = %s",
            (username, day),
        )
        row = cur.fetchone()
        cur.close()
    return row["note"] if row else ""


def set_day_note(username, day, note):
    note = note.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        if note:
            cur.execute(
                """
                INSERT INTO day_notes (username, day, note) VALUES (%s, %s, %s)
                ON CONFLICT (username, day) DO UPDATE SET note = excluded.note
                """,
                (username, day, note),
            )
        else:
            cur.execute(
                "DELETE FROM day_notes WHERE username = %s AND day = %s", (username, day)
            )
        cur.close()
