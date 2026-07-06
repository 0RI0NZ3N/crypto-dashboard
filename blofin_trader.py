"""
BloFin exchange integration — account balance/positions (read-only) and
auto-trade execution (write), built on CCXT. CCXT's blofin implementation
is already a dependency of this project (scraper.py uses it, unauthenticated,
for live price data) and its create_order() understands BloFin's native
stopLoss/takeProfit trigger-order params directly, so no hand-rolled request
signing is needed here for placing orders — only the credentials differ.

Safety model, since this fires real trades with no per-trade confirmation:
  - BLOFIN_DRY_RUN defaults to "true". Even with the dashboard's
    auto_trade_enabled toggle on, no order is actually sent to BloFin unless
    BLOFIN_DRY_RUN is explicitly set to "false" in the deploy environment —
    a separate, harder-to-flip switch than the dashboard checkbox, so going
    live for the first time takes a deliberate env change, not just a click.
  - Every attempt (dry-run, filled, or failed) is logged to blofin_trades,
    which also serves as the durable de-dup record so a scraper process
    restart can't cause the same consensus signal to be traded twice.
"""

import os
import re
import logging
import ccxt
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("blofin_trader")


def _secret(key: str, default=None):
    try:
        import streamlit as st
        v = st.secrets.get(key)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(key, default)


def is_dry_run() -> bool:
    return str(_secret("BLOFIN_DRY_RUN", "true")).strip().lower() != "false"


def is_sandbox() -> bool:
    return str(_secret("BLOFIN_SANDBOX", "false")).strip().lower() == "true"


_client = None


def get_trade_client():
    """Authenticated CCXT BloFin client, or None if credentials aren't configured."""
    global _client
    if _client is not None:
        return _client
    api_key    = _secret("BLOFIN_API_KEY")
    api_secret = _secret("BLOFIN_API_SECRET")
    passphrase = _secret("BLOFIN_API_PASSPHRASE")
    if not all([api_key, api_secret, passphrase]):
        return None
    client = ccxt.blofin({
        "apiKey": api_key,
        "secret": api_secret,
        "password": passphrase,
        "enableRateLimit": True,
    })
    if is_sandbox():
        client.set_sandbox_mode(True)
    _client = client
    return client


def to_ccxt_symbol(ticker: str) -> str:
    """'BTCUSDT' -> 'BTC/USDT:USDT' (BloFin's linear USDT-margined swap format)."""
    if ticker.endswith("USDT") and "/" not in ticker:
        return f"{ticker[:-4]}/USDT:USDT"
    return ticker


def get_balance_usdt(client) -> float | None:
    try:
        bal  = client.fetch_balance(params={"accountType": "futures"})
        usdt = bal.get("USDT") or {}
        return float(usdt.get("total") or usdt.get("free") or 0)
    except Exception as e:
        logger.warning(f"BloFin balance fetch failed: {e}")
        return None


def get_positions(client) -> list:
    try:
        return client.fetch_positions()
    except Exception as e:
        logger.warning(f"BloFin positions fetch failed: {e}")
        return []


def extract_leverage(text: str, default: int) -> int:
    m = re.search(r'(\d{1,3})\s*[xX]\b', str(text))
    return int(m.group(1)) if m else default


def compute_margin(balance_usdt: float, confidence: float, settings: dict) -> float:
    """
    Position sizing. Fixed mode uses the user's exact override, unscaled —
    they picked a specific number, don't second-guess it. Percent mode sizes
    off account balance (capped at margin_cap_usdt) and then scales that down
    for lower-confidence signals: a consensus from historically weak/unproven
    channels risks less than one from channels with a strong track record,
    down to a 30% floor so a low-confidence signal still gets a token size
    rather than being skipped entirely.
    """
    if settings.get("margin_mode") == "fixed":
        return float(settings.get("margin_fixed_usdt", 50))
    base = min(
        balance_usdt * float(settings.get("margin_percent", 0.15)),
        float(settings.get("margin_cap_usdt", 100)),
    )
    conf_scale = max(min((confidence or 50) / 100, 1.0), 0.3)
    return round(base * conf_scale, 2)


