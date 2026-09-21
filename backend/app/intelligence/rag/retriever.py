"""Qdrant integration against existing `content` collection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import Settings, get_settings
from app.intelligence.rag.embeddings import EmbeddingClient, extract_keywords
from app.intelligence.rag.reranker import parse_hit_timestamp

logger = logging.getLogger(__name__)


class QdrantService:
    def __init__(
        self,
        settings: Settings | None = None,
        embedder: EmbeddingClient | None = None,
    ):
        self.settings = settings or get_settings()
        self.embedder = embedder or EmbeddingClient(self.settings)
        kwargs: dict[str, Any] = {"url": self.settings.qdrant_url}
        if self.settings.qdrant_api_key:
            kwargs["api_key"] = self.settings.qdrant_api_key
        self.client = QdrantClient(**kwargs)
        self.collection = self.settings.qdrant_collection

    def _window_bounds(self) -> tuple[float, float]:
        """Inclusive unix window: [now - max_age_days, now + 1 day]."""
        now = datetime.now(timezone.utc)
        days = max(1, int(self.settings.osint_max_age_days or 7))
        start = (now - timedelta(days=days)).timestamp()
        end = (now + timedelta(days=1)).timestamp()  # reject far-future / garbage dates
        return start, end

    def _recent_filter(self) -> qm.Filter:
        start, end = self._window_bounds()
        return qm.Filter(
            must=[
                qm.FieldCondition(
                    key="date_ts",
                    range=qm.Range(gte=start, lte=end),
                )
            ]
        )

    def _hit_to_dict(self, point: Any, score: float | None = None) -> dict[str, Any]:
        payload = point.payload or {}
        return {
            "id": point.id,
            "score": score,
            "text": payload.get("text"),
            "network": payload.get("network"),
            "category": payload.get("nlp_category") or payload.get("category"),
            "date": payload.get("date"),
            "date_ts": payload.get("date_ts"),
            "link": payload.get("link"),
            "display_name": payload.get("display_name"),
            "source_type": payload.get("source_type"),
        }

    def _within_window(self, hit: dict[str, Any]) -> bool:
        start, end = self._window_bounds()
        ts = parse_hit_timestamp(hit)
        return start <= ts <= end

    def _filter_recent(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [h for h in hits if self._within_window(h)]

    def _search_vector(self, query: str, limit: int, *, recent_only: bool) -> list[dict[str, Any]]:
        vectors = self.embedder.embed([query])
        if not vectors:
            return []
        # Over-fetch then post-filter if needed
        fetch_n = max(limit * 4, limit) if recent_only else limit
        kwargs: dict[str, Any] = {
            "collection_name": self.collection,
            "query_vector": vectors[0],
            "limit": fetch_n,
            "with_payload": True,
        }
        if recent_only:
            kwargs["query_filter"] = self._recent_filter()
        try:
            hits = self.client.search(**kwargs)
        except Exception as exc:
            logger.warning("Filtered vector search failed (%s); retry without filter", exc)
            hits = self.client.search(
                collection_name=self.collection,
                query_vector=vectors[0],
                limit=fetch_n,
                with_payload=True,
            )
        rows = [self._hit_to_dict(h, h.score) for h in hits]
        if recent_only:
            rows = self._filter_recent(rows)
        return rows[:limit]

    def _search_keyword(self, query: str, limit: int, *, recent_only: bool) -> list[dict[str, Any]]:
        keywords = extract_keywords(query)
        if not keywords:
            keywords = [query[:64]]
        results: list[dict[str, Any]] = []
        seen: set[Any] = set()
        must: list[qm.FieldCondition] = []
        if recent_only:
            start, end = self._window_bounds()
            must.append(
                qm.FieldCondition(key="date_ts", range=qm.Range(gte=start, lte=end))
            )
        for kw in keywords:
            conditions = [
                *must,
                qm.FieldCondition(key="text", match=qm.MatchText(text=kw)),
            ]
            try:
                scroll = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=qm.Filter(must=conditions),
                    limit=max(limit * 2, limit),
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:
                logger.warning("Filtered keyword scroll failed (%s)", exc)
                try:
                    scroll = self.client.scroll(
                        collection_name=self.collection,
                        scroll_filter=qm.Filter(
                            must=[qm.FieldCondition(key="text", match=qm.MatchText(text=kw))]
                        ),
                        limit=max(limit * 3, limit),
                        with_payload=True,
                        with_vectors=False,
                    )
                except Exception as exc2:
                    # Qdrant unreachable / misconfigured — never let this crash the
                    # caller (AI query, gate-close alerts). Degrade to "no OSINT".
                    logger.warning("Qdrant unreachable, skipping OSINT for this query (%s)", exc2)
                    return results
            for point in scroll[0]:
                if point.id in seen:
                    continue
                seen.add(point.id)
                row = self._hit_to_dict(point, score=None)
                if recent_only and not self._within_window(row):
                    continue
                results.append(row)
                if len(results) >= limit:
                    return results
        return results

    def search(
        self,
        query: str,
        limit: int | None = None,
        *,
        recent_only: bool = True,
    ) -> list[dict[str, Any]]:
        limit = limit or self.settings.qdrant_top_k
        try:
            hits = self._search_vector(query, limit, recent_only=recent_only)
            if hits:
                return hits
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
        try:
            return self._search_keyword(query, limit, recent_only=recent_only)
        except Exception as exc:
            # Last line of defense: Qdrant/OSINT is an enrichment source, not a
            # hard dependency. If it is down/unreachable the agent must still
            # answer using weather + map + gate data instead of crashing.
            logger.warning("Qdrant OSINT unavailable (%s); continuing without it", exc)
            return []

    def search_osint_events(self, query: str, limit: int | None = None) -> list[dict]:
        return self.search(query, limit=limit, recent_only=True)

    def search_route_risk(self, route_hint: str, limit: int | None = None) -> list[dict]:
        q = f"{route_hint} road flood closure conflict traffic checkpoint"
        return self.search(q, limit=limit, recent_only=True)

    def search_similar_incidents(self, incident: str, limit: int | None = None) -> list[dict]:
        return self.search(incident, limit=limit, recent_only=True)
