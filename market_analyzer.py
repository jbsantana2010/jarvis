"""
market_analyzer.py — Claude-powered market analysis for JARVIS (Sprint 21)

Combines technical data + news from stock_market.py and feeds it to
claude-haiku for spoken trade reads, watchlist scans, and morning briefs.

All output is spoken-word friendly (no markdown, short sentences).
Includes a soft disclaimer baked into every trade analysis response.
"""

import asyncio
from typing import Optional

import anthropic

import stock_market as sm

# ---------------------------------------------------------------------------
# Anthropic client (reuse env key from server)
# ---------------------------------------------------------------------------

_client: Optional[anthropic.AsyncAnthropic] = None

def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct_str(val: Optional[float]) -> str:
    if val is None:
        return "unknown"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _price_str(val: Optional[float]) -> str:
    return f"${val:.2f}" if val else "N/A"


def _rsi_read(rsi: Optional[float]) -> str:
    if rsi is None:
        return "RSI unavailable"
    if rsi >= 70:
        return f"RSI {rsi} — overbought territory"
    elif rsi <= 30:
        return f"RSI {rsi} — oversold territory"
    elif rsi >= 60:
        return f"RSI {rsi} — getting extended"
    elif rsi <= 40:
        return f"RSI {rsi} — approaching oversold"
    else:
        return f"RSI {rsi} — neutral zone"


# ---------------------------------------------------------------------------
# Single stock quote (spoken)
# ---------------------------------------------------------------------------

async def spoken_quote(ticker: str) -> str:
    """Quick price read — no AI needed."""
    q = sm.get_quote(ticker)
    if q.get("error"):
        return f"I couldn't pull a quote for {ticker}. It may be an invalid ticker."

    name = q.get("name") or ticker
    price = _price_str(q.get("price"))
    chg = _pct_str(q.get("change_pct"))
    change_val = q.get("change")
    direction = "up" if (change_val or 0) >= 0 else "down"

    return f"{name} is trading at {price}, {direction} {abs(change_val or 0):.2f} points, {chg} on the day."


# ---------------------------------------------------------------------------
# Full trade analysis (AI)
# ---------------------------------------------------------------------------

async def analyze_trade(ticker: str) -> str:
    """
    Full AI trade read: technicals + news → Claude gives a spoken setup assessment.
    Short-term focused (days to weeks) with longer-term context.
    """
    ticker = ticker.upper().strip()

    # Gather data concurrently
    tech_task = asyncio.get_event_loop().run_in_executor(None, sm.get_technicals, ticker)
    news_task = asyncio.get_event_loop().run_in_executor(None, sm.get_news, ticker, 4)
    quote_task = asyncio.get_event_loop().run_in_executor(None, sm.get_quote, ticker)
    tech, news, quote = await asyncio.gather(tech_task, news_task, quote_task)

    if tech.get("error"):
        return f"I couldn't get data for {ticker}: {tech['error']}"

    name = quote.get("name") or ticker

    # Build context block for Claude
    news_lines = "\n".join(
        f"- {n['title']} ({n['publisher']})" for n in news
    ) or "No recent news found."

    ma_context = ""
    if tech.get("above_mas"):
        ma_context += f"Trading above its {', '.join(tech['above_mas'])}. "
    if tech.get("below_mas"):
        ma_context += f"Trading below its {', '.join(tech['below_mas'])}. "

    prompt = f"""You are a sharp, concise market analyst giving a quick spoken trade read to a retail trader.
Analyze {name} ({ticker}) for short-term trading opportunities (days to a few weeks).

TECHNICAL DATA:
- Current price: {_price_str(tech.get('price'))} (day change: {_pct_str(quote.get('change_pct'))})
- {_rsi_read(tech.get('rsi'))}
- {ma_context}
- 52-week range: {_price_str(tech.get('low_52w'))} – {_price_str(tech.get('high_52w'))}
- Volume ratio vs 20-day avg: {tech.get('volume_ratio', 'N/A')}x
- Overall trend: {tech.get('trend', 'unknown')}

RECENT NEWS:
{news_lines}

Give a spoken trade read in 3-4 sentences:
1. Where is price relative to key levels and what does that mean right now?
2. Is this a good short-term entry, a wait-and-see, or a pass — and why?
3. What would change your read (what to watch)?
End with one sentence: "This is market analysis only — not financial advice."

Speak conversationally. No bullet points. No markdown. Under 100 words total."""

    try:
        response = await _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=220,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"I had trouble analyzing {ticker}: {e}"


