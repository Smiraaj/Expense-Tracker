"""
Expense Tracker — Streamlit app
Username + password accounts (no email, ever). Each account has its own
private budget and expense history, stored locally in expense_tracker.db.
"""

import streamlit as st
from datetime import datetime
import pandas as pd

import database as db

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="centered")

db.init_db()

CATEGORIES = ["Food", "Transport", "Rent", "Bills", "Fun", "Health", "Shopping", "Other"]
CATEGORY_ICONS = {
    "Food": "🍛", "Transport": "🚌", "Rent": "🏠", "Bills": "💡",
    "Fun": "🎬", "Health": "💊", "Shopping": "🛍️", "Other": "📒",
}


def rupees(amount):
    return f"₹{amount:,.2f}"


def current_month():
    return datetime.now().strftime("%Y-%m")


def month_label(key):
    return datetime.strptime(key, "%Y-%m").strftime("%B %Y")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "username" not in st.session_state:
    st.session_state.username = None

# ---------------------------------------------------------------------------
# Auth screen
# ---------------------------------------------------------------------------

def auth_screen():
    st.title("💰 Expense Tracker")
    st.caption("No email or phone number is ever asked for — just a username and password.")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", width='stretch', type="primary")
            if submitted:
                try:
                    resolved = db.verify_login(username, password)
                    st.session_state.username = resolved
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with tab_signup:
        with st.form("signup_form"):
            username = st.text_input("Choose a username", key="signup_username")
            password = st.text_input("Choose a password", type="password", key="signup_password",
                                      help="At least 6 characters")
            confirm = st.text_input("Confirm password", type="password", key="signup_confirm")
            submitted = st.form_submit_button("Create account", width='stretch', type="primary")
            if submitted:
                if password != confirm:
                    st.error("Passwords don't match.")
                else:
                    try:
                        db.create_user(username, password)
                        st.session_state.username = username.strip()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    st.info(
        "Heads up: since no email or phone is collected, there's no automated "
        "password recovery. If you forget your password, you'll need a new account.",
        icon="ℹ️",
    )


# ---------------------------------------------------------------------------
# Onboarding (first login, or a new month with no budget set yet)
# ---------------------------------------------------------------------------

