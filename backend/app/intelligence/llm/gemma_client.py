"""Configurable Gemma-e2b OpenAI-compatible client."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class GemmaClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.gemma_url.rstrip("/")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.gemma_api_key}",
        }
        payload = {
            "model": self.settings.llm_model_gemma,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.settings.gemma_max_tokens,
        }
        with httpx.Client(timeout=self.settings.gemma_timeout) as client:
            resp = client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        raw = self.chat(messages, temperature=temperature)
        return parse_json_object(raw)


def _extract_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    # strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fenced:
        text = fenced.group(1).strip()
    candidates = [text]
    balanced = _extract_balanced_object(text)
    if balanced and balanced not in candidates:
        candidates.append(balanced)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    logger.warning("Failed to parse LLM JSON; wrapping raw text")
    return {
        "answer": text[:2000],
        "risk_level": None,
        "risk_score": None,
        "reasons": ["LLM returned non-JSON; heuristic risk used"],
        "recommendation": None,
        "_parse_failed": True,
    }