# ---------------------------------------------------------------------------
# Watchlist scan
# ---------------------------------------------------------------------------

async def scan_watchlist() -> str:
    """
    Scans all watchlist tickers and returns AI-curated spoken summary
    of the best setups right now.
    """
    tickers = sm.get_watchlist()
    if not tickers:
        return "Your watchlist is empty. Say 'add AAPL to my watchlist' to start tracking stocks."

    # Fetch summaries
    summaries = await asyncio.get_event_loop().run_in_executor(None, sm.get_watchlist_summary)

    if not summaries:
        return "I couldn't pull data for your watchlist right now."

    # Build compact data block
    lines = []
    for s in summaries:
        lines.append(
            f"{s['ticker']} ({s['name']}): {_price_str(s.get('price'))} "
            f"{_pct_str(s.get('change_pct'))} | RSI {s.get('rsi') or 'N/A'} | "
            f"Trend: {s.get('trend') or 'N/A'} | Volume: {s.get('volume_ratio') or 'N/A'}x avg"
        )

    data_block = "\n".join(lines)

    prompt = f"""You are a market analyst giving a quick spoken watchlist scan to a short-term retail trader.

WATCHLIST DATA:
{data_block}

In 4-5 sentences:
- Which 1-2 tickers look like the cleanest setups right now and why?
- Which ones to avoid or wait on?
- One key thing to watch today across the list.
End with: "Remember, this is analysis only — not financial advice."

Spoken, conversational tone. No bullet points. No markdown. Under 120 words."""

    try:
        response = await _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"Watchlist scan failed: {e}"


# ---------------------------------------------------------------------------
# Market overview (spoken)
# ---------------------------------------------------------------------------

async def spoken_market_overview() -> str:
    """Spoken market overview — indices + VIX, no AI needed."""
    overview = await asyncio.get_event_loop().run_in_executor(None, sm.get_market_overview)

    parts = []
    for name, data in overview.items():
        price = data.get("price")
        chg = data.get("change_pct")
        if price is None:
            continue
        if name == "VIX":
            mood = "elevated — market is fearful" if price > 20 else "calm"
            parts.append(f"VIX is at {price:.1f}, which is {mood}.")
        else:
            direction = "up" if (chg or 0) >= 0 else "down"
            parts.append(f"{name} is {direction} {_pct_str(chg)}.")

    if not parts:
        return "Market data is unavailable right now."

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Morning market brief (for briefing.py integration)
# ---------------------------------------------------------------------------

async def build_market_brief() -> str:
    """
    Returns a compact spoken market section for the morning briefing.
    Covers: index direction, VIX, watchlist highlights (if any).
    """
    try:
        overview = await asyncio.get_event_loop().run_in_executor(None, sm.get_market_overview)
        watchlist = sm.get_watchlist()

        # Index summary
        index_parts = []
        vix_line = ""
        for name, data in overview.items():
            price = data.get("price")
            chg = data.get("change_pct")
            if price is None:
                continue
            if name == "VIX":
                mood = "fearful — stay cautious" if price > 25 else ("cautious" if price > 18 else "calm")
                vix_line = f"VIX sits at {price:.0f}, market mood is {mood}."
            elif name in ("S&P 500", "Nasdaq"):
                direction = "higher" if (chg or 0) >= 0 else "lower"
                index_parts.append(f"{name} futures pointing {direction} {_pct_str(chg)}")

        index_line = " and ".join(index_parts) + "." if index_parts else ""

        # Watchlist highlights (top movers only — no AI call to keep briefing fast)
        watch_line = ""
        if watchlist:
            summaries = await asyncio.get_event_loop().run_in_executor(None, sm.get_watchlist_summary)
            movers = sorted(
                [s for s in summaries if s.get("change_pct") is not None],
                key=lambda x: abs(x["change_pct"]),
                reverse=True
            )[:2]
            if movers:
                mentions = []
                for m in movers:
                    direction = "up" if m["change_pct"] >= 0 else "down"
                    mentions.append(f"{m['ticker']} {direction} {_pct_str(m['change_pct'])}")
                watch_line = f"On your watchlist: {', '.join(mentions)}."

        sections = [s for s in [index_line, vix_line, watch_line] if s]
        if not sections:
            return ""

        return "Markets: " + " ".join(sections)

    except Exception as e:
        return f"Market data unavailable: {e}"