def onboarding_screen(username, month):
    st.title("💰 Expense Tracker")
    st.subheader(f"Set up {month_label(month)}")
    st.write("A new month starts fresh. Set your budget and saving goal — last "
             "month's ledger stays saved for you to look back on anytime.")

    with st.form("onboard_form"):
        budget = st.number_input("Monthly budget (₹)", min_value=1.0, step=100.0)
        savings = st.number_input("Saving goal (₹)", min_value=0.0, step=100.0)
        submitted = st.form_submit_button("Start tracking", width='stretch', type="primary")
        if submitted:
            if budget <= 0:
                st.error("Enter a valid monthly budget.")
            else:
                db.set_budget(username, month, budget, savings)
                st.rerun()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main_app(username, month):
    settings = db.get_budget(username, month)

    with st.sidebar:
        st.markdown(f"### 👤 {username}")
        if st.button("Log out", width='stretch'):
            st.session_state.username = None
            st.rerun()

        st.divider()
        st.markdown(f"**Edit budget for {month_label(month)}**")
        with st.form("edit_budget_form"):
            new_budget = st.number_input("Monthly budget (₹)", min_value=1.0, step=100.0,
                                          value=float(settings["budget"]))
            new_savings = st.number_input("Saving goal (₹)", min_value=0.0, step=100.0,
                                           value=float(settings["savings"]))
            if st.form_submit_button("Save", width='stretch'):
                db.set_budget(username, month, new_budget, new_savings)
                st.rerun()

    all_expenses = db.get_expenses(username)
    month_expenses = [e for e in all_expenses if e["occurred_at"][:7] == month]

    spent = sum(e["amount"] for e in month_expenses)
    remaining = settings["budget"] - spent
    daily_avg = (settings["budget"] - settings["savings"]) / 30

    st.title("💰 Expense Tracker")
    st.caption(month_label(month))

    tab_home, tab_add, tab_history, tab_categories = st.tabs(
        ["🏠 Home", "➕ Add", "📜 History", "📊 Categories"]
    )

    # ------------------------------ HOME ------------------------------
    with tab_home:
        c1, c2 = st.columns(2)
        c1.metric("Remaining this month", rupees(remaining))
        c2.metric("Spent so far", rupees(spent))

        pct_used = min(1.0, spent / settings["budget"]) if settings["budget"] > 0 else 0
        st.progress(pct_used)
        if remaining < 0:
            st.warning(f"You've gone {rupees(abs(remaining))} over budget this month.")

        c3, c4 = st.columns(2)
        c3.metric("Saving goal", rupees(settings["savings"]))
        c4.metric("Daily avg", rupees(daily_avg))

        st.markdown("#### Recent entries")
        recent = month_expenses[:5]
        if not recent:
            st.caption("No entries yet this month. Use the **Add** tab to log your first one.")
        else:
            for e in recent:
                icon = CATEGORY_ICONS.get(e["category"], "📒")
                dt = datetime.fromisoformat(e["occurred_at"])
                col_a, col_b = st.columns([4, 1])
                col_a.write(f"{icon} **{e['description']}** — {e['category']} · {dt.strftime('%d %b, %I:%M %p')}")
                col_b.write(rupees(e["amount"]))

    # ------------------------------ ADD ------------------------------
    with tab_add:
        with st.form("add_expense_form", clear_on_submit=True):
            description = st.text_input("What was it for")
            category = st.selectbox("Category", CATEGORIES)
            amount = st.number_input("Amount (₹)", min_value=0.01, step=10.0)
            submitted = st.form_submit_button("Add to ledger", width='stretch', type="primary")
            if submitted:
                if not description.strip():
                    st.error("Add a short description for this expense.")
                elif amount <= 0:
                    st.error("Amount must be a positive number.")
                else:
                    db.add_expense(username, description, category, amount)
                    st.success("Expense added!")
                    st.rerun()

    # ------------------------------ HISTORY ------------------------------
    with tab_history:
        if not all_expenses:
            st.caption("Nothing recorded yet. Every entry you add will show up here, across all months.")
        else:
            df = pd.DataFrame(all_expenses)
            df["occurred_at"] = pd.to_datetime(df["occurred_at"])
            df = df.sort_values("occurred_at", ascending=False)
            df_display = pd.DataFrame({
                "Date & time": df["occurred_at"].dt.strftime("%d %b %Y, %I:%M %p"),
                "Description": df["description"],
                "Category": df["category"],
                "Amount": df["amount"].apply(rupees),
            })
            st.dataframe(df_display, width='stretch', hide_index=True)

    # ------------------------------ CATEGORIES ------------------------------
    with tab_categories:
        if not month_expenses:
            st.caption("No spending logged this month yet.")
        else:
            cat_totals = {}
            for e in month_expenses:
                cat_totals[e["category"]] = cat_totals.get(e["category"], 0) + e["amount"]
            cat_df = pd.DataFrame(
                sorted(cat_totals.items(), key=lambda x: -x[1]), columns=["Category", "Amount"]
            ).set_index("Category")
            st.bar_chart(cat_df)
            for cat, amt in sorted(cat_totals.items(), key=lambda x: -x[1]):
                icon = CATEGORY_ICONS.get(cat, "📒")
                st.write(f"{icon} **{cat}** — {rupees(amt)}")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if st.session_state.username is None:
    auth_screen()
else:
    _month = current_month()
    _settings = db.get_budget(st.session_state.username, _month)
    if _settings is None:
        onboarding_screen(st.session_state.username, _month)
    else:
        main_app(st.session_state.username, _month)