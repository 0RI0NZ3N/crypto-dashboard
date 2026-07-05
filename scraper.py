import os
import re
import datetime
import http.server
import socketserver
import threading
import time
import urllib.request
import json
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import psycopg2
from dotenv import load_dotenv

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

if not API_ID or not API_HASH:
    raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH not set in environment.")

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
        print(f"📡 Health-check server on port {port}")
        httpd.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ─────────────────────────────────────────
# TELETHON CLIENT
# ─────────────────────────────────────────
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SOURCE LIVE PRICE FETCHER
# Fallback chain: Binance → Bybit → OKX
# Binance is geo-blocked (HTTP 451) on Render US servers.
# Bybit and OKX have no regional restrictions on their public ticker APIs.
# ─────────────────────────────────────────────────────────────────────────────
_price_cache: dict = {}
_price_cache_ts: dict = {}
PRICE_CACHE_TTL = 30  # seconds

def _http_get(url: str, timeout: int = 5) -> dict | None:
    """Shared HTTP GET with a browser User-Agent header."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _from_bybit(ticker: str) -> float | None:
    # Bybit linear perpetuals use the same symbol format (BTCUSDT, ETHUSDT, etc.)
    data = _http_get(
        f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={ticker}"
    )
    try:
        return float(data["result"]["list"][0]["lastPrice"])
    except Exception:
        return None

def _from_okx(ticker: str) -> float | None:
    # OKX uses BTC-USDT format (hyphen-separated)
    if not ticker.endswith("USDT"):
        return None
    base   = ticker[:-4]           # e.g. "BTC"
    inst   = f"{base}-USDT"        # e.g. "BTC-USDT"
    data   = _http_get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")
    try:
        return float(data["data"][0]["last"])
    except Exception:
        return None

def fetch_live_price(ticker: str) -> float | None:
    """
    Fetch the current market price for a USDT-margined pair.
    Primary: Bybit — Fallback: OKX.
    Results are cached for PRICE_CACHE_TTL seconds.
    """
    now = time.time()
    if ticker in _price_cache and now - _price_cache_ts.get(ticker, 0) < PRICE_CACHE_TTL:
        return _price_cache[ticker]

    sources = [
        ("Bybit", _from_bybit),
        ("OKX",   _from_okx),
    ]

    for name, fn in sources:
        price = fn(ticker)
        if price and price > 0:
            _price_cache[ticker]    = price
            _price_cache_ts[ticker] = now
            print(f"💱 {ticker} price {price} fetched via {name}")
            return price
        else:
            print(f"⚠️  {name} price fetch failed for {ticker} — trying next source")

    print(f"❌ All price sources failed for {ticker}")
    return None

# Keep old name as alias so nothing else breaks
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
    m = re.search(r'[#$]([A-Z]{2,10})\b', text_upper)
    if m:
        candidate = m.group(1)
        if candidate in KNOWN_COINS or len(candidate) <= 5:
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

        return {
            "ticker":      ticker,
            "trade_type":  trade_type,
            "entry_min":   round(entry_min, 6),
            "entry_max":   round(entry_max, 6),
            "stop_loss":   round(stop_loss, 6),
            "source_type": "STRUCTURED",
            "raw_message": text,
        }
    except Exception:
        return None


def parse_opinion_text(text: str) -> dict | None:
    """
    Fallback opinion parser.
    Digests unstructured trader commentary into actionable signals
    by combining sentiment analysis with a live Binance price anchor.
    Tags result with source_type = 'OPINION'.
    """
    try:
        ticker = detect_ticker(text)
        if not ticker:
            return None

        trade_type = analyze_sentiment(text)
        if not trade_type:
            return None

        live_price = fetch_binance_price(ticker)
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

def get_conn():
    return psycopg2.connect(**DB_PARAMS)

def init_db():
    if not DB_PARAMS["host"]:
        print("⚠️  No DB host configured — skipping DB init.")
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
                closed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("✅ DB tables verified / migrated (active_signals + closed_signals).")
    except Exception as e:
        print(f"⚠️  DB init error: {e}")


# ─────────────────────────────────────────
# DB INSERT HELPER
# ─────────────────────────────────────────

def insert_signal(parsed: dict, group_name: str, created_at=None):
    if not DB_PARAMS["host"]:
        print(f"📡 [no-DB] {parsed['ticker']} {parsed['trade_type']} ({parsed['source_type']})")
        return
    try:
        conn = get_conn()
        cur  = conn.cursor()
        if created_at:
            cur.execute("""
                INSERT INTO active_signals
                    (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, source_type, raw_message, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (group_name, parsed["ticker"], parsed["trade_type"],
                  parsed["entry_min"], parsed["entry_max"], parsed["stop_loss"],
                  parsed["source_type"], parsed["raw_message"], created_at))
        else:
            cur.execute("""
                INSERT INTO active_signals
                    (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, source_type, raw_message)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (group_name, parsed["ticker"], parsed["trade_type"],
                  parsed["entry_min"], parsed["entry_max"], parsed["stop_loss"],
                  parsed["source_type"], parsed["raw_message"]))
        conn.commit()
        cur.close()
        conn.close()
        icon = "🟢" if parsed["trade_type"] == "LONG" else "🔴"
        print(f"✅ {icon} {parsed['ticker']} {parsed['trade_type']} [{parsed['source_type']}] from {group_name}")
    except Exception as e:
        print(f"❌ DB insert error: {e}")


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
                ticker, trade_type, avg_emin, avg_emax, avg_sl, cnt, rooms = row
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
                        (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, source_type, raw_message)
                    VALUES ('CONSENSUS', %s, %s, %s, %s, %s, 'CONSENSUS', %s)
                """, (ticker, trade_type,
                      round(avg_emin, 6), round(avg_emax, 6), round(avg_sl, 6),
                      raw))

            conn.commit()
            cur.close()
            conn.close()
            if rows:
                print(f"⚡ Consolidation: {len(rows)} consensus zone(s) updated.")
        except Exception as e:
            print(f"⚠️  Consolidation error: {e}")

threading.Thread(target=run_consolidation, daemon=True).start()


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
    print("⏳ Starting historical sync (back to 2026-01-01)…")
    if not DB_PARAMS["host"]:
        print("⚠️  No DB host — skipping history sync.")
        return

    cutoff = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    conn = get_conn()
    cur  = conn.cursor()

    for channel_id in CHANNELS:
        try:
            entity       = await client.get_entity(channel_id)
            group_name   = getattr(entity, "title", f"Group {channel_id}")
            print(f"🔄 Syncing {group_name} ({channel_id})…")
            inserted = 0

            async for msg in client.iter_messages(channel_id, limit=None):
                if msg.date < cutoff:
                    break
                if not msg.text or len(msg.text.strip()) < 8:
                    continue

                parsed = parse_message(msg.text)
                if not parsed:
                    continue

                # Skip duplicates by raw_message + date composite
                cur.execute(
                    "SELECT id FROM active_signals WHERE raw_message = %s AND created_at = %s",
                    (parsed["raw_message"], msg.date),
                )
                if cur.fetchone():
                    continue

                cur.execute("""
                    INSERT INTO active_signals
                        (group_name, ticker, trade_type, entry_min, entry_max,
                         stop_loss, source_type, raw_message, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (group_name, parsed["ticker"], parsed["trade_type"],
                      parsed["entry_min"], parsed["entry_max"], parsed["stop_loss"],
                      parsed["source_type"], parsed["raw_message"], msg.date))
                inserted += 1

                if inserted % 50 == 0:
                    conn.commit()

            conn.commit()
            print(f"✅ {group_name}: {inserted} signals synced.")
        except Exception as e:
            print(f"⚠️  Error on channel {channel_id}: {e}")

    cur.close()
    conn.close()


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

async def run():
    init_db()
    await scrape_history()
    print("⚡ Live listener active. Monitoring channels…")

client.start()
client.loop.run_until_complete(run())
client.run_until_disconnected()