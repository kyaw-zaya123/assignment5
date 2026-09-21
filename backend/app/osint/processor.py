"""Lightweight OSINT NLP processor for ingest pipeline."""

from __future__ import annotations

import re
from typing import Any


LOCATION_PATTERNS = [
    ("Myawaddy", r"myawaddy|မြဝတီ"),
    ("Muse", r"muse|မူဆယ်"),
    ("Yangon", r"yangon|ရန်ကုန်"),
    ("Mandalay", r"mandalay|မန္တလေး"),
    ("Tamu", r"tamu|တမူး"),
]

EVENT_RULES = [
    ("road_block", r"block|closure|closed|ပိတ်", "high"),
    ("flood", r"flood|ရေကြီး|inundat", "high"),
    ("conflict", r"clash|conflict|တိုက်ပွဲ|fighting", "high"),
    ("traffic", r"traffic|jam|congestion", "medium"),
    ("weather", r"storm|rain|landslide|မုန်တိုင်း", "medium"),
]


def process_text(text: str, source: str = "manual") -> dict[str, Any]:
    location = None
    for name, pat in LOCATION_PATTERNS:
        if re.search(pat, text, re.I):
            location = name
            break

    event = "unknown"
    severity = "low"
    for etype, pat, sev in EVENT_RULES:
        if re.search(pat, text, re.I):
            event = etype
            severity = sev
            break

    title = text.strip().split("\n")[0][:180]
    return {
        "source": source,
        "title": title,
        "content": text,
        "event_type": event,
        "location": location,
        "severity": severity,
    }
