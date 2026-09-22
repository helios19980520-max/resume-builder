"""Thin Anthropic wrapper: text + robust JSON extraction with one repair retry."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from . import config

log = logging.getLogger("llm")

_client: anthropic.Anthropic | None = None
_client_key = ""


def client() -> anthropic.Anthropic:
    global _client, _client_key
    key = config.anthropic_key()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (open Settings in the app)")
    if _client is None or _client_key != key:
        _client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=600)
        _client_key = key
    return _client


def complete(system: str, user: str, *, model: str | None = None, max_tokens: int = 8000,
             temperature: float | None = None) -> str:
    kwargs: dict[str, Any] = dict(
        model=model or config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = client().messages.create(**kwargs)
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _extract_json(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    # take from first { or [ to the matching last } or ]
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON found")
    s = min(starts)
    e = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[s:e + 1])


def complete_json(system: str, user: str, *, model: str | None = None, max_tokens: int = 8000) -> Any:
    sys_json = system + "\n\nReturn ONLY valid JSON (no prose before or after, no markdown fences needed)."
    raw = complete(sys_json, user, model=model, max_tokens=max_tokens)
    try:
        return _extract_json(raw)
    except Exception as e:  # repair pass
        log.warning("JSON parse failed (%s); repairing", e)
        fixed = complete(
            "You fix malformed JSON. Return only the corrected JSON, nothing else.",
            f"Fix this JSON so it parses. Keep all content.\n\n{raw}",
            model=config.CLAUDE_FAST_MODEL, max_tokens=max_tokens,
        )
        return _extract_json(fixed)
