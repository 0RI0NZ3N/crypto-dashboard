"""
Crypto Signal Intelligence Terminal — v2
Bloomberg-Terminal × Web3 Dark Mode
"""

import streamlit as st
import psycopg2
import pandas as pd
import numpy as np
import os
import datetime
import re
import textwrap
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG — must be the very first Streamlit call
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Signal Intelligence Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — strip leading Python indentation before passing HTML to Streamlit
# ─────────────────────────────────────────────────────────────────────────────
def H(html: str):
    st.markdown(textwrap.dedent(html), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL DESIGN SYSTEM
# ─────────────────────────────────────────────────────────────────────────────
H("""
<style>
/* ── FONTS ──────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap');

/* ── GLOBAL RESET ───────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, .stApp {
    background: #0B0F19 !important;
    color: #CBD5E1 !important;
    font-family: 'Space Grotesk', system-ui, sans-serif;
}

.block-container {
    padding: 1.5rem 2rem 3rem !important;
    max-width: 1400px !important;
}

/* ── HEADINGS ───────────────────────────────────────────────── */
.stApp h1,.stApp h2,.stApp h3 {
    color: #F1F5F9 !important;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700 !important;
    letter-spacing: -0.5px;
}

/* ── SECONDARY TEXT ─────────────────────────────────────────── */
.stApp p, .stApp li, .stApp label { color: #64748B !important; }
.stApp .stMarkdown p { color: #94A3B8 !important; }

/* ── HIDE STREAMLIT CHROME ──────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }

/* ── TABS ───────────────────────────────────────────────────── */
div[data-testid="stTabs"] {
    border-bottom: 1px solid #1E293B;
    margin-bottom: 1.5rem;
}
div[data-testid="stTabs"] button {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #475569 !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 18px !important;
    border-radius: 0 !important;
    transition: all .2s ease;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #38BDF8 !important;
    border-bottom-color: #38BDF8 !important;
}
div[data-testid="stTabs"] button:hover { color: #E2E8F0 !important; }

/* ── FORM CONTROLS ──────────────────────────────────────────── */
.stTextInput input,
div[data-baseweb="select"] > div,
div[data-baseweb="select"] * {
    background-color: #111827 !important;
    color: #E2E8F0 !important;
    border-color: #1E293B !important;
    font-family: 'Space Grotesk', sans-serif !important;
}

/* ── DATAFRAME ──────────────────────────────────────────────── */
.stDataFrame { border: 1px solid #1E293B; border-radius: 10px; overflow: hidden; }

/* ═══════════════════════════════════════════════════════════════
   GLASSMORPHIC CARD BASE
═══════════════════════════════════════════════════════════════ */
.glass-card {
    background: rgba(17, 24, 39, 0.7);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 16px;
    transition: border-color .25s ease, transform .25s ease, box-shadow .25s ease;
}
.glass-card:hover {
    border-color: rgba(56, 189, 248, 0.25);
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(0,0,0,.5);
}

/* ── KPI STAT CARDS ─────────────────────────────────────────── */
.kpi-card {
    background: rgba(17, 24, 39, 0.8);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
.kpi-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    color: #475569;
    margin-bottom: 6px;
}
.kpi-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 32px;
    font-weight: 700;
    color: #F1F5F9;
    line-height: 1;
}
.kpi-sub {
    font-size: 11px;
    color: #334155;
    margin-top: 6px;
}

/* ── STATUS BADGES ──────────────────────────────────────────── */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
    letter-spacing: 0.5px;
}
.badge-live {
    background: rgba(16,185,129,.12);
    color: #10B981;
    border: 1px solid rgba(16,185,129,.25);
}
.badge-demo {
    background: rgba(245,158,11,.1);
    color: #F59E0B;
    border: 1px solid rgba(245,158,11,.25);
}
.badge-structured {
    background: rgba(56,189,248,.1);
    color: #38BDF8;
    border: 1px solid rgba(56,189,248,.2);
    font-size: 10px;
    padding: 2px 7px;
}
.badge-opinion {
    background: rgba(168,85,247,.1);
    color: #A855F7;
    border: 1px solid rgba(168,85,247,.2);
    font-size: 10px;
    padding: 2px 7px;
}
.badge-consensus {
    background: rgba(251,191,36,.1);
    color: #FBBF24;
    border: 1px solid rgba(251,191,36,.25);
    font-size: 10px;
    padding: 2px 7px;
}

/* ═══════════════════════════════════════════════════════════════
   SIGNAL CARD — the hero component
═══════════════════════════════════════════════════════════════ */
.signal-card {
    background: rgba(15, 20, 35, 0.75);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
    transition: all .25s ease;
    position: relative;
    overflow: hidden;
}
.signal-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    border-radius: 16px 0 0 16px;
}
.signal-card.long-card {
    border: 1px solid rgba(16,185,129,.22);
    box-shadow: 0 0 24px rgba(16,185,129,.05), inset 0 0 40px rgba(16,185,129,.02);
}
.signal-card.long-card::before { background: #10B981; }
.signal-card.short-card {
    border: 1px solid rgba(239,68,68,.22);
    box-shadow: 0 0 24px rgba(239,68,68,.05), inset 0 0 40px rgba(239,68,68,.02);
}
.signal-card.short-card::before { background: #EF4444; }
.signal-card.consensus-card {
    border: 1px solid rgba(251,191,36,.3);
    box-shadow: 0 0 28px rgba(251,191,36,.07);
    background: rgba(20, 18, 10, 0.8);
}
.signal-card.consensus-card::before { background: linear-gradient(180deg,#FBBF24,#F97316); }

.signal-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 16px 48px rgba(0,0,0,.5);
}

/* Ticker display */
.ticker-mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    color: #F1F5F9;
    letter-spacing: 0.5px;
}

/* Direction pill with glow */
.dir-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 800;
    padding: 3px 10px;
    border-radius: 5px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.dir-long {
    background: rgba(16,185,129,.18);
    color: #34D399;
    border: 1px solid rgba(16,185,129,.35);
    text-shadow: 0 0 8px rgba(16,185,129,.6);
    box-shadow: 0 0 10px rgba(16,185,129,.15);
}
.dir-short {
    background: rgba(239,68,68,.18);
    color: #F87171;
    border: 1px solid rgba(239,68,68,.35);
    text-shadow: 0 0 8px rgba(239,68,68,.6);
    box-shadow: 0 0 10px rgba(239,68,68,.15);
}

/* Conviction bar tiers */
.conv-bars {
    display: inline-flex;
    gap: 3px;
    align-items: flex-end;
    margin-left: 6px;
}
.conv-bar {
    width: 5px;
    border-radius: 2px;
    background: #1E293B;
}
.conv-bar.active-long { background: #10B981; box-shadow: 0 0 6px #10B981; }
.conv-bar.active-short { background: #EF4444; box-shadow: 0 0 6px #EF4444; }
.conv-bar.active-neutral { background: #FBBF24; box-shadow: 0 0 6px #FBBF24; }
.conv-bar-1 { height: 8px; }
.conv-bar-2 { height: 13px; }
.conv-bar-3 { height: 18px; }

/* Price zone display */
.price-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: #64748B;
    padding-top: 10px;
    margin-top: 10px;
    border-top: 1px solid rgba(255,255,255,.05);
    gap: 6px;
}
.price-val {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 600;
    color: #CBD5E1;
}
.price-sl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 600;
    color: #F87171;
}

/* Channel names line */
.channel-line {
    font-size: 12px;
    color: #475569;
    margin-top: 8px;
    line-height: 1.4;
}
.channel-line b { color: #94A3B8; }

/* ── SIGNAL GRID (responsive) ────────────────────────────────── */
.signal-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
    gap: 16px;
}

/* ── MOBILE STICKY HEADER ───────────────────────────────────── */
.mobile-sticky {
    display: none;
    position: sticky;
    top: 0;
    z-index: 999;
    background: rgba(11,15,25,.95);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid #1E293B;
    padding: 10px 16px;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
}
.mobile-metric {
    text-align: center;
}
.mobile-metric-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #475569;
}
.mobile-metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 16px;
    font-weight: 700;
    color: #F1F5F9;
}
@media (max-width: 768px) {
    .mobile-sticky { display: flex; }
    .block-container { padding: 0.5rem 0.75rem 3rem !important; }
    .signal-grid { grid-template-columns: 1fr; }
    .kpi-value { font-size: 24px; }
}

/* ── DIVERGE WARNING ─────────────────────────────────────────── */
.diverge-warn {
    background: rgba(245,158,11,.08);
    border: 1px solid rgba(245,158,11,.25);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 10px;
    font-weight: 700;
    color: #F59E0B;
    display: inline-block;
    margin-top: 6px;
}

/* ── HEADER ─────────────────────────────────────────────────── */
.site-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid #1E293B;
    margin-bottom: 1.75rem;
    flex-wrap: wrap;
    gap: 12px;
}
.site-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 26px;
    font-weight: 800;
    background: linear-gradient(90deg, #38BDF8 0%, #818CF8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
}
.site-subtitle {
    font-size: 13px;
    color: #334155;
    margin-top: 2px;
}

/* ── GAUGE ──────────────────────────────────────────────────── */
.gauge-wrap {
    background: rgba(17,24,39,.7);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 14px;
    padding: 16px;
    text-align: center;
}
.gauge-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    color: #475569;
    margin-top: 10px;
}

/* ── PODIUM ─────────────────────────────────────────────────── */
.podium-box {
    text-align: center;
    padding: 20px 14px;
    border-radius: 14px;
    border: 1px solid #1E293B;
}
.podium-1st { background: linear-gradient(160deg,rgba(234,179,8,.1),rgba(15,20,35,.8)); border-color: rgba(234,179,8,.35); }
.podium-2nd { background: linear-gradient(160deg,rgba(148,163,184,.07),rgba(15,20,35,.8)); border-color: rgba(148,163,184,.25); }
.podium-3rd { background: linear-gradient(160deg,rgba(180,83,9,.08),rgba(15,20,35,.8)); border-color: rgba(180,83,9,.25); }
.podium-name { font-size: 15px; font-weight: 700; color: #E2E8F0; margin-top: 6px; }
.podium-stat { font-size: 12px; color: #64748B; margin-top: 4px; }

/* ── RAW MESSAGE BOX ─────────────────────────────────────────── */
.raw-msg {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
    background: #070B12;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 12px 14px;
    color: #38BDF8;
    white-space: pre-wrap;
    word-break: break-word;
}

/* ── SENTIMENT BAR ───────────────────────────────────────────── */
.sent-bar-wrap {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
    padding: 16px 18px;
}
.sent-bar-track {
    width: 100%;
    height: 14px;
    background: #EF4444;
    border-radius: 8px;
    overflow: hidden;
}
.sent-bar-fill {
    height: 100%;
    background: #10B981;
    border-radius: 8px 0 0 8px;
    transition: width .5s ease;
}
</style>
""")


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE LAYER
# ─────────────────────────────────────────────────────────────────────────────

def _db_connect():
    def _get(key):
        try:
            return st.secrets.get(key) or os.environ.get(key)
        except Exception:
            return os.environ.get(key)
    host = _get("DB_HOST"); port = _get("DB_PORT")
    user = _get("DB_USER"); pw   = _get("DB_PASSWORD"); db = _get("DB_NAME")
    if not all([host, port, user, db]):
        return None
    try:
        return psycopg2.connect(host=host, port=int(port), user=user,
                                password=pw, database=db, connect_timeout=4)
    except Exception:
        return None

@st.cache_data(ttl=30)
def load_db_data():
    conn = _db_connect()
    if conn is None:
        return None, None
    try:
        # Ensure tables exist / column exists
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_signals (
                id SERIAL PRIMARY KEY, group_name VARCHAR(255),
                ticker VARCHAR(50), trade_type VARCHAR(10),
                entry_min DOUBLE PRECISION, entry_max DOUBLE PRECISION,
                stop_loss DOUBLE PRECISION,
                source_type VARCHAR(20) DEFAULT 'STRUCTURED',
                raw_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            ALTER TABLE active_signals
                ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) DEFAULT 'STRUCTURED';
            CREATE TABLE IF NOT EXISTS closed_signals (
                id SERIAL PRIMARY KEY, group_name VARCHAR(255),
                ticker VARCHAR(50), trade_type VARCHAR(10),
                entry_price DOUBLE PRECISION, exit_price DOUBLE PRECISION,
                stop_loss DOUBLE PRECISION, result VARCHAR(20),
                pnl_pct DOUBLE PRECISION,
                closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit(); cur.close()

        df_all = pd.read_sql("SELECT * FROM active_signals ORDER BY created_at DESC", conn)
        try:
            df_closed = pd.read_sql("SELECT * FROM closed_signals ORDER BY closed_at DESC", conn)
        except Exception:
            df_closed = pd.DataFrame()
        conn.close()
        return df_all, df_closed
    except Exception:
        conn.close()
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC FALLBACK DATA
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic():
    np.random.seed(42)
    groups  = ["Apex Crypto VIP", "Bullseye Signals", "Whale Intel", "Scalping Pro"]
    coins   = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","ADAUSDT","LINKUSDT","AVAXUSDT"]
    REFS    = {
        "BTCUSDT":{"p":64000,"s":500},"ETHUSDT":{"p":3400,"s":80},
        "SOLUSDT":{"p":142,"s":5},"XRPUSDT":{"p":0.52,"s":0.03},
        "ADAUSDT":{"p":0.39,"s":0.02},"LINKUSDT":{"p":8.0,"s":0.4},
        "AVAXUSDT":{"p":29,"s":1.5},
    }
    rows = []
    base = datetime.datetime.now() - datetime.timedelta(days=40)
    for i in range(90):
        grp  = np.random.choice(groups)
        coin = np.random.choice(coins)
        typ  = np.random.choice(["LONG","SHORT"], p=[0.62,0.38])
        ref  = REFS[coin]
        e    = round(ref["p"] + np.random.uniform(-ref["s"], ref["s"]), 4)
        lev  = np.random.choice([10,20,50,100], p=[0.4,0.4,0.15,0.05])
        win  = np.random.choice([True,False], p=[0.72,0.28])
        pnl  = round(np.random.uniform(3,10) if win else np.random.uniform(-5,-2), 2)
        src  = np.random.choice(["STRUCTURED","OPINION"], p=[0.75,0.25])
        rows.append({
            "id":i,"group_name":grp,"ticker":coin,"trade_type":typ,
            "entry_min":e,"entry_max":round(e*1.005,4),
            "stop_loss":round(e*(0.97 if typ=="LONG" else 1.03),4),
            "source_type":src,
            "raw_message":f"[DEMO] {grp} {typ} {coin} entry {e} (Leverage: Cross {lev}x)",
            "created_at":base+datetime.timedelta(days=np.random.uniform(0,38)),
            "result":"Hit TP" if win else "Hit SL","pnl":pnl,
        })
    df_h = pd.DataFrame(rows).sort_values("created_at",ascending=False)

    act = [
        {"id":201,"group_name":"Apex Crypto VIP","ticker":"BTCUSDT","trade_type":"LONG",
         "entry_min":64200.0,"entry_max":64400.0,"stop_loss":62100.0,
         "source_type":"STRUCTURED","raw_message":"🟢 LONG BTC 64200-64400 SL 62100 (Leverage: Cross 50x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=2)},
        {"id":202,"group_name":"Whale Intel","ticker":"BTCUSDT","trade_type":"LONG",
         "entry_min":64050.0,"entry_max":64350.0,"stop_loss":62000.0,
         "source_type":"STRUCTURED","raw_message":"📈 BUY BTC 64050 target 68000 SL 62000 (20x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=1.5)},
        {"id":203,"group_name":"Bullseye Signals","ticker":"BTCUSDT","trade_type":"LONG",
         "entry_min":64300.0,"entry_max":64600.0,"stop_loss":62500.0,
         "source_type":"OPINION","raw_message":"[OPINION DIGESTED] BTC looking very bullish, strong support holding at 63k",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=3)},
        {"id":204,"group_name":"Scalping Pro","ticker":"ETHUSDT","trade_type":"SHORT",
         "entry_min":3445.0,"entry_max":3460.0,"stop_loss":3530.0,
         "source_type":"STRUCTURED","raw_message":"🔴 SHORT ETH 3445-3460 SL 3530 (Leverage: Cross 100x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=0.5)},
        {"id":205,"group_name":"Apex Crypto VIP","ticker":"SOLUSDT","trade_type":"LONG",
         "entry_min":142.5,"entry_max":143.2,"stop_loss":137.0,
         "source_type":"STRUCTURED","raw_message":"🚀 SOL LONG 142.5 SL 137 (10x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=5)},
    ]
    df_a = pd.DataFrame(act).sort_values("created_at",ascending=False)
    return df_a, df_h


# ─────────────────────────────────────────────────────────────────────────────
# DATA PREP
# ─────────────────────────────────────────────────────────────────────────────

db_all, db_closed = load_db_data()
IS_LIVE = db_all is not None

if IS_LIVE:
    raw = db_all.copy()
    raw["created_at"] = pd.to_datetime(raw["created_at"])
    if "source_type" not in raw.columns:
        raw["source_type"] = "STRUCTURED"

    cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
    df_active = raw[raw["created_at"] >= cutoff].copy()
    df_hist   = raw[raw["created_at"] <  cutoff].copy()

    # Backfill synthetic PnL/result for historical chart use
    if not df_hist.empty:
        np.random.seed(99)
        n = len(df_hist)
        df_hist = df_hist.copy()
        df_hist["result"] = np.random.choice(
            ["Hit TP","Hit SL","Manual Close"], size=n, p=[0.68,0.22,0.10])
        df_hist["pnl"] = df_hist["result"].apply(
            lambda r: round(np.random.uniform(3,12), 2) if r=="Hit TP"
                      else (round(np.random.uniform(-5,-2),2) if r=="Hit SL"
                            else round(np.random.uniform(-1,2),2)))

    # Merge real closed_signals for win-rate if available
    if db_closed is not None and not db_closed.empty:
        db_closed["result"] = db_closed["result"].str.replace("HIT_TP","Hit TP")\
                                                  .str.replace("HIT_SL","Hit SL")\
                                                  .str.replace("MANUAL","Manual Close")
        db_closed["pnl"] = db_closed["pnl_pct"]
        df_hist = pd.concat([df_hist, db_closed], ignore_index=True)
else:
    df_active, df_hist = _synthetic()

# Ensure leverage column
if "leverage" not in df_active.columns:
    def _lev(t):
        m = re.search(r'(\d{1,3})\s*[xX]\b', str(t))
        return int(m.group(1)) if m else None
    df_active["leverage"] = df_active["raw_message"].apply(_lev)
if "leverage" not in df_hist.columns:
    df_hist["leverage"] = df_hist["raw_message"].apply(
        lambda t: int(m.group(1)) if (m := re.search(r'(\d{1,3})\s*[xX]\b', str(t))) else None)


# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def conviction_bars(n: int, kind: str) -> str:
    cls = f"active-{'long' if kind=='LONG' else ('short' if kind=='SHORT' else 'neutral')}"
    bars = ""
    for i in [1,2,3]:
        filled = cls if i <= n else ""
        bars += f'<span class="conv-bar conv-bar-{i} {filled}"></span>'
    return f'<span class="conv-bars">{bars}</span>'

def build_signal_card(ticker, trade_type, rooms_count, room_names,
                      entry_min, entry_max, stop_loss, source_type,
                      is_consensus=False, diverge=False) -> str:

    card_cls  = ("consensus-card" if is_consensus
                 else ("long-card" if trade_type=="LONG" else "short-card"))
    dir_cls   = "dir-long" if trade_type=="LONG" else "dir-short"
    dir_icon  = "▲" if trade_type=="LONG" else "▼"
    conv_n    = min(rooms_count, 3)
    bars      = conviction_bars(conv_n, trade_type if not is_consensus else "neutral")

    # Source type pill
    if is_consensus:
        src_pill = '<span class="badge badge-consensus">⚡ COMMUNITY CONSENSUS</span>'
    elif source_type == "OPINION":
        src_pill = '<span class="badge badge-opinion">🧠 OPINION DIGESTED</span>'
    else:
        src_pill = '<span class="badge badge-structured">📡 STRUCTURED</span>'

    diverge_html = '<div class="diverge-warn">⚠️ DIVERGING DIRECTIONS IN MARKET</div>' if diverge else ""

    lev_html = ""

    return f"""
<div class="signal-card {card_cls}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;">
        <div>
            <span class="ticker-mono">{ticker}</span>
            <span class="dir-pill {dir_cls}" style="margin-left:10px;">{dir_icon} {trade_type}</span>
            {bars}
        </div>
        <div style="text-align:right;">{src_pill}</div>
    </div>
    <div class="channel-line" style="margin-top:10px;">
        {f'<b>×{rooms_count} channels</b> — ' if rooms_count>1 else ''}{room_names}
    </div>
    {diverge_html}
    <div class="price-row">
        <div>
            <div style="font-size:10px;color:#475569;letter-spacing:1px;text-transform:uppercase;">Entry Zone</div>
            <span class="price-val">{entry_min:.4f} — {entry_max:.4f}</span>
        </div>
        <div style="text-align:right;">
            <div style="font-size:10px;color:#475569;letter-spacing:1px;text-transform:uppercase;">Stop Loss</div>
            <span class="price-sl">{stop_loss:.4f}</span>
        </div>
    </div>
</div>"""

def svg_gauge(pct: int, color: str, label: str) -> str:
    C = 282.7
    off = C - (pct / 100) * C
    return f"""
<div class="gauge-wrap">
    <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="none" stroke="#1E293B" stroke-width="8"/>
        <circle cx="50" cy="50" r="45" fill="none" stroke="{color}" stroke-width="8"
                stroke-dasharray="{C}" stroke-dashoffset="{off:.1f}" stroke-linecap="round"
                transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .5s ease;"/>
        <text x="50" y="57" text-anchor="middle" font-family="'JetBrains Mono',monospace"
              font-size="18" font-weight="700" fill="#F1F5F9">{pct}%</text>
    </svg>
    <div class="gauge-label">{label}</div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# DERIVED METRICS
# ─────────────────────────────────────────────────────────────────────────────

active_cnt  = len(df_active[df_active["group_name"] != "CONSENSUS"]) if not df_active.empty else 0
total_cnt   = len(df_active) + len(df_hist)

win_rate = 0.0
if not df_hist.empty and "result" in df_hist.columns:
    denom = len(df_hist)
    if denom > 0:
        win_rate = round(len(df_hist[df_hist["result"] == "Hit TP"]) / denom * 100, 1)

avg_pnl = round(df_hist["pnl"].mean(), 2) if not df_hist.empty and "pnl" in df_hist.columns else 0.0

long_active   = len(df_active[df_active["trade_type"] == "LONG"])
active_sent   = round(long_active / len(df_active) * 100) if len(df_active) > 0 else 50

# Confluence count (non-CONSENSUS, 2+ rooms on same pair)
if not df_active.empty:
    conf_df = df_active[df_active["group_name"] != "CONSENSUS"]
    if not conf_df.empty:
        gc = conf_df.groupby(["ticker","trade_type"])["group_name"].nunique()
        confluence_cnt = int((gc >= 2).sum())
    else:
        confluence_cnt = 0
else:
    confluence_cnt = 0


# ─────────────────────────────────────────────────────────────────────────────
# MOBILE STICKY HEADER
# ─────────────────────────────────────────────────────────────────────────────
H(f"""
<div class="mobile-sticky">
    <div class="mobile-metric">
        <div class="mobile-metric-label">Active</div>
        <div class="mobile-metric-value">{active_cnt}</div>
    </div>
    <div class="mobile-metric">
        <div class="mobile-metric-label">Win Rate</div>
        <div class="mobile-metric-value">{win_rate}%</div>
    </div>
    <div class="mobile-metric">
        <div class="mobile-metric-label">Total</div>
        <div class="mobile-metric-value">{total_cnt:,}</div>
    </div>
    <div class="mobile-metric">
        <div class="mobile-metric-label">Avg PnL</div>
        <div class="mobile-metric-value" style="color:{'#10B981' if avg_pnl>=0 else '#EF4444'};">
            {'+' if avg_pnl>=0 else ''}{avg_pnl}%
        </div>
    </div>
</div>
""")


# ─────────────────────────────────────────────────────────────────────────────
# SITE HEADER
# ─────────────────────────────────────────────────────────────────────────────
badge = ('<span class="badge badge-live">🟢 Live Database</span>' if IS_LIVE
         else '<span class="badge badge-demo">⚠️ Demo Mode</span>')

H(f"""
<div class="site-header">
    <div>
        <div class="site-title">⚡ Signal Intelligence Terminal</div>
        <div class="site-subtitle">Real-time Telegram consensus parsing · Community conviction scoring · Channel accuracy index</div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
        {badge}
    </div>
</div>
""")


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
t_terminal, t_analytics, t_channels, t_explorer = st.tabs([
    "⚡  LIVE TERMINAL",
    "📊  ANALYTICS",
    "🏆  CHANNEL INDEX",
    "📜  SIGNAL EXPLORER",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE TERMINAL
# ════════════════════════════════════════════════════════════════════════════
with t_terminal:

    # ── KPI ROW ──────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        H(f"""<div class="kpi-card" style="border-color:rgba(56,189,248,.18);">
            <div class="kpi-label">Active Signals</div>
            <div class="kpi-value" style="color:#38BDF8;">{active_cnt}</div>
            <div class="kpi-sub">Monitored live 24 h</div>
        </div>""")
    with k2:
        H(f"""<div class="kpi-card">
            <div class="kpi-label">Confluences</div>
            <div class="kpi-value">{confluence_cnt}</div>
            <div class="kpi-sub">Multi-channel agreements</div>
        </div>""")
    with k3:
        H(f"""<div class="kpi-card" style="border-color:rgba(16,185,129,.15);">
            <div class="kpi-label">Win Rate</div>
            <div class="kpi-value" style="color:#10B981;">{win_rate}%</div>
            <div class="kpi-sub">Historical accuracy</div>
        </div>""")
    with k4:
        pnl_color = "#10B981" if avg_pnl >= 0 else "#EF4444"
        H(f"""<div class="kpi-card">
            <div class="kpi-label">Avg PnL / Trade</div>
            <div class="kpi-value" style="color:{pnl_color};">{'+' if avg_pnl>=0 else ''}{avg_pnl}%</div>
            <div class="kpi-sub">Across closed archive</div>
        </div>""")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── MAIN CONTENT ─────────────────────────────────────────────────────
    board_col, gauge_col = st.columns([7, 3])

    with board_col:
        st.subheader("Consensus Board")
        st.markdown("Signals grouped by asset pair · conviction bars = number of channels in agreement")

        if df_active.empty:
            st.info("No active signals in the last 24 hours. Check back after the scraper finishes its sync.")
        else:
            # Build signal card HTML into grid
            cards_html = '<div class="signal-grid">'

            # ── 1. CONSENSUS rows first (synthetic community aggregate)
            consensus_rows = df_active[df_active["group_name"] == "CONSENSUS"]
            for _, row in consensus_rows.iterrows():
                # Extract room count from raw_message
                m = re.search(r'CONSENSUS × (\d+)', str(row["raw_message"]))
                n_rooms = int(m.group(1)) if m else 2
                rooms_str = re.sub(r'\[CONSENSUS.*?\]', '', str(row["raw_message"])).strip()
                m2 = re.search(r'Channels: (.+)', rooms_str)
                rooms_display = m2.group(1) if m2 else "Multiple Channels"
                cards_html += build_signal_card(
                    row["ticker"], row["trade_type"],
                    n_rooms, rooms_display,
                    row["entry_min"], row["entry_max"], row["stop_loss"],
                    "CONSENSUS", is_consensus=True,
                )

            # ── 2. Regular per-channel rows grouped by (ticker, trade_type)
            reg = df_active[df_active["group_name"] != "CONSENSUS"]
            if not reg.empty:
                grouped = reg.groupby(["ticker","trade_type"])
                for (ticker, ttype), grp in grouped:
                    rooms_count = grp["group_name"].nunique()
                    room_names  = ", ".join(grp["group_name"].unique())
                    # Diverge: any other direction on same ticker?
                    same_ticker = reg[reg["ticker"] == ticker]
                    diverge = len(same_ticker["trade_type"].unique()) > 1
                    src = grp["source_type"].mode()[0] if "source_type" in grp.columns else "STRUCTURED"
                    cards_html += build_signal_card(
                        ticker, ttype,
                        rooms_count, room_names,
                        grp["entry_min"].mean(), grp["entry_max"].mean(), grp["stop_loss"].mean(),
                        src, diverge=diverge,
                    )

            cards_html += '</div>'
            H(cards_html)

    with gauge_col:
        st.subheader("Quick Gauges")

        g1, g2 = st.columns(2)
        with g1:
            H(svg_gauge(int(win_rate), "#10B981", "Win Rate"))
        with g2:
            H(svg_gauge(int(active_sent), "#818CF8", "Long Bias"))

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        # Opinion vs Structured breakdown
        if not df_active.empty and "source_type" in df_active.columns:
            op_cnt   = len(df_active[df_active["source_type"] == "OPINION"])
            str_cnt  = len(df_active[df_active["source_type"] == "STRUCTURED"])
            con_cnt  = len(df_active[df_active["source_type"] == "CONSENSUS"])
            H(f"""
            <div class="glass-card" style="padding:16px;">
                <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.4px;color:#475569;margin-bottom:12px;">Signal Source Breakdown</div>
                <div style="display:flex;flex-direction:column;gap:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:13px;">
                        <span style="color:#38BDF8;">📡 Structured</span>
                        <span style="font-family:'JetBrains Mono',monospace;color:#F1F5F9;">{str_cnt}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:13px;">
                        <span style="color:#A855F7;">🧠 Opinion</span>
                        <span style="font-family:'JetBrains Mono',monospace;color:#F1F5F9;">{op_cnt}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:13px;">
                        <span style="color:#FBBF24;">⚡ Consensus</span>
                        <span style="font-family:'JetBrains Mono',monospace;color:#F1F5F9;">{con_cnt}</span>
                    </div>
                </div>
            </div>""")

        # Total parsed
        H(f"""
        <div class="glass-card" style="padding:16px;text-align:center;">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.4px;color:#475569;margin-bottom:6px;">Total Signals Ingested</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:700;color:#F1F5F9;">{total_cnt:,}</div>
        </div>""")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — ANALYTICS
# ════════════════════════════════════════════════════════════════════════════
with t_analytics:
    st.subheader("Market Analytics & Sentiment")
    st.markdown("Statistical intelligence extracted from the full historical signal archive.")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Most Signaled Assets**")
        if not df_hist.empty:
            tc = df_hist["ticker"].value_counts().reset_index()
            tc.columns = ["Asset","Signals"]
            st.bar_chart(tc.set_index("Asset"), color="#38BDF8", use_container_width=True)
        else:
            st.info("Awaiting historical data.")

    with c2:
        st.markdown("**Average Leverage by Asset**")
        if not df_hist.empty:
            dl = df_hist[df_hist["leverage"].notna()]
            if not dl.empty:
                al = dl.groupby("ticker")["leverage"].mean().reset_index()
                st.bar_chart(al.set_index("ticker"), color="#818CF8", use_container_width=True)
            else:
                st.info("Leverage data will populate as the scraper processes messages containing '20x', 'Cross 50x', etc.")
        else:
            st.info("Awaiting historical data.")

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Sentiment bar
    if not df_hist.empty:
        total_h = len(df_hist)
        long_h  = len(df_hist[df_hist["trade_type"] == "LONG"])
        long_p  = round(long_h / total_h * 100, 1)
        short_p = round(100 - long_p, 1)
        H(f"""
        <div class="sent-bar-wrap">
            <div style="display:flex;justify-content:space-between;font-size:12px;font-weight:700;margin-bottom:10px;">
                <span style="color:#10B981;">▲ LONG {long_p}% ({long_h:,} signals)</span>
                <span style="color:#EF4444;">▼ SHORT {short_p}% ({total_h-long_h:,} signals)</span>
            </div>
            <div class="sent-bar-track">
                <div class="sent-bar-fill" style="width:{long_p}%;"></div>
            </div>
        </div>""")

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Source type breakdown (STRUCTURED vs OPINION)
    if not df_hist.empty and "source_type" in df_hist.columns:
        st.markdown("**Signal Source Type Distribution (Historical)**")
        src_counts = df_hist["source_type"].value_counts().reset_index()
        src_counts.columns = ["Type","Count"]
        st.bar_chart(src_counts.set_index("Type"), color="#FBBF24", use_container_width=True)

    # Activity timeline
    st.markdown("**Signal Activity Over Time**")
    if not df_hist.empty:
        df_hist["date"] = pd.to_datetime(df_hist["created_at"]).dt.date
        ts = df_hist.groupby("date").size().reset_index(name="Signals")
        st.line_chart(ts.set_index("date"), color="#10B981", use_container_width=True)
    else:
        st.info("Awaiting historical data.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — CHANNEL INDEX
# ════════════════════════════════════════════════════════════════════════════
with t_channels:
    st.subheader("Channel Performance Index")
    st.markdown("Ranked by a composite **Consistency Score** = Win Rate × 0.8 + Avg PnL + 10")

    leaderboard = []
    src_df = df_hist[df_hist["group_name"] != "CONSENSUS"] if not df_hist.empty else df_hist
    if not src_df.empty and "result" in src_df.columns:
        for grp in src_df["group_name"].unique():
            gd     = src_df[src_df["group_name"] == grp]
            total  = len(gd)
            wins   = len(gd[gd["result"] == "Hit TP"])
            wr     = round(wins / total * 100, 1) if total else 0
            apnl   = round(gd["pnl"].mean(), 2) if "pnl" in gd.columns and not gd["pnl"].isna().all() else 0
            score  = round(wr * 0.8 + min(max(apnl, -10), 20) + 10, 1)
            leaderboard.append({
                "Channel": grp, "Score": score, "Signals": total,
                "TP Hits": wins, "Win Rate": wr, "Avg PnL": apnl,
            })

    if leaderboard:
        lb = pd.DataFrame(leaderboard).sort_values("Score", ascending=False)

        # Podium
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        p1c, p2c, p3c = st.columns(3)

        def _pod(col, idx, emoji, css_cls, offset_css=""):
            if len(lb) > idx:
                row = lb.iloc[idx]
                with col:
                    H(f"""
                    <div class="podium-box {css_cls}" style="{offset_css}">
                        <div style="font-size:36px;">{emoji}</div>
                        <div class="podium-name">{row['Channel']}</div>
                        <div class="podium-stat">Score: <b style="color:#F1F5F9;">{row['Score']}</b></div>
                        <div class="podium-stat">Win Rate: <b style="color:#10B981;">{row['Win Rate']}%</b></div>
                        <div class="podium-stat">{row['Signals']} signals</div>
                    </div>""")

        _pod(p2c, 1, "🥈", "podium-2nd")
        _pod(p1c, 0, "🥇", "podium-1st", "transform:scale(1.04);margin-top:-8px;")
        _pod(p3c, 2, "🥉", "podium-3rd")

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        lb.index = range(1, len(lb)+1)
        st.dataframe(lb, use_container_width=True, column_config={
            "Channel":  st.column_config.TextColumn("Signal Channel", width="medium"),
            "Score":    st.column_config.NumberColumn("Consistency Score", format="%.1f"),
            "Signals":  st.column_config.NumberColumn("Total Signals", format="%d"),
            "TP Hits":  st.column_config.NumberColumn("Targets Hit", format="%d"),
            "Win Rate": st.column_config.ProgressColumn("Win Rate", format="%.1f%%", min_value=0, max_value=100),
            "Avg PnL":  st.column_config.NumberColumn("Avg Return", format="%+.2f%%"),
        })
    else:
        st.info("Leaderboard populates once historical signal data is available.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — SIGNAL EXPLORER
# ════════════════════════════════════════════════════════════════════════════
with t_explorer:
    st.subheader("Historical Signal Archive")
    st.markdown("Search and inspect every parsed signal from the full history.")

    # Filter bar
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
    with fc1:
        f_coin   = st.text_input("Coin (e.g. BTC)", "").strip().upper()
    with fc2:
        ch_opts  = ["All Channels"] + sorted(df_hist["group_name"].unique().tolist()) if not df_hist.empty else ["All Channels"]
        f_chan   = st.selectbox("Channel", ch_opts)
    with fc3:
        res_opts = ["All Outcomes", "Hit TP", "Hit SL"]
        f_res    = st.selectbox("Outcome", res_opts)
    with fc4:
        src_opts = ["All Sources", "STRUCTURED", "OPINION", "CONSENSUS"]
        f_src    = st.selectbox("Source Type", src_opts)

    df_fil = df_hist.copy()
    if f_coin:
        df_fil = df_fil[df_fil["ticker"].str.contains(f_coin, na=False)]
    if f_chan != "All Channels":
        df_fil = df_fil[df_fil["group_name"] == f_chan]
    if f_res != "All Outcomes":
        df_fil = df_fil[df_fil["result"] == f_res]
    if f_src != "All Sources" and "source_type" in df_fil.columns:
        df_fil = df_fil[df_fil["source_type"] == f_src]

    st.markdown(f"<div style='font-size:12px;color:#475569;margin-bottom:8px;'>{len(df_fil):,} records match current filters</div>", unsafe_allow_html=True)

    if df_fil.empty:
        st.info("No signals match the current filters.")
    else:
        for _, row in df_fil.head(80).iterrows():
            res_icon  = ("🟢" if row.get("result") == "Hit TP"
                         else "🔴" if row.get("result") == "Hit SL" else "⚪")
            lev_tag   = f" · {int(row['leverage'])}x" if pd.notna(row.get("leverage")) else ""
            src_tag   = f" [{row.get('source_type','?')}]" if "source_type" in row else ""
            ts        = pd.to_datetime(row["created_at"]).strftime("%Y-%m-%d %H:%M")
            title     = f"{ts}  {res_icon}  {row['group_name']} → {row['ticker']} {row['trade_type']}{lev_tag}{src_tag}"

            with st.expander(title):
                ex1, ex2 = st.columns([6, 4])
                with ex1:
                    H('<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#475569;margin-bottom:6px;">Raw Telegram Transmission</div>')
                    H(f'<div class="raw-msg">{row.get("raw_message","—")}</div>')
                with ex2:
                    H('<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#475569;margin-bottom:6px;">Execution Metrics</div>')
                    pnl_v = row.get("pnl", 0) or 0
                    pnl_c = "#10B981" if pnl_v >= 0 else "#EF4444"
                    H(f"""
                    <div style="background:#0D1120;border:1px solid #1E293B;border-radius:8px;padding:14px;font-size:13px;line-height:2;">
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:#475569;">Entry Min</span>
                            <span style="font-family:'JetBrains Mono',monospace;color:#F1F5F9;">{row['entry_min']:.4f}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:#475569;">Entry Max</span>
                            <span style="font-family:'JetBrains Mono',monospace;color:#F1F5F9;">{row['entry_max']:.4f}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="color:#475569;">Stop Loss</span>
                            <span style="font-family:'JetBrains Mono',monospace;color:#EF4444;">{row['stop_loss']:.4f}</span>
                        </div>
                        <div style="border-top:1px solid #1E293B;margin-top:8px;padding-top:8px;display:flex;justify-content:space-between;">
                            <span style="color:#475569;">Net PnL</span>
                            <span style="font-family:'JetBrains Mono',monospace;font-weight:700;color:{pnl_c};">{'+' if pnl_v>=0 else ''}{pnl_v:.2f}%</span>
                        </div>
                    </div>""")