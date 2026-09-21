# Myanmar Logistics Intelligence Platform

Real-time logistics monitoring and decision support for Myanmar trading corridors.

Stack: **FastAPI + PostGIS + Qdrant (`content`) + Gemma-e2b + React/Leaflet**.

## Architecture

```text
React dashboard (:4173)
        │
   FastAPI (:8010)
        ├── PostGIS (shipments, GPS, risks)
        ├── Weather (stub / OpenWeather)
        ├── Qdrant OSINT @ 192.168.11.52:6333 / content
        └── Gemma-e2b @ GEMMA_URL (default :8004)
```

The **LogisticsAgent** is not a chatbot: it loads shipment + GPS, weather, Qdrant OSINT, scores risk, then asks Gemma for structured JSON (reasons + recommendation).

## Quick start (Docker)

```bash
cd KyawZayaNaing-assignment5
cp backend/.env.example backend/.env
docker compose up --build -d
```

- UI: http://localhost:4173
- API docs: http://127.0.0.1:8010/api/docs
- Postgres/PostGIS: `localhost:5435`

External (already running on this host):

- Qdrant: `http://192.168.11.52:6333` collection `content`
- Gemma: `http://127.0.0.1:8004` model `Gemma-SEA-LION-v4.5-E2B-IT`

## Native API (optional)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ensure PostGIS on DATABASE_URL (compose postgres is enough)
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Frontend:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev   # http://localhost:4173
```

## RBAC demo accounts

After `python -m app.seed` (or Alembic `0002_rbac`):

| Username | Password | Role | UI |
| --- | --- | --- | --- |
| `admin` | `Admin123!` | ADMIN | `/admin` — all shipments, border gates, AI, alerts |
| `trader` | `Trader123!` | TRADER | `/trader` — create/track own shipments, AI alerts |
| `driver1` | `Driver123!` | DRIVER | `/driver` — mobile actions + offline queue |

Login: http://localhost:4173/login

## Demo: SH001 risk

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8010/api/auth/login/json \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin123!"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -sS -X POST http://127.0.0.1:8010/api/ai/query \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Is shipment SH001 safe?","tracking_number":"SH001"}'
```

Close Myawaddy gate (alerts + AI for affected shipments):

```bash
curl -sS -X PATCH http://127.0.0.1:8010/api/gates/2 \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"CLOSED"}'
```

Or:

```bash
curl -sS http://127.0.0.1:8010/api/shipments/1/risk
```

## Tests

Requires seeded PostGIS (`python -m app.seed`) and `DATABASE_URL` in `backend/.env`.

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Covers auth/RBAC, border gates (list/impact/ADMIN patch with mocked AI), shipment timeline, and document upload → timeline attachment.

## Environment

See [backend/.env.example](backend/.env.example).

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostGIS SQLAlchemy URL |
| `QDRANT_URL` / `QDRANT_COLLECTION` | OSINT vector store (`content`) |
| `EMBEDDING_MODE` | `keyword` (default, text filter) / `http` / `local` / `auto` |
| `EMBEDDING_BASE_URL` | OpenAI-compatible embeddings API (1024-dim) |
| `GEMMA_URL` / `GEMMA_API_KEY` / `LLM_MODEL_GEMMA` | LLM client |
| `WEATHER_PROVIDER` | `stub` or `openweather` |
| `CORS_ORIGINS` | Frontend origins |

## API surface

Auth / RBAC:

- `POST /api/auth/login/json`
- `GET /api/auth/me`

Shipments / timeline / driver:

- `POST /api/shipments`
- `GET /api/shipments` (role-filtered)
- `GET /api/shipments/{id}/timeline`
- `POST /api/shipments/{id}/driver-action`
- `GET /api/shipments/{id}/risk`

Border gates:

- `GET /api/gates`
- `PATCH /api/gates/{id}` (ADMIN) — OPEN | WARNING | CLOSED
- `GET /api/gates/{id}/impact`

Map / AI:

- `GET /api/map/overview` (vehicles, gates, risk zones, weather tiles)
- `POST /api/ai/query`
- `POST /api/osint/ingest`
- `GET /api/alerts`
- OpenAPI: `/api/docs`

## Notes

- Driver offline: assigned trips are cached in **IndexedDB until DELIVERED**. GPS/actions/documents queue while offline and sync when back online. Open the driver page once online so the trip is cached before the border corridor goes dark.
- Dashboards **auto-poll** map / shipments / alerts / timeline every ~8s while the tab is visible (Live badge). No page reload needed.
- Embeddings for `content` were built with **Qwen3-Embedding-0.6B (1024-d)**. Default MVP uses Qdrant **text filters** (`EMBEDDING_MODE=keyword`) so the stack runs without loading the embedder on GPU. Point `EMBEDDING_BASE_URL` at a matching `/v1/embeddings` service for true vector RAG.
- Live Telegram/Facebook crawlers are deferred; OSINT is read from Qdrant + optional local `osint_events` ingest.
