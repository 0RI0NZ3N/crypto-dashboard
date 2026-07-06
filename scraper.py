import os
import re
import datetime
import http.server
import socketserver
import threading
import time
import urllib.request
import json
import logging
import sys
import ccxt
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import psycopg2
from psycopg2 import pool as pg_pool
from dotenv import load_dotenv

# ─────────────────────────────────────────
# STRUCTURED LOGGING
# Render captures stdout, so a StreamHandler there is enough to make logs
# searchable/filterable by level instead of scrolling through bare print()s.
# ─────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("signal_scraper")

# ─────────────────────────────────────────
# CONFIGURATION — all from environment/secrets
# ─────────────────────────────────────────
load_dotenv()

API_ID          = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH        = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING  = os.environ.get("TELEGRAM_SESSION_STRING", "")

CHANNELS_STR    = os.environ.get("TELEGRAM_CHANNELS", "")
CHANNELS        = [int(c.strip()) for c in CHANNELS_STR.split(",") if c.strip()]

DB_PARAMS = {
    "host":     os.environ.get("DB_HOST", ""),
    "port":     int(os.environ.get("DB_PORT", 5432)) if os.environ.get("DB_PORT") else 5432,
    "user":     os.environ.get("DB_USER", ""),
    "database": os.environ.get("DB_NAME", ""),
    "password": os.environ.get("DB_PASSWORD", ""),
}

# Telegram bot used for pushing consensus-signal alerts (separate bot/token
# from the userbot session used for scraping — create one via @BotFather).
ALERT_BOT_TOKEN      = os.environ.get("ALERT_BOT_TOKEN", "")
ALERT_CHAT_ID        = os.environ.get("ALERT_CHAT_ID", "")
ALERT_COOLDOWN_HOURS = float(os.environ.get("ALERT_COOLDOWN_HOURS", 6))

if not API_ID or not API_HASH:
    raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH not set in environment.")

# ─────────────────────────────────────────
# DB CONNECTION POOL
# Every DB call previously opened its own psycopg2.connect(), which is fine
# at low volume but adds real latency/overhead as channel count grows and
# the consolidation + outcome-tracker threads run concurrently. A small
# threaded pool lets those threads share a handful of persistent connections
# instead of establishing a fresh TCP+auth handshake every time.
# ─────────────────────────────────────────
_pool = None
if DB_PARAMS["host"]:
    try:
        _pool = pg_pool.ThreadedConnectionPool(minconn=1, maxconn=10, **DB_PARAMS)
        logger.info("DB connection pool created (1-10 connections).")
    except Exception as e:
        logger.error(f"Failed to create DB connection pool, falling back to per-call connections: {e}")
        _pool = None

def get_conn():
    if _pool:
        return _pool.getconn()
    return psycopg2.connect(**DB_PARAMS)

def release_conn(conn):
    if _pool:
        try:
            _pool.putconn(conn)
        except Exception:
            pass
    else:
        conn.close()


# ─────────────────────────────────────────
# TELEGRAM ALERTING
# Pushes a message to a Telegram chat/channel via the Bot API whenever a
# new (or strengthened) multi-channel consensus signal appears.
# ─────────────────────────────────────────
_alert_state: dict = {}  # (ticker, trade_type) -> {"count": int, "last_alert": datetime}

def send_telegram_alert(text: str):
    if not ALERT_BOT_TOKEN or not ALERT_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{ALERT_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": ALERT_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")


