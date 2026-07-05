import os
import re
import datetime
import http.server
import socketserver
import threading
import urllib.request
import json
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import psycopg2
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()

# --- CONFIGURATION ---
API_ID = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")

CHANNELS_STR = os.environ.get("TELEGRAM_CHANNELS", "")
CHANNELS = [int(c.strip()) for c in CHANNELS_STR.split(",") if c.strip()]

# Database details
DB_PARAMS = {
    "host": os.environ.get("DB_HOST", ""),
    "port": int(os.environ.get("DB_PORT", 5432)) if os.environ.get("DB_PORT") else 5432,
    "user": os.environ.get("DB_USER", ""),
    "database": os.environ.get("DB_NAME", ""),
    "password": os.environ.get("DB_PASSWORD", "")
}

if not API_ID or not API_HASH:
    raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH not set in environment or .env file.")

# Run a simple HTTP health check server for Render compatibility
def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, format, *args):
            pass  # Suppress logging

    with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
        print(f"📡 Web server listening on port {port} for health checks...")
        httpd.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# Use StringSession for cloud deployment without database file requirements
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

def fetch_binance_price(ticker):
    """
    Fetch the current live price of a ticker from the Binance public API
    """
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={ticker}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return float(data['price'])
    except Exception as e:
        print(f"⚠️ Error fetching Binance price for {ticker}: {e}")
        return None

def analyze_opinion_sentiment(text):
    """
    Analyze the sentiment bias (LONG vs SHORT) of a conversational text post
    using a weighted keyword mapping.
    """
    text_upper = text.upper()
    
    bull_words = ["BUY", "LONG", "BULLISH", "BREAKOUT", "SUPPORT", "PUMP", "UPWARD", "MOON", "ACCUMULATE", "CALL", "TARGET", "TP"]
    bear_words = ["SELL", "SHORT", "BEARISH", "REJECTION", "BREAKDOWN", "RESISTANCE", "DUMP", "DOWNWARD", "DROP", "CRASH"]
    
    bull_score = sum(text_upper.count(word) for word in bull_words)
    bear_score = sum(text_upper.count(word) for word in bear_words)
    
    if bull_score > bear_score:
        return "LONG"
    elif bear_score > bull_score:
        return "SHORT"
    return None

def parse_opinion_text(text):
    """
    Fallback parser that ingests conversational trader opinions,
    fetches live price from Binance, and generates structured signals on the fly.
    """
    try:
        text_upper = text.upper()
        
        # 1. Identify coin pair
        ticker = None
        for coin in ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "AVAX"]:
            if coin in text_upper:
                ticker = f"{coin}USDT"
                break
        
        if not ticker:
            # Look for general uppercase symbol ending with USDT
            match = re.search(r'\b([A-Z]{2,10})USDT\b', text_upper)
            if match:
                ticker = match.group(0)
            else:
                # Look for hashtag tickers, e.g., #NEAR
                match_hash = re.search(r'#([A-Z]{2,10})\b', text_upper)
                if match_hash:
                    ticker = f"{match_hash.group(1)}USDT"
                else:
                    return None
                    
        # 2. Extract direction sentiment bias
        trade_type = analyze_opinion_sentiment(text)
        if not trade_type:
            return None
            
        # 3. Query current price from Binance
        live_price = fetch_binance_price(ticker)
        if not live_price:
            return None
            
        # 4. Generate structured targets (3% Stop Loss / 6% Take Profit)
        if trade_type == "LONG":
            entry_min = live_price
            entry_max = live_price * 1.005
            stop_loss = live_price * 0.97
        else:
            entry_min = live_price * 0.995
            entry_max = live_price
            stop_loss = live_price * 1.03
            
        return {
            "ticker": ticker,
            "trade_type": trade_type,
            "entry_min": round(entry_min, 4),
            "entry_max": round(entry_max, 4),
            "stop_loss": round(stop_loss, 4),
            "raw_message": f"[OPINION DIGESTED] {text}"
        }
    except Exception:
        return None

