"""
Signal Intelligence Terminal — v3
Cyberpunk Bloomberg Terminal Dark Mode
"""

import streamlit as st
import psycopg2
import pandas as pd
import numpy as np
import os
import datetime
import re
import json
import warnings
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

# ── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Signal Intelligence Terminal",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

load_dotenv()

# pandas emits a UserWarning when fed a raw psycopg2 (non-SQLAlchemy) connection.
# The direct-connection path is intentional here (avoids adding SQLAlchemy as a
# dependency for a single query), so silence the noise rather than the warning.
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

# ── RENDER HELPER ─────────────────────────────────────────────────────────────
# Critical: pass directly to st.markdown with unsafe_allow_html=True.
# Do NOT wrap with textwrap.dedent — it strips leading '<' from HTML tags.
def md(html: str):
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL DESIGN SYSTEM — Cyberpunk Bloomberg Terminal
# ══════════════════════════════════════════════════════════════════════════════
md("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,600;0,700;1,400&display=swap');

/* ── RESET ──────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

/* ── DESIGN TOKENS ──────────────────────────────────────────────────────── */
:root {
    --glass: rgba(255,255,255,0.055);
    --glass-soft: rgba(255,255,255,0.035);
    --glass-strong: rgba(255,255,255,0.09);
    --glass-border: rgba(255,255,255,0.11);
    --glass-border-soft: rgba(255,255,255,0.07);
    --glass-blur: blur(22px) saturate(160%);
    --glass-blur-sm: blur(12px) saturate(150%);
    --glass-shadow: 0 8px 32px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.07);
    --glass-shadow-lift: 0 24px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.09);
}

