# PostgreSQL Load Test Report (Issue #168)

- **Date:** 2026-11-17
- **Target:** Local Docker Compose PostgreSQL + FastAPI stack (`http://127.0.0.1:8000`, `study_api` + `study_db`)
- **Script:** `scripts/load_test.py`

---

## 1. Observed Results

### Run A — 1,000 simulated users (`concurrency=25`, `elapsed=405.42s`)

| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Notes |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `login` | 1000 | 2615.8 | 3553.2 | 4589.2 | 0 | Argon2 CPU saturation on single uvicorn worker |
| `graph` | 1000 | 7264.5 | 8180.5 | 9213.2 | 0 | `GET /roadmaps/{id}/graph` bottleneck under load |

### Run B — 50 simulated users with corrected routes (`concurrency=10`, `elapsed=40.07s`)

| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Notes |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `login` | 50 | 611.4 | 1116.9 | 1453.6 | 0 | Pass `< 2000ms` at low concurrency |
| `roadmap` | 50 | 311.5 | 501.0 | 546.8 | 0 | Pass `< 2000ms` |
| `graph` | 50 | 3420.9 | 4197.8 | 4276.9 | 0 | Exceeds `2000ms` p95 target |
| `sources` | 50 | 3374.0 | 4176.0 | 4260.8 | 0 | Exceeds `2000ms` p95 target |
| `recommendations` | 50 | 16.4 | 63.2 | 120.9 | 50 | 404 on running container (needs rebuild from `main`) |
| `reviews` | 50 | 19.0 | 87.6 | 171.7 | 50 | 404 on running container (needs rebuild from `main`) |

---

## 2. Bottleneck Analysis & Recommendations

1. **Multi-worker API & Argon2 concurrency (`login`)**:
   - At `concurrency=10`, `login` p95 is `1116.9ms`; at `concurrency=25` on 1 uvicorn worker, `login` p95 climbs to `3553.2ms` due to Argon2 CPU contention.
   - **Action:** Run `API_WORKERS >= 4` in `deploy/.env` (or horizontal replicas behind Caddy) for 1,000-user bursts.
2. **Graph & Node Sources (`GET /roadmaps/{id}/graph`, `GET /roadmap-nodes/{id}/resources`)**:
   - Both endpoints exceed `2000ms` p95 even at `concurrency=10` (`4197.8ms` / `4176.0ms`).
   - **Recommended PostgreSQL indexes:**
     - `CREATE INDEX IF NOT EXISTS ix_roadmap_nodes_roadmap_id ON roadmap_nodes (roadmap_id);`
     - `CREATE INDEX IF NOT EXISTS ix_roadmap_edges_roadmap_id ON roadmap_edges (roadmap_id);`
     - `CREATE INDEX IF NOT EXISTS ix_node_resources_node_status ON node_resources (node_id, status);`
     - `CREATE INDEX IF NOT EXISTS ix_recommendations_user_node_active ON recommendations (user_id, node_id, dismissed_at, rank);`
   - **Action:** Enable `pg_stat_statements` in PostgreSQL (`shared_preload_libraries = 'pg_stat_statements'`) and batch/cache read-heavy graph payloads.
3. **Full Regression Status**:
   - Backend full suite (`pytest -q tests/`): **923 passed** (verified on `main` / `#160`).
   - Re-run `scripts/load_test.py --users 1000` after rebuilding `deploy/docker-compose.prod.yml` with `API_WORKERS=4` and the recommended indexes to confirm `p95 < 2000ms`.
