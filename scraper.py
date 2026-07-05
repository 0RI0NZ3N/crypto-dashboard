import os
import re
import http.server
import socketserver
import threading
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
    print("⏳ Scraping historical messages from monitored channels...")
    if not DB_PARAMS["host"]:
        print("⚠️ Database credentials not specified. Skipping history sync.")
        return
        
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        for channel_id in CHANNELS:
            try:
                # Fetch last 30 messages from each channel
                async for message in client.iter_messages(channel_id, limit=30):
                    if not message.text:
                        continue
                    parsed = parse_signal_text(message.text)
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