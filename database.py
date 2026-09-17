import streamlit as st
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

# ------------------------------------------------------------------------------
# 1. Database Connection & Pooling Setup
# ------------------------------------------------------------------------------
@st.cache_resource
def get_connection_pool():
    """
    Creates a single shared connection pool across all users.
    @st.cache_resource ensures the pool stays open and reused.
    """
    db_url = st.secrets["DATABASE_URL"]
    return ThreadedConnectionPool(minconn=1, maxconn=10, dsn=db_url)

@contextmanager
def get_conn():
    """Context manager to safely get and return a connection from the pool."""
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

def init_db():
    """Initializes tables if they do not already exist in Supabase."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

# ------------------------------------------------------------------------------
# 2. READ Operations (Cached for Speed)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_expenses(user_id: str):
    """
    Fetches user expenses. Cached for 60 seconds to avoid repeating DB calls 
    on every Streamlit rerun or UI click.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, category, amount, description, created_at 
                FROM expenses 
                WHERE user_id = %s 
                ORDER BY created_at DESC;
            """, (user_id,))
            rows = cur.fetchall()
            return rows

@st.cache_data(ttl=300)
def get_expense_summary(user_id: str):
    """Fetches category-wise totals for analytical charts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT category, SUM(amount) 
                FROM expenses 
                WHERE user_id = %s 
                GROUP BY category;
            """, (user_id,))
            return cur.fetchall()

# ------------------------------------------------------------------------------
# 3. WRITE / UPDATE / DELETE Operations (Clears Cache)
# ------------------------------------------------------------------------------
def add_expense(user_id: str, category: str, amount: float, description: str):
    """Inserts a new expense and instantly invalidates the query cache."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO expenses (user_id, category, amount, description)
                VALUES (%s, %s, %s, %s);
            """, (user_id, category, amount, description))
            conn.commit()
    
    # Invalidate cache so fresh data displays on next page load
    st.cache_data.clear()

def delete_expense(expense_id: int):
    """Deletes an expense and invalidates the query cache."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM expenses WHERE id = %s;", (expense_id,))
            conn.commit()
            
    # Invalidate cache so fresh data displays on next page load
    st.cache_data.clear()