def has_recent_trade(cur, ticker: str, trade_type: str, hours: int = 24) -> bool:
    cur.execute("""
        SELECT 1 FROM blofin_trades
        WHERE ticker = %s AND trade_type = %s AND status IN ('FILLED', 'DRY_RUN')
          AND created_at >= NOW() - make_interval(hours => %s)
        LIMIT 1
    """, (ticker, trade_type, hours))
    return cur.fetchone() is not None


def get_bot_settings(cur) -> dict:
    cur.execute("""
        SELECT auto_trade_enabled, margin_mode, margin_percent, margin_cap_usdt,
               margin_fixed_usdt, leverage_cap, default_leverage, min_consensus_rooms
        FROM bot_settings WHERE id = 1
    """)
    row = cur.fetchone()
    if not row:
        return {"auto_trade_enabled": False}
    return {
        "auto_trade_enabled":  row[0],
        "margin_mode":         row[1],
        "margin_percent":      row[2],
        "margin_cap_usdt":     row[3],
        "margin_fixed_usdt":   row[4],
        "leverage_cap":        row[5],
        "default_leverage":    row[6],
        "min_consensus_rooms": row[7],
    }


def _log_trade(cur, r: dict):
    cur.execute("""
        INSERT INTO blofin_trades
            (ticker, trade_type, room_count, confidence, margin_usdt, leverage,
             order_id, entry_price, stop_loss, take_profit, status, error)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (r["ticker"], r["trade_type"], r["room_count"], r["confidence"], r["margin_usdt"],
          r["leverage"], r["order_id"], r["entry_price"], r["stop_loss"], r["take_profit"],
          r["status"], r["error"]))


def place_consensus_trade(client, cur, *, ticker, trade_type, stop_loss, take_profit,
                           room_count, confidence, margin_usdt, leverage) -> dict:
    """
    Places (or, in dry-run mode, simulates) a market order sized from
    margin_usdt * leverage, with the signal's stop-loss and take-profit
    attached as native BloFin trigger orders on the same request. Always
    logs the attempt — filled, failed, or dry-run — to blofin_trades.
    """
    symbol = to_ccxt_symbol(ticker)
    side   = "buy" if trade_type == "LONG" else "sell"
    result = {
        "ticker": ticker, "trade_type": trade_type, "room_count": room_count,
        "confidence": confidence, "margin_usdt": margin_usdt, "leverage": leverage,
        "order_id": None, "entry_price": None, "stop_loss": stop_loss,
        "take_profit": take_profit, "status": None, "error": None,
    }

    try:
        ticker_data   = client.fetch_ticker(symbol)
        price         = ticker_data["last"]
        market        = client.market(symbol)
        contract_size = market.get("contractSize") or 1.0
        notional      = margin_usdt * leverage
        contracts     = float(client.amount_to_precision(symbol, (notional / price) / contract_size))
        result["entry_price"] = price

        if contracts <= 0:
            result["status"] = "FAILED"
            result["error"]  = "computed contract size rounded to 0 — margin too small for this instrument"
            _log_trade(cur, result)
            return result

        if is_dry_run():
            result["status"]   = "DRY_RUN"
            result["order_id"] = "dry-run"
            logger.info(
                f"[DRY RUN] Would place {side} {contracts} contracts of {symbol} "
                f"(~${notional:.2f} notional, {leverage}x, margin ${margin_usdt:.2f}) "
                f"SL={stop_loss} TP={take_profit}"
            )
            _log_trade(cur, result)
            return result

        client.set_leverage(leverage, symbol, params={"marginMode": "cross"})

        order_params = {"marginMode": "cross"}
        if stop_loss:
            order_params["stopLoss"] = {"triggerPrice": stop_loss}
        if take_profit:
            order_params["takeProfit"] = {"triggerPrice": take_profit}

        order = client.create_order(symbol, "market", side, contracts, params=order_params)
        result["status"]   = "FILLED"
        result["order_id"] = order.get("id")
        logger.info(f"✅ BloFin order placed: {side} {contracts} {symbol} (order {order.get('id')})")

    except Exception as e:
        result["status"] = "FAILED"
        result["error"]  = str(e)[:500]
        logger.error(f"BloFin order failed for {ticker} {trade_type}: {e}")

    _log_trade(cur, result)
    return result
