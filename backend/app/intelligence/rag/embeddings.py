"""Configurable embedding client (HTTP / local / keyword fallback)."""

from __future__ import annotations

import logging
import re
from typing import Sequence

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._local_model = None

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        mode = (self.settings.embedding_mode or "auto").lower()
        if mode == "keyword":
            return None
        if mode in {"http", "auto"} and self.settings.embedding_base_url:
            try:
                return self._embed_http(list(texts))
            except Exception as exc:
                logger.warning("HTTP embedding failed: %s", exc)
                if mode == "http":
                    return None
        if mode in {"local", "auto"}:
            try:
                return self._embed_local(list(texts))
            except Exception as exc:
                logger.warning("Local embedding unavailable: %s", exc)
        return None

    def _embed_http(self, texts: list[str]) -> list[list[float]]:
        base = self.settings.embedding_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.settings.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.settings.embedding_api_key}"
        payload = {"model": self.settings.embedding_model, "input": texts}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{base}/v1/embeddings", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        vectors = [item["embedding"] for item in items]
        for v in vectors:
            if len(v) != self.settings.embedding_dim:
                raise ValueError(
                    f"Embedding dim {len(v)} != expected {self.settings.embedding_dim}"
                )
        return vectors

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading local embedding model %s", self.settings.embedding_model)
            self._local_model = SentenceTransformer(
                self.settings.embedding_model,
                trust_remote_code=True,
            )
        vectors = self._local_model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [v.tolist() for v in vectors]


def extract_keywords(query: str) -> list[str]:
    places = [
        "Myawaddy",
        "Muse",
        "Yangon",
        "Mandalay",
        "Tamu",
        "Mae Sot",
        "flood",
        "road",
        "highway",
        "closure",
        "conflict",
        "checkpoint",
        "rain",
        "landslide",
    ]
    found = [p for p in places if re.search(re.escape(p), query, re.I)]
    if not found:
        tokens = re.findall(r"[A-Za-z\u1000-\u109F]{3,}", query)
        found = tokens[:4]
    return found