def maybe_alert_consensus(ticker: str, trade_type: str, room_count: int, rooms: str,
                          entry_min: float, entry_max: float, stop_loss: float):
    """
    Alert on a genuinely new consensus, on growing agreement (more channels
    joined in), or as a periodic reminder — never on every 60s re-scan of an
    unchanged consensus, which would spam the chat.
    """
    key   = (ticker, trade_type)
    now   = datetime.datetime.now(datetime.timezone.utc)
    prev  = _alert_state.get(key)

    is_new       = prev is None
    grew         = prev is not None and room_count > prev["count"]
    cooldown_hit = (prev is not None and
                    (now - prev["last_alert"]).total_seconds() >= ALERT_COOLDOWN_HOURS * 3600)

    if is_new or grew or cooldown_hit:
        dir_emoji = "🟢" if trade_type == "LONG" else "🔴"
        reason    = "NEW" if is_new else ("STRENGTHENING" if grew else "STILL ACTIVE")
        text = (
            f"{dir_emoji} <b>{reason} CONSENSUS — {ticker} {trade_type}</b>\n"
            f"Channels ({room_count}): {rooms}\n"
            f"Entry: {entry_min:.4f} – {entry_max:.4f}\n"
            f"Stop Loss: {stop_loss:.4f}"
        )
        send_telegram_alert(text)
        _alert_state[key] = {"count": room_count, "last_alert": now}

# ─────────────────────────────────────────
# HEALTH-CHECK HTTP SERVER (Render free tier)
# ─────────────────────────────────────────
def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK - Signal Scraper Running")
        def log_message(self, format, *args):
            pass  # suppress noisy access logs
    with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
        logger.info(f"Health-check server on port {port}")
        httpd.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ─────────────────────────────────────────
# TELETHON CLIENT
# ─────────────────────────────────────────
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SOURCE LIVE PRICE FETCHER
# Primary: Blofin (CCXT) — Fallback: Bitunix (HTTP) — Failsafe: MEXC (CCXT)
# ─────────────────────────────────────────────────────────────────────────────
_price_cache: dict = {}
_price_cache_ts: dict = {}
PRICE_CACHE_TTL = 30  # seconds

# Initialize CCXT exchanges
blofin = ccxt.blofin()
mexc = ccxt.mexc()

def _from_bitunix(ticker: str) -> float | None:
    """Manual HTTP fetcher for Bitunix since it isn't in CCXT yet."""
    try:
        # Query the public Bitunix futures ticker endpoint
        url = "https://fapi.bitunix.com/api/v1/futures/market/tickers"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            
            # Find the specific ticker in the returned array
            for item in data.get("data", []):
                if item.get("symbol") == ticker:
                    return float(item.get("close", 0))
    except Exception:
        pass
    return None

def fetch_live_price(ticker: str) -> float | None:
    """
    Fetch the current market price for a USDT-margined pair.
    """
    now = time.time()
    if ticker in _price_cache and now - _price_cache_ts.get(ticker, 0) < PRICE_CACHE_TTL:
        return _price_cache[ticker]

    # CCXT requires standard format with slashes (e.g., BTC/USDT)
    ccxt_symbol = ticker
    if ticker.endswith("USDT") and "/" not in ticker:
        ccxt_symbol = f"{ticker[:-4]}/USDT"

    # 1. Attempt Primary: Blofin
    try:
        ticker_data = blofin.fetch_ticker(ccxt_symbol)
        price = ticker_data['last']
        if price and price > 0:
            _price_cache[ticker] = price
            _price_cache_ts[ticker] = now
            logger.debug(f"{ticker} price {price} fetched via Blofin")
            return price
    except Exception as e:
        logger.debug(f"Blofin fetch failed for {ticker} — trying Bitunix...")

    # 2. Attempt Fallback: Bitunix
    price = _from_bitunix(ticker)
    if price and price > 0:
        _price_cache[ticker] = price
        _price_cache_ts[ticker] = now
        logger.debug(f"{ticker} price {price} fetched via Bitunix")
        return price
    else:
        logger.debug(f"Bitunix fetch failed for {ticker} — trying MEXC failsafe...")

    # 3. Attempt Ultimate Failsafe: MEXC
    try:
        ticker_data = mexc.fetch_ticker(ccxt_symbol)
        price = ticker_data['last']
        if price and price > 0:
            _price_cache[ticker] = price
            _price_cache_ts[ticker] = now
            logger.debug(f"{ticker} price {price} fetched via MEXC")
            return price
    except Exception as e:
        logger.warning(f"All price sources failed for {ticker}")

    return None

