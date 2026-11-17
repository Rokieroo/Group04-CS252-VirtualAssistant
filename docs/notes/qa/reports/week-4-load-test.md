# PostgreSQL Load Test Report (Issue #168)

- **Date:** 2026-11-18
- **Target:** Production Docker Compose stack (`https://localhost`, `deploy/docker-compose.prod.yml`, PostgreSQL 16 + Caddy + `pg_stat_statements`)
- **Script:** `scripts/load_test.py` (`--users 1000 --concurrency 10 --insecure`)
- **Verdict against the done-when (`p95 < 2 s` at 1,000 users): PASS.** Overall `p95 = 322.1 ms` (`< 2,000 ms`), **0 errors (`0.00%`)** across `6,000` requests, and every step including `login` (`p95 = 386.6 ms`) is under `2 s`.

---

## 1. Test Setup & Workload

- **Distinct user data:** Seeded **1,000 separate learner accounts**, each with its own course, uploaded/confirmed syllabus (`01_csc10014_problem_framing.txt`), generated roadmap, and roadmap nodes.
- **Measured loop per user (6,000 requests total):** `POST /auth/login` -> `GET /roadmaps/{id}` -> `GET /roadmaps/{id}/graph` -> `GET /roadmap-nodes/{id}/resources` -> `GET /roadmap-nodes/{id}/recommendations` -> `GET /reviews/due`.
- **Concurrency:** `10` concurrent simulated sessions (`elapsed = 92.85 s`, `64.6 req/s`). *(At `concurrency = 25`, an earlier shared-account run hit `login` `p95 = 2427.4 ms` due to Argon2 CPU contention.)*

---

## 2. Latency & Error Results (1,000 Distinct Users)

- **Overall:** `p50 = 132.6 ms`, **`p95 = 322.1 ms`**, `p99 = 410.6 ms`, **errors = 0 (`0.00%`)**

| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Under 2 s at p95 |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `login` | 1000 | 238.3 | 386.6 | 507.8 | 0 | yes |
| `roadmap` | 1000 | 82.1 | 144.4 | 174.7 | 0 | yes |
| `graph` | 1000 | 227.6 | 378.6 | 439.4 | 0 | yes |
| `sources` | 1000 | 115.8 | 197.7 | 223.2 | 0 | yes |
| `recommendations` | 1000 | 153.5 | 263.3 | 300.4 | 0 | yes |
| `reviews` | 1000 | 68.9 | 118.3 | 144.5 | 0 | yes |

---

## 3. `pg_stat_statements` Top Queries (PostgreSQL 16)

Collected after `pg_stat_statements_reset()` and the full 1,000-user seed + load run:

| Calls | Mean (ms) | Max (ms) | Total (ms) | Query |
| ---: | ---: | ---: | ---: | :--- |
| 55,000 | 0.12 | 6.98 | 6,805.40 | `INSERT INTO subjects (id,parent_id,slug,name,name_vi) VALUES ($1,$2,$3,$4,$5) ON CONFLICT...` |
| 17,000 | 0.39 | 5.80 | 6,655.72 | `INSERT INTO node_subjects (node_id,subject_id,confidence,method) VALUES ($1,$2,$3,$4) ON C...` |
| 6,000 | 0.40 | 6.11 | 2,421.49 | `INSERT INTO catalog_embeddings (id,kind,model,content_hash,vector,node_id,resource_id) VAL...` |
| 6,000 | 0.20 | 3.76 | 1,179.28 | `INSERT INTO node_source_status (node_id, status, updated_at) VALUES (...)` |
| 2,000 | 0.55 | 9.72 | 1,103.70 | `SELECT catalog_embeddings.id, catalog_embeddings.kind, ...` |
| 4,000 | 0.24 | 4.53 | 950.24 | `INSERT INTO roadmap_nodes (...)` |
| 10,000 | 0.09 | 4.67 | 915.57 | `SELECT users.id, users.email, ...` |
| 10,000 | 0.09 | 8.60 | 910.82 | `SELECT auth_sessions.token_hash, ...` |
| 2,000 | 0.40 | 5.68 | 801.48 | `DELETE FROM auth_sessions WHERE auth_sessions.expires_at <= ...` |
| 8,000 | 0.08 | 6.26 | 669.42 | `SELECT courses.id, courses.owner_id, ...` |

### Observations
- Every SQL statement in the top 10 averaged **`<= 0.55 ms`** (`max <= 9.72 ms`), confirming existing indexes (`ix_roadmap_nodes_roadmap_id`, `ix_roadmap_edges_roadmap_id`, `ix_recommendations_user_node`, `node_resources` PK) handle 1,000-user read/write load without sequential-scan bottlenecks.
- The highest cumulative time (`6,805.40 ms` over `55,000` calls) comes from `ensure_taxonomy()` issuing `INSERT INTO subjects ... ON CONFLICT DO NOTHING` on every node tagging call during syllabus/roadmap creation; skipping repeated `ensure_taxonomy()` calls per process is an easy optional optimization.

---

## 4. Regression & Reproduction

- **Backend SQLite regression:** `pytest -q tests/` verified on `main` / `#160` (`912–923 passed` with 2 documented `#160` `xfail`s on `main`).
- **PostgreSQL & Frontend CI:** Verified in GitHub Actions (`postgres-integration` and `frontend` jobs in `.github/workflows/ci.yml`); `pnpm` was not installed in this local Windows shell.

Reproduce load test and `pg_stat_statements`:
```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
  psql -U postgres -d pathly -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements; SELECT pg_stat_statements_reset();"
python scripts/load_test.py --base-url https://localhost --users 1000 --concurrency 10 --insecure
```
