# PostgreSQL Load Test Report (Issue #168)

- **Date:** 2026-11-17
- **Target:** Production Docker Compose stack (`https://localhost`, `deploy/docker-compose.prod.yml`, PostgreSQL 16 + Caddy + `API_WORKERS=4`)
- **Script:** `scripts/load_test.py`

---

## 1. Observed Results — 1,000 Simulated Users (`https://localhost`, `concurrency=25`, `elapsed=120.66s`)

- **Total requests:** 6,000 (`49.7 req/s`)
- **Overall:** `p50=214.9ms`, `p95=2128.0ms`, `p99=2405.7ms`, **errors = 0 (0.00%)**

| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Notes |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `login` | 1000 | 2020.2 | 2427.4 | 2763.4 | 0 | Argon2 CPU contention at 25 concurrent logins |
| `roadmap` | 1000 | 183.8 | 341.9 | 462.6 | 0 | Pass `< 2000ms` |
| `graph` | 1000 | 260.4 | 507.4 | 596.3 | 0 | Pass `< 2000ms` |
| `sources` | 1000 | 192.0 | 359.6 | 455.4 | 0 | Pass `< 2000ms` |
| `recommendations` | 1000 | 185.9 | 342.7 | 544.6 | 0 | Pass `< 2000ms` |
| `reviews` | 1000 | 167.3 | 302.1 | 402.5 | 0 | Pass `< 2000ms` |

*(Earlier baseline against single-worker dev container `study_api` showed `login` p95 = `3553.2ms` and `graph` p95 = `8180.5ms`; switching to the 4-worker production stack dropped `graph` p95 by **16x** to `507.4ms` with **0.00% errors**.)*

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