# Keep old name as alias so nothing else breaks inside the Opinion Parser
fetch_binance_price = fetch_live_price
# ─────────────────────────────────────────
# COIN / TICKER DETECTION
# ─────────────────────────────────────────
# Ordered by specificity — longer symbols first to avoid substring collisions
KNOWN_COINS = [
    "DOGE", "LINK", "AVAX", "NEAR", "AAVE", "MATIC", "ATOM",
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "BNB", "LTC",
    "UNI", "FIL", "ICP", "ETC", "TRX", "APT", "ARB", "OP",
]

def detect_ticker(text: str) -> str | None:
    """Extract the most likely USDT trading pair from the message text."""
    text_upper = text.upper()

    # 1. Explicit XYZUSDT symbol in text
    m = re.search(r'\b([A-Z]{2,10})USDT\b', text_upper)
    if m:
        return m.group(0)

    # 2. Hashtag-prefixed ticker e.g. #NEAR or $SOL
    # Only trust this if the candidate is a coin we actually recognize —
    # previously ANY <=5 char hashtag/cashtag (#PLS, $ATH, $GM, etc.) was
    # accepted as a real ticker, producing false-positive signals.
    m = re.search(r'[#$]([A-Z]{2,10})\b', text_upper)
    if m:
        candidate = m.group(1)
        if candidate in KNOWN_COINS:
            return f"{candidate}USDT"

    # 3. Known coin list substring scan
    for coin in KNOWN_COINS:
        if re.search(rf'\b{coin}\b', text_upper):
            return f"{coin}USDT"

    return None


# ─────────────────────────────────────────
# OPINION SENTIMENT ANALYZER
# ─────────────────────────────────────────
BULL_WORDS = [
    "BUY", "LONG", "BULLISH", "BREAKOUT", "SUPPORT", "PUMP",
    "UPWARD", "MOON", "ACCUMULATE", "CALL", "TARGET", "TP",
    "BOUNCE", "REVERSAL UP", "HOLD", "STRONG",
]
BEAR_WORDS = [
    "SELL", "SHORT", "BEARISH", "REJECTION", "BREAKDOWN",
    "RESISTANCE", "DUMP", "DOWNWARD", "DROP", "CRASH",
    "FADE", "WEAK", "FALLING", "CLOSE LONG",
]

def analyze_sentiment(text: str) -> str | None:
    t = text.upper()
    bull = sum(t.count(w) for w in BULL_WORDS)
    bear = sum(t.count(w) for w in BEAR_WORDS)
    if bull > bear:
        return "LONG"
    if bear > bull:
        return "SHORT"
    return None


# ─────────────────────────────────────────
# SIGNAL PARSERS
# ─────────────────────────────────────────

