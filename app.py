import os
import re
import sqlite3
import pandas as pd
import streamlit as st

st.set_page_config(page_title="OSU P-Card Audit Dashboard", layout="wide")
st.title("🛡️ OSU P-Card Audit & Forensic Dashboard")


# 1. Database Connection & Dynamic Reassembly
@st.cache_resource
def get_connection():
    db_file = "pcards.db"

    # Stitch the 5 parts back together if pcards.db doesn't exist on server
    if not os.path.exists(db_file):
        parts = [f"pcards.db.p{i}" for i in range(1, 6)]
        if all(os.path.exists(p) for p in parts):
            with open(db_file, "wb") as outfile:
                for p in parts:
                    with open(p, "rb") as infile:
                        outfile.write(infile.read())

    return sqlite3.connect(db_file, check_same_thread=False)


# 2. Natural Language Parsing Engine
def parse_natural_language(text):
    text_lower = text.lower().strip()

    if "employee" in text_lower and (
        "more than" in text_lower or ">" in text_lower or "over" in text_lower
    ):
        amount_match = re.search(r"\$?(\d+[\d,.]*)", text_lower)
        amount = (
            amount_match.group(1).replace(",", "") if amount_match else "5000"
        )
        return f"SELECT FullName, SUM(Amount) as Total_Spend FROM pcards GROUP BY FullName HAVING Total_Spend > {amount} ORDER BY Total_Spend DESC;"

    elif "top" in text_lower and "vendor" in text_lower:
        limit_match = re.search(r"top\s+(\d+)", text_lower)
        limit = limit_match.group(1) if limit_match else "10"
        return f"SELECT Vendor, SUM(Amount) as Total_Spend, COUNT(*) as Transaction_Count FROM pcards GROUP BY Vendor ORDER BY Total_Spend DESC LIMIT {limit};"

    elif (
        "containing" in text_lower
        or "with" in text_lower
        or "show" in text_lower
    ):
        for word in ["alcohol", "gift card", "liquor", "walmart", "amazon"]:
            if word in text_lower:
                return f"SELECT * FROM pcards WHERE Description LIKE '%{word.upper()}%' OR MCC LIKE '%{word.upper()}%';"

    elif "over" in text_lower or "greater than" in text_lower:
        amount_match = re.search(r"\$?(\d+[\d,.]*)", text_lower)
        amount = (
            amount_match.group(1).replace(",", "") if amount_match else "5000"
        )
        return (
            f"SELECT * FROM pcards WHERE Amount > {amount} ORDER BY Amount DESC;"
        )

    return text


# 3. User Interface Tabs
tab1, tab2 = st.tabs(
    ["💬 Natural Language Query", "🔍 Prohibited Purchase Search"]
)

# TAB 1: Natural Language Query
with tab1:
    st.header("Ask the Database")
    st.write("Type your question in plain English:")

    user_prompt = st.text_input(
        "Enter natural language question or SQL query:", value=""
    )

    if st.button("Run Query"):
        if user_prompt:
            translated_sql = parse_natural_language(user_prompt)
            st.caption(f"**Executed SQL:** `{translated_sql}`")

            conn = get_connection()
            try:
                df_result = pd.read_sql_query(translated_sql, conn)
                st.success(f"Query returned {len(df_result)} results.")
                st.dataframe(df_result, use_container_width=True)
            except Exception as e:
                st.error(f"Could not execute query. Error: {e}")

# TAB 2: Interactive Forensic Search
with tab2:
    st.header("Interactive Transaction Search")
    col1, col2, col3 = st.columns(3)
    with col1:
        search_desc = st.text_input(
            "Search Description Keyword:", placeholder="e.g., Walmart, Cash"
        )
    with col2:
        search_vendor = st.text_input(
            "Search Vendor Name:", placeholder="e.g., Amazon, Lowes"
        )
    with col3:
        min_amount = st.number_input(
            "Min Transaction Amount ($):", min_value=0.0, value=0.0, step=100.0
        )

    base_sql = "SELECT * FROM pcards WHERE Amount >= ?"
    params = [min_amount]

    if search_desc:
        base_sql += " AND Description LIKE ?"
        params.append(f"%{search_desc}%")
    if search_vendor:
        base_sql += " AND Vendor LIKE ?"
        params.append(f"%{search_vendor}%")

    base_sql += " LIMIT 500;"

    conn = get_connection()
    df_filtered = pd.read_sql_query(base_sql, conn, params=params)

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Flagged Transactions", f"{len(df_filtered):,}")
    m2.metric(
        "Total Flagged Spend",
        f"${df_filtered['Amount'].sum():,.2f}" if not df_filtered.empty else "$0",
    )
    m3.metric(
        "Average Flagged Spend",
        f"${df_filtered['Amount'].mean():,.2f}"
        if not df_filtered.empty
        else "$0",
    )

    st.dataframe(df_filtered, use_container_width=True)