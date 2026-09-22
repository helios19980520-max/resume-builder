"""Web research helpers built on Tavily (search + extract) with an httpx fallback for the JD page."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from . import config

log = logging.getLogger("search")

_tavily = None
_tavily_key = ""


def tavily():
    global _tavily, _tavily_key
    from tavily import TavilyClient
    key = config.tavily_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set (open Settings in the app)")
    if _tavily is None or _tavily_key != key:
        _tavily = TavilyClient(api_key=key)
        _tavily_key = key
    return _tavily


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        t.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def fetch_page_text(url: str) -> str:
    """Return the readable text of a public page. Tavily extract first (handles JS-heavy job boards),
    plain HTTP second."""
    text = ""
    try:
        res = tavily().extract(urls=[url], extract_depth="advanced", format="markdown")
        for r in res.get("results", []):
            text = r.get("raw_content") or ""
            if text:
                break
    except Exception as e:
        log.warning("tavily extract failed for %s: %s", url, e)
    if len(text) < 400:
        try:
            with httpx.Client(follow_redirects=True, timeout=30,
                              headers={"User-Agent": "Mozilla/5.0 (resume-builder)"}) as c:
                r = c.get(url)
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                text = _html_to_text(r.text) if "html" in ctype or "<html" in r.text[:2000].lower() else r.text
        except Exception as e:
            log.warning("http fetch failed for %s: %s", url, e)
    return text[:60000]


def search(query: str, *, max_results: int = 5, depth: str = "advanced", days: int | None = None,
           include_domains: list[str] | None = None, topic: str = "general") -> list[dict]:
    kwargs = dict(query=query, max_results=max_results, search_depth=depth, topic=topic,
                  include_answer=False)
    if include_domains:
        kwargs["include_domains"] = include_domains
    if days:
        kwargs["time_range"] = "month" if days <= 31 else "year"
    try:
        res = tavily().search(**kwargs)
        out = []
        for r in res.get("results", []):
            out.append({"title": r.get("title", ""), "url": r.get("url", ""),
                        "content": (r.get("content") or "")[:2500], "score": r.get("score", 0)})
        return out
    except Exception as e:
        log.warning("tavily search failed for %r: %s", query, e)
        return []


def search_many(queries: list[str], **kw) -> dict[str, list[dict]]:
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda q: search(q, **kw), queries))
    return dict(zip(queries, results))


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def format_results(results: dict[str, list[dict]], limit_per_query: int = 5) -> str:
    """Compact digest for the LLM: query -> numbered snippets with URLs."""
    blocks = []
    for q, rs in results.items():
        if not rs:
            continue
        lines = [f"### Query: {q}"]
        for r in rs[:limit_per_query]:
            lines.append(f"- [{r['title']}]({r['url']})\n  {r['content']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