def parse_signal_text(text: str) -> dict | None:
    """
    Primary structured parser.
    Attempts to extract explicit numeric entry / SL from formatted signal messages.
    Tags result with source_type = 'STRUCTURED'.
    """
    try:
        t_up = text.upper()

        # Direction
        if "LONG" in t_up or re.search(r'\bBUY\b', t_up):
            trade_type = "LONG"
        elif "SHORT" in t_up or re.search(r'\bSELL\b', t_up):
            trade_type = "SHORT"
        else:
            return None

        ticker = detect_ticker(text)
        if not ticker:
            return None

        # Price reference defaults (used to filter noise numbers)
        DEFAULTS = {
            "BTCUSDT":  {"entry": 65000.0, "sl": 62000.0, "step": 500.0},
            "ETHUSDT":  {"entry": 3500.0,  "sl": 3300.0,  "step": 50.0},
            "SOLUSDT":  {"entry": 145.0,   "sl": 135.0,   "step": 5.0},
            "XRPUSDT":  {"entry": 0.52,    "sl": 0.47,    "step": 0.02},
            "ADAUSDT":  {"entry": 0.40,    "sl": 0.36,    "step": 0.02},
            "DOGEUSDT": {"entry": 0.13,    "sl": 0.11,    "step": 0.01},
            "LINKUSDT": {"entry": 8.0,     "sl": 7.0,     "step": 0.3},
            "AVAXUSDT": {"entry": 30.0,    "sl": 27.0,    "step": 1.0},
            "DOTUSDT":  {"entry": 7.0,     "sl": 6.0,     "step": 0.3},
        }
        ref = DEFAULTS.get(ticker, {"entry": 1.0, "sl": 0.9, "step": 0.05})

        # Extract numbers, stripping commas (e.g. 62,800 → 62800)
        clean = text.replace(",", "")
        numbers = [float(n) for n in re.findall(r'\b\d+(?:\.\d+)?\b', clean)]

        # Keep only numbers plausibly within 0.1× – 15× of reference entry
        lo, hi = ref["entry"] * 0.1, ref["entry"] * 15
        valid = sorted(n for n in numbers if lo <= n <= hi)

        if len(valid) >= 3:
            if trade_type == "LONG":
                stop_loss, entry_min, entry_max = valid[0], valid[1], valid[2]
            else:
                entry_min, entry_max, stop_loss = valid[0], valid[1], valid[2]
        elif len(valid) == 2:
            if trade_type == "LONG":
                stop_loss, entry_min = min(valid), max(valid)
                entry_max = entry_min * 1.005
            else:
                entry_min, stop_loss = min(valid), max(valid)
                entry_max = entry_min * 1.005
        else:
            # No valid prices found — fall through to opinion parser
            return None

        # Look for an explicit take-profit level (TP, TP1, TARGET, etc.).
        # When present, this is used instead of a derived 2:1 reward:risk
        # target, so tracked outcomes reflect what the channel actually
        # called rather than an assumption.
        take_profit = None
        tp_match = re.search(
            r'\bT(?:AKE)?[\s\-]?P(?:ROFIT)?S?1?\b\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)',
            t_up,
        )
        if not tp_match:
            tp_match = re.search(r'\bTARGET1?\b\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)', t_up)
        if tp_match:
            try:
                tp_val = float(tp_match.group(1).replace(",", ""))
                # TP levels sit further from entry than the noise-filter
                # range used for entry/SL, so allow a wider band.
                if ref["entry"] * 0.1 <= tp_val <= ref["entry"] * 30:
                    take_profit = round(tp_val, 6)
            except ValueError:
                pass

        return {
            "ticker":      ticker,
            "trade_type":  trade_type,
            "entry_min":   round(entry_min, 6),
            "entry_max":   round(entry_max, 6),
            "stop_loss":   round(stop_loss, 6),
            "take_profit": take_profit,
            "source_type": "STRUCTURED",
            "raw_message": text,
        }
    except Exception:
        return None


def parse_opinion_text(text: str) -> dict | None:
    """
    Fallback opinion parser.
    Digests unstructured trader commentary into actionable signals
    by combining sentiment analysis with a live Blofin/Bitunix price anchor.
    Tags result with source_type = 'OPINION'.
    """
    try:
        ticker = detect_ticker(text)
        if not ticker:
            return None

        trade_type = analyze_sentiment(text)
        if not trade_type:
            return None

        live_price = fetch_live_price(ticker)
        if not live_price:
            return None

        # Generate a ±3 % / ±6 % zone around current price
        if trade_type == "LONG":
            entry_min = round(live_price * 0.999, 6)
            entry_max = round(live_price * 1.005, 6)
            stop_loss = round(live_price * 0.97,  6)
        else:
            entry_min = round(live_price * 0.995, 6)
            entry_max = round(live_price * 1.001, 6)
            stop_loss = round(live_price * 1.03,  6)

        return {
            "ticker":      ticker,
            "trade_type":  trade_type,
            "entry_min":   entry_min,
            "entry_max":   entry_max,
            "stop_loss":   stop_loss,
            "take_profit": None,
            "source_type": "OPINION",
            "raw_message": f"[OPINION DIGESTED] {text}",
        }
    except Exception:
        return None


def parse_message(text: str) -> dict | None:
    """Try structured parser first; fall back to opinion parser."""
    return parse_signal_text(text) or parse_opinion_text(text)


# ─────────────────────────────────────────
# DATABASE INIT (creates both tables)
# ─────────────────────────────────────────