/* ── ROOT / AMBIENT GRADIENT MESH ───────────────────────────────────────── */
html, body { background: #060814 !important; }
.stApp {
    background:
        radial-gradient(1100px 620px at 12% -8%,  rgba(56,189,248,0.20), transparent 60%),
        radial-gradient(1000px 640px at 102% 4%,  rgba(167,139,250,0.18), transparent 62%),
        radial-gradient(900px 680px at 46% 108%,  rgba(16,185,129,0.14), transparent 60%),
        radial-gradient(760px 520px at -4% 96%,   rgba(244,63,94,0.09), transparent 58%),
        radial-gradient(640px 480px at 70% 46%,   rgba(251,191,36,0.05), transparent 60%),
        #060814 !important;
    background-attachment: fixed !important;
    color: #CBD5E1 !important;
    font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
}
.block-container {
    padding: 0 2rem 3rem !important;
    max-width: 1440px !important;
}

/* ── TYPOGRAPHY ─────────────────────────────────────────────────────────── */
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
    letter-spacing: -0.4px;
}
.stApp p, .stApp li, .stApp span { color: #94A3B8 !important; }
.stApp .stMarkdown p { color: #94A3B8 !important; }

/* ── STREAMLIT CHROME ───────────────────────────────────────────────────── */
#MainMenu, footer, header, [data-testid="stSidebar"] { display: none !important; }

/* ── FORM ELEMENTS ──────────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
div[data-baseweb="select"] > div {
    background: var(--glass) !important;
    backdrop-filter: var(--glass-blur-sm) !important;
    -webkit-backdrop-filter: var(--glass-blur-sm) !important;
    border: 1px solid var(--glass-border) !important;
    color: #F1F5F9 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    border-radius: 10px !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06) !important;
}
.stSelectbox label, .stTextInput label, .stNumberInput label { color: #94A3B8 !important; font-size: 12px !important; }

/* ── GENERIC BUTTONS / CHECKBOXES / DOWNLOAD ────────────────────────────── */
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    background: var(--glass) !important;
    backdrop-filter: var(--glass-blur-sm) !important;
    -webkit-backdrop-filter: var(--glass-blur-sm) !important;
    border: 1px solid var(--glass-border) !important;
    color: #CBD5E1 !important;
    border-radius: 10px !important;
    box-shadow: var(--glass-shadow) !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {
    border-color: rgba(56,189,248,0.55) !important;
    color: #38BDF8 !important;
    background: rgba(56,189,248,0.09) !important;
    box-shadow: var(--glass-shadow), 0 0 20px rgba(56,189,248,0.18) !important;
}
.stCheckbox label p { color: #94A3B8 !important; font-size: 12px !important; }
[data-testid="stWidgetLabel"] p { color: #94A3B8 !important; }

/* ── DATAFRAME ──────────────────────────────────────────────────────────── */
.stDataFrame {
    border: 1px solid var(--glass-border) !important;
    border-radius: 14px !important;
    overflow: hidden;
    backdrop-filter: var(--glass-blur-sm) !important;
    -webkit-backdrop-filter: var(--glass-blur-sm) !important;
    box-shadow: var(--glass-shadow) !important;
}
[data-testid="stDataFrame"] th { background: var(--glass-soft) !important; color: #94A3B8 !important; }

/* ── EXPANDER ───────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--glass) !important;
    backdrop-filter: var(--glass-blur-sm) !important;
    -webkit-backdrop-filter: var(--glass-blur-sm) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 12px !important;
    color: #CBD5E1 !important;
    font-size: 13px !important;
    font-family: 'JetBrains Mono', monospace !important;
}
.streamlit-expanderContent {
    background: var(--glass-soft) !important;
    backdrop-filter: var(--glass-blur-sm) !important;
    -webkit-backdrop-filter: var(--glass-blur-sm) !important;
    border: 1px solid var(--glass-border) !important;
    border-top: none !important;
    border-radius: 0 0 12px 12px !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   TOP NAV BAR
══════════════════════════════════════════════════════════════════════════ */
.t-nav {
    position: sticky;
    top: 0;
    z-index: 1000;
    background: rgba(8, 10, 22, 0.55);
    backdrop-filter: blur(26px) saturate(180%);
    -webkit-backdrop-filter: blur(26px) saturate(180%);
    border-bottom: 1px solid var(--glass-border-soft);
    box-shadow: 0 1px 0 rgba(255,255,255,0.04), 0 20px 40px -20px rgba(0,0,0,0.6);
    padding: 0 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: 56px;
    margin: 0 -2rem 1.5rem;
}
.t-nav-brand {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 700;
    color: #38BDF8;
    letter-spacing: 1px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 10px;
}
.t-nav-brand::before {
    content: '';
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10B981;
    box-shadow: 0 0 10px #10B981;
}
.t-nav-status {
    font-size: 11px;
    font-weight: 700;
    padding: 5px 14px;
    border-radius: 20px;
    letter-spacing: 0.8px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    text-transform: uppercase;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}
.t-nav-status.live {
    background: rgba(16,185,129,0.16);
    color: #10B981;
    border: 1px solid rgba(16,185,129,0.4);
    box-shadow: 0 0 16px rgba(16,185,129,0.18);
}
.t-nav-status.demo {
    background: rgba(245,158,11,0.14);
    color: #F59E0B;
    border: 1px solid rgba(245,158,11,0.35);
}
.t-nav-status::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}

/* Streamlit Tabs override */
div[data-testid="stTabs"] {
    border-bottom: 1px solid var(--glass-border-soft);
    margin-bottom: 1.75rem;
}
div[data-testid="stTabs"] [role="tablist"] {
    gap: 0 !important;
    background: transparent !important;
    overflow-x: auto !important;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    flex-wrap: nowrap !important;
}
div[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { display: none; height: 0; }
div[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase !important;
    color: #64748B !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 12px 20px !important;
    margin: 0 !important;
    transition: all 0.2s ease;
    white-space: nowrap;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #38BDF8 !important;
    border-bottom-color: #38BDF8 !important;
    background: linear-gradient(180deg, rgba(56,189,248,0.10), transparent) !important;
}
div[data-testid="stTabs"] button[role="tab"]:hover {
    color: #CBD5E1 !important;
    background: rgba(255,255,255,0.03) !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   KPI STAT CARDS
══════════════════════════════════════════════════════════════════════════ */
.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 1.5rem; }
@media (max-width: 1100px) { .kpi-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px)  { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
    box-shadow: var(--glass-shadow);
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.kpi-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(56,189,248,0.6), transparent);
}
.kpi-card:hover { transform: translateY(-2px); border-color: var(--glass-strong); box-shadow: var(--glass-shadow-lift); }
.kpi-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    color: #64748B;
    margin-bottom: 8px;
    font-family: 'Space Grotesk', sans-serif;
}
.kpi-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 28px;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1;
    letter-spacing: -0.5px;
}
.kpi-sub { font-size: 11px; color: #64748B; margin-top: 7px; }
.kpi-accent-blue::after { background: linear-gradient(90deg,transparent,rgba(56,189,248,0.6),transparent); }
.kpi-accent-green::after { background: linear-gradient(90deg,transparent,rgba(16,185,129,0.6),transparent); }
.kpi-accent-red::after { background: linear-gradient(90deg,transparent,rgba(239,68,68,0.55),transparent); }
.kpi-accent-purple::after { background: linear-gradient(90deg,transparent,rgba(139,92,246,0.6),transparent); }

/* ══════════════════════════════════════════════════════════════════════════
   SIGNAL CARDS — hero component
══════════════════════════════════════════════════════════════════════════ */
.signal-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 14px;
    margin-bottom: 1.5rem;
}
.signal-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border-radius: 18px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
    border: 1px solid var(--glass-border);
    box-shadow: var(--glass-shadow);
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}
.signal-card:hover {
    transform: translateY(-3px);
    box-shadow: var(--glass-shadow-lift);
}
/* Accent left stripe */
.signal-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    border-radius: 18px 0 0 18px;
}
/* Long variant */
.card-long { border-color: rgba(16,185,129,0.4); background: linear-gradient(160deg, rgba(16,185,129,0.09), var(--glass)); }
.card-long::before { background: linear-gradient(180deg, #10B981, #059669); box-shadow: 2px 0 16px rgba(16,185,129,0.5); }
.card-long:hover { border-color: rgba(16,185,129,0.65); box-shadow: var(--glass-shadow-lift), 0 0 40px rgba(16,185,129,0.1); }
/* Short variant */
.card-short { border-color: rgba(239,68,68,0.4); background: linear-gradient(160deg, rgba(239,68,68,0.09), var(--glass)); }
.card-short::before { background: linear-gradient(180deg, #EF4444, #B91C1C); box-shadow: 2px 0 16px rgba(239,68,68,0.5); }
.card-short:hover { border-color: rgba(239,68,68,0.65); box-shadow: var(--glass-shadow-lift), 0 0 40px rgba(239,68,68,0.1); }
/* Consensus variant */
.card-consensus { border-color: rgba(251,191,36,0.4); background: linear-gradient(160deg, rgba(251,191,36,0.12), var(--glass)); }
.card-consensus::before { background: linear-gradient(180deg, #FBBF24, #D97706); box-shadow: 2px 0 18px rgba(251,191,36,0.5); }
.card-consensus:hover { border-color: rgba(251,191,36,0.65); box-shadow: var(--glass-shadow-lift), 0 0 40px rgba(251,191,36,0.1); }

/* Card inner elements */
.card-ticker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: 0.5px;
}
.card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.dir-pill {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 4px 12px;
    border-radius: 6px;
    display: inline-block;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
}
.dir-long {
    background: rgba(16,185,129,0.22);
    color: #34D399;
    border: 1px solid rgba(16,185,129,0.5);
    text-shadow: 0 0 12px rgba(16,185,129,0.6);
    box-shadow: 0 0 12px rgba(16,185,129,0.2);
}
.dir-short {
    background: rgba(239,68,68,0.22);
    color: #F87171;
    border: 1px solid rgba(239,68,68,0.5);
    text-shadow: 0 0 12px rgba(239,68,68,0.6);
    box-shadow: 0 0 12px rgba(239,68,68,0.2);
}
/* Conviction bars */
.conv-wrap { display: inline-flex; align-items: flex-end; gap: 3px; margin-left: 8px; vertical-align: middle; }
.conv-bar { width: 4px; border-radius: 2px; background: rgba(255,255,255,0.12); display: inline-block; }
.conv-b1 { height: 7px; }
.conv-b2 { height: 12px; }
.conv-b3 { height: 17px; }
.conv-on-long { background: #10B981; box-shadow: 0 0 6px rgba(16,185,129,0.7); }
.conv-on-short { background: #EF4444; box-shadow: 0 0 6px rgba(239,68,68,0.7); }
.conv-on-gold { background: #FBBF24; box-shadow: 0 0 6px rgba(251,191,36,0.7); }

.card-channels { font-size: 12px; color: #64748B; margin-top: 10px; line-height: 1.6; }
.card-channels b { color: #94A3B8; }

.card-price-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid var(--glass-border-soft);
    gap: 8px;
    flex-wrap: wrap;
}
.price-block { display: flex; flex-direction: column; gap: 3px; }
.price-lbl { font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; color: #64748B; font-weight: 700; }
.price-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 600;
    color: #F1F5F9;
}
.price-sl { color: #EF4444 !important; }
/* Source type tags */
.tag {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 3px 9px;
    border-radius: 4px;
    display: inline-block;
}
.tag-struct { background: rgba(56,189,248,0.14); color: #38BDF8; border: 1px solid rgba(56,189,248,0.32); }
.tag-opinion { background: rgba(168,85,247,0.14); color: #C084FC; border: 1px solid rgba(168,85,247,0.32); }
.tag-consensus { background: rgba(251,191,36,0.14); color: #FBBF24; border: 1px solid rgba(251,191,36,0.34); }
.diverge-pill {
    font-size: 9px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;
    padding: 3px 9px; border-radius: 4px; display: inline-block; margin-top: 8px;
    background: rgba(245,158,11,0.14); color: #F59E0B; border: 1px solid rgba(245,158,11,0.34);
}
.consensus-banner {
    font-size: 9px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase;
    color: #FBBF24; margin-bottom: 10px; padding-bottom: 10px;
    border-bottom: 1px solid rgba(251,191,36,0.25);
}
.suggested-banner {
    font-size: 9px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase;
    color: #818CF8; margin-bottom: 10px; padding-bottom: 10px;
    border-bottom: 1px solid rgba(129,140,248,0.28);
}
.card-suggested { border-color: rgba(129,140,248,0.55) !important; box-shadow: var(--glass-shadow), 0 0 0 1px rgba(129,140,248,0.25) !important; background: linear-gradient(160deg, rgba(129,140,248,0.1), var(--glass)) !important; }
.card-suggested::before { background: linear-gradient(180deg, #818CF8, #6366F1) !important; box-shadow: 2px 0 18px rgba(129,140,248,0.55) !important; }

/* ══════════════════════════════════════════════════════════════════════════
   CONFIDENCE BADGE + CONFLICT RESOLVER
══════════════════════════════════════════════════════════════════════════ */
.conf-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 20px;
    letter-spacing: 0.5px;
    white-space: nowrap;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
}
.conf-green { background: rgba(16,185,129,0.16); color: #34D399; border: 1px solid rgba(16,185,129,0.45); box-shadow: 0 0 12px rgba(16,185,129,0.35); }
.conf-amber { background: rgba(245,158,11,0.16); color: #FBBF24; border: 1px solid rgba(245,158,11,0.45); box-shadow: 0 0 12px rgba(245,158,11,0.35); }
.conf-red   { background: rgba(239,68,68,0.16); color: #F87171; border: 1px solid rgba(239,68,68,0.45); box-shadow: 0 0 12px rgba(239,68,68,0.35); }

.conflict-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    border-radius: 18px;
    padding: 20px;
    margin-bottom: 18px;
    box-shadow: var(--glass-shadow);
}
.conflict-card.conflict-resolved { opacity: 0.5; filter: grayscale(0.25); }
.conflict-header {
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 700;
    color: #F1F5F9;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}
.conflict-side {
    background: var(--glass-soft);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid var(--glass-border);
    border-radius: 14px;
    padding: 16px 18px;
    height: 100%;
}
.conflict-side-long  { border-color: rgba(16,185,129,0.4); }
.conflict-side-short { border-color: rgba(239,68,68,0.4); }
.conflict-side-title {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 12px;
}
.conflict-stat { font-size: 12px; color: #94A3B8; line-height: 1.9; }
.conflict-stat b { color: #E2E8F0; font-family: 'JetBrains Mono', monospace; }
.resolution-done {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 700;
    color: #10B981;
    margin-top: 10px;
}

.signal-card-col div[data-testid="stButton"] > button {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 17px !important;
    font-weight: 700 !important;
    letter-spacing: 0.5px !important;
    background: transparent !important;
    border: 1px solid var(--glass-border) !important;
    color: #FFFFFF !important;
    border-radius: 10px !important;
    padding: 6px 12px !important;
    margin-bottom: 6px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
    box-shadow: none !important;
}
.signal-card-col div[data-testid="stButton"] > button:hover {
    border-color: #38BDF8 !important;
    color: #38BDF8 !important;
    box-shadow: 0 0 14px rgba(56,189,248,0.25) !important;
}

div[data-testid="column"] div[data-testid="stButton"] > button[kind="secondary"] {
    font-weight: 700 !important;
    letter-spacing: 0.8px !important;
    text-transform: uppercase !important;
    border-radius: 10px !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   GLASS PANEL
══════════════════════════════════════════════════════════════════════════ */
.glass-panel {
    background: var(--glass);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    border-radius: 18px;
    padding: 20px 22px;
    margin-bottom: 14px;
    box-shadow: var(--glass-shadow);
}

/* Dark monospace surfaces (execution metrics, activity log) */
.mono-box {
    background: rgba(3,6,16,0.5);
    backdrop-filter: blur(14px) saturate(140%);
    -webkit-backdrop-filter: blur(14px) saturate(140%);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 14px;
    box-shadow: var(--glass-shadow);
}

/* ══════════════════════════════════════════════════════════════════════════
   ROW CARD — replaces raw st.dataframe tables with a clean scannable list
══════════════════════════════════════════════════════════════════════════ */
.row-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur-sm);
    -webkit-backdrop-filter: var(--glass-blur-sm);
    border: 1px solid var(--glass-border);
    border-left: 3px solid var(--glass-border);
    border-radius: 12px;
    padding: 12px 16px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    flex-wrap: wrap;
    box-shadow: var(--glass-shadow);
}
.row-card.row-long  { border-left-color: #10B981; }
.row-card.row-short { border-left-color: #EF4444; }
.row-card-main { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; min-width: 180px; }
.row-card-chan { font-weight: 700; color: #E2E8F0; font-size: 13px; }
.row-card-meta { display: flex; gap: 18px; flex-wrap: wrap; }
.row-card-stat { text-align: right; }
.row-card-stat-lbl { font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #64748B; font-weight: 700; }
.row-card-stat-val { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #CBD5E1; font-weight: 600; }
.row-card-msg { flex-basis: 100%; font-size: 11.5px; color: #64748B; margin-top: 4px; border-top: 1px solid var(--glass-border-soft); padding-top: 8px; }

/* Asset direction bias card (replaces per-asset breakdown dataframe) */
.asset-bias-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur-sm);
    -webkit-backdrop-filter: var(--glass-blur-sm);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
    box-shadow: var(--glass-shadow);
}
.asset-bias-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.asset-bias-ticker { font-weight: 700; color: #F1F5F9; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.asset-bias-track { width: 100%; height: 10px; border-radius: 5px; overflow: hidden; display: flex; background: rgba(255,255,255,0.06); }
.asset-bias-long  { background: #10B981; height: 100%; }
.asset-bias-short { background: #EF4444; height: 100%; }
.asset-bias-counts { display: flex; justify-content: space-between; font-size: 11px; color: #64748B; margin-top: 6px; font-family: 'JetBrains Mono', monospace; }

/* Leaderboard row card (replaces raw channel index dataframe) */
.lb-row {
    background: var(--glass);
    backdrop-filter: var(--glass-blur-sm);
    -webkit-backdrop-filter: var(--glass-blur-sm);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 12px 18px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: var(--glass-shadow);
}
.lb-rank { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #64748B; font-size: 13px; width: 26px; }
.lb-name { font-weight: 700; color: #E2E8F0; font-size: 13px; flex: 1 1 160px; min-width: 140px; }
.lb-bar-track { flex: 2 1 160px; height: 8px; border-radius: 4px; background: rgba(255,255,255,0.06); overflow: hidden; min-width: 100px; }
.lb-bar-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg,#38BDF8,#818CF8); }
.lb-stats { display: flex; gap: 16px; flex: 0 0 auto; }
.lb-stat { text-align: right; min-width: 58px; }
.lb-stat-lbl { font-size: 9px; letter-spacing: 0.8px; text-transform: uppercase; color: #64748B; font-weight: 700; }
.lb-stat-val { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; }

/* Stat comparison card (lifetime vs rolling, consensus vs solo, etc.) */
.compare-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur-sm);
    -webkit-backdrop-filter: var(--glass-blur-sm);
    border: 1px solid var(--glass-border);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: var(--glass-shadow);
}
.compare-title { font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; color: #64748B; font-weight: 700; margin-bottom: 10px; }
.compare-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.compare-label { font-size: 12px; color: #94A3B8; }
.compare-val { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; }
.trend-up   { color: #10B981; }
.trend-down { color: #EF4444; }
.trend-flat { color: #64748B; }

/* Heatmap table (channel x coin win-rate matrix) */
.heatmap-table { width: 100%; border-collapse: separate; border-spacing: 4px; font-size: 11.5px; }
.heatmap-table th { color: #64748B; font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; padding: 4px 8px; text-align: center; }
.heatmap-table td { text-align: center; padding: 8px 6px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #0B0F1A; }
.heatmap-table td.hm-empty { background: var(--glass-soft) !important; color: #475569; font-weight: 400; }
.heatmap-table .hm-rowlabel { text-align: right; color: #CBD5E1; font-family: 'Space Grotesk', sans-serif; font-weight: 700; padding-right: 10px; }

/* ══════════════════════════════════════════════════════════════════════════
   GAUGES
══════════════════════════════════════════════════════════════════════════ */
.gauge-wrap { text-align: center; }
.gauge-lbl { font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase; color: #64748B; margin-top: 8px; font-weight: 700; }

/* ══════════════════════════════════════════════════════════════════════════
   SENTIMENT BAR
══════════════════════════════════════════════════════════════════════════ */
.sent-wrap {
    background: var(--glass);
    backdrop-filter: var(--glass-blur-sm);
    -webkit-backdrop-filter: var(--glass-blur-sm);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: var(--glass-shadow);
}
.sent-track { width: 100%; height: 14px; background: rgba(239,68,68,0.28); border-radius: 7px; overflow: hidden; margin-top: 10px; }
.sent-fill { height: 100%; background: #10B981; border-radius: 7px 0 0 7px; transition: width 0.5s ease; }

/* ══════════════════════════════════════════════════════════════════════════
   PODIUM
══════════════════════════════════════════════════════════════════════════ */
.podium {
    text-align: center;
    padding: 24px 14px;
    border-radius: 16px;
    border: 1px solid var(--glass-border);
    backdrop-filter: var(--glass-blur-sm);
    -webkit-backdrop-filter: var(--glass-blur-sm);
    box-shadow: var(--glass-shadow);
}
.pod-1 { background: linear-gradient(160deg,rgba(234,179,8,0.16),var(--glass)); border-color: rgba(234,179,8,0.45); }
.pod-2 { background: linear-gradient(160deg,rgba(148,163,184,0.10),var(--glass)); border-color: rgba(148,163,184,0.3); }
.pod-3 { background: linear-gradient(160deg,rgba(180,83,9,0.12),var(--glass)); border-color: rgba(180,83,9,0.35); }
.pod-rank { font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 700; color: #FFFFFF; }
.pod-name { font-size: 14px; font-weight: 700; color: #F1F5F9; margin: 8px 0 6px; }
.pod-stat { font-size: 12px; color: #94A3B8; margin-top: 3px; }

/* ══════════════════════════════════════════════════════════════════════════
   RAW MESSAGE BOX
══════════════════════════════════════════════════════════════════════════ */
.raw-msg {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    background: rgba(3,6,16,0.5);
    backdrop-filter: blur(14px) saturate(140%);
    -webkit-backdrop-filter: blur(14px) saturate(140%);
    border: 1px solid var(--glass-border);
    border-radius: 10px;
    padding: 13px 15px;
    color: #38BDF8;
    white-space: pre-wrap;
    word-break: break-all;
    box-shadow: var(--glass-shadow);
}

/* ══════════════════════════════════════════════════════════════════════════
   MOBILE STICKY STRIP
══════════════════════════════════════════════════════════════════════════ */
.m-strip {
    display: none;
    position: sticky;
    top: 0; z-index: 999;
    background: rgba(8,10,22,0.55);
    backdrop-filter: blur(22px) saturate(170%);
    -webkit-backdrop-filter: blur(22px) saturate(170%);
    border-bottom: 1px solid var(--glass-border-soft);
    padding: 10px 16px;
    justify-content: space-around;
    align-items: center;
}
.m-metric { text-align: center; }
.m-lbl { font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px; color: #64748B; }
.m-val { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; color: #F1F5F9; }

/* ══════════════════════════════════════════════════════════════════════════
   MARKET BIAS — new tab
══════════════════════════════════════════════════════════════════════════ */
.bias-card {
    background: var(--glass);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    padding: 18px 20px;
    box-shadow: var(--glass-shadow);
}
.bias-title { font-size: 11px; letter-spacing: 1.4px; text-transform: uppercase; color: #64748B; margin-bottom: 12px; font-weight: 700; }
.bias-value { font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 700; line-height: 1; }
.bias-delta { font-size: 12px; margin-top: 6px; }

/* ══════════════════════════════════════════════════════════════════════════
   AI RESEARCH NOTEBOOK
══════════════════════════════════════════════════════════════════════════ */
.ai-card {
    background: linear-gradient(160deg, rgba(129,140,248,0.08), var(--glass));
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    border-left: 3px solid #818CF8;
    border-radius: 16px;
    padding: 18px 20px;
    margin-bottom: 12px;
    box-shadow: var(--glass-shadow);
}
.ai-ticker { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; color: #E2E8F0; }
.ai-conf { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; margin-left: 8px;
    background: rgba(129,140,248,0.14); color: #A5B4FC; border: 1px solid rgba(129,140,248,0.3); }
.ai-summary { font-size: 13px; color: #94A3B8; line-height: 1.6; margin-top: 10px; }
.ai-rationale { font-size: 12px; color: #64748B; font-style: italic; margin-top: 8px; border-top: 1px solid var(--glass-border-soft); padding-top: 8px; }

/* ══════════════════════════════════════════════════════════════════════════
   SYSTEM LOGS
══════════════════════════════════════════════════════════════════════════ */
.sys-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--glass-border-soft); }
.sys-row:last-child { border-bottom: none; }
.sys-key { font-size: 12px; font-weight: 600; color: #64748B; letter-spacing: 0.5px; }
.sys-val { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; }
.sys-ok { color: #10B981; }
.sys-warn { color: #F59E0B; }
.sys-err { color: #EF4444; }
.sys-log-line {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 3px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    display: flex;
    gap: 10px;
}
.log-ts { color: #475569; }
.log-ok { color: #10B981; }
.log-warn { color: #F59E0B; }
.log-info { color: #38BDF8; }

/* ══════════════════════════════════════════════════════════════════════════
   RESPONSIVE — Mobile
══════════════════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    .block-container { padding: 0 0.75rem 3rem !important; }
    .signal-grid { grid-template-columns: 1fr !important; }
    .kpi-row { grid-template-columns: repeat(2, 1fr) !important; }
    .m-strip { display: flex !important; }
    .t-nav { padding: 0 0.75rem; margin: 0 -0.75rem 1.5rem; }
    .t-nav-brand { font-size: 12px; }
    .card-ticker { font-size: 18px; }
    .kpi-value { font-size: 22px; }
    div[data-testid="stTabs"] button[role="tab"] { padding: 10px 14px !important; font-size: 11px !important; }
}
/* Streamlit's native st.columns() don't reflow on their own — without this,
   filter rows / gauges / podium / nav controls squeeze into unreadably thin
   slivers on phone-width screens, so wrap them into a 2-up grid instead. */
@media (max-width: 640px) {
    div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; row-gap: 10px; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        min-width: 46% !important;
        flex: 1 1 46% !important;
        width: auto !important;
    }
}

/* Streamlit fades every element to partial opacity (its "stale" state) while
   a script rerun is in flight, then fades back in when it finishes. With
   st_autorefresh firing a full rerun every 30s, that reads as the whole page
   repeatedly dimming and brightening. Pin opacity so reruns are silent. */
[data-stale="true"] {
    opacity: 1 !important;
    transition: none !important;
}
</style>""")


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE LAYER
# ══════════════════════════════════════════════════════════════════════════════

def _secret(key: str):
    try:
        v = st.secrets.get(key)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(key)

@st.cache_data(ttl=30, show_spinner="Loading live signal data…")
def load_db() -> tuple:
    host, port, user = _secret("DB_HOST"), _secret("DB_PORT"), _secret("DB_USER")
    pw, db = _secret("DB_PASSWORD"), _secret("DB_NAME")
    if not all([host, port, user, db]):
        return None, None
    try:
        conn = psycopg2.connect(
            host=host, port=int(port), user=user,
            password=pw, database=db, connect_timeout=4,
        )
        cur = conn.cursor()
        # Auto-migrate
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
            ALTER TABLE active_signals ADD COLUMN IF NOT EXISTS take_profit DOUBLE PRECISION;
            ALTER TABLE active_signals ADD COLUMN IF NOT EXISTS price_at_post DOUBLE PRECISION;
            ALTER TABLE active_signals ADD COLUMN IF NOT EXISTS best_excursion DOUBLE PRECISION;
            ALTER TABLE active_signals ADD COLUMN IF NOT EXISTS worst_excursion DOUBLE PRECISION;
            CREATE TABLE IF NOT EXISTS closed_signals (
                id SERIAL PRIMARY KEY, group_name VARCHAR(255),
                ticker VARCHAR(50), trade_type VARCHAR(10),
                entry_price DOUBLE PRECISION, exit_price DOUBLE PRECISION,
                stop_loss DOUBLE PRECISION, result VARCHAR(20),
                pnl_pct DOUBLE PRECISION,
                closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            ALTER TABLE closed_signals ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) DEFAULT 'STRUCTURED';
            ALTER TABLE closed_signals ADD COLUMN IF NOT EXISTS price_at_post DOUBLE PRECISION;
            ALTER TABLE closed_signals ADD COLUMN IF NOT EXISTS mae_pct DOUBLE PRECISION;
            ALTER TABLE closed_signals ADD COLUMN IF NOT EXISTS mfe_pct DOUBLE PRECISION;
            CREATE INDEX IF NOT EXISTS idx_active_signals_created_at ON active_signals (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_active_signals_ticker_type ON active_signals (ticker, trade_type);
            CREATE INDEX IF NOT EXISTS idx_closed_signals_closed_at ON closed_signals (closed_at DESC);
        """)
        conn.commit(); cur.close()
        # Table grows forever (history sync goes back to Jan 2026 and never trims), so
        # cap what we pull per refresh — newest rows first, index above makes this cheap.
        ROW_CAP = 20_000
        df_a  = pd.read_sql(f"SELECT * FROM active_signals ORDER BY created_at DESC LIMIT {ROW_CAP}", conn)
        try:
            df_cl = pd.read_sql(f"SELECT * FROM closed_signals ORDER BY closed_at DESC LIMIT {ROW_CAP}", conn)
        except Exception:
            df_cl = pd.DataFrame()
        conn.close()
        return df_a, df_cl
    except Exception:
        return None, None


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC DEMO DATA
# ══════════════════════════════════════════════════════════════════════════════

def _demo():
    np.random.seed(42)
    groups = ["Apex VIP Signals","Bullseye Futures","Whale Intel Pro","Scalping Command"]
    coins  = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","ADAUSDT","LINKUSDT","AVAXUSDT"]
    REFS   = {
        "BTCUSDT":{"p":65000,"s":600},"ETHUSDT":{"p":3450,"s":90},
        "SOLUSDT":{"p":145,"s":6},"XRPUSDT":{"p":0.54,"s":0.03},
        "ADAUSDT":{"p":0.40,"s":0.02},"LINKUSDT":{"p":8.5,"s":0.5},
        "AVAXUSDT":{"p":30,"s":2},
    }
    rows = []
    base = datetime.datetime.now() - datetime.timedelta(days=45)
    # Give channels distinct underlying skill levels so per-channel /
    # per-channel-per-coin analytics have something real to show.
    channel_skill = {"Apex VIP Signals": 0.78, "Bullseye Futures": 0.52,
                      "Whale Intel Pro": 0.68, "Scalping Command": 0.45}
    for i in range(220):
        g = np.random.choice(groups); c = np.random.choice(coins)
        t = np.random.choice(["LONG","SHORT"], p=[0.60,0.40])
        ref = REFS[c]; e = round(ref["p"] + np.random.uniform(-ref["s"],ref["s"]),4)
        win_p = channel_skill[g]
        win = np.random.choice([True,False], p=[win_p,1-win_p])
        pnl = round(np.random.uniform(3,11) if win else np.random.uniform(-5,-2), 2)
        src = np.random.choice(["STRUCTURED","OPINION"], p=[0.72,0.28])
        lev = np.random.choice([10,20,50,100], p=[0.4,0.4,0.15,0.05])
        created = base + datetime.timedelta(days=np.random.uniform(0,43),
                                             hours=np.random.uniform(0,24))
        # Simulate signal latency: most signals post close to entry, some
        # channels post noticeably after the move already happened.
        latency_bias = 0.003 if g != "Scalping Command" else 0.018
        price_at_post = round(e * (1 + np.random.uniform(-latency_bias, latency_bias)), 4)
        # MAE = how much it drew down against the position before resolving;
        # MFE = the best excursion in favor (>= final pnl for winners).
        mae_pct = round(np.random.uniform(0.3, 3.5), 2)
        mfe_pct = round(pnl + np.random.uniform(0, 2.5), 2) if win else round(np.random.uniform(0.2, 2.0), 2)
        rows.append({
            "id":i,"group_name":g,"ticker":c,"trade_type":t,
            "entry_min":e,"entry_max":round(e*1.005,4),
            "stop_loss":round(e*(0.97 if t=="LONG" else 1.03),4),
            "source_type":src,
            "raw_message":f"[DEMO] {g} {t} {c} entry {e} (Leverage: Cross {lev}x)",
            "created_at":created,
            "result":"Hit TP" if win else "Hit SL","pnl":pnl,
            "price_at_post": price_at_post, "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        })
    df_h = pd.DataFrame(rows).sort_values("created_at", ascending=False)
    acts = [
        {"id":201,"group_name":"Apex VIP Signals","ticker":"BTCUSDT","trade_type":"LONG",
         "entry_min":64800.0,"entry_max":65100.0,"stop_loss":62200.0,
         "source_type":"STRUCTURED","raw_message":"BUY BTC 64800-65100 SL 62200 (Cross 50x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=1.5)},
        {"id":202,"group_name":"Whale Intel Pro","ticker":"BTCUSDT","trade_type":"LONG",
         "entry_min":64600.0,"entry_max":65000.0,"stop_loss":62000.0,
         "source_type":"STRUCTURED","raw_message":"LONG BTC 64600 TP 68000 SL 62000 (20x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=2)},
        {"id":203,"group_name":"Bullseye Futures","ticker":"BTCUSDT","trade_type":"LONG",
         "entry_min":64900.0,"entry_max":65200.0,"stop_loss":62500.0,
         "source_type":"OPINION","raw_message":"[OPINION DIGESTED] BTC strong support, breakout imminent",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=3)},
        {"id":204,"group_name":"Scalping Command","ticker":"ETHUSDT","trade_type":"SHORT",
         "entry_min":3440.0,"entry_max":3460.0,"stop_loss":3530.0,
         "source_type":"STRUCTURED","raw_message":"SHORT ETH 3440-3460 SL 3530 (Cross 100x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=0.5)},
        {"id":205,"group_name":"Apex VIP Signals","ticker":"SOLUSDT","trade_type":"LONG",
         "entry_min":143.5,"entry_max":145.0,"stop_loss":137.0,
         "source_type":"STRUCTURED","raw_message":"SOL LONG 143.5 SL 137 (10x)",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=4)},
        {"id":206,"group_name":"Whale Intel Pro","ticker":"ETHUSDT","trade_type":"LONG",
         "entry_min":3420.0,"entry_max":3450.0,"stop_loss":3280.0,
         "source_type":"OPINION","raw_message":"[OPINION DIGESTED] ETH holding key level, bullish bias",
         "created_at":datetime.datetime.now()-datetime.timedelta(hours=5)},
    ]
    df_a = pd.DataFrame(acts).sort_values("created_at", ascending=False)
    return df_a, df_h


# ══════════════════════════════════════════════════════════════════════════════
# DATA PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

db_all, db_closed = load_db()
IS_LIVE = db_all is not None

def _extract_lev(t):
    m = re.search(r'(\d{1,3})\s*[xX]\b', str(t))
    return int(m.group(1)) if m else None

df_stale = pd.DataFrame()  # active signals older than 24h, still genuinely open (no result yet)

if IS_LIVE:
    raw = db_all.copy()
    raw["created_at"] = pd.to_datetime(raw["created_at"])
    if "source_type" not in raw.columns:
        raw["source_type"] = "STRUCTURED"

    cutoff    = datetime.datetime.now() - datetime.timedelta(hours=24)
    df_active = raw[raw["created_at"] >= cutoff].copy()
    df_stale  = raw[raw["created_at"] <  cutoff].copy()  # still open, just aging — NOT a result

    # df_hist is built ONLY from real closed_signals. Previously, any active
    # signal older than 24h was assigned a randomly-generated win/loss and
    # PnL, which meant every "historical" stat (win rate, leaderboard,
    # analytics, market bias) was fabricated rather than derived from real
    # price outcomes. Now that scraper.py actually closes signals against
    # live prices, we only trust real closed rows.
    if db_closed is not None and not db_closed.empty:
        df_hist = db_closed.copy()
        df_hist["result"] = df_hist["result"].str.replace("HIT_TP","Hit TP",regex=False)\
                                              .str.replace("HIT_SL","Hit SL",regex=False)\
                                              .str.replace("MANUAL","Manual Close",regex=False)
        df_hist["pnl"]         = df_hist["pnl_pct"]
        df_hist["created_at"]  = pd.to_datetime(df_hist["closed_at"])
        df_hist["entry_min"]   = df_hist["entry_price"]
        df_hist["entry_max"]   = df_hist["entry_price"]
        df_hist["raw_message"] = df_hist.apply(
            lambda r: f"{r['ticker']} {r['trade_type']} closed [{r['result']}] "
                      f"entry {r['entry_price']:.4f} -> exit {r['exit_price']:.4f}", axis=1)
    else:
        df_hist = pd.DataFrame(columns=[
            "group_name","ticker","trade_type","entry_min","entry_max","stop_loss",
            "result","pnl","created_at","raw_message","source_type",
        ])
else:
    df_active, df_hist = _demo()

df_active["leverage"] = df_active["raw_message"].apply(_extract_lev)
df_hist["leverage"]   = df_hist["raw_message"].apply(_extract_lev) if not df_hist.empty else None
if not df_stale.empty:
    df_stale["leverage"] = df_stale["raw_message"].apply(_extract_lev)


# ══════════════════════════════════════════════════════════════════════════════
# DERIVED METRICS
# ══════════════════════════════════════════════════════════════════════════════

_non_cons   = df_active[df_active["group_name"] != "CONSENSUS"] if not df_active.empty else df_active
active_cnt  = len(_non_cons)
total_cnt   = len(df_active) + len(df_hist)

win_rate = 0.0
if not df_hist.empty and "result" in df_hist.columns and len(df_hist) > 0:
    win_rate = round(len(df_hist[df_hist["result"] == "Hit TP"]) / len(df_hist) * 100, 1)

avg_pnl = round(df_hist["pnl"].mean(), 2) if (not df_hist.empty and "pnl" in df_hist.columns) else 0.0

long_a    = len(df_active[df_active["trade_type"] == "LONG"]) if not df_active.empty else 0
active_s  = round(long_a / max(len(df_active), 1) * 100)

conf_cnt = 0
if not _non_cons.empty:
    gc = _non_cons.groupby(["ticker","trade_type"])["group_name"].nunique()
    conf_cnt = int((gc >= 2).sum())


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT BUILDERS  — no textwrap, direct HTML strings
# ══════════════════════════════════════════════════════════════════════════════

def _conv_bars(n: int, kind: str) -> str:
    css = ("conv-on-long" if kind == "LONG" else
           "conv-on-short" if kind == "SHORT" else "conv-on-gold")
    bars = "".join(
        f'<span class="conv-bar conv-b{i} {css if i<=n else ""}"></span>'
        for i in [1, 2, 3]
    )
    return f'<span class="conv-wrap">{bars}</span>'

def signal_card(ticker, trade_type, rooms_count, room_names,
                entry_min, entry_max, stop_loss, source_type,
                is_consensus=False, diverge=False, confidence=None,
                hide_ticker=False, suggested=False) -> str:

    card_cls = ("card-consensus" if is_consensus else
                "card-long" if trade_type == "LONG" else "card-short")
    if suggested:
        card_cls += " card-suggested"
    dir_cls  = "dir-long" if trade_type == "LONG" else "dir-short"
    dir_lbl  = "LONG" if trade_type == "LONG" else "SHORT"
    bars     = _conv_bars(min(rooms_count, 3),
                           "neutral" if is_consensus else trade_type)

    if is_consensus:
        src_tag   = '<span class="tag tag-consensus">COMMUNITY CONSENSUS</span>'
        banner    = '<div class="consensus-banner">AGGREGATED MULTI-CHANNEL SIGNAL</div>'
    elif source_type == "OPINION":
        src_tag   = '<span class="tag tag-opinion">AI OPINION</span>'
        banner    = ""
    else:
        src_tag   = '<span class="tag tag-struct">STRUCTURED</span>'
        banner    = ""

    if suggested:
        banner = '<div class="suggested-banner">★ YOUR SUGGESTED POSITION — DIVERGENCE RESOLVED</div>' + banner

    conf_html = ""
    if confidence is not None:
        conf_cls = ("green" if confidence >= 75 else
                    "amber" if confidence >= 50 else "red")
        conf_html = f'<span class="conf-badge conf-{conf_cls}">{confidence}%</span>'

    ticker_html = ""
    if not hide_ticker:
        ticker_html = f'<span class="card-ticker">{ticker}</span>'

    div_html  = '<div class="diverge-pill">DIVERGING DIRECTIONS DETECTED</div>' if diverge else ""
    room_html = (f'<b>{rooms_count} channels</b> &mdash; ' if rooms_count > 1 else "") + room_names

    return (
        f'<div class="signal-card {card_cls}">'
        f'  {banner}'
        f'  <div class="card-header">'
        f'    <div>'
        f'      {ticker_html}'
        f'      <span class="dir-pill {dir_cls}" style="margin-left:10px;">{dir_lbl}</span>'
        f'      {bars}'
        f'    </div>'
        f'    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;">'
        f'      {conf_html}'
        f'      {src_tag}'
        f'    </div>'
        f'  </div>'
        f'  <div class="card-channels">{room_html}</div>'
        f'  {div_html}'
        f'  <div class="card-price-row">'
        f'    <div class="price-block">'
        f'      <span class="price-lbl">Entry Zone</span>'
        f'      <span class="price-num">{entry_min:.4f} &ndash; {entry_max:.4f}</span>'
        f'    </div>'
        f'    <div class="price-block" style="text-align:right;">'
        f'      <span class="price-lbl">Stop Loss</span>'
        f'      <span class="price-num price-sl">{stop_loss:.4f}</span>'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )

def _svg_gauge(pct: int, color: str, label: str) -> str:
    C   = 282.7
    off = C - (pct / 100) * C
    return (
        f'<div class="gauge-wrap">'
        f'<svg width="110" height="110" viewBox="0 0 100 100">'
        f'<circle cx="50" cy="50" r="45" fill="none" stroke="#1E2A3A" stroke-width="7"/>'
        f'<circle cx="50" cy="50" r="45" fill="none" stroke="{color}" stroke-width="7"'
        f' stroke-dasharray="{C}" stroke-dashoffset="{off:.1f}" stroke-linecap="round"'
        f' transform="rotate(-90 50 50)"/>'
        f'<text x="50" y="57" text-anchor="middle"'
        f' font-family="JetBrains Mono,monospace" font-size="18" font-weight="700" fill="#F1F5F9">'
        f'{pct}%</text>'
        f'</svg>'
        f'<div class="gauge-lbl">{label}</div>'
        f'</div>'
    )


def _channel_win_rates(hist_df) -> dict:
    rates = {}
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return rates
    src = hist_df[hist_df["group_name"] != "CONSENSUS"]
    for grp in src["group_name"].unique():
        gd = src[src["group_name"] == grp]
        tot = len(gd)
        wins = len(gd[gd["result"] == "Hit TP"])
        rates[grp] = round(wins / tot * 100, 1) if tot else 50.0
    return rates


# ══════════════════════════════════════════════════════════════════════════════
# EDGE ANALYTICS — derived entirely from real closed-signal outcomes
# ══════════════════════════════════════════════════════════════════════════════

def _wr(df) -> float:
    if df.empty:
        return 0.0
    return round(len(df[df["result"] == "Hit TP"]) / len(df) * 100, 1)


def channel_skill_decay(hist_df, days=30, min_samples=5) -> list:
    """Lifetime win rate vs a trailing window, per channel — surfaces
    channels that are currently cold even if their all-time record looks good."""
    out = []
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return out
    src = hist_df[hist_df["group_name"] != "CONSENSUS"].copy()
    if src.empty:
        return out
    src["created_at"] = pd.to_datetime(src["created_at"])
    cutoff = pd.Timestamp.now(tz=src["created_at"].dt.tz) - datetime.timedelta(days=days)
    for grp in src["group_name"].unique():
        gd = src[src["group_name"] == grp]
        if len(gd) < min_samples:
            continue
        recent = gd[gd["created_at"] >= cutoff]
        lifetime_wr = _wr(gd)
        recent_wr   = _wr(recent) if len(recent) >= min_samples else None
        out.append({
            "channel": grp, "lifetime_wr": lifetime_wr, "recent_wr": recent_wr,
            "lifetime_n": len(gd), "recent_n": len(recent),
        })
    return sorted(out, key=lambda r: r["lifetime_wr"], reverse=True)


def channel_coin_matrix(hist_df, min_samples=3):
    """Per-(channel, coin) win rate matrix — a channel's edge is often
    concentrated in one or two assets rather than spread evenly.
    Returns (channels, tickers, cells) where cells maps (channel, ticker) -> {wr, n}."""
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return [], [], {}
    src = hist_df[hist_df["group_name"] != "CONSENSUS"].copy()
    if src.empty:
        return [], [], {}
    grouped = src.groupby(["group_name", "ticker"])
    cells = {}
    for (grp, tkr), gd in grouped:
        if len(gd) >= min_samples:
            cells[(grp, tkr)] = {"wr": _wr(gd), "n": len(gd)}
    if not cells:
        return [], [], {}
    channels = sorted({k[0] for k in cells}, key=lambda c: -sum(v["n"] for k, v in cells.items() if k[0] == c))
    tickers  = sorted({k[1] for k in cells}, key=lambda t: -sum(v["n"] for k, v in cells.items() if k[1] == t))
    return channels[:8], tickers[:8], cells


def consensus_vs_solo(hist_df) -> dict:
    """Does multi-channel agreement actually outperform single-channel calls?
    Approximated from the data model we have: closed CONSENSUS rows (2+
    channels agreed) vs closed single-channel rows."""
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return {}
    cons = hist_df[hist_df["group_name"] == "CONSENSUS"]
    solo = hist_df[hist_df["group_name"] != "CONSENSUS"]
    return {
        "consensus_wr": _wr(cons), "consensus_n": len(cons),
        "consensus_pnl": round(cons["pnl"].mean(), 2) if not cons.empty else 0.0,
        "solo_wr": _wr(solo), "solo_n": len(solo),
        "solo_pnl": round(solo["pnl"].mean(), 2) if not solo.empty else 0.0,
    }


def channel_expectancy(hist_df, min_samples=5) -> list:
    """Expectancy = (win% x avg win) - (loss% x avg loss). Ranks channels by
    what they actually pay out, not just how often they're right — a 40%
    win rate with big winners can beat a 70% win rate with tiny ones."""
    out = []
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return out
    src = hist_df[hist_df["group_name"] != "CONSENSUS"]
    for grp in src["group_name"].unique():
        gd = src[src["group_name"] == grp]
        if len(gd) < min_samples:
            continue
        wins = gd[gd["result"] == "Hit TP"]
        losses = gd[gd["result"] == "Hit SL"]
        win_pct = len(wins) / len(gd)
        loss_pct = len(losses) / len(gd)
        avg_win = wins["pnl"].mean() if not wins.empty else 0.0
        avg_loss = abs(losses["pnl"].mean()) if not losses.empty else 0.0
        expectancy = round(win_pct * avg_win - loss_pct * avg_loss, 3)
        out.append({
            "channel": grp, "expectancy": expectancy, "win_pct": round(win_pct*100,1),
            "avg_win": round(avg_win,2), "avg_loss": round(avg_loss,2), "n": len(gd),
        })
    return sorted(out, key=lambda r: r["expectancy"], reverse=True)


def entry_latency_stats(hist_df, tolerance_pct=0.3, min_samples=5) -> list:
    """% of a channel's signals where the stated entry zone was still
    reachable at the moment the signal was posted, using price_at_post.
    Low 'fresh' rates suggest a channel is posting after the move already
    happened (a common paid-group trick)."""
    out = []
    if (hist_df is None or hist_df.empty
            or "price_at_post" not in hist_df.columns
            or hist_df["price_at_post"].isna().all()):
        return out
    src = hist_df[(hist_df["group_name"] != "CONSENSUS") & hist_df["price_at_post"].notna()]
    for grp in src["group_name"].unique():
        gd = src[src["group_name"] == grp]
        if len(gd) < min_samples:
            continue
        tol = gd["entry_min"] * (tolerance_pct / 100)
        fresh = ((gd["price_at_post"] >= gd["entry_min"] - tol) &
                  (gd["price_at_post"] <= gd["entry_max"] + tol))
        out.append({
            "channel": grp,
            "fresh_pct": round(fresh.mean() * 100, 1),
            "n": len(gd),
        })
    return sorted(out, key=lambda r: r["fresh_pct"], reverse=True)


def excursion_stats(hist_df, min_samples=5) -> list:
    """Average drawdown winners survive (MAE) and average favorable move
    losers still got (MFE) before reversing, per channel."""
    out = []
    if (hist_df is None or hist_df.empty
            or "mae_pct" not in hist_df.columns
            or hist_df["mae_pct"].isna().all()):
        return out
    src = hist_df[hist_df["group_name"] != "CONSENSUS"]
    for grp in src["group_name"].unique():
        gd = src[src["group_name"] == grp]
        if len(gd) < min_samples:
            continue
        wins = gd[gd["result"] == "Hit TP"]
        losses = gd[gd["result"] == "Hit SL"]
        out.append({
            "channel": grp,
            "avg_mae_winners": round(wins["mae_pct"].mean(), 2) if not wins.empty and wins["mae_pct"].notna().any() else None,
            "avg_mfe_losers":  round(losses["mfe_pct"].mean(), 2) if not losses.empty and losses["mfe_pct"].notna().any() else None,
            "n": len(gd),
        })
    return out


def divergence_track_record(hist_df, window_hours=24) -> list:
    """Approximate divergence resolution: for each ticker, find same-day
    windows where both LONG and SHORT closed signals occurred, and tally
    which direction actually won more often in those overlapping windows."""
    out = []
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return out
    src = hist_df[hist_df["group_name"] != "CONSENSUS"].copy()
    if src.empty:
        return out
    src["created_at"] = pd.to_datetime(src["created_at"])
    src["_day"] = src["created_at"].dt.date
    for ticker in src["ticker"].unique():
        td = src[src["ticker"] == ticker]
        overlap_days = set(td[td["trade_type"]=="LONG"]["_day"]) & set(td[td["trade_type"]=="SHORT"]["_day"])
        if not overlap_days:
            continue
        window = td[td["_day"].isin(overlap_days)]
        long_wr  = _wr(window[window["trade_type"]=="LONG"])
        short_wr = _wr(window[window["trade_type"]=="SHORT"])
        n = len(window)
        if n < 4:
            continue
        out.append({
            "ticker": ticker, "long_wr": long_wr, "short_wr": short_wr,
            "n_days": len(overlap_days), "n": n,
        })
    return sorted(out, key=lambda r: r["n"], reverse=True)


def timing_patterns(hist_df):
    """Win rate by hour-of-day and day-of-week — cheap to compute, sometimes
    reveals that weekend / off-hours signals underperform."""
    if hist_df is None or hist_df.empty or "result" not in hist_df.columns:
        return None, None
    src = hist_df.copy()
    src["created_at"] = pd.to_datetime(src["created_at"])
    src["hour"] = src["created_at"].dt.hour
    src["weekday"] = src["created_at"].dt.day_name()
    by_hour = src.groupby("hour").apply(
        lambda g: pd.Series({"Win Rate": _wr(g), "Signals": len(g)})
    ).reset_index()
    order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    by_day = src.groupby("weekday").apply(
        lambda g: pd.Series({"Win Rate": _wr(g), "Signals": len(g)})
    ).reindex(order).dropna().reset_index()
    return by_hour, by_day


def compute_confidence(grp_df, hist_df) -> int:
    """Score a (ticker, direction) group 0–100 from agreement, source, recency, win rate."""
    if grp_df is None or grp_df.empty:
        return 0

    score = 0.0

    n_channels = grp_df["group_name"].nunique()
    score += min(n_channels, 3) * 15

    src = (grp_df["source_type"].mode()[0]
           if "source_type" in grp_df.columns else "STRUCTURED")
    if src == "STRUCTURED":
        score += 15
    elif src == "OPINION":
        score += 5
    elif src == "CONSENSUS":
        score += 10
    else:
        score += 10

    if "created_at" in grp_df.columns:
        latest = pd.to_datetime(grp_df["created_at"]).max()
        if pd.notna(latest):
            now = pd.Timestamp.now(tz=latest.tz) if getattr(latest, "tz", None) else pd.Timestamp.now()
            age_h = max((now - latest).total_seconds() / 3600, 0)
            if age_h < 1:
                score += 20
            elif age_h < 4:
                score += 12
            elif age_h < 12:
                score += 5

    wr_map = _channel_win_rates(hist_df)
    wrs = [wr_map.get(c, 50.0) for c in grp_df["group_name"].unique() if c != "CONSENSUS"]
    if wrs:
        score += sum(wrs) / len(wrs) / 100 * 20

    return min(int(round(score)), 100)


def detect_conflicts(df_active) -> dict:
    """Return tickers with both LONG and SHORT signals in the last 24 h."""
    if df_active is None or df_active.empty:
        return {}
    reg = df_active[df_active["group_name"] != "CONSENSUS"]
    out = {}
    for ticker in reg["ticker"].unique():
        tdf = reg[reg["ticker"] == ticker]
        types = set(tdf["trade_type"].unique())
        if "LONG" in types and "SHORT" in types:
            out[ticker] = {
                "long":  tdf[tdf["trade_type"] == "LONG"].copy(),
                "short": tdf[tdf["trade_type"] == "SHORT"].copy(),
            }
    return out


# Must match TARGET_RR in scraper.py — that's the multiple the outcome
# tracker actually uses to decide when a signal has hit its take-profit.
TARGET_RR = 2.0

def _estimate_rr(entry_mid, stop, trade_type) -> str:
    risk = abs(entry_mid - stop)
    if risk == 0:
        return "—"
    return f"1:{TARGET_RR:.1f}"


def _recency_label(ts) -> str:
    ts = pd.to_datetime(ts)
    now = pd.Timestamp.now(tz=ts.tz) if getattr(ts, "tz", None) else pd.Timestamp.now()
    mins = max(int((now - ts).total_seconds() / 60), 0)
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h ago"
    return f"{hrs // 24}d ago"


def _conflict_side_html(trade_type, side_df, hist_df) -> str:
    conf = compute_confidence(side_df, hist_df)
    conf_cls = "green" if conf >= 75 else ("amber" if conf >= 50 else "red")
    channels = ", ".join(side_df["group_name"].unique())
    entry_mid = float((side_df["entry_min"].mean() + side_df["entry_max"].mean()) / 2)
    stop = float(side_df["stop_loss"].mean())
    wr_map = _channel_win_rates(hist_df)
    wrs = [wr_map.get(c, 50.0) for c in side_df["group_name"].unique()]
    avg_wr = round(sum(wrs) / len(wrs), 1) if wrs else 0
    latest = pd.to_datetime(side_df["created_at"]).max()
    side_cls = "conflict-side-long" if trade_type == "LONG" else "conflict-side-short"
    color = "#10B981" if trade_type == "LONG" else "#EF4444"
    return f"""
<div class="conflict-side {side_cls}">
  <div class="conflict-side-title" style="color:{color};">{trade_type} CASE</div>
  <div class="conflict-stat"><span style="color:#64748B;">Channels</span><br><b>{channels}</b></div>
  <div class="conflict-stat"><span style="color:#64748B;">Entry Zone</span><br>
    <b>{side_df['entry_min'].mean():.4f} – {side_df['entry_max'].mean():.4f}</b></div>
  <div class="conflict-stat"><span style="color:#64748B;">Stop Loss</span><br><b style="color:#EF4444;">{stop:.4f}</b></div>
  <div class="conflict-stat"><span style="color:#64748B;">Est. R:R</span><br><b>{_estimate_rr(entry_mid, stop, trade_type)}</b></div>
  <div class="conflict-stat"><span style="color:#64748B;">Avg Channel Win Rate</span><br><b>{avg_wr}%</b></div>
  <div class="conflict-stat"><span style="color:#64748B;">Latest Signal</span><br><b>{_recency_label(latest)}</b></div>
  <div class="conflict-stat" style="margin-top:10px;">
    <span class="conf-badge conf-{conf_cls}">{conf}% confidence</span>
  </div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI-POWERED SIGNAL SYNTHESIS
# The model only narrates the structured data we hand it — the confidence score
# shown to the user is always our own deterministic compute_confidence() value,
# never something the LLM invents, so the two can't contradict each other.
# Defined here (before Tab 1) so the Live Signals drill-down can call it too,
# not just the AI Research Notebook tab.
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def _gemini_client():
    key = _secret("GEMINI_API_KEY")
    if not key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _gemini_signal_synthesis(ticker, direction, n_rooms, room_names, entry_min, entry_max,
                              stop_loss, source_mix, avg_win_rate, confidence, recency_label):
    client = _gemini_client()
    if client is None:
        return None
    from google.genai import types
    prompt = f"""You are a terse crypto trading-signal analyst. Analyze ONLY the structured
data below — never invent prices, news, or facts not given here. Do not give a buy/sell
recommendation; describe the situation and the key risk factor only.

Ticker: {ticker}
Direction across reporting channels: {direction}
Channels reporting: {n_rooms} ({room_names})
Entry zone: {entry_min:.4f} - {entry_max:.4f}
Stop loss: {stop_loss:.4f}
Signal source mix: {source_mix}
Average historical win rate of these channels: {avg_win_rate}%
Deterministic confidence score (already computed from channel count, source type,
recency and win rate — do not recompute or restate this number, just use it as context): {confidence}%
Most recent signal: {recency_label}

Return strict JSON with exactly two keys:
"summary": a 1-2 sentence synthesis of the confluence/divergence picture and what it implies.
"rationale": one short sentence naming the key risk factor to watch.
"""
    try:
        resp = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
                max_output_tokens=400,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        data = json.loads(resp.text)
        summary = str(data.get("summary", "")).strip()
        rationale = str(data.get("rationale", "")).strip()
        return (summary, rationale) if summary else None
    except Exception:
        return None


conflicts    = detect_conflicts(df_active)
conflict_cnt = len(conflicts)

if "drill_ticker" not in st.session_state:
    st.session_state.drill_ticker = None
if "conflict_resolutions" not in st.session_state:
    st.session_state.conflict_resolutions = {}


# ══════════════════════════════════════════════════════════════════════════════
# TOP NAV BAR
# ══════════════════════════════════════════════════════════════════════════════

nav_status = (
    '<span class="t-nav-status live">LIVE DATABASE</span>' if IS_LIVE
    else '<span class="t-nav-status demo">DEMO MODE</span>'
)
md(f"""
<div class="t-nav">
    <div class="t-nav-brand">SIG&nbsp;&nbsp;INTELLIGENCE&nbsp;&nbsp;TERMINAL</div>
    <div>{nav_status}</div>
</div>
""")

if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True

refresh_time = datetime.datetime.now().strftime("%H:%M:%S")
rc_gap, rc_ts, rc_toggle, rc_btn = st.columns([6, 3, 2, 2])
with rc_ts:
    md(f'<div style="font-size:11px;color:#475569;padding-top:9px;text-align:right;">'
       f'Updated&nbsp;<b style="color:#64748B;">{refresh_time}</b></div>')
with rc_toggle:
    st.checkbox("Live refresh", key="auto_refresh")
with rc_btn:
    if st.button("Refresh now", use_container_width=True):
        load_db.clear()
        st.rerun()

if st.session_state.auto_refresh:
    st_autorefresh(interval=30_000, key="live_autorefresh")


# ══════════════════════════════════════════════════════════════════════════════
# MOBILE STICKY STRIP
# ══════════════════════════════════════════════════════════════════════════════
pnl_col = "#10B981" if avg_pnl >= 0 else "#EF4444"
pnl_str = f"{'+'if avg_pnl>=0 else ''}{avg_pnl}%"
md(f"""
<div class="m-strip">
    <div class="m-metric"><div class="m-lbl">ACTIVE</div><div class="m-val">{active_cnt}</div></div>
    <div class="m-metric"><div class="m-lbl">WIN RATE</div><div class="m-val">{win_rate}%</div></div>
    <div class="m-metric"><div class="m-lbl">TOTAL</div><div class="m-val">{total_cnt:,}</div></div>
    <div class="m-metric"><div class="m-lbl">AVG PNL</div>
        <div class="m-val" style="color:{pnl_col};">{pnl_str}</div></div>
</div>
""")


# ══════════════════════════════════════════════════════════════════════════════
# 8-TAB NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════
_div_tab = f"DIVERGENCE ({conflict_cnt})" if conflict_cnt else "DIVERGENCE"
tabs = st.tabs([
    "LIVE SIGNALS",
    "ANALYTICS",
    "CHANNEL INDEX",
    "SIGNAL EXPLORER",
    "MARKET BIAS",
    "AI RESEARCH",
    "SYSTEM LOGS",
    _div_tab,
])
t_term, t_anal, t_chan, t_exp, t_bias, t_ai, t_sys, t_div = tabs


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE SIGNALS
# ════════════════════════════════════════════════════════════════════════════
with t_term:

    # KPI row
    _conf_col = "#EF4444" if conflict_cnt else "#64748B"
    md(f"""
<div class="kpi-row">
  <div class="kpi-card kpi-accent-blue">
    <div class="kpi-label">Active Signals</div>
    <div class="kpi-value" style="color:#38BDF8;">{active_cnt}</div>
    <div class="kpi-sub">Monitored last 24 h</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Confluences</div>
    <div class="kpi-value">{conf_cnt}</div>
    <div class="kpi-sub">Multi-channel agreements</div>
  </div>
  <div class="kpi-card" style="border-color:{'rgba(239,68,68,0.35)' if conflict_cnt else 'rgba(45,63,85,1)'};">
    <div class="kpi-label">Divergences</div>
    <div class="kpi-value" style="color:{_conf_col};">{conflict_cnt}</div>
    <div class="kpi-sub">LONG + SHORT conflicts</div>
  </div>
  <div class="kpi-card kpi-accent-green">
    <div class="kpi-label">Win Rate</div>
    <div class="kpi-value" style="color:#10B981;">{win_rate}%</div>
    <div class="kpi-sub">Historical accuracy</div>
  </div>
  <div class="kpi-card kpi-accent-purple">
    <div class="kpi-label">Avg PnL / Trade</div>
    <div class="kpi-value" style="color:{pnl_col};">{pnl_str}</div>
    <div class="kpi-sub">Closed archive average</div>
  </div>
</div>
""")

    board_col, side_col = st.columns([7, 3])

    with board_col:
        st.markdown(
            '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
            'color:#334155;font-weight:700;margin-bottom:12px;">'
            'LIVE SIGNAL BOARD &mdash; CONFIDENCE-SCORED GRID</div>',
            unsafe_allow_html=True,
        )

        if df_active.empty:
            st.info("No active signals in the last 24 hours. The scraper is syncing historical data — check the System Logs tab.")
        else:
            signal_groups = []
            wr_map = _channel_win_rates(df_hist)
            resolutions = st.session_state.conflict_resolutions

            cons_rows = df_active[df_active["group_name"] == "CONSENSUS"]
            for _, row in cons_rows.iterrows():
                ticker = row["ticker"]
                # Once a divergence is resolved, the losing side shouldn't keep
                # showing up on the live board — only the chosen direction does.
                if ticker in resolutions and row["trade_type"] != resolutions[ticker]:
                    continue
                m = re.search(r"CONSENSUS x (\d+)", str(row["raw_message"]))
                n = int(m.group(1)) if m else 2
                m2 = re.search(r"Channels: (.+)", str(row["raw_message"]))
                rooms = m2.group(1) if m2 else "Multiple Channels"
                grp_df = pd.DataFrame([row])
                signal_groups.append({
                    "ticker": ticker, "trade_type": row["trade_type"],
                    "rooms_count": n, "room_names": rooms,
                    "entry_min": float(row["entry_min"]),
                    "entry_max": float(row["entry_max"]),
                    "stop_loss": float(row["stop_loss"]),
                    "source_type": "CONSENSUS", "is_consensus": True,
                    "diverge": ticker in conflicts,
                    "suggested": ticker in resolutions,
                    "grp_df": grp_df,
                    "confidence": compute_confidence(grp_df, df_hist),
                })

            reg = df_active[df_active["group_name"] != "CONSENSUS"]
            if not reg.empty:
                for (ticker, ttype), grp in reg.groupby(["ticker", "trade_type"]):
                    if ticker in resolutions and ttype != resolutions[ticker]:
                        continue
                    n = grp["group_name"].nunique()
                    rooms = ", ".join(grp["group_name"].unique())
                    src = (grp["source_type"].mode()[0]
                           if "source_type" in grp.columns else "STRUCTURED")
                    signal_groups.append({
                        "ticker": ticker, "trade_type": ttype,
                        "rooms_count": n, "room_names": rooms,
                        "entry_min": float(grp["entry_min"].mean()),
                        "entry_max": float(grp["entry_max"].mean()),
                        "stop_loss": float(grp["stop_loss"].mean()),
                        "source_type": src, "is_consensus": False,
                        "diverge": ticker in conflicts,
                        "suggested": ticker in resolutions,
                        "grp_df": grp.copy(),
                        "confidence": compute_confidence(grp, df_hist),
                    })

            # Resolved divergence picks are surfaced first (they represent an
            # explicit decision), then ranked by confidence within each group —
            # so "suggested" positions land in the top row(s) instead of wherever
            # ticker/direction grouping happened to place them.
            signal_groups.sort(key=lambda g: (not g["suggested"], -g["confidence"]))

            ncols = 3
            for row_start in range(0, len(signal_groups), ncols):
                row_groups = signal_groups[row_start:row_start + ncols]
                cols = st.columns(ncols)
                for col_idx, g in enumerate(row_groups):
                    with cols[col_idx]:
                        st.markdown('<div class="signal-card-col">', unsafe_allow_html=True)
                        if st.button(
                            g["ticker"],
                            key=f"tbtn_{g['ticker']}_{g['trade_type']}_{row_start + col_idx}",
                            use_container_width=True,
                        ):
                            st.session_state.drill_ticker = g["ticker"]
                        md(signal_card(
                            g["ticker"], g["trade_type"], g["rooms_count"], g["room_names"],
                            g["entry_min"], g["entry_max"], g["stop_loss"], g["source_type"],
                            is_consensus=g["is_consensus"], diverge=g["diverge"],
                            confidence=g["confidence"], hide_ticker=True,
                            suggested=g["suggested"],
                        ))
                        st.markdown('</div>', unsafe_allow_html=True)

            if st.session_state.drill_ticker:
                drill = st.session_state.drill_ticker
                tdf = df_active[df_active["ticker"] == drill]
                if not tdf.empty:
                    with st.expander(f"{drill} — Full Signal Detail", expanded=True):
                        n_long_ch  = tdf[tdf["trade_type"] == "LONG"]["group_name"].nunique()
                        n_short_ch = tdf[tdf["trade_type"] == "SHORT"]["group_name"].nunique()
                        lp = round(n_long_ch / max(n_long_ch + n_short_ch, 1) * 100, 1)
                        md(f"""
<div class="sent-wrap" style="margin-bottom:14px;">
  <div style="font-size:12px;font-weight:700;color:#CBD5E1;">
    {n_long_ch} channel{'s' if n_long_ch != 1 else ''} LONG / {n_short_ch} channel{'s' if n_short_ch != 1 else ''} SHORT for this asset
  </div>
  <div class="sent-track"><div class="sent-fill" style="width:{lp}%;"></div></div>
</div>
""")

                        # ── Historical accuracy for this ticker specifically ──
                        drill_confidence = compute_confidence(tdf, df_hist)
                        hist_t = (df_hist[df_hist["ticker"] == drill]
                                  if not df_hist.empty and "ticker" in df_hist.columns else pd.DataFrame())
                        if not hist_t.empty and "result" in hist_t.columns:
                            t_total = len(hist_t)
                            t_wins  = len(hist_t[hist_t["result"] == "Hit TP"])
                            t_wr    = round(t_wins / t_total * 100, 1) if t_total else 0.0
                            t_pnl   = round(hist_t["pnl"].mean(), 2) if "pnl" in hist_t.columns and not hist_t["pnl"].isna().all() else None
                        else:
                            t_total, t_wr, t_pnl = 0, None, None

                        md(f"""
<div class="compare-card" style="margin-bottom:14px;">
  <div class="compare-title">HISTORICAL ACCURACY — {drill}</div>
  <div class="compare-row"><span class="compare-label">Confidence Score</span>
    <span class="compare-val" style="color:#818CF8;">{drill_confidence}%</span></div>
  <div class="compare-row"><span class="compare-label">Win Rate (closed signals)</span>
    <span class="compare-val" style="color:#10B981;">{f'{t_wr}%' if t_wr is not None else '—'}</span></div>
  <div class="compare-row"><span class="compare-label">Avg PnL (closed signals)</span>
    <span class="compare-val" style="color:{'#10B981' if (t_pnl or 0) >= 0 else '#EF4444'};">{f"{'+' if t_pnl>=0 else ''}{t_pnl}%" if t_pnl is not None else '—'}</span></div>
  <div class="compare-row"><span class="compare-label">Closed Sample Size</span>
    <span class="compare-val" style="color:#64748B;">{t_total}</span></div>
</div>
""")

                        # ── AI Review — same Gemini synthesis used in the AI Research tab,
                        # scoped to this one ticker so a drill-down click surfaces it inline. ──
                        ai_direction  = tdf["trade_type"].mode()[0] if not tdf.empty else "LONG"
                        ai_n_rooms    = tdf["group_name"].nunique()
                        ai_room_names = ", ".join(tdf["group_name"].unique())
                        ai_entry_min  = float(tdf["entry_min"].mean())
                        ai_entry_max  = float(tdf["entry_max"].mean())
                        ai_stop_loss  = float(tdf["stop_loss"].mean())
                        ai_latest     = pd.to_datetime(tdf["created_at"]).max()
                        ai_recency    = _recency_label(ai_latest) if pd.notna(ai_latest) else "unknown"
                        ai_src_counts = (tdf["source_type"].value_counts()
                                         if "source_type" in tdf.columns else pd.Series(dtype=int))
                        ai_source_mix = ", ".join(f"{k}: {v}" for k, v in ai_src_counts.items()) or "STRUCTURED: 1"
                        ai_wrs        = [wr_map.get(c, 50.0) for c in tdf["group_name"].unique()]
                        ai_avg_wr     = round(sum(ai_wrs) / len(ai_wrs), 1) if ai_wrs else 50.0

                        gemini_live_dd = _gemini_client() is not None
                        ai_result = None
                        if gemini_live_dd:
                            ai_result = _gemini_signal_synthesis(
                                drill, ai_direction, ai_n_rooms, ai_room_names,
                                ai_entry_min, ai_entry_max, ai_stop_loss,
                                ai_source_mix, ai_avg_wr, drill_confidence, ai_recency,
                            )

                        if ai_result:
                            ai_summary, ai_rationale = ai_result
                            ai_tag_html = '<span class="ai-conf" style="background:rgba(16,185,129,0.1);color:#10B981;border-color:rgba(16,185,129,0.25);">GEMINI LIVE</span>'
                        else:
                            ai_summary = (f"Signal activity detected from {ai_n_rooms} channel(s) with a {ai_direction.lower()} bias "
                                          f"and {ai_avg_wr}% average historical win rate among reporting channels.")
                            ai_rationale = ("Add GEMINI_API_KEY to your environment to enable live narrative synthesis."
                                            if not gemini_live_dd else
                                            "Gemini call unavailable this cycle — showing data-only fallback.")
                            ai_tag_html = '<span class="ai-conf">DATA-ONLY</span>'

                        ai_dir_cls = "dir-long" if ai_direction == "LONG" else "dir-short"
                        md(f"""
<div class="ai-card">
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
    <span class="ai-ticker">AI REVIEW</span>
    <span class="dir-pill {ai_dir_cls}">{ai_direction}</span>
    {ai_tag_html}
  </div>
  <div class="ai-summary">{ai_summary}</div>
  <div class="ai-rationale">RISK FACTOR: {ai_rationale}</div>
</div>
""")

                        st.markdown(
                            '<div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;'
                            'color:#334155;font-weight:700;margin:14px 0 8px;">WHO SIGNALED THIS</div>',
                            unsafe_allow_html=True,
                        )
                        for _, row in tdf.iterrows():
                            ch = row["group_name"]
                            raw = str(row.get("raw_message", ""))
                            preview = raw[:110] + ("…" if len(raw) > 110 else "")
                            wr_val = wr_map.get(ch)
                            side_cls = "row-long" if row["trade_type"] == "LONG" else "row-short"
                            dir_color = "#10B981" if row["trade_type"] == "LONG" else "#EF4444"
                            md(f"""
<div class="row-card {side_cls}">
  <div class="row-card-main">
    <span class="row-card-chan">{ch}</span>
    <span class="dir-pill {'dir-long' if row['trade_type']=='LONG' else 'dir-short'}">{row['trade_type']}</span>
    <span class="tag {'tag-opinion' if row.get('source_type')=='OPINION' else 'tag-struct'}">{row.get('source_type','STRUCTURED')}</span>
  </div>
  <div class="row-card-meta">
    <div class="row-card-stat">
      <div class="row-card-stat-lbl">Entry Zone</div>
      <div class="row-card-stat-val">{row['entry_min']:.4f}–{row['entry_max']:.4f}</div>
    </div>
    <div class="row-card-stat">
      <div class="row-card-stat-lbl">Stop Loss</div>
      <div class="row-card-stat-val" style="color:#F87171;">{row['stop_loss']:.4f}</div>
    </div>
    <div class="row-card-stat">
      <div class="row-card-stat-lbl">Channel Win Rate</div>
      <div class="row-card-stat-val" style="color:{dir_color};">{f'{wr_val}%' if wr_val is not None else '—'}</div>
    </div>
  </div>
  <div class="row-card-msg">{preview}</div>
</div>
""")

    with side_col:
        st.markdown(
            '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
            'color:#334155;font-weight:700;margin-bottom:12px;">QUICK GAUGES</div>',
            unsafe_allow_html=True,
        )

        g1, g2 = st.columns(2)
        with g1:
            md(_svg_gauge(int(win_rate), "#10B981", "WIN RATE"))
        with g2:
            md(_svg_gauge(int(active_s), "#818CF8", "LONG BIAS"))

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # Source breakdown
        if not df_active.empty and "source_type" in df_active.columns:
            str_n = len(df_active[df_active["source_type"] == "STRUCTURED"])
            opin  = len(df_active[df_active["source_type"] == "OPINION"])
            cons  = len(df_active[df_active["source_type"] == "CONSENSUS"])
            md(f"""
<div class="glass-panel" style="padding:16px;">
  <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:12px;font-weight:700;">SIGNAL SOURCES</div>
  <div style="display:flex;flex-direction:column;gap:10px;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <span class="tag tag-struct">STRUCTURED</span>
      <span style="font-family:'JetBrains Mono',monospace;color:#E2E8F0;font-size:14px;font-weight:700;">{str_n}</span>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <span class="tag tag-opinion">AI OPINION</span>
      <span style="font-family:'JetBrains Mono',monospace;color:#E2E8F0;font-size:14px;font-weight:700;">{opin}</span>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <span class="tag tag-consensus">CONSENSUS</span>
      <span style="font-family:'JetBrains Mono',monospace;color:#E2E8F0;font-size:14px;font-weight:700;">{cons}</span>
    </div>
  </div>
</div>
""")

        md(f"""
<div class="glass-panel" style="padding:16px;text-align:center;">
  <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:6px;font-weight:700;">TOTAL INGESTED</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:30px;font-weight:700;color:#E2E8F0;">{total_cnt:,}</div>
  <div style="font-size:11px;color:#1E3A5F;margin-top:6px;">signals parsed all-time</div>
</div>
""")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — ANALYTICS & METRICS
# ════════════════════════════════════════════════════════════════════════════
with t_anal:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:16px;">'
        'HISTORICAL STRATEGY ANALYTICS</div>',
        unsafe_allow_html=True,
    )

    (a_over, a_skill, a_edge, a_exec, a_time) = st.tabs([
        "OVERVIEW", "CHANNEL SKILL", "CONSENSUS & EXPECTANCY",
        "EXECUTION QUALITY", "DIVERGENCE & TIMING",
    ])

    # ── OVERVIEW ──────────────────────────────────────────────────────────
    with a_over:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Most Signaled Assets**")
            if not df_hist.empty:
                tc = df_hist["ticker"].value_counts().reset_index()
                tc.columns = ["Asset", "Signals"]
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
                    st.info("Leverage extracted once scraper processes tagged messages.")
            else:
                st.info("Awaiting historical data.")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        if not df_hist.empty:
            n_tot  = len(df_hist)
            n_long = len(df_hist[df_hist["trade_type"] == "LONG"])
            lp     = round(n_long / n_tot * 100, 1) if n_tot else 50
            sp     = round(100 - lp, 1)
            md(f"""
<div class="sent-wrap">
  <div style="display:flex;justify-content:space-between;font-size:12px;font-weight:700;">
    <span style="color:#10B981;">LONG {lp}% ({n_long:,} signals)</span>
    <span style="color:#EF4444;">SHORT {sp}% ({n_tot-n_long:,} signals)</span>
  </div>
  <div class="sent-track"><div class="sent-fill" style="width:{lp}%;"></div></div>
</div>
""")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        oc1, oc2 = st.columns(2)
        with oc1:
            if not df_hist.empty and "source_type" in df_hist.columns:
                st.markdown("**Signal Source Distribution — Structured vs AI Opinion**")
                sc = df_hist["source_type"].value_counts().reset_index()
                sc.columns = ["Type", "Count"]
                st.bar_chart(sc.set_index("Type"), color="#FBBF24", use_container_width=True)
        with oc2:
            # Opinion vs structured performance — are AI-digested opinion
            # signals actually worth acting on, or should consensus counting
            # exclude them?
            if not df_hist.empty and "source_type" in df_hist.columns and "result" in df_hist.columns:
                st.markdown("**Win Rate — Structured vs AI Opinion**")
                struct_wr = _wr(df_hist[df_hist["source_type"] == "STRUCTURED"])
                opin_wr   = _wr(df_hist[df_hist["source_type"] == "OPINION"])
                struct_n  = len(df_hist[df_hist["source_type"] == "STRUCTURED"])
                opin_n    = len(df_hist[df_hist["source_type"] == "OPINION"])
                md(f"""
<div class="compare-card">
  <div class="compare-row"><span class="compare-label">STRUCTURED ({struct_n})</span>
    <span class="compare-val" style="color:#38BDF8;">{struct_wr}%</span></div>
  <div class="compare-row"><span class="compare-label">AI OPINION ({opin_n})</span>
    <span class="compare-val" style="color:#FBBF24;">{opin_wr}%</span></div>
</div>
""")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        st.markdown("**Signal Volume Over Time**")
        if not df_hist.empty:
            df_hist["_date"] = pd.to_datetime(df_hist["created_at"]).dt.date
            ts = df_hist.groupby("_date").size().reset_index(name="Signals")
            st.line_chart(ts.set_index("_date"), color="#10B981", use_container_width=True)
        else:
            st.info("Awaiting historical data.")

    # ── CHANNEL SKILL ─────────────────────────────────────────────────────
    with a_skill:
        st.caption(
            "Lifetime win rate can hide a channel that's gone cold recently. "
            "The 30-day column shows whether their edge is holding up."
        )
        decay = channel_skill_decay(df_hist, days=30, min_samples=5)
        if not decay:
            st.info("Needs at least 5 closed signals per channel to compare lifetime vs 30-day performance.")
        else:
            for r in decay:
                if r["recent_wr"] is None:
                    trend_cls, trend_txt = "trend-flat", "— not enough recent data"
                else:
                    delta = r["recent_wr"] - r["lifetime_wr"]
                    trend_cls = "trend-up" if delta > 3 else ("trend-down" if delta < -3 else "trend-flat")
                    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
                    trend_txt = f"{arrow} {delta:+.1f} pts vs lifetime"
                recent_val = f"{r['recent_wr']}%" if r["recent_wr"] is not None else "—"
                md(f"""
<div class="lb-row">
  <div class="lb-name">{r['channel']}</div>
  <div class="lb-stats">
    <div class="lb-stat"><div class="lb-stat-lbl">Lifetime WR</div>
      <div class="lb-stat-val" style="color:#94A3B8;">{r['lifetime_wr']}%</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">30d WR</div>
      <div class="lb-stat-val" style="color:#38BDF8;">{recent_val}</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">Trend</div>
      <div class="lb-stat-val {trend_cls}" style="font-size:11px;">{trend_txt}</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">Signals</div>
      <div class="lb-stat-val" style="color:#64748B;">{r['lifetime_n']}</div></div>
  </div>
</div>
""")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown("**Per-Channel, Per-Coin Win Rate** &mdash; where each channel's edge is actually concentrated")
        channels, tickers, cells = channel_coin_matrix(df_hist, min_samples=3)
        if not channels:
            st.info("Needs at least 3 closed signals for a given channel+coin pair to show here.")
        else:
            def _hm_color(wr):
                # green at high win rate, red at low, muted amber in between
                if wr >= 65: return "#10B981"
                if wr >= 50: return "#84CC16"
                if wr >= 35: return "#F59E0B"
                return "#EF4444"
            rows_html = ""
            for ch in channels:
                cells_html = f'<td class="hm-rowlabel">{ch}</td>'
                for tk in tickers:
                    c = cells.get((ch, tk))
                    if c is None:
                        cells_html += '<td class="hm-empty">—</td>'
                    else:
                        cells_html += (f'<td style="background:{_hm_color(c["wr"])};" '
                                       f'title="{c["n"]} signals">{c["wr"]}%</td>')
                rows_html += f"<tr>{cells_html}</tr>"
            header_html = "<th></th>" + "".join(f"<th>{tk}</th>" for tk in tickers)
            md(f'<table class="heatmap-table"><tr>{header_html}</tr>{rows_html}</table>')
            st.caption("Cell = win rate for that channel on that asset (min. 3 closed signals). Hover a cell for sample size.")

    # ── CONSENSUS & EXPECTANCY ────────────────────────────────────────────
    with a_edge:
        st.markdown("**Does multi-channel consensus actually outperform single-channel calls?**")
        cvs = consensus_vs_solo(df_hist)
        if not cvs or (cvs["consensus_n"] == 0 and cvs["solo_n"] == 0):
            st.info("Awaiting closed signals to compare consensus vs solo performance.")
        else:
            cc1, cc2 = st.columns(2)
            with cc1:
                md(f"""
<div class="compare-card">
  <div class="compare-title">CONSENSUS SIGNALS (2+ CHANNELS AGREED)</div>
  <div class="compare-row"><span class="compare-label">Win Rate</span>
    <span class="compare-val" style="color:#10B981;">{cvs['consensus_wr']}%</span></div>
  <div class="compare-row"><span class="compare-label">Avg PnL</span>
    <span class="compare-val" style="color:{'#10B981' if cvs['consensus_pnl']>=0 else '#EF4444'};">{'+' if cvs['consensus_pnl']>=0 else ''}{cvs['consensus_pnl']}%</span></div>
  <div class="compare-row"><span class="compare-label">Sample Size</span>
    <span class="compare-val" style="color:#64748B;">{cvs['consensus_n']}</span></div>
</div>
""")
            with cc2:
                md(f"""
<div class="compare-card">
  <div class="compare-title">SINGLE-CHANNEL SIGNALS</div>
  <div class="compare-row"><span class="compare-label">Win Rate</span>
    <span class="compare-val" style="color:#38BDF8;">{cvs['solo_wr']}%</span></div>
  <div class="compare-row"><span class="compare-label">Avg PnL</span>
    <span class="compare-val" style="color:{'#10B981' if cvs['solo_pnl']>=0 else '#EF4444'};">{'+' if cvs['solo_pnl']>=0 else ''}{cvs['solo_pnl']}%</span></div>
  <div class="compare-row"><span class="compare-label">Sample Size</span>
    <span class="compare-val" style="color:#64748B;">{cvs['solo_n']}</span></div>
</div>
""")
            st.caption(
                "Approximate: consensus rows are the aggregated CONSENSUS entries your consolidation "
                "engine creates when 2+ channels agree; solo rows are everything else. If consensus "
                "doesn't clearly outperform, that's a sign the channels may be echoing each other "
                "rather than independently confirming a move."
            )

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown("**Channel Expectancy** &mdash; ranked by what each channel actually pays out, not just how often it's right")
        exp = channel_expectancy(df_hist, min_samples=5)
        if not exp:
            st.info("Needs at least 5 closed signals per channel to compute expectancy.")
        else:
            for r in exp:
                exp_color = "#10B981" if r["expectancy"] > 0 else "#EF4444"
                md(f"""
<div class="lb-row">
  <div class="lb-name">{r['channel']}</div>
  <div class="lb-stats">
    <div class="lb-stat"><div class="lb-stat-lbl">Expectancy</div>
      <div class="lb-stat-val" style="color:{exp_color};">{'+' if r['expectancy']>=0 else ''}{r['expectancy']}%/trade</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">Win %</div>
      <div class="lb-stat-val" style="color:#38BDF8;">{r['win_pct']}%</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">Avg Win</div>
      <div class="lb-stat-val" style="color:#10B981;">+{r['avg_win']}%</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">Avg Loss</div>
      <div class="lb-stat-val" style="color:#EF4444;">-{r['avg_loss']}%</div></div>
    <div class="lb-stat"><div class="lb-stat-lbl">Signals</div>
      <div class="lb-stat-val" style="color:#64748B;">{r['n']}</div></div>
  </div>
</div>
""")
            st.caption("Expectancy = (win% × avg win) − (loss% × avg loss). Positive means the channel is profitable on average per signal.")

    # ── EXECUTION QUALITY ─────────────────────────────────────────────────
    with a_exec:
        st.markdown("**Entry Freshness** &mdash; was the stated entry zone still reachable when the signal was posted?")
        latency = entry_latency_stats(df_hist)
        if not latency:
            st.info(
                "Needs price_at_post data, which is only captured for signals ingested in real time "
                "going forward (not backfilled history). Give it a few days of live signals."
            )
        else:
            for r in latency:
                bar_color = "#10B981" if r["fresh_pct"] >= 70 else ("#F59E0B" if r["fresh_pct"] >= 40 else "#EF4444")
                md(f"""
<div class="asset-bias-card">
  <div class="asset-bias-top">
    <span class="asset-bias-ticker">{r['channel']}</span>
    <span style="font-size:11px;color:#64748B;">{r['n']} signals</span>
  </div>
  <div class="asset-bias-track"><div style="width:{r['fresh_pct']}%;height:100%;background:{bar_color};"></div></div>
  <div class="asset-bias-counts"><span>Entry still reachable at post time</span><span style="color:{bar_color};">{r['fresh_pct']}%</span></div>
</div>
""")
            st.caption("Low percentages suggest a channel often posts after the move has already happened.")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown("**Drawdown to Target (MAE / MFE)**")
        exc = excursion_stats(df_hist)
        if not exc:
            st.info(
                "Needs mae_pct/mfe_pct data, populated by the outcome tracker for signals closed "
                "going forward. Give it time to accumulate closed signals."
            )
        else:
            for r in exc:
                mae_txt = f"-{r['avg_mae_winners']}%" if r["avg_mae_winners"] is not None else "—"
                mfe_txt = f"+{r['avg_mfe_losers']}%" if r["avg_mfe_losers"] is not None else "—"
                md(f"""
<div class="row-card">
  <div class="row-card-main"><span class="row-card-chan">{r['channel']}</span>
    <span style="font-size:11px;color:#64748B;">{r['n']} signals</span></div>
  <div class="row-card-meta">
    <div class="row-card-stat"><div class="row-card-stat-lbl">Avg Heat Before Winning</div>
      <div class="row-card-stat-val" style="color:#F59E0B;">{mae_txt}</div></div>
    <div class="row-card-stat"><div class="row-card-stat-lbl">Avg Favorable Move Before Losing</div>
      <div class="row-card-stat-val" style="color:#818CF8;">{mfe_txt}</div></div>
  </div>
</div>
""")
            st.caption(
                "'Heat before winning' = how far winning trades drew down before recovering to TP — "
                "high values suggest stops are tight relative to normal volatility. 'Favorable move before "
                "losing' = how close losing trades got before reversing to SL."
            )

    # ── DIVERGENCE & TIMING ────────────────────────────────────────────────
    with a_time:
        st.markdown("**Divergence Track Record** &mdash; when a ticker had both LONG and SHORT signals the same day, which side actually won?")
        div_rec = divergence_track_record(df_hist)
        if not div_rec:
            st.info("Needs overlapping same-day LONG and SHORT closed signals on the same ticker to compare.")
        else:
            for r in div_rec:
                long_c  = "#10B981" if r["long_wr"]  > r["short_wr"] else "#64748B"
                short_c = "#EF4444" if r["short_wr"] > r["long_wr"]  else "#64748B"
                md(f"""
<div class="row-card">
  <div class="row-card-main"><span class="row-card-chan">{r['ticker']}</span>
    <span style="font-size:11px;color:#64748B;">{r['n_days']} overlapping day(s), {r['n']} signals</span></div>
  <div class="row-card-meta">
    <div class="row-card-stat"><div class="row-card-stat-lbl">LONG Win Rate</div>
      <div class="row-card-stat-val" style="color:{long_c};">{r['long_wr']}%</div></div>
    <div class="row-card-stat"><div class="row-card-stat-lbl">SHORT Win Rate</div>
      <div class="row-card-stat-val" style="color:{short_c};">{r['short_wr']}%</div></div>
  </div>
</div>
""")
            st.caption("Approximate: 'same day' is used as a proxy for a genuine divergence window.")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown("**Timing Patterns**")
        by_hour, by_day = timing_patterns(df_hist)
        if by_hour is None or by_hour.empty:
            st.info("Awaiting closed signals to analyze timing patterns.")
        else:
            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown("*Win Rate by Hour of Day (UTC-local)*")
                st.bar_chart(by_hour.set_index("hour")["Win Rate"], color="#38BDF8", use_container_width=True)
            with tc2:
                st.markdown("*Win Rate by Day of Week*")
                st.bar_chart(by_day.set_index("weekday")["Win Rate"], color="#818CF8", use_container_width=True)
            st.caption("Based on signal creation time, not necessarily local trading-session time.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — CHANNEL INDEX (LEADERBOARD)
# ════════════════════════════════════════════════════════════════════════════
with t_chan:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:4px;">CHANNEL PERFORMANCE INDEX</div>',
        unsafe_allow_html=True,
    )
    st.caption("Ranked by Consistency Score = (Win Rate × 0.8) + Avg PnL + 10")

    src_h = df_hist[df_hist["group_name"] != "CONSENSUS"] if not df_hist.empty else df_hist
    lb    = []
    if not src_h.empty and "result" in src_h.columns:
        for grp in src_h["group_name"].unique():
            gd    = src_h[src_h["group_name"] == grp]
            tot   = len(gd)
            wins  = len(gd[gd["result"] == "Hit TP"])
            wr    = round(wins / tot * 100, 1) if tot else 0
            apnl  = round(gd["pnl"].mean(), 2) if ("pnl" in gd.columns and not gd["pnl"].isna().all()) else 0
            score = round(wr * 0.8 + min(max(apnl, -10), 20) + 10, 1)
            lb.append({"Channel":grp,"Score":score,"Signals":tot,"TP Hits":wins,"Win Rate":wr,"Avg PnL":apnl})

    if lb:
        lb_df = pd.DataFrame(lb).sort_values("Score", ascending=False)

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        p1c, p2c, p3c = st.columns(3)

        def _pod(col, idx, rank_lbl, css_cls, scale=""):
            if len(lb_df) > idx:
                r = lb_df.iloc[idx]
                with col:
                    md(f"""
<div class="podium {css_cls}" style="{scale}">
  <div class="pod-rank">{rank_lbl}</div>
  <div class="pod-name">{r['Channel']}</div>
  <div class="pod-stat">Score: <b style="color:#E2E8F0;">{r['Score']}</b></div>
  <div class="pod-stat" style="color:#10B981;">{r['Win Rate']}% win rate</div>
  <div class="pod-stat">{r['Signals']} signals tracked</div>
</div>
""")

        _pod(p2c, 1, "#2", "pod-2")
        _pod(p1c, 0, "#1", "pod-1", "transform:scale(1.04);margin-top:-10px;")
        _pod(p3c, 2, "#3", "pod-3")

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        lb_df = lb_df.reset_index(drop=True)
        for i, r in lb_df.iterrows():
            pnl_c = "#10B981" if r["Avg PnL"] >= 0 else "#EF4444"
            md(f"""
<div class="lb-row">
  <div class="lb-rank">#{i+1}</div>
  <div class="lb-name">{r['Channel']}</div>
  <div class="lb-bar-track"><div class="lb-bar-fill" style="width:{r['Win Rate']}%;"></div></div>
  <div class="lb-stats">
    <div class="lb-stat">
      <div class="lb-stat-lbl">Score</div>
      <div class="lb-stat-val" style="color:#E2E8F0;">{r['Score']}</div>
    </div>
    <div class="lb-stat">
      <div class="lb-stat-lbl">Win Rate</div>
      <div class="lb-stat-val" style="color:#38BDF8;">{r['Win Rate']}%</div>
    </div>
    <div class="lb-stat">
      <div class="lb-stat-lbl">Signals</div>
      <div class="lb-stat-val" style="color:#94A3B8;">{r['Signals']}</div>
    </div>
    <div class="lb-stat">
      <div class="lb-stat-lbl">Avg PnL</div>
      <div class="lb-stat-val" style="color:{pnl_c};">{'+' if r['Avg PnL']>=0 else ''}{r['Avg PnL']}%</div>
    </div>
  </div>
</div>
""")
    else:
        st.info("Leaderboard populates once historical data is available.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — SIGNAL EXPLORER
# ════════════════════════════════════════════════════════════════════════════
with t_exp:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:12px;">HISTORICAL SIGNAL ARCHIVE</div>',
        unsafe_allow_html=True,
    )

    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        f_coin = st.text_input("Coin filter (e.g. BTC)", "").strip().upper()
    with fc2:
        ch_opts = (["All Channels"] + sorted(df_hist["group_name"].unique().tolist())
                   if not df_hist.empty else ["All Channels"])
        f_chan  = st.selectbox("Channel", ch_opts)
    with fc3:
        f_res   = st.selectbox("Outcome", ["All Outcomes","Hit TP","Hit SL"])
    with fc4:
        f_src   = st.selectbox("Source Type", ["All Sources","STRUCTURED","OPINION","CONSENSUS"])

    df_f = df_hist.copy()
    if f_coin:
        df_f = df_f[df_f["ticker"].str.contains(f_coin, na=False)]
    if f_chan != "All Channels":
        df_f = df_f[df_f["group_name"] == f_chan]
    if f_res != "All Outcomes":
        df_f = df_f[df_f["result"] == f_res]
    if f_src != "All Sources" and "source_type" in df_f.columns:
        df_f = df_f[df_f["source_type"] == f_src]

    if df_f.empty:
        st.caption("0 records match current filters")
        st.info("No records match the current filter combination.")
    else:
        dl_col, cap_col = st.columns([2, 6])
        with dl_col:
            st.download_button(
                "⬇ Export filtered CSV",
                data=df_f.to_csv(index=False).encode("utf-8"),
                file_name=f"signal_archive_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with cap_col:
            md(f'<div style="font-size:12px;color:#64748B;padding-top:10px;">{len(df_f):,} records match current filters</div>')

        PAGE_SIZE = 25
        total_pages = max((len(df_f) - 1) // PAGE_SIZE + 1, 1)
        if "explorer_page" not in st.session_state:
            st.session_state.explorer_page = 1
        st.session_state.explorer_page = min(max(st.session_state.explorer_page, 1), total_pages)

        pg1, pg2, pg3 = st.columns([2, 2, 6])
        with pg1:
            if st.button("← Prev page", disabled=st.session_state.explorer_page <= 1, use_container_width=True):
                st.session_state.explorer_page -= 1
                st.rerun()
        with pg2:
            if st.button("Next page →", disabled=st.session_state.explorer_page >= total_pages, use_container_width=True):
                st.session_state.explorer_page += 1
                st.rerun()
        with pg3:
            md(f'<div style="font-size:12px;color:#64748B;padding-top:10px;">'
               f'Page {st.session_state.explorer_page} of {total_pages}</div>')

        start = (st.session_state.explorer_page - 1) * PAGE_SIZE
        page_df = df_f.iloc[start:start + PAGE_SIZE]

        for _, row in page_df.iterrows():
            ri   = "+" if row.get("result") == "Hit TP" else ("-" if row.get("result") == "Hit SL" else "~")
            lev  = f" {int(row['leverage'])}x" if pd.notna(row.get("leverage")) else ""
            src  = f" [{row.get('source_type','?')}]" if "source_type" in row else ""
            ts   = pd.to_datetime(row["created_at"]).strftime("%Y-%m-%d %H:%M")
            title = f"[{ri}] {ts}  |  {row['group_name']}  ->  {row['ticker']} {row['trade_type']}{lev}{src}"

            with st.expander(title):
                ex1, ex2 = st.columns([6, 4])
                pnl_v = row.get("pnl", 0) or 0
                pnl_c = "#10B981" if pnl_v >= 0 else "#EF4444"
                with ex1:
                    md('<div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:6px;font-weight:700;">RAW TELEGRAM MESSAGE</div>')
                    md(f'<div class="raw-msg">{row.get("raw_message","—")}</div>')
                with ex2:
                    md('<div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:6px;font-weight:700;">EXECUTION METRICS</div>')
                    md(f"""
<div class="mono-box" style="font-size:13px;line-height:2.1;">
  <div style="display:flex;justify-content:space-between;">
    <span style="color:#334155;">Entry Min</span>
    <span style="font-family:'JetBrains Mono',monospace;color:#CBD5E1;">{row['entry_min']:.4f}</span>
  </div>
  <div style="display:flex;justify-content:space-between;">
    <span style="color:#334155;">Entry Max</span>
    <span style="font-family:'JetBrains Mono',monospace;color:#CBD5E1;">{row['entry_max']:.4f}</span>
  </div>
  <div style="display:flex;justify-content:space-between;">
    <span style="color:#334155;">Stop Loss</span>
    <span style="font-family:'JetBrains Mono',monospace;color:#F87171;">{row['stop_loss']:.4f}</span>
  </div>
  <div style="border-top:1px solid #1A2235;margin-top:8px;padding-top:8px;display:flex;justify-content:space-between;">
    <span style="color:#334155;">Net PnL</span>
    <span style="font-family:'JetBrains Mono',monospace;font-weight:700;color:{pnl_c};">{'+'if pnl_v>=0 else ''}{pnl_v:.2f}%</span>
  </div>
</div>
""")


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — MARKET BIAS GAUGES
# ════════════════════════════════════════════════════════════════════════════
with t_bias:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:4px;">MACRO MARKET BIAS INDICATORS</div>',
        unsafe_allow_html=True,
    )
    st.caption("Live-feed indicators require an exchange API integration. Displaying signal-derived proxies.")

    b1, b2, b3 = st.columns(3)

    long_h  = len(df_hist[df_hist["trade_type"]=="LONG"])  if not df_hist.empty else 0
    short_h = len(df_hist[df_hist["trade_type"]=="SHORT"]) if not df_hist.empty else 0
    tot_h   = long_h + short_h or 1
    long_pct  = round(long_h / tot_h * 100, 1)
    short_pct = round(short_h / tot_h * 100, 1)

    avg_lev = round(df_hist["leverage"].mean(), 1) if (not df_hist.empty and "leverage" in df_hist and df_hist["leverage"].notna().any()) else "N/A"
    avg_lev_str = f"{avg_lev}x" if avg_lev != "N/A" else "N/A"

    with b1:
        md(f"""
<div class="bias-card">
  <div class="bias-title">SIGNAL LONG BIAS</div>
  <div class="bias-value" style="color:#10B981;">{long_pct}%</div>
  <div class="bias-delta" style="color:#334155;">{long_h:,} long signals recorded</div>
</div>
""")

    with b2:
        md(f"""
<div class="bias-card">
  <div class="bias-title">SIGNAL SHORT BIAS</div>
  <div class="bias-value" style="color:#EF4444;">{short_pct}%</div>
  <div class="bias-delta" style="color:#334155;">{short_h:,} short signals recorded</div>
</div>
""")

    with b3:
        md(f"""
<div class="bias-card">
  <div class="bias-title">AVG LEVERAGE SIGNALED</div>
  <div class="bias-value" style="color:#F59E0B;">{avg_lev_str}</div>
  <div class="bias-delta" style="color:#334155;">Average across all leverage-tagged messages</div>
</div>
""")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Gauge row
    gv1, gv2, gv3, gv4 = st.columns(4)
    with gv1:
        md(_svg_gauge(int(win_rate), "#10B981", "OVERALL WIN RATE"))
    with gv2:
        md(_svg_gauge(int(long_pct), "#38BDF8", "LONG BIAS"))
    with gv3:
        md(_svg_gauge(int(short_pct), "#EF4444", "SHORT BIAS"))
    with gv4:
        conf_pct = min(int(conf_cnt / max(active_cnt, 1) * 100), 100)
        md(_svg_gauge(conf_pct, "#818CF8", "CONFLUENCE RATE"))

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Asset bias breakdown
    if not df_hist.empty:
        st.markdown("**Per-Asset Direction Breakdown**")
        ab = df_hist.groupby(["ticker", "trade_type"]).size().unstack(fill_value=0)
        for col in ("LONG", "SHORT"):
            if col not in ab.columns:
                ab[col] = 0
        ab = ab.reset_index().sort_values(["LONG", "SHORT"], ascending=False)

        bc1, bc2 = st.columns(2)
        half = (len(ab) + 1) // 2
        for col, chunk in zip((bc1, bc2), (ab.iloc[:half], ab.iloc[half:])):
            with col:
                for _, r in chunk.iterrows():
                    tot = r["LONG"] + r["SHORT"]
                    lp  = round(r["LONG"] / tot * 100, 1) if tot else 50
                    sp  = round(100 - lp, 1)
                    md(f"""
<div class="asset-bias-card">
  <div class="asset-bias-top">
    <span class="asset-bias-ticker">{r['ticker']}</span>
    <span style="font-size:11px;color:#64748B;">{tot} signals</span>
  </div>
  <div class="asset-bias-track">
    <div class="asset-bias-long" style="width:{lp}%;"></div>
    <div class="asset-bias-short" style="width:{sp}%;"></div>
  </div>
  <div class="asset-bias-counts">
    <span style="color:#10B981;">{r['LONG']} LONG ({lp}%)</span>
    <span style="color:#EF4444;">{r['SHORT']} SHORT ({sp}%)</span>
  </div>
</div>
""")

    # Funding rate placeholder
    md("""
<div class="glass-panel" style="margin-top:16px;">
  <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:10px;font-weight:700;">FUNDING RATES &amp; LIQUIDATIONS</div>
  <div style="font-size:13px;color:#475569;line-height:1.7;">
    Real-time funding rate and liquidation data requires direct exchange REST/WebSocket integration
    (Bitunix or Blofin). Connect an exchange feed and this panel will auto-populate with
    per-asset funding rate heatmaps, cumulative liquidation delta, and open interest change.
  </div>
  <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
    <span class="tag tag-struct">BITUNIX READY</span>
    <span class="tag tag-opinion">BLOFIN READY</span>
  </div>
</div>
""")


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — AI RESEARCH NOTEBOOK
# ════════════════════════════════════════════════════════════════════════════
with t_ai:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:4px;">AI RESEARCH NOTEBOOK</div>',
        unsafe_allow_html=True,
    )
    gemini_live = _gemini_client() is not None
    if gemini_live:
        st.caption("Live Gemini synthesis of active signal confluence — refreshed every 10 minutes per ticker. Not financial advice.")
    else:
        st.caption("Autonomous LLM analysis of active signal pairs. Add GEMINI_API_KEY to enable live inference.")

    if not df_active.empty:
        active_tickers = _non_cons["ticker"].value_counts().head(5).index.tolist()
        wr_map_ai = _channel_win_rates(df_hist)

        for ticker in active_tickers:
            grp_data  = _non_cons[_non_cons["ticker"] == ticker]
            n_rooms   = grp_data["group_name"].nunique()
            room_names = ", ".join(grp_data["group_name"].unique())
            direction = grp_data["trade_type"].mode()[0] if not grp_data.empty else "LONG"
            entry_min = float(grp_data["entry_min"].mean())
            entry_max = float(grp_data["entry_max"].mean())
            stop_loss = float(grp_data["stop_loss"].mean())
            confidence = compute_confidence(grp_data, df_hist)
            latest = pd.to_datetime(grp_data["created_at"]).max()
            recency = _recency_label(latest) if pd.notna(latest) else "unknown"

            src_counts = (grp_data["source_type"].value_counts()
                          if "source_type" in grp_data.columns else pd.Series(dtype=int))
            source_mix = ", ".join(f"{k}: {v}" for k, v in src_counts.items()) or "STRUCTURED: 1"

            wrs = [wr_map_ai.get(c, 50.0) for c in grp_data["group_name"].unique()]
            avg_wr = round(sum(wrs) / len(wrs), 1) if wrs else 50.0

            result = None
            if gemini_live:
                result = _gemini_signal_synthesis(
                    ticker, direction, n_rooms, room_names, entry_min, entry_max,
                    stop_loss, source_mix, avg_wr, confidence, recency,
                )

            if result:
                summary, rationale = result
                tag_html = '<span class="ai-conf" style="background:rgba(16,185,129,0.1);color:#10B981;border-color:rgba(16,185,129,0.25);">GEMINI LIVE</span>'
            else:
                summary = (f"Signal activity detected from {n_rooms} channel(s) with a {direction.lower()} bias "
                           f"and {avg_wr}% average historical win rate among reporting channels.")
                rationale = ("Add GEMINI_API_KEY to your environment to enable live narrative synthesis."
                              if not gemini_live else
                              "Gemini call unavailable this cycle — showing data-only fallback.")
                tag_html = '<span class="ai-conf">DATA-ONLY</span>'

            conf_color = "#10B981" if confidence >= 70 else ("#F59E0B" if confidence >= 50 else "#EF4444")
            dir_cls_ai = "dir-long" if direction == "LONG" else "dir-short"

            md(f"""
<div class="ai-card">
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
    <span class="ai-ticker">{ticker}</span>
    <span class="dir-pill {dir_cls_ai}">{direction}</span>
    <span class="ai-conf">CONFIDENCE: <b style="color:{conf_color};">{confidence}%</b></span>
    {tag_html}
    <span style="margin-left:auto;font-size:10px;color:#334155;">{n_rooms} channel(s) active</span>
  </div>
  <div class="ai-summary">{summary}</div>
  <div class="ai-rationale">RISK FACTOR: {rationale}</div>
</div>
""")
    else:
        md("""
<div class="glass-panel">
  <div style="font-size:13px;color:#475569;line-height:1.8;">
    No active signals to analyze. Once the Telegram scraper populates the database,
    this notebook will auto-generate analysis cards for each active trading pair,
    including confidence scores, chart rationales, and risk commentary.
  </div>
</div>
""")

    if not gemini_live:
        md("""
<div class="glass-panel" style="margin-top:8px;border-color:rgba(129,140,248,0.2);">
  <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:10px;font-weight:700;">ENABLE LIVE LLM INFERENCE</div>
  <div style="font-size:13px;color:#475569;line-height:1.8;">
    Add <code style="background:rgba(56,189,248,0.12);padding:2px 6px;border-radius:6px;color:#38BDF8;border:1px solid rgba(56,189,248,0.25);">GEMINI_API_KEY</code>
    to your <code style="background:rgba(56,189,248,0.12);padding:2px 6px;border-radius:6px;color:#38BDF8;border:1px solid rgba(56,189,248,0.25);">.env</code>
    / Streamlit Secrets to replace the data-only fallback with real-time synthesis
    of each active signal group.
  </div>
</div>
""")


# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — SYSTEM CONTROL LOGS
# ════════════════════════════════════════════════════════════════════════════
with t_sys:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:12px;">SYSTEM CONTROL LOGS</div>',
        unsafe_allow_html=True,
    )

    sys1, sys2 = st.columns(2)

    with sys1:
        db_status    = "CONNECTED" if IS_LIVE else "OFFLINE"
        db_css       = "sys-ok" if IS_LIVE else "sys-err"
        db_row_count = len(db_all) if IS_LIVE and db_all is not None else 0
        md(f"""
<div class="glass-panel">
  <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:12px;font-weight:700;">POSTGRESQL — AIVEN CLOUD</div>
  <div class="sys-row">
    <span class="sys-key">Connection Status</span>
    <span class="sys-val {db_css}">{db_status}</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">active_signals rows</span>
    <span class="sys-val sys-ok">{db_row_count:,}</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">Schema Version</span>
    <span class="sys-val sys-ok">v3 (dual-table)</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">SSL Mode</span>
    <span class="sys-val sys-ok">REQUIRED</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">Cache TTL</span>
    <span class="sys-val sys-info" style="color:#38BDF8;">30 seconds</span>
  </div>
</div>
""")

    _configured_channels = _secret("TELEGRAM_CHANNELS")
    if _configured_channels:
        channels_monitored = len([c for c in str(_configured_channels).split(",") if c.strip()])
    elif IS_LIVE and db_all is not None and not db_all.empty:
        channels_monitored = db_all[db_all["group_name"] != "CONSENSUS"]["group_name"].nunique()
    else:
        channels_monitored = "—"

    with sys2:
        md(f"""
<div class="glass-panel">
  <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#334155;margin-bottom:12px;font-weight:700;">TELETHON SCRAPER — RENDER</div>
  <div class="sys-row">
    <span class="sys-key">Scraper Platform</span>
    <span class="sys-val sys-ok">Render Free Tier</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">Session Type</span>
    <span class="sys-val sys-ok">StringSession (Cloud)</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">Channels Monitored</span>
    <span class="sys-val sys-ok">{channels_monitored}</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">Consolidation Engine</span>
    <span class="sys-val sys-ok">60s background thread</span>
  </div>
  <div class="sys-row">
    <span class="sys-key">History Sync Target</span>
    <span class="sys-val sys-ok">Jan 1, 2026</span>
  </div>
</div>
""")

    # Recent activity — built from real ingested signals, not simulated data
    recent_src = pd.concat([df_active, df_hist], ignore_index=True) if not df_hist.empty else df_active.copy()
    if not recent_src.empty:
        recent_src = recent_src[recent_src["group_name"] != "CONSENSUS"]
        recent_src = recent_src[recent_src["created_at"].notna()].sort_values("created_at", ascending=False).head(12)

    st.markdown(
        '<div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin:14px 0 8px;">RECENT SIGNAL ACTIVITY</div>',
        unsafe_allow_html=True,
    )

    if recent_src.empty:
        md('<div class="glass-panel" style="font-size:13px;color:#475569;">No signals ingested yet — this fills in as the scraper processes Telegram messages.</div>')
    else:
        log_html = '<div class="mono-box">'
        for _, row in recent_src.iterrows():
            ts_str = pd.to_datetime(row["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            is_long = row["trade_type"] == "LONG"
            dir_css = "log-ok" if is_long else "log-warn"
            src     = row.get("source_type", "STRUCTURED")
            msg     = f'{row["ticker"]} from {row["group_name"]} [{src}]'
            log_html += (f'<div class="sys-log-line">'
                         f'<span class="log-ts">{ts_str}</span>'
                         f'<span class="{dir_css}" style="min-width:44px;font-weight:700;">{row["trade_type"]}</span>'
                         f'<span style="color:#475569;">{msg}</span>'
                         f'</div>')
        log_html += "</div>"
        md(log_html)


# ════════════════════════════════════════════════════════════════════════════
# TAB 8 — DIVERGENCE ALERT
# ════════════════════════════════════════════════════════════════════════════
with t_div:
    st.markdown(
        '<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;'
        'color:#334155;font-weight:700;margin-bottom:4px;">DIVERGENCE ALERT — CONFLICT RESOLVER</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Assets with simultaneous LONG and SHORT signals in the last 24 hours. "
        "Review both cases and pick a direction."
    )

    if not conflicts:
        md("""
<div class="glass-panel" style="text-align:center;padding:32px;">
  <div style="font-size:14px;color:#10B981;font-weight:700;margin-bottom:8px;">No active divergences</div>
  <div style="font-size:13px;color:#475569;">All monitored assets have a unified directional bias in the last 24 h.</div>
</div>
""")
    else:
        for ticker, sides in conflicts.items():
            resolved = st.session_state.conflict_resolutions.get(ticker)
            dim_cls = " conflict-resolved" if resolved else ""
            badge = (
                f'<span class="conf-badge conf-green">✓ {resolved}</span>'
                if resolved else
                '<span class="conf-badge conf-red">UNRESOLVED</span>'
            )
            md(f"""
<div class="conflict-card{dim_cls}">
  <div class="conflict-header">
    <span>{ticker}</span>
    {badge}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
    {_conflict_side_html("LONG", sides["long"], df_hist)}
    {_conflict_side_html("SHORT", sides["short"], df_hist)}
  </div>
</div>
""")

            if resolved:
                md(f'<div class="resolution-done">✓ Resolved — leaning <b>{resolved}</b></div>')
            else:
                rb1, rb2 = st.columns(2)
                with rb1:
                    if st.button("I'M BULLISH", key=f"bull_{ticker}", use_container_width=True):
                        st.session_state.conflict_resolutions[ticker] = "LONG"
                        st.rerun()
                with rb2:
                    if st.button("I'M BEARISH", key=f"bear_{ticker}", use_container_width=True):
                        st.session_state.conflict_resolutions[ticker] = "SHORT"
                        st.rerun()

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)