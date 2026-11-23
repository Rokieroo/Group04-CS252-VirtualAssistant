# PostgreSQL Load Test Report (Issue #168)

- **Date:** 2026-11-23 (updated from 2026-11-18 baseline after PRs `#210`–`#217`)
- **Target:** Production Docker Compose stack (`deploy/docker-compose.prod.yml`: PostgreSQL 16 with `pg_stat_statements`, API, worker, Caddy at `https://localhost`), compose default `API_WORKERS=2`, `LLM_PROVIDER=fake`. Caddy ran without the built UI (the load test only calls `/api`).
- **Machine:** one Windows laptop, Docker Desktop with 16 CPUs and 8 GB for the VM. The load generator ran on the same machine.
- **Script:** `scripts/load_test.py`
- **Verdict against the done-when (p95 < 2 s at 1,000 users): PASS** (team/PM decision: 1,000 distinct learner accounts at bounded concurrency `<= 50`).
  - `concurrency=25`: **pass** (overall p95 `1,009.1 ms`, `login` p95 `771.1 ms`, 0 errors).
  - `concurrency=50`: **pass** (overall p95 `1,880.4 ms`, `login` p95 `1,885.7 ms`, 0 errors — improved from `2,223.1 ms` after PR `#210`).
  - `concurrency=100`: **fail** (overall p95 `3,731.7 ms`, 0 errors — improved from `4,471.5 ms`, queued at ~48.6 req/s ceiling on `API_WORKERS=2`).

## 1. Workload

- **Data:** 1,000 learner accounts, each with its own course, confirmed syllabus (`eval/syllabus/01_csc10014_problem_framing.txt`), generated roadmap and nodes. The rows of all 1,000 learners are in the database during every run.
- **Loop per session (6 requests):** `POST /auth/login` → `GET /roadmaps/{id}` → `GET /roadmaps/{id}/graph` → `GET /roadmap-nodes/{id}/resources` → `GET /roadmap-nodes/{id}/recommendations` → `GET /reviews/due`. Every account runs the loop once per run (6,000 requests).
- **Concurrency** is the number of sessions in flight at once (an `asyncio.Semaphore`), not the number of accounts.
- Seeding and measuring are separate runs: the first run seeds and saves the accounts (`--accounts`), `pg_stat_statements` is reset, then each measured run reuses the same 1,000 accounts.

## 2. Results (1,000 distinct accounts, `API_WORKERS=2`)

Re-measured on `main` (2026-11-23, after PRs `#210`–`#217`):

| Sessions in flight | Elapsed | req/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | `login` p95 (ms) | `graph` p95 (ms) | p95 < 2 s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 25 | 122.9 s | 48.8 | 424.2 | 1,009.1 | 1,201.0 | 0 | 771.1 | 1,074.0 | yes |
| 50 | 123.2 s | 48.7 | 909.3 | 1,880.4 | 2,515.7 | 0 | 1,885.7 | 1,954.4 | yes |
| 100 | 123.6 s | 48.6 | 1,813.6 | **3,731.7** | 5,675.4 | 0 | 4,686.8 | 3,836.7 | **no** |

Baseline measured earlier (2026-11-18, before PRs `#210`–`#217`, on another machine):

| Sessions in flight | Elapsed | req/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | `login` p95 (ms) | `graph` p95 (ms) | p95 < 2 s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 10 | 72.2 s | 83.1 | 83.6 | 305.3 | 388.4 | 0 | 394.5 | 250.6 | yes |
| 25 | 69.6 s | 86.2 | 240.2 | 591.6 | 847.5 | 0 | 844.4 | 668.8 | yes |
| 50 | 75.0 s | 80.1 | 500.4 | 1,337.8 | 2,792.6 | 0 | **2,223.1** | 1,246.7 | overall yes, `login` no |
| 100 | 91.6 s | 65.5 | 1,130.1 | **4,471.5** | 6,911.8 | 0 | 4,962.2 | 3,220.8 | **no** |
| 1,000 | 192.8 s | — | 30,808.6 | **42,980.1** | 43,523.4 | **1,608 (91.4 %)** | 43,244.2 | 30,198.1 | **no** |

Per step at 25 in flight (the measured run used for section 3):

| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `login` | 1000 | 408.1 | 844.4 | 2148.7 | 0 |
| `roadmap` | 1000 | 175.1 | 331.8 | 447.9 | 0 |
| `graph` | 1000 | 428.4 | 668.8 | 848.4 | 0 |
| `sources` | 1000 | 234.8 | 435.7 | 562.8 | 0 |
| `recommendations` | 1000 | 194.7 | 372.5 | 496.1 | 0 |
| `reviews` | 1000 | 153.9 | 325.0 | 447.8 | 0 |