def init_db():
    if not DB_PARAMS["host"]:
        logger.warning("No DB host configured — skipping DB init.")
        return
    try:
        conn = get_conn()
        cur  = conn.cursor()

        # ── active_signals ───────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_signals (
                id          SERIAL PRIMARY KEY,
                group_name  VARCHAR(255),
                ticker      VARCHAR(50),
                trade_type  VARCHAR(10),
                entry_min   DOUBLE PRECISION,
                entry_max   DOUBLE PRECISION,
                stop_loss   DOUBLE PRECISION,
                source_type VARCHAR(20) DEFAULT 'STRUCTURED',
                raw_message TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add source_type column to existing deployments that predate v2
        cur.execute("""
            ALTER TABLE active_signals
                ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) DEFAULT 'STRUCTURED';
        """)
        # Explicit take-profit level, when the source message states one.
        # NULL means "no explicit TP found — fall back to the derived
        # reward:risk target" (handled in the outcome tracker).
        cur.execute("""
            ALTER TABLE active_signals
                ADD COLUMN IF NOT EXISTS take_profit DOUBLE PRECISION;
        """)
        # Live price at the moment the signal was ingested — lets us measure
        # whether the stated entry zone was still reachable when posted
        # (signal latency / "hindsight signal" detection).
        cur.execute("""
            ALTER TABLE active_signals
                ADD COLUMN IF NOT EXISTS price_at_post DOUBLE PRECISION;
        """)
        # Running best/worst price seen while the signal has been open —
        # updated every outcome-tracker poll — used to compute max favorable
        # / max adverse excursion (MFE/MAE) once the signal closes.
        cur.execute("""
            ALTER TABLE active_signals
                ADD COLUMN IF NOT EXISTS best_excursion DOUBLE PRECISION;
        """)
        cur.execute("""
            ALTER TABLE active_signals
                ADD COLUMN IF NOT EXISTS worst_excursion DOUBLE PRECISION;
        """)

        # ── closed_signals ───────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS closed_signals (
                id          SERIAL PRIMARY KEY,
                group_name  VARCHAR(255),
                ticker      VARCHAR(50),
                trade_type  VARCHAR(10),
                entry_price DOUBLE PRECISION,
                exit_price  DOUBLE PRECISION,
                stop_loss   DOUBLE PRECISION,
                result      VARCHAR(20),
                pnl_pct     DOUBLE PRECISION,
                source_type VARCHAR(20) DEFAULT 'STRUCTURED',
                closed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            ALTER TABLE closed_signals
                ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) DEFAULT 'STRUCTURED';
        """)
        cur.execute("""
            ALTER TABLE closed_signals
                ADD COLUMN IF NOT EXISTS price_at_post DOUBLE PRECISION;
        """)
        cur.execute("""
            ALTER TABLE closed_signals
                ADD COLUMN IF NOT EXISTS mae_pct DOUBLE PRECISION;
        """)
        cur.execute("""
            ALTER TABLE closed_signals
                ADD COLUMN IF NOT EXISTS mfe_pct DOUBLE PRECISION;
        """)

        # Indexes — the dashboard and the consolidation/outcome-tracker
        # threads repeatedly filter/group by these columns.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_created_at ON active_signals (created_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_ticker     ON active_signals (ticker, trade_type);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_group      ON active_signals (group_name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_closed_closed_at  ON closed_signals (closed_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_closed_group      ON closed_signals (group_name);")

        conn.commit()
        cur.close()
        release_conn(conn)
        logger.info("DB tables verified / migrated (active_signals + closed_signals).")
    except Exception as e:
        logger.error(f"DB init error: {e}")


# ─────────────────────────────────────────
# DB INSERT HELPER
# ─────────────────────────────────────────

def insert_signal(parsed: dict, group_name: str, created_at=None):
    if not DB_PARAMS["host"]:
        logger.info(f"[no-DB] {parsed['ticker']} {parsed['trade_type']} ({parsed['source_type']})")
        return
    try:
        conn = get_conn()
        cur  = conn.cursor()
        tp = parsed.get("take_profit")
        # Only stamp a "price at post" for real-time signals — during
        # historical backfill this would just be today's price, not the
        # price at the time the old message was sent, so it's left NULL.
        price_at_post = fetch_live_price(parsed["ticker"]) if created_at is None else None
        if created_at:
            cur.execute("""
                INSERT INTO active_signals
                    (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, take_profit, source_type, raw_message, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (group_name, parsed["ticker"], parsed["trade_type"],
                  parsed["entry_min"], parsed["entry_max"], parsed["stop_loss"], tp,
                  parsed["source_type"], parsed["raw_message"], created_at))
        else:
            cur.execute("""
                INSERT INTO active_signals
                    (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, take_profit, price_at_post, source_type, raw_message)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (group_name, parsed["ticker"], parsed["trade_type"],
                  parsed["entry_min"], parsed["entry_max"], parsed["stop_loss"], tp, price_at_post,
                  parsed["source_type"], parsed["raw_message"]))
        conn.commit()
        cur.close()
        release_conn(conn)
        icon = "🟢" if parsed["trade_type"] == "LONG" else "🔴"
        tp_note = f" TP={tp:.4f}" if tp else ""
        logger.info(f"{icon} {parsed['ticker']} {parsed['trade_type']}{tp_note} [{parsed['source_type']}] from {group_name}")
    except Exception as e:
        logger.error(f"DB insert error: {e}")


# ─────────────────────────────────────────
# CONSOLIDATION ENGINE
# Groups signals by (ticker, trade_type), computes averaged community consensus
# zones when 2+ channels agree. Runs every 60 seconds.
# ─────────────────────────────────────────

def run_consolidation():
    """
    Background thread: every 60 s, scan active_signals from the last 24 h,
    find consensus groups (2+ channels, same ticker + direction),
    and upsert a synthetic 'CONSENSUS' row with averaged entry/SL values.
    """
    while True:
        time.sleep(60)
        if not DB_PARAMS["host"]:
            continue
        try:
            conn = get_conn()
            cur  = conn.cursor()

            # Pull last-24h signals
            cur.execute("""
                SELECT ticker, trade_type,
                       AVG(entry_min) AS avg_entry_min,
                       AVG(entry_max) AS avg_entry_max,
                       AVG(stop_loss) AS avg_sl,
                       AVG(take_profit) AS avg_tp,
                       COUNT(DISTINCT group_name) AS room_count,
                       STRING_AGG(DISTINCT group_name, ' + ' ORDER BY group_name) AS rooms
                FROM active_signals
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                  AND group_name != 'CONSENSUS'
                GROUP BY ticker, trade_type
                HAVING COUNT(DISTINCT group_name) >= 2
            """)
            rows = cur.fetchall()

            for row in rows:
                ticker, trade_type, avg_emin, avg_emax, avg_sl, avg_tp, cnt, rooms = row
                raw = (f"[CONSENSUS × {cnt}] {ticker} {trade_type} "
                       f"entry {avg_emin:.4f}–{avg_emax:.4f} SL {avg_sl:.4f} "
                       f"| Channels: {rooms}")

                # Delete stale consensus row for same pair before reinserting
                cur.execute("""
                    DELETE FROM active_signals
                    WHERE group_name = 'CONSENSUS'
                      AND ticker = %s AND trade_type = %s
                      AND created_at >= NOW() - INTERVAL '2 hours'
                """, (ticker, trade_type))

                cur.execute("""
                    INSERT INTO active_signals
                        (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, take_profit, source_type, raw_message)
                    VALUES ('CONSENSUS', %s, %s, %s, %s, %s, %s, 'CONSENSUS', %s)
                """, (ticker, trade_type,
                      round(avg_emin, 6), round(avg_emax, 6), round(avg_sl, 6),
                      round(avg_tp, 6) if avg_tp is not None else None,
                      raw))

                maybe_alert_consensus(ticker, trade_type, cnt, rooms, avg_emin, avg_emax, avg_sl)

            conn.commit()
            cur.close()
            release_conn(conn)
            if rows:
                logger.info(f"⚡ Consolidation: {len(rows)} consensus zone(s) updated.")
        except Exception as e:
            logger.error(f"Consolidation error: {e}")

threading.Thread(target=run_consolidation, daemon=True).start()


# ─────────────────────────────────────────
# OUTCOME TRACKER
# Watches every open (non-CONSENSUS) signal against the live price feed and
# moves it into closed_signals with a REAL result the moment price hits
# stop-loss, hits the take-profit target, or the signal expires from age.
#
# Uses the channel's own stated take-profit level when the parser found one
# (take_profit column). Only falls back to a derived reward:risk multiple
# for messages that didn't state an explicit TP. The fallback multiple is
# the same one used for the "Est. R:R" figure shown in the dashboard, so
# the two stay consistent with each other.
# ─────────────────────────────────────────
TARGET_RR      = 2.0     # fallback take-profit distance = 2x the stop-loss distance
MAX_SIGNAL_AGE_DAYS = 7   # signals still open after this long are force-closed

def _close_signal(cur, row_id, group_name, ticker, trade_type,
                   entry_price, stop_loss, exit_price, result, source_type="STRUCTURED",
                   price_at_post=None, best_excursion=None, worst_excursion=None):
    if trade_type == "LONG":
        pnl_pct = round((exit_price - entry_price) / entry_price * 100, 4)
        mfe_pct = (round((best_excursion - entry_price) / entry_price * 100, 4)
                   if best_excursion is not None else None)
        mae_pct = (round((entry_price - worst_excursion) / entry_price * 100, 4)
                   if worst_excursion is not None else None)
    else:
        pnl_pct = round((entry_price - exit_price) / entry_price * 100, 4)
        mfe_pct = (round((entry_price - best_excursion) / entry_price * 100, 4)
                   if best_excursion is not None else None)
        mae_pct = (round((worst_excursion - entry_price) / entry_price * 100, 4)
                   if worst_excursion is not None else None)

    cur.execute("""
        INSERT INTO closed_signals
            (group_name, ticker, trade_type, entry_price, exit_price, stop_loss, result, pnl_pct,
             source_type, price_at_post, mae_pct, mfe_pct)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (group_name, ticker, trade_type, entry_price, exit_price, stop_loss, result, pnl_pct,
          source_type, price_at_post, mae_pct, mfe_pct))
    cur.execute("DELETE FROM active_signals WHERE id = %s", (row_id,))


