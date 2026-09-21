# Setup

## Docker Compose

```bash
docker compose up --build -d
```

Ports:

- Web `4173`
- API `8010`
- PostGIS `5435`

## Prerequisites on host

- Qdrant reachable at `192.168.11.52:6333`
- Gemma chat API on `127.0.0.1:8004` (or set `GEMMA_URL`)

## Seed

Compose entrypoint runs `python -m app.seed` (creates SH001 / SH002).
