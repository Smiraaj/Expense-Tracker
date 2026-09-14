"""
Expense Tracker — Streamlit app
Username + password accounts (no email, ever). Each account has its own
private budget and expense history, stored locally in expense_tracker.db.
"""

import streamlit as st
from datetime import datetime
import calendar as cal_module
import pandas as pd
import plotly.express as px

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

    tab_home, tab_add, tab_history, tab_calendar, tab_categories = st.tabs(
        ["🏠 Home", "➕ Add", "📜 History", "📅 Calendar", "📊 Categories"]
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

    # ------------------------------ CALENDAR ------------------------------
    with tab_calendar:
        render_calendar_tab(username, month, daily_avg, all_expenses)

    # ------------------------------ CATEGORIES ------------------------------
    with tab_categories:
        if not month_expenses:
            st.caption("No spending logged this month yet.")
        else:
            cat_totals = {}
            for e in month_expenses:
                cat_totals[e["category"]] = cat_totals.get(e["category"], 0) + e["amount"]
            cat_items = sorted(cat_totals.items(), key=lambda x: -x[1])
            cat_df = pd.DataFrame(cat_items, columns=["Category", "Amount"])

            fig = px.pie(
                cat_df, names="Category", values="Amount", hole=0.45,
                color="Category",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=True, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, width='stretch')

            for cat, amt in cat_items:
                icon = CATEGORY_ICONS.get(cat, "📒")
                st.write(f"{icon} **{cat}** — {rupees(amt)}")


# ---------------------------------------------------------------------------
# Calendar tab
# ---------------------------------------------------------------------------

def render_calendar_tab(username, month, daily_avg, all_expenses):
    if "calendar_view_month" not in st.session_state:
        st.session_state.calendar_view_month = month  # 'YYYY-MM'
    if "calendar_selected_day" not in st.session_state:
        st.session_state.calendar_selected_day = None  # 'YYYY-MM-DD'

    view_month = st.session_state.calendar_view_month
    year, mon = map(int, view_month.split("-"))

    # --- month navigation ---
    nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
    if nav_prev.button("◀", key="cal_prev", width='stretch'):
        prev_year, prev_mon = (year - 1, 12) if mon == 1 else (year, mon - 1)
        st.session_state.calendar_view_month = f"{prev_year}-{prev_mon:02d}"
        st.session_state.calendar_selected_day = None
        st.rerun()
    nav_label.markdown(f"<h4 style='text-align:center'>{month_label(view_month)}</h4>", unsafe_allow_html=True)
    if nav_next.button("▶", key="cal_next", width='stretch'):
        next_year, next_mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
        st.session_state.calendar_view_month = f"{next_year}-{next_mon:02d}"
        st.session_state.calendar_selected_day = None
        st.rerun()

    # Daily avg only really applies to the month it was set for.
    view_settings = db.get_budget(username, view_month)
    view_daily_avg = (
        (view_settings["budget"] - view_settings["savings"]) / 30 if view_settings else None
    )

    # Totals per day for this displayed month
    day_totals = {}
    for e in all_expenses:
        if e["occurred_at"][:7] == view_month:
            day_key = e["occurred_at"][:10]
            day_totals[day_key] = day_totals.get(day_key, 0) + e["amount"]

    if view_daily_avg is None:
        st.caption("No budget was set for this month, so there's nothing to compare days against.")
    else:
        st.caption(f"Days spending over {rupees(view_daily_avg)} (this month's Daily Avg) are shown in red.")

    weekday_cols = st.columns(7)
    for col, name in zip(weekday_cols, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        col.markdown(f"<div style='text-align:center;color:#888;font-size:12px'>{name}</div>", unsafe_allow_html=True)

    weeks = cal_module.monthcalendar(year, mon)
    today_str = datetime.now().strftime("%Y-%m-%d")

    for week in weeks:
        cols = st.columns(7)
        for col, day_num in zip(cols, week):
            if day_num == 0:
                col.write("")
                continue
            day_key = f"{view_month}-{day_num:02d}"
            day_total = day_totals.get(day_key, 0)
            is_over = view_daily_avg is not None and day_total > view_daily_avg
            is_today = day_key == today_str

            label = str(day_num)
            if day_total > 0:
                label += " 🔴" if is_over else " •"

            btn_type = "primary" if is_over else ("secondary" if is_today else "tertiary")
            if col.button(label, key=f"cal_day_{day_key}", width='stretch', type=btn_type):
                st.session_state.calendar_selected_day = day_key
                st.rerun()

    st.divider()
    selected = st.session_state.calendar_selected_day
    if selected and selected[:7] == view_month:
        day_expenses = [e for e in all_expenses if e["occurred_at"][:10] == selected]
        pretty_date = datetime.strptime(selected, "%Y-%m-%d").strftime("%d %B %Y")
        day_total = sum(e["amount"] for e in day_expenses)
        st.markdown(f"#### {pretty_date} — {rupees(day_total)}")
        if not day_expenses:
            st.caption("No expenses logged on this day.")
        else:
            for e in sorted(day_expenses, key=lambda x: x["occurred_at"], reverse=True):
                icon = CATEGORY_ICONS.get(e["category"], "📒")
                dt = datetime.fromisoformat(e["occurred_at"])
                col_a, col_b = st.columns([4, 1])
                col_a.write(f"{icon} **{e['description']}** — {e['category']} · {dt.strftime('%I:%M %p')}")
                col_b.write(rupees(e["amount"]))
    else:
        st.caption("Tap a day above to see what you spent on it.")


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