def run_outcome_tracker():
    """
    Background thread: every 45s, check open signals against live prices.
    Also tracks the running best/worst excursion (MFE/MAE) for every open
    signal so that, once closed, we know not just whether it won but how
    much heat/drawdown it took to get there.
    """
    while True:
        time.sleep(45)
        if not DB_PARAMS["host"]:
            continue
        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute("""
                SELECT id, group_name, ticker, trade_type, entry_min, entry_max,
                       stop_loss, take_profit, created_at, source_type,
                       price_at_post, best_excursion, worst_excursion
                FROM active_signals
                WHERE group_name != 'CONSENSUS'
            """)
            rows = cur.fetchall()
            closed = 0

            for (rid, group_name, ticker, trade_type, entry_min, entry_max,
                 stop_loss, take_profit, created_at, source_type,
                 price_at_post, best_excursion, worst_excursion) in rows:

                entry_mid = (entry_min + entry_max) / 2
                risk = abs(entry_mid - stop_loss)
                if risk == 0:
                    continue
                if take_profit is not None:
                    target = take_profit
                else:
                    target = (entry_mid + TARGET_RR * risk if trade_type == "LONG"
                              else entry_mid - TARGET_RR * risk)

                price = fetch_live_price(ticker)
                age_days = (datetime.datetime.now(datetime.timezone.utc)
                            - created_at.replace(tzinfo=datetime.timezone.utc)
                            if created_at.tzinfo is None else
                            datetime.datetime.now(datetime.timezone.utc) - created_at
                            ).days

                if price is None:
                    if age_days >= MAX_SIGNAL_AGE_DAYS:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, entry_mid, "Manual Close", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1
                    continue

                # Update running best/worst excursion before evaluating close
                # conditions, so the very tick that closes the signal is
                # still reflected in its own MFE/MAE.
                if best_excursion is None:
                    best_excursion = worst_excursion = entry_mid
                if trade_type == "LONG":
                    best_excursion  = max(best_excursion, price)
                    worst_excursion = min(worst_excursion, price)
                else:
                    best_excursion  = min(best_excursion, price)
                    worst_excursion = max(worst_excursion, price)
                cur.execute("""
                    UPDATE active_signals SET best_excursion = %s, worst_excursion = %s
                    WHERE id = %s
                """, (best_excursion, worst_excursion, rid))

                if trade_type == "LONG":
                    if price <= stop_loss:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, price, "Hit SL", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1
                    elif price >= target:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, price, "Hit TP", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1
                    elif age_days >= MAX_SIGNAL_AGE_DAYS:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, price, "Manual Close", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1
                else:  # SHORT
                    if price >= stop_loss:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, price, "Hit SL", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1
                    elif price <= target:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, price, "Hit TP", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1
                    elif age_days >= MAX_SIGNAL_AGE_DAYS:
                        _close_signal(cur, rid, group_name, ticker, trade_type,
                                       entry_mid, stop_loss, price, "Manual Close", source_type,
                                       price_at_post, best_excursion, worst_excursion)
                        closed += 1

            conn.commit()
            cur.close()
            release_conn(conn)
            if closed:
                logger.info(f"Outcome tracker: {closed} signal(s) closed with real results.")
        except Exception as e:
            logger.error(f"Outcome tracker error: {e}")

