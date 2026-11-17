# PostgreSQL Load Test Report (Issue #168)

- **Date:** 2026-11-17
- **Target:** Production Docker Compose stack (`https://localhost`, `deploy/docker-compose.prod.yml`, PostgreSQL 16 + Caddy), run with `API_WORKERS=4` (the compose default is 2)
- **Script:** `scripts/load_test.py`
- **Verdict against the done-when (p95 < 2 s at 1,000 users): FAIL.** Overall p95 is 2128.0 ms, and `login` alone is 2427.4 ms. The five read endpoints are each under 2 s.

## What was measured

1,000 sessions run the learner loop: login, roadmap, graph, node sources, recommendations, reviews. At most 25 sessions run at once. All sessions log in to **one seeded account** and read **the same roadmap and node**. This differs from 1,000 real users in two ways:

- **Concurrency:** this is 25 concurrent users, not 1,000 concurrent.
- **Data:** the database holds one learner's rows, so per-user data growth and row contention are not exercised.

## 1. Observed Results (`concurrency=25`, `elapsed=120.66s`)

- **Total requests:** 6,000 (`49.7 req/s`)
- **Overall:** `p50=214.9ms`, `p95=2128.0ms`, `p99=2405.7ms`, **errors = 0 (0.00%)**

| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Under 2 s at p95 |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `login` | 1000 | 2020.2 | 2427.4 | 2763.4 | 0 | **no** (Argon2 CPU contention) |
| `roadmap` | 1000 | 183.8 | 341.9 | 462.6 | 0 | yes |
| `graph` | 1000 | 260.4 | 507.4 | 596.3 | 0 | yes |
| `sources` | 1000 | 192.0 | 359.6 | 455.4 | 0 | yes |
| `recommendations` | 1000 | 185.9 | 342.7 | 544.6 | 0 | yes |
| `reviews` | 1000 | 167.3 | 302.1 | 402.5 | 0 | yes |

An earlier run against the single-worker dev container (`study_api`) gave `login` p95 = 3553.2 ms and `graph` p95 = 8180.5 ms. Moving to the production stack with 4 workers brought `graph` down to 507.4 ms.

## 2. Bottlenecks and next steps

1. **`login` (Argon2):** each login hashes on the API's CPU. With 25 logins at once, p95 is 2.4 s even with 4 workers. Options, still untested:
   - more API replicas behind Caddy;
   - lower Argon2 cost parameters, which is a security trade-off for the DB/security owner;
   - longer-lived sessions, so a learner does not log in on every visit.
2. **Slow queries are not measured yet.** `pg_stat_statements` was not enabled during this run, so no index is proposed. The candidates in the first draft already exist: `ix_roadmap_nodes_roadmap_id`, `ix_roadmap_edges_roadmap_id`, `ix_recommendations_user_node`, and the `node_resources` primary key `(node_id, resource_id)`. Enable `shared_preload_libraries = 'pg_stat_statements'` on the `db` service and re-run before adding any index.
3. **Cache race (fixed):** a smoke run of the script (30 sessions, 5 at once, SQLite) returned one `500` on `recommendations`. Two first-time requests for a node both inserted the same `external_results` row. `set_external_cache` now keeps the first row, like `store_search` does, and `tests/test_recommendations.py` covers the race. The production run above probably missed it because the cache was already warm.
4. **Full regression (step 4 of #168)** was not run for this report: backend on SQLite and PostgreSQL, UI, and e2e.

## To close #168

- Seed one account (with its own roadmap) per simulated user, and run at the target concurrency with the compose default `API_WORKERS`, or document the worker count production will use.
- Bring `login` under 2 s at p95, or agree with the team that the 2 s target excludes authentication.
- Record the `pg_stat_statements` top queries and the full regression result.
