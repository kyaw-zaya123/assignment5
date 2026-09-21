# Architecture

## Decision agent flow

```text
Question
  → intent + shipment resolve
  → GPS (vehicle_positions / PostGIS)
  → WeatherClient
  → Qdrant content search (vector or keyword)
  → heuristic risk score
  → context fusion
  → Gemma-e2b JSON decision
  → persist logistics_risk_predictions
```

## Data stores

| Store | Role |
| --- | --- |
| PostGIS | Operational logistics + geography |
| Qdrant `content` | OSINT evidence (~4.5M points) |
| Gemma | Reasoning / recommendation |

## Modules

- `app/intelligence/agents/logistics_agent.py` — orchestrator
- `app/intelligence/rag/` — retrieve / rerank / context
- `app/intelligence/llm/gemma_client.py` — configurable LLM
- `app/weather/weather_client.py` — weather providers
- `app/gis/spatial.py` — distance / risk zones