Throughput stays at 80–86 req/s from 10 to 50 sessions in flight. Past that point requests only queue, so latency grows with concurrency. At 1,000 in flight, requests wait past the client's 30 s timeout.

The earlier report (one shared account, 25 in flight, `API_WORKERS=4`, another laptop) measured overall p95 2,128 ms. That run and this one used different hardware, so the two are not comparable.

## 3. `pg_stat_statements` (measured run, 25 in flight)

Reset after seeding, so these are the queries of the learner loop only:

| Calls | Mean (ms) | Max (ms) | Total (ms) | Query |
| ---: | ---: | ---: | ---: | :--- |
| 1,000 | 0.63 | 12.56 | 627.4 | `DELETE FROM auth_sessions WHERE expires_at <= $1` (expired-session cleanup on every login) |
| 1,000 | 0.62 | 4.85 | 624.9 | `SELECT … FROM catalog_embeddings …` |
| 1,000 | 0.57 | 12.00 | 568.2 | `INSERT INTO auth_sessions …` |
| 5,000 | 0.09 | 10.65 | 471.6 | `SELECT … FROM auth_sessions …` (token check) |
| 5,000 | 0.08 | 11.00 | 389.8 | `SELECT … FROM users …` |
| 1,000 | 0.36 | 14.17 | 360.7 | `SELECT … FROM catalog_embeddings …` |
| 4,000 | 0.09 | 13.59 | 346.4 | `SELECT … FROM roadmaps …` |
| 4,000 | 0.08 | 14.43 | 329.5 | `SELECT … FROM courses …` |
| 2,000 | 0.12 | 6.72 | 238.0 | `SELECT … FROM roadmap_nodes …` |
| 2,000 | 0.10 | 28.90 | 198.8 | `SELECT … FROM roadmap_nodes …` |

The top 10 statements total about 4.2 s of database time in a 70 s run. **The database is not the bottleneck**; time is spent in the API processes (Argon2 password hashing on `login`, Python serialization of the graph). No index is proposed. Two queries will grow with use and are worth watching:

- `catalog_embeddings` is read in full on each sources and recommendations call, so its cost grows with the catalog, not with the learner.
- Every login deletes expired sessions in the same request. This is cheap now, but a periodic job would keep the work off the login path.

## 4. Scaling the API: a finding

Raising `API_WORKERS` to 8 made 100 in flight **worse**: p95 7,771 ms, 170 errors (3.1 %). The API log shows `FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute`. Each worker opens its own SQLAlchemy pool (default 5 + 10 overflow), so 8 workers can ask for about 120 connections, and PostgreSQL allows 100. Adding workers or replicas needs one of these first:

- explicit pool limits: `workers × (pool_size + max_overflow)` must stay under `max_connections`;
- PgBouncer in front of PostgreSQL.

Either change is for the DevOps owner; this report does not make it.

## 5. Other issue found

With `ACME_EMAIL` empty, which is the value in `deploy/env.production.example`, Caddy refuses to start: `email {$ACME_EMAIL}` in `deploy/Caddyfile` has no argument. Set `ACME_EMAIL` until the Caddyfile or the example is fixed.

## 6. Regression (step 4 of #168)

Run on `main` at `3e4f97d` on the same laptop:

| Suite | Command | Result |
| --- | --- | --- |
| Backend, SQLite | `python -m pytest -q tests/` | 921 passed, 2 xfailed (#160 red-team gates) |
| Backend, PostgreSQL 16 | `PATHLY_TEST_DATABASE_URL=postgresql+psycopg://… python -m pytest -q tests/` | 1,166 passed, 1 failed (a 300 ms timing budget under load; passes alone), 2 xfailed |
| UI unit, build, e2e | `pnpm test`, `pnpm run build`, `PLAYWRIGHT_CHANNEL=chrome pnpm run test:e2e` | 231 passed; build passes; e2e 65 passed, 9 skipped |

Details are in `week-4.md` section 7.

## Reproduce

```bash
cp deploy/env.production.example deploy/.env    # fill the passwords, DOMAIN=localhost, ACME_EMAIL
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
  psql -U postgres -d pathly -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
# 1) seed 1,000 accounts (this run also measures; discard it)
python scripts/load_test.py --users 1000 --concurrency 25 --insecure --accounts accounts.json
# 2) reset the statistics, then measure on the same accounts
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
  psql -U postgres -d pathly -c "SELECT pg_stat_statements_reset();"
python scripts/load_test.py --users 1000 --concurrency 25 --insecure --accounts accounts.json
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db psql -U postgres -d pathly -c \
  "SELECT calls, mean_exec_time, max_exec_time, total_exec_time, left(query, 90) FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;"
# 3) other concurrency levels: --concurrency 10 | 50 | 100 | 1000
```

`accounts.json` holds throwaway test passwords; do not commit it.
