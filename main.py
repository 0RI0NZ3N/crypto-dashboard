import streamlit as st
import psycopg2
import pandas as pd

# Set up visual browser parameters
st.set_page_config(page_title="Product Overview", page_icon="⚡", layout="wide")

# Custom CSS styling injection to build a clean premium card UI
st.markdown("""
    <style>
    body { background-color: #F8F9FA; }
    .main-title { font-size: 28px; font-weight: 600; color: #1E293B; margin-bottom: 20px; }
    .card-container {
        background-color: #FFFFFF;
        padding: 24px;
        border-radius: 16px;
        box-shadow: 0px 4px 20px rgba(0, 0, 0, 0.04);
        margin-bottom: 24px;
        border: 1px solid #E2E8F0;
    }
    .metric-title { font-size: 14px; font-weight: 500; color: #64748B; margin-bottom: 4px; }
    .metric-value { font-size: 36px; font-weight: 700; color: #0F172A; }
    .metric-delta { font-size: 13px; font-weight: 600; color: #10B981; background-color: #E6F4EA; padding: 4px 8px; border-radius: 20px; display: inline-block; }
    </style>
""", unsafe_allow_index=True)

# Main Title Area
st.markdown('<div class="main-title">Product overview</div>', unsafe_allow_index=True)

def get_db_connection():
    return psycopg2.connect(
        host=st.secrets["DB_HOST"],
        port=st.secrets["DB_PORT"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"]
    )

# Top KPI Metric Card Row
col1, col2 = st.columns(2)

with col1:
    st.markdown("""
        <div class="card-container">
            <div class="metric-title">Active Consolidated Trades</div>
            <div class="metric-value">$128k</div>
            <div class="metric-delta">↑ 36.8% <span style='color:#64748B; font-weight:400;'>vs last year</span></div>
        </div>
    """, unsafe_allow_index=True)

with col2:
    st.markdown("""
        <div class="card-container">
            <div class="metric-title">Win Rate Across Rooms</div>
            <div class="metric-value">512</div>
            <div class="metric-delta" style='color:#EF4444; background-color:#FCE8E6;'>↓ 12.4% <span style='color:#64748B; font-weight:400;'>vs last week</span></div>
        </div>
    """, unsafe_allow_index=True)

# Live Signals Section
st.markdown('<div style="font-size: 20px; font-weight: 600; color: #1E293B; margin-bottom: 12px;">Active Signals Activity</div>', unsafe_allow_index=True)

try:
    conn = get_db_connection()
    query = """
        SELECT ticker as "Asset", 
               trade_type as "Position", 
               COUNT(group_name) as "Rooms Backing",
               ROUND(AVG(entry_min), 2) as "Optimum Entry",
               ROUND(AVG(stop_loss), 2) as "Safety Stop Loss"
        FROM active_signals 
        GROUP BY ticker, trade_type
    """
    df = pd.read_sql(query, conn)
    conn.close()

    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No live parsed alerts found in database. Run scraper.py to capture live messages.")
except Exception:
    # Stylized clean fallback if secrets aren't running locally yet
    mock_data = pd.DataFrame({
        "Asset": ["BTCUSDT", "SOLUSDT", "ETHUSDT"],
        "Position": ["LONG", "LONG", "SHORT"],
        "Rooms Backing": [4, 2, 1],
        "Optimum Entry": [64200.00, 142.50, 3450.00],
        "Safety Stop Loss": [62100.00, 135.00, 3580.00]
    })
    st.dataframe(mock_data, use_container_width=True, hide_index=True)