"""mcp-web-search — FastMCP STREAMABLE_HTTP server (port 3001, path /mcp).

Exposes a single MCP tool ``web_search`` backed by DuckDuckGo via the ``ddgs``
package (no API key). If ``ddgs`` is unavailable or fails at runtime, falls back
to a minimal DuckDuckGo HTML fetch using httpx.

kagent connects over ``protocol: STREAMABLE_HTTP`` to
``http://mcp-web-search.ai-platform:3001/mcp``.
"""

from __future__ import annotations

import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("mcp-web-search")

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "3001"))

DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CAP = 20
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "15"))

mcp = FastMCP(
    "mcp-web-search",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
)


def _search_ddgs(query: str, max_results: int) -> list[dict]:
    """Primary path: DuckDuckGo via the ``ddgs`` package."""
    from ddgs import DDGS

    ddgs = DDGS(timeout=SEARCH_TIMEOUT)
    results: list[dict] = []
    for hit in ddgs.text(query, max_results=max_results):
        results.append(
            {
                "title": hit.get("title", ""),
                "url": hit.get("href", "") or hit.get("url", ""),
                "snippet": hit.get("body", "") or hit.get("snippet", ""),
            }
        )
    return results


def _search_httpx(query: str, max_results: int) -> list[dict]:
    """Fallback: scrape DuckDuckGo's HTML endpoint with httpx + stdlib parsing."""
    import html
    import re

    resp = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (compatible; mcp-web-search/0.1)"},
        timeout=SEARCH_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    body = resp.text

    link_re = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_re = re.compile(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    tag_re = re.compile(r"<[^>]+>")

    def clean(text: str) -> str:
        return html.unescape(tag_re.sub("", text)).strip()

    links = link_re.findall(body)
    snippets = snippet_re.findall(body)

    results: list[dict] = []
    for idx, (url, title) in enumerate(links[:max_results]):
        snippet = clean(snippets[idx]) if idx < len(snippets) else ""
        results.append({"title": clean(title), "url": url, "snippet": snippet})
    return results


@mcp.tool()
def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    """Search the web (DuckDuckGo) and return a list of results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5, capped at 20).

    Returns:
        A list of ``{"title", "url", "snippet"}`` dicts. Empty list on failure.
    """
    if not isinstance(query, str) or not query.strip():
        return []
    try:
        bounded = int(max_results)
    except (TypeError, ValueError):
        bounded = DEFAULT_MAX_RESULTS
    bounded = max(1, min(bounded, MAX_RESULTS_CAP))

    try:
        return _search_ddgs(query, bounded)
    except Exception as exc:
        logger.warning("ddgs search failed (%s); using httpx fallback", exc)
        try:
            return _search_httpx(query, bounded)
        except Exception as exc2:
            logger.error("httpx fallback search failed: %s", exc2)
            return []


if __name__ == "__main__":
    logger.info("starting mcp-web-search on %s:%s path /mcp", HOST, PORT)
    mcp.run(transport="streamable-http")
