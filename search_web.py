"""
search_web.py — Web search integration for JARVIS (Sprint 10)

Provider: Brave Search API  https://brave.com/search/api/
Free tier: 2,000 queries/month

Config (.env):
  BRAVE_SEARCH_API_KEY=your-key-here
  SEARCH_PROVIDER=brave          # only supported value for now

Usage:
  from search_web import search_and_summarize, is_configured
  msg = await search_and_summarize("latest NVIDIA news", anthropic_client)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

log = logging.getLogger("jarvis.search")

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT = 8.0
_NOT_CONFIGURED = (
    "Web search isn't configured yet, sir. "
    "Add a BRAVE_SEARCH_API_KEY to your .env file — "
    "free tier is available at brave.com/search/api."
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """True if a search API key is present in the environment."""
    return bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())


# ---------------------------------------------------------------------------
# Brave Search API
# ---------------------------------------------------------------------------

_FRESH_KEYWORDS = (
    "price", "cost", "score", "result", "latest", "news", "today",
    "current", "live", "now", "standings", "weather", "winner", "won",
    "happening", "update", "right now", "this week", "this month",
)


def _needs_freshness(query: str) -> bool:
    """Return True if the query is time-sensitive and should prefer recent results."""
    q = query.lower()
    return any(kw in q for kw in _FRESH_KEYWORDS)


async def _brave_search(query: str, count: int = 7) -> list[dict]:
    """
    Call Brave Search API and return a flat list of result dicts.
    Each dict: {"title": str, "url": str, "description": str}
    Raises on HTTP / config errors — callers handle gracefully.
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY not set")

    params: dict = {
        "q": query,
        "count": count,
        "text_decorations": "false",
        "search_lang": "en",
    }
    if _needs_freshness(query):
        params["freshness"] = "pw"   # past week — recent data for prices/scores/news

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            _BRAVE_ENDPOINT,
            params=params,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results: list[dict] = []

    # Web results
    for item in data.get("web", {}).get("results", []):
        title = (item.get("title") or "").strip()
        desc  = (item.get("description") or "").strip()
        url   = (item.get("url") or "").strip()
        if title or desc:
            results.append({"title": title, "url": url, "description": desc})

    # News results — supplement if web results are sparse
    if len(results) < 3:
        for item in data.get("news", {}).get("results", []):
            title = (item.get("title") or "").strip()
            desc  = (item.get("description") or "").strip()
            url   = (item.get("url") or "").strip()
            if title or desc:
                results.append({"title": title, "url": url, "description": desc})

    return results[:count]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _build_llm_context(query: str, results: list[dict]) -> str:
    """Structured text to feed Haiku for summarization."""
    lines = [f'Web search results for: "{query}"', ""]
    for i, r in enumerate(results[:5], 1):
        lines.append(f"{i}. {r['title']}")
        if r["description"]:
            lines.append(f"   {r['description'][:250]}")
    return "\n".join(lines)


def _fallback_summary(results: list[dict]) -> str:
    """Plain-text summary used when Haiku is unavailable."""
    snippets = []
    for r in results[:3]:
        if r["description"]:
            snippets.append(r["description"][:180])
        elif r["title"]:
            snippets.append(r["title"])
    return " ".join(snippets) if snippets else ""


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

async def search_and_summarize(query: str, anthropic_client=None) -> str:
    """
    Search the web for `query` and return a voice-ready answer.

    - Uses Haiku to summarise results when anthropic_client is provided.
    - Falls back to top snippet text if Haiku is unavailable.
    - Returns a clear spoken error if unconfigured or if the API fails.
    """
    if not is_configured():
        return _NOT_CONFIGURED

    try:
        results = await asyncio.wait_for(_brave_search(query, count=5), timeout=10.0)
    except asyncio.TimeoutError:
        return "The web search timed out, sir. Try again in a moment."
    except httpx.HTTPStatusError as e:
        log.warning("Brave search HTTP error: %s", e)
        if e.response.status_code == 401:
            return "The search API key appears to be invalid, sir. Please check BRAVE_SEARCH_API_KEY in your .env."
        if e.response.status_code == 429:
            return "The search API rate limit has been reached, sir. Free tier allows 2,000 queries per month."
        return f"The search API returned an error, sir ({e.response.status_code})."
    except Exception as e:
        log.warning("Brave search failed: %s", e)
        return "The web search failed, sir. Check your connection and API key."

    if not results:
        return f"No results found for that query, sir."

    if anthropic_client:
        try:
            context = _build_llm_context(query, results)
            resp = await anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=220,
                system=(
                    "You are JARVIS. Answer the user's question using only the search results provided. "
                    "Be direct and factual. 2-4 sentences maximum. "
                    "For prices, scores, or live data: always state the value AND note if the result may be delayed "
                    "(e.g. 'as of earlier today' or 'last reported at X'). Never present stale data as live. "
                    "If results don't clearly answer the question, say so honestly — do not guess. "
                    "Address the user as 'sir'. No markdown, no bullet points, no source citations."
                ),
                messages=[{"role": "user", "content": context}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            log.debug("Haiku search summarization failed, using fallback: %s", e)

    # Plain fallback
    snippet = _fallback_summary(results)
    if snippet:
        return f"Here's what I found, sir: {snippet}"
    return f"Found {len(results)} results for that query but couldn't extract a clear answer, sir."
