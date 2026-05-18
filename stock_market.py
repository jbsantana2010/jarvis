"""
stock_market.py — Market data layer for JARVIS (Sprint 21)

Uses yfinance (free, no API key) for:
  - Real-time quotes and price history
  - Technical indicator calculation (RSI, SMA, volume ratio)
  - Stock news headlines
  - Market overview (indices + VIX)
  - Top movers (gainers/losers)
  - Personal watchlist (SQLite)
"""

import os
import json
import sqlite3
import datetime
from pathlib import Path
from typing import Optional

import yfinance as yf
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = Path(os.path.expanduser("~/.jarvis/market.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

MARKET_INDICES = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
    "VIX": "^VIX",
}

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            added_at TEXT NOT NULL,
            notes TEXT
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def get_watchlist() -> list[str]:
    """Return list of tickers in watchlist."""
    with _get_db() as conn:
        rows = conn.execute("SELECT ticker FROM watchlist ORDER BY added_at").fetchall()
    return [r[0] for r in rows]


def add_to_watchlist(ticker: str, notes: str = "") -> bool:
    """Add ticker to watchlist. Returns True if added, False if already present."""
    ticker = ticker.upper().strip()
    with _get_db() as conn:
        existing = conn.execute("SELECT ticker FROM watchlist WHERE ticker=?", (ticker,)).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO watchlist (ticker, added_at, notes) VALUES (?, ?, ?)",
            (ticker, datetime.datetime.now().isoformat(), notes)
        )
        conn.commit()
    return True


def remove_from_watchlist(ticker: str) -> bool:
    """Remove ticker from watchlist. Returns True if removed."""
    ticker = ticker.upper().strip()
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))
        conn.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------

def get_quote(ticker: str) -> dict:
    """
    Get current quote for a ticker.
    Returns: price, change, change_pct, volume, avg_volume, market_cap, name
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info

        price = getattr(info, "last_price", None) or getattr(info, "regular_market_price", None)
        prev_close = getattr(info, "previous_close", None) or getattr(info, "regular_market_previous_close", None)

        change = None
        change_pct = None
        if price and prev_close:
            change = round(price - prev_close, 2)
            change_pct = round((change / prev_close) * 100, 2)

        return {
            "ticker": ticker,
            "price": round(price, 2) if price else None,
            "change": change,
            "change_pct": change_pct,
            "volume": getattr(info, "three_month_average_volume", None),
            "market_cap": getattr(info, "market_cap", None),
            "name": _get_name(t),
            "error": None,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def _get_name(t: yf.Ticker) -> str:
    try:
        return t.info.get("shortName") or t.info.get("longName") or t.ticker
    except Exception:
        return t.ticker


# ---------------------------------------------------------------------------
# History & Technicals
# ---------------------------------------------------------------------------

def get_technicals(ticker: str) -> dict:
    """
    Calculate key technical indicators from 6 months of daily data.
    Returns: RSI(14), SMA20, SMA50, SMA200, volume_ratio, trend, price
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo", interval="1d")

        if hist.empty or len(hist) < 20:
            return {"ticker": ticker, "error": "Insufficient history"}

        close = hist["Close"]
        volume = hist["Volume"]

        price = round(float(close.iloc[-1]), 2)

        # SMAs
        sma20  = round(float(close.rolling(20).mean().iloc[-1]), 2) if len(close) >= 20  else None
        sma50  = round(float(close.rolling(50).mean().iloc[-1]), 2) if len(close) >= 50  else None
        sma200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None

        # RSI(14)
        rsi = _calc_rsi(close, 14)

        # Volume ratio vs 20-day avg
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        vol_ratio = round(float(volume.iloc[-1]) / avg_vol, 2) if avg_vol > 0 else None

        # Simple trend: price vs SMAs
        above = []
        below = []
        for label, ma in [("20-day", sma20), ("50-day", sma50), ("200-day", sma200)]:
            if ma:
                if price > ma:
                    above.append(label)
                else:
                    below.append(label)

        if len(above) == 3:
            trend = "bullish"
        elif len(below) == 3:
            trend = "bearish"
        elif price > (sma50 or price):
            trend = "mixed-bullish"
        else:
            trend = "mixed-bearish"

        # 52-week high/low
        hist_1y = t.history(period="1y")
        high_52w = round(float(hist_1y["High"].max()), 2) if not hist_1y.empty else None
        low_52w  = round(float(hist_1y["Low"].min()), 2)  if not hist_1y.empty else None

        return {
            "ticker": ticker,
            "price": price,
            "rsi": rsi,
            "sma20": sma20,
            "sma50": sma50,
            "sma200": sma200,
            "volume_ratio": vol_ratio,
            "trend": trend,
            "above_mas": above,
            "below_mas": below,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "error": None,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def _calc_rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Calculate RSI using Wilder's smoothing method."""
    try:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        val = float(rsi.iloc[-1])
        return round(val, 1) if not pd.isna(val) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

def get_news(ticker: str, max_items: int = 5) -> list[dict]:
    """
    Get recent news headlines for a ticker.
    Returns list of {title, publisher, published, link}
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        raw = t.news or []
        results = []
        for item in raw[:max_items]:
            content = item.get("content", {})
            title = content.get("title") or item.get("title", "")
            publisher = content.get("provider", {}).get("displayName", "") or item.get("publisher", "")
            pub_time = content.get("pubDate") or ""
            link = content.get("canonicalUrl", {}).get("url", "") or item.get("link", "")
            if title:
                results.append({
                    "title": title,
                    "publisher": publisher,
                    "published": pub_time,
                    "link": link,
                })
        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Market Overview
# ---------------------------------------------------------------------------

def get_market_overview() -> dict:
    """
    Returns current readings for major indices + VIX.
    """
    result = {}
    for name, symbol in MARKET_INDICES.items():
        q = get_quote(symbol)
        result[name] = {
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
        }
    return result


# ---------------------------------------------------------------------------
# Watchlist Summary
# ---------------------------------------------------------------------------

def get_watchlist_summary() -> list[dict]:
    """
    Returns quote + technicals for every ticker in the watchlist.
    """
    tickers = get_watchlist()
    if not tickers:
        return []

    summaries = []
    for ticker in tickers:
        q = get_quote(ticker)
        tech = get_technicals(ticker)
        summaries.append({
            "ticker": ticker,
            "name": q.get("name", ticker),
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "rsi": tech.get("rsi"),
            "trend": tech.get("trend"),
            "volume_ratio": tech.get("volume_ratio"),
            "sma20": tech.get("sma20"),
            "sma50": tech.get("sma50"),
        })
    return summaries