threading.Thread(target=run_outcome_tracker, daemon=True).start()


# ─────────────────────────────────────────
# REAL-TIME EVENT HANDLER
# ─────────────────────────────────────────

@client.on(events.NewMessage(chats=CHANNELS))
async def on_new_message(event):
    raw_text = event.raw_text
    if not raw_text or len(raw_text.strip()) < 8:
        return

    chat = await event.get_chat()
    group_name = getattr(chat, "title", "Unknown Group") or "Unknown Group"

    parsed = parse_message(raw_text)
    if parsed:
        insert_signal(parsed, group_name)


# ─────────────────────────────────────────
# HISTORICAL SYNC (back to Jan 1 2026)
# ─────────────────────────────────────────

async def scrape_history():
    logger.info("Starting historical sync (back to 2026-01-01)…")
    if not DB_PARAMS["host"]:
        logger.warning("No DB host — skipping history sync.")
        return

    cutoff = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    conn = get_conn()
    cur  = conn.cursor()

    for channel_id in CHANNELS:
        try:
            entity       = await client.get_entity(channel_id)
            group_name   = getattr(entity, "title", f"Group {channel_id}")
            logger.info(f"Syncing {group_name} ({channel_id})…")
            inserted = 0

            # Preload existing (raw_message, created_at) pairs for this group
            # once, instead of issuing a SELECT per message (which made large
            # history syncs extremely slow / DB-connection-heavy).
            cur.execute(
                "SELECT raw_message, created_at FROM active_signals WHERE group_name = %s",
                (group_name,),
            )
            existing = {(msg_text, ts) for msg_text, ts in cur.fetchall()}

            async for msg in client.iter_messages(channel_id, limit=None):
                if msg.date < cutoff:
                    break
                if not msg.text or len(msg.text.strip()) < 8:
                    continue

                parsed = parse_message(msg.text)
                if not parsed:
                    continue

                if (parsed["raw_message"], msg.date) in existing:
                    continue
                existing.add((parsed["raw_message"], msg.date))

                cur.execute("""
                    INSERT INTO active_signals
                        (group_name, ticker, trade_type, entry_min, entry_max,
                         stop_loss, take_profit, source_type, raw_message, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (group_name, parsed["ticker"], parsed["trade_type"],
                      parsed["entry_min"], parsed["entry_max"], parsed["stop_loss"],
                      parsed.get("take_profit"),
                      parsed["source_type"], parsed["raw_message"], msg.date))
                inserted += 1

                if inserted % 50 == 0:
                    conn.commit()

            conn.commit()
            logger.info(f"{group_name}: {inserted} signals synced.")
        except Exception as e:
            logger.error(f"Error on channel {channel_id}: {e}")

    cur.close()
    release_conn(conn)


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

async def run():
    init_db()
    await scrape_history()
    logger.info("Live listener active. Monitoring channels…")

client.start()
client.loop.run_until_complete(run())
client.run_until_disconnected()