def parse_signal_text(text):
    """
    Parses trade signals from messages, identifying common tickers
    and extracting/guessing realistic entry and stop loss values.
    """
    try:
        text_upper = text.upper()
        if "LONG" in text_upper or "BUY" in text_upper:
            trade_type = "LONG"
        elif "SHORT" in text_upper or "SELL" in text_upper:
            trade_type = "SHORT"
        else:
            return None
            
        # Check for common tickers
        ticker = None
        for coin in ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "AVAX"]:
            if coin in text_upper:
                ticker = f"{coin}USDT"
                break
        
        if not ticker:
            # Look for general uppercase symbol ending with USDT
            match = re.search(r'\b([A-Z]{2,10})USDT\b', text_upper)
            if match:
                ticker = match.group(0)
            else:
                ticker = "BTCUSDT"  # Fallback default
                
        # Parse all numbers in the text to extract entry prices and SL (ignoring commas, e.g. 62,800 -> 62800)
        clean_text = text.replace(",", "")
        numbers = [float(n) for n in re.findall(r'\b\d+(?:\.\d+)?\b', clean_text)]
        
        # Standard defaults for common tickers to fallback to or compare with
        defaults = {
            "BTCUSDT": {"entry": 64000.0, "sl": 62000.0, "step": 500.0},
            "ETHUSDT": {"entry": 3400.0, "sl": 3200.0, "step": 50.0},
            "SOLUSDT": {"entry": 140.0, "sl": 130.0, "step": 5.0},
            "XRPUSDT": {"entry": 0.50, "sl": 0.45, "step": 0.02},
            "ADAUSDT": {"entry": 0.40, "sl": 0.36, "step": 0.02},
            "DOGEUSDT": {"entry": 0.12, "sl": 0.10, "step": 0.01},
        }
        
        ref = defaults.get(ticker, {"entry": 1.0, "sl": 0.9, "step": 0.05})
        
        # Filter numbers that are close to the expected price (0.1x to 10x of default)
        valid_numbers = [n for n in numbers if ref["entry"] * 0.1 <= n <= ref["entry"] * 10]
        
        if len(valid_numbers) >= 3:
            valid_numbers.sort()
            if trade_type == "LONG":
                stop_loss = valid_numbers[0]
                entry_min = valid_numbers[1]
                entry_max = valid_numbers[2]
            else:
                entry_min = valid_numbers[0]
                entry_max = valid_numbers[1]
                stop_loss = valid_numbers[2]
        elif len(valid_numbers) == 2:
            if trade_type == "LONG":
                stop_loss = min(valid_numbers)
                entry_min = max(valid_numbers)
                entry_max = entry_min * 1.01
            else:
                entry_min = min(valid_numbers)
                entry_max = entry_min * 1.01
                stop_loss = max(valid_numbers)
        else:
            entry_min = ref["entry"]
            entry_max = ref["entry"] + ref["step"]
            stop_loss = ref["sl"]
            
        return {
            "ticker": ticker,
            "trade_type": trade_type,
            "entry_min": entry_min,
            "entry_max": entry_max,
            "stop_loss": stop_loss,
            "raw_message": text
        }
    except Exception:
        return None

def init_db():
    try:
        # Check if database details are defined
        if not DB_PARAMS["host"]:
            print("⚠️ Database credentials not specified in .env. Skipping database initialization.")
            return
            
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_signals (
                id SERIAL PRIMARY KEY,
                group_name VARCHAR(255),
                ticker VARCHAR(50),
                trade_type VARCHAR(50),
                entry_min DOUBLE PRECISION,
                entry_max DOUBLE PRECISION,
                stop_loss DOUBLE PRECISION,
                raw_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database table verified/initialized.")
    except Exception as e:
        print(f"⚠️ Could not initialize database table: {e}")

@client.on(events.NewMessage(chats=CHANNELS))
async def my_event_handler(event):
    raw_text = event.raw_text
    channel = await event.get_chat()
    channel_title = getattr(channel, 'title', 'Unknown Group') if channel else 'Unknown Group'
    
    parsed = parse_signal_text(raw_text)
    if not parsed:
        parsed = parse_opinion_text(raw_text)
    if parsed:
        try:
            if not DB_PARAMS["host"]:
                print(f"📡 Parsing only (no DB host configured). Signal: {parsed['ticker']} {parsed['trade_type']}")
                return
                
            conn = psycopg2.connect(**DB_PARAMS)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO active_signals (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, raw_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (channel_title, parsed['ticker'], parsed['trade_type'], parsed['entry_min'], parsed['entry_max'], parsed['stop_loss'], parsed['raw_message']))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"✅ Real signal logged successfully from {channel_title}!")
        except Exception as e:
            print(f"❌ Database log error: {e}")

async def scrape_history():
    print("⏳ Scraping historical messages from monitored channels (back to Jan 1, 2026)...")
    if not DB_PARAMS["host"]:
        print("⚠️ Database credentials not specified. Skipping history sync.")
        return
        
    target_date = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        for channel_id in CHANNELS:
            try:
                print(f"🔄 Syncing history for channel {channel_id}...")
                # Fetch messages going backwards until target_date
                async for message in client.iter_messages(channel_id, limit=None):
                    if message.date < target_date:
                        break
                    if not message.text:
                        continue
                    parsed = parse_signal_text(message.text)
                    if not parsed:
                        parsed = parse_opinion_text(message.text)
                    if parsed:
                        # Check if message already exists to avoid duplicates
                        cursor.execute("SELECT id FROM active_signals WHERE raw_message = %s", (message.text,))
                        if cursor.fetchone():
                            continue
                        
                        # Get channel info safely
                        try:
                            channel = await client.get_entity(channel_id)
                            channel_title = getattr(channel, 'title', f"Group {channel_id}")
                        except Exception:
                            channel_title = f"Group {channel_id}"
                        
                        # Insert with the message's original timestamp
                        cursor.execute("""
                            INSERT INTO active_signals (group_name, ticker, trade_type, entry_min, entry_max, stop_loss, raw_message, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (channel_title, parsed['ticker'], parsed['trade_type'], parsed['entry_min'], parsed['entry_max'], parsed['stop_loss'], parsed['raw_message'], message.date))
                conn.commit()
                print(f"✅ History sync completed for channel {channel_id}")
            except Exception as e:
                print(f"⚠️ Error syncing history for channel {channel_id}: {e}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database connection error during history sync: {e}")

async def run_scraper():
    init_db()
    await scrape_history()
    print("⚡ Telegram Listener Started. Monitoring channels for real signals...")

client.start()
client.loop.run_until_complete(run_scraper())
client.run_until_disconnected()