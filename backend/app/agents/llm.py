"""Thin, optional LLM client (OpenAI-compatible chat API). Credentials come from the environment and
are only ever used server-side. When no key is configured callers fall back to deterministic logic."""
from __future__ import annotations

import json
import logging

import httpx

from app.core.config import settings

log = logging.getLogger("flowforge.llm")


def available() -> bool:
    return bool(settings.llm_api_key)


def engine_name() -> str:
    return f"llm:{settings.llm_model}" if available() else "heuristic"


def _chat(messages: list[dict], json_mode: bool) -> str | None:
    if not available():
        return None
    payload = {"model": settings.llm_model, "messages": messages, "temperature": 0}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=payload, timeout=settings.llm_timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 - never let the AI layer break the platform
        log.warning("LLM call failed: %s", exc)
        return None


def complete_json(system: str, user: str) -> dict | None:
    raw = _chat([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=True)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def complete_text(system: str, user: str) -> str | None:
    return _chat([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=False)
