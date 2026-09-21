# API

Base: `http://127.0.0.1:8010/api`

Interactive docs: `/api/docs`

## AI query

`POST /ai/query`

```json
{
  "question": "Is shipment SH001 safe?",
  "tracking_number": "SH001"
}
```

Response includes `answer`, `risk`, `risk_score`, `reasons`, `recommendation`, `sources` (Qdrant hits), `weather`, `position`.

## Shipment risk

`GET /shipments/{id}/risk` — runs the LogisticsAgent for that shipment.
