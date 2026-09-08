# Vehicle Visual Re-ID (Phase 14 §1)

Appearance-based matching of vehicle sightings across cameras, as an
**investigative lead layer** on top of the existing plate-string journey.

> **Visual similarity is not identity.** Every result is labelled
> `VISUAL MATCH` with an explicit similarity % and a confidence that is
> **capped at MEDIUM** — only a deterministic plate match (correlation
> layer, `CROSS_CAMERA_INTELLIGENCE.md`) yields "same vehicle".

---

## 1. Pipeline

```
vehicle_event (detection)
      │
      ▼
feature extraction  ──►  embedding backend  ──►  unit vector  ──►  vehicle_embeddings
      │                  (pluggable)
      ▼
bounded cosine similarity search  ──►  ranked candidates  ──►  cross-camera correlation
```

Embeddings are computed **best-effort after the event is committed** — the
ANPR / YOLO / ByteTrack ingest path is untouched. When government feeds
return, new events flow through the existing ingest and are indexed
automatically (`REID_AUTO_INDEX`, default on).

## 2. Embedding backends (pluggable, like the LLM provider)

| Backend | `REID_EMBEDDING_BACKEND` | Deps | Vector |
| :--- | :--- | :--- | :--- |
| **Attribute baseline** (default) | `attribute` | none | `attr-baseline-v1`, dim 29. Weighted `[ type one-hot | colour one-hot | plate-known | confidence | texture-signature(8) ]`, L2-normalised. |
| Torch CNN (optional) | `torch` | torch, torchvision, PIL | `torch-resnet50-v1`, dim 2048. ResNet-50 penultimate features on the stored crop. Constructed only if the imports succeed (AI-pipeline container); silently falls back to the baseline otherwise. |
| Pipeline-supplied | — | — | An upgraded pipeline may POST `embedding[]` + `embedding_model` on the ingest event; stored verbatim (`source="pipeline"`). |

### The attribute baseline is a real, working model

- **Deterministic**: same input → identical vector.
- **Identity signal**: the texture signature is seeded by the plate string,
  so two sightings of `GJ18TC0450` embed identically (cosine ≈ 1.0); an
  `UNKNOWN`-plate vehicle is seeded by `camera+track` so distinct unknowns
  still separate.
- **Appearance signal**: same type **and** colour embed close; a different
  colour or type pulls the cosine down measurably (test-asserted ordering).

It is deliberately not a CNN — absent GPU and crop storage in the backend
tier, plate-string identity + coarse appearance is the honest baseline, and
the architecture drops in a real extractor without an API change.

## 3. Storage & search — no pgvector

`postgis/postgis:15-3.3` has no `pgvector`, so `vehicle_embeddings.embedding`
is a JSON float array and the **repository does bounded brute-force cosine
similarity** in-process:

- a scan loads at most `REID_MAX_CANDIDATES` (500) rows, time-ordered,
  optionally windowed to ±`time_window_hours` around the query sighting;
- ranking is `cosine_similarity` (pure-Python dot product of unit vectors);
- the top `limit` above `REID_SIMILARITY_WEAK` are returned.

At PoC scale (retention-bounded `vehicle_events`) this is <10 ms. The
`VectorRepository` seam is `VehicleReIDService.find_similar` /
`rank_candidates`; swapping in pgvector or a real ANN index is a
drop-in that keeps the same method signatures.

## 4. Similarity bands

| Cosine | Band | Confidence | Meaning |
| :--- | :--- | :--- | :--- |
| ≥ 0.92 | `STRONG` | MEDIUM | strong appearance match — corroborate with plate/time/geo |
| ≥ 0.80 | `MODERATE` | LOW | plausible — a lead |
| ≥ 0.65 | `WEAK` | LOW | weak — low-priority lead |
| < 0.65 | `NONE` | INSUFFICIENT | not returned |

`same_plate == true` overrides the band label to `PLATE MATCH` and the note
to "deterministically the same vehicle".

## 5. API (`/api/v1/ai/reid/*`, JWT-authenticated)

| Endpoint | Role | Purpose |
| :--- | :--- | :--- |
| `POST /ai/reid/search` | any auth | rank appearance-similar sightings for an `event_id` or `plate`. Bounded. Audited `AI_REID_SEARCH`. |
| `POST /ai/reid/compare` | any auth | cosine similarity of two sightings + band + `same_plate`. |
| `GET /ai/reid/embedding/{event_id}` | any auth | stored embedding metadata (indexes on demand). |
| `POST /ai/reid/backfill` | ADMIN/OFFICER | index events with no embedding yet (bounded `REID_BACKFILL_BATCH`). Audited `AI_REID_BACKFILL`. |

`find_similar` runs a bounded idempotent backfill first, so search works on
a DB whose events predate embedding indexing (migration day).

## 6. Config

| Setting | Default | Notes |
| :--- | :--- | :--- |
| `REID_EMBEDDING_BACKEND` | `attribute` | `attribute` \| `torch` |
| `REID_AUTO_INDEX` | `true` | index every ingested event (off in tests) |
| `REID_MAX_CANDIDATES` | `500` | hard scan ceiling |
| `REID_BACKFILL_BATCH` | `500` | max events per backfill call |
| `REID_SIMILARITY_STRONG` / `_MODERATE` / `_WEAK` | `0.92` / `0.80` / `0.65` | band thresholds |

## 7. Schema

`vehicle_embeddings` (migration `0009`, additive): `id`,
`vehicle_event_id` (unique FK), denormalised `plate_number_normalized` /
`camera_id` / `camera_code` / `track_id` / `timestamp` /
`vehicle_type` / `vehicle_color`, `embedding` (JSON), `dim`, `model_name`,
`source`. No existing table changed.

## 8. Tests

`backend/tests/test_reid.py` (13): deterministic + unit-norm embedding,
same-plate identical, attribute similarity ordering, band cap (never HIGH),
idempotent index, same-plate ranked first, no-match handling, exclude-same-
plate, compare, search endpoint + audit, auth 401, backfill RBAC.

## 9. Limitations

- The attribute baseline cannot distinguish two same-colour same-type
  vehicles with unknown plates beyond their track seed — it will rank them
  as `MODERATE`, never `STRONG`. This is intended (no false "same vehicle").
- Real visual Re-ID (colour/shape/logo invariance, occlusion) needs the
  `torch` backend with crop storage — architected, not enabled in the
  backend tier.
- No online re-ranking / query expansion; the scan is single-pass bounded.
