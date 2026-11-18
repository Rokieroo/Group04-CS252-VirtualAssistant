"""Async 1,000-user load test against the production Docker Compose stack (issue #168).

Usage:
    python scripts/load_test.py --base-url https://localhost --users 1000 --concurrency 25 --insecure

Seeds one distinct learner account, course, roadmap, and node per simulated user before
running the login -> roadmap -> graph -> sources -> recommendations -> reviews loop.
With --accounts FILE the seeded accounts are saved there and reused by the next run, so
pg_stat_statements can be reset between seeding and measuring, and several concurrency
levels can be measured on the same data. The file holds throwaway test passwords.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

SYLLABUS = Path(__file__).resolve().parents[1] / "eval/syllabus/01_csc10014_problem_framing.txt"


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(len(sorted_vals) * pct) - 1))
    return sorted_vals[idx]


async def _seed_fixture(client: httpx.AsyncClient) -> tuple[str, str, str, str, str]:
    """Create a seed user + course + roadmap + node so 1,000 users can exercise the read/review loop."""
    email = f"loadseed-{uuid.uuid4().hex[:10]}@example.com"
    password = "load-test-password-2026"
    reg = await client.post(
        "/auth/register",
        json={"name": "Load Seed", "email": email, "password": password, "birth_year": 2003},
    )
    reg.raise_for_status()
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    course = await client.post(
        "/courses",
        headers=headers,
        json={"title": "Load Test CSC10014", "level": "university", "language": "en"},
    )
    course.raise_for_status()
    cid = course.json()["id"]

    up = await client.post(
        f"/courses/{cid}/sources",
        headers=headers,
        data={"kind": "syllabus"},
        files={"file": (SYLLABUS.name, SYLLABUS.read_bytes(), "text/plain")},
    )
    up.raise_for_status()

    parse_resp = await client.post(
        f"/courses/{cid}/syllabus:parse",
        headers=headers,
        json={"file_name": SYLLABUS.name, "use_llm": False},
    )
    parse_resp.raise_for_status()
    preview = parse_resp.json()["parsed"]

    confirm = await client.post(
        f"/courses/{cid}/syllabus",
        headers=headers,
        json={
            "raw_text": "\n".join(
                f"Week {w.get('week', i + 1)}: {w.get('topic', '')}"
                for i, w in enumerate(preview["weeks"])
            ),
            "outcomes": [
                {
                    "code": o.get("code") or f"CLO{i + 1}",
                    "description": o.get("description") or o.get("text") or "outcome",
                }
                for i, o in enumerate(preview["outcomes"])
            ],
            "assessments": [
                {"name": "Midterm", "weight": 40.0, "due_week": 5},
                {"name": "Final", "weight": 60.0, "due_week": 10},
            ],
        },
    )
    confirm.raise_for_status()
    syllabus = confirm.json()

    rm = await client.post(
        f"/courses/{cid}/roadmap:generate",
        headers=headers,
        json={"syllabus_id": syllabus["id"]},
    )
    rm.raise_for_status()
    rm_data = rm.json()
    rid = rm_data["id"]
    nid = rm_data["nodes"][0]["id"]
    return email, password, cid, rid, nid


async def _run_user(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    email: str,
    password: str,
    cid: str,
    rid: str,
    nid: str,
    latencies: dict[str, list[float]],
    errors: dict[str, int],
) -> None:
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.post("/auth/login", json={"email": email, "password": password})
        except httpx.HTTPError:
            latencies["login"].append((time.perf_counter() - t0) * 1000)
            errors["login"] += 1
            return
        latencies["login"].append((time.perf_counter() - t0) * 1000)
        if resp.status_code != 200:
            errors["login"] += 1
            return
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        steps = [
            ("roadmap", f"/roadmaps/{rid}"),
            ("graph", f"/roadmaps/{rid}/graph"),
            ("sources", f"/roadmap-nodes/{nid}/resources"),
            ("recommendations", f"/roadmap-nodes/{nid}/recommendations"),
            ("reviews", "/reviews/due"),
        ]
        for name, path in steps:
            ts = time.perf_counter()
            try:
                r = await client.get(path, headers=headers)
            except httpx.HTTPError:
                latencies[name].append((time.perf_counter() - ts) * 1000)
                errors[name] += 1
                continue
            latencies[name].append((time.perf_counter() - ts) * 1000)
            if r.status_code >= 400:
                errors[name] += 1


async def _seed_with_sem(
    client: httpx.AsyncClient, sem: asyncio.Semaphore
) -> tuple[str, str, str, str, str]:
    async with sem:
        return await _seed_fixture(client)


async def _accounts(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, users: int, saved: Path | None
) -> list[tuple[str, str, str, str, str]]:
    if saved and saved.exists():
        accounts = [tuple(row) for row in json.loads(saved.read_text(encoding="utf-8"))]
        if len(accounts) >= users:
            return accounts[:users]
    accounts = await asyncio.gather(*[_seed_with_sem(client, sem) for _ in range(users)])
    if saved:
        saved.write_text(json.dumps(accounts), encoding="utf-8")
    return accounts


async def main_async(
    base_url: str, users: int, concurrency: int, insecure: bool, saved: Path | None = None
) -> int:
    limits = httpx.Limits(max_connections=concurrency + 20, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/") + "/api/v1",
        verify=not insecure,
        timeout=30.0,
        limits=limits,
    ) as client:
        sem = asyncio.Semaphore(concurrency)
        accounts = await _accounts(client, sem, users, saved)
        latencies: dict[str, list[float]] = defaultdict(list)
        errors: dict[str, int] = defaultdict(int)

        t_start = time.perf_counter()
        await asyncio.gather(
            *[
                _run_user(client, sem, email, password, cid, rid, nid, latencies, errors)
                for email, password, cid, rid, nid in accounts
            ]
        )
        elapsed = time.perf_counter() - t_start

    all_lat = sorted(v for vals in latencies.values() for v in vals)
    total_reqs = len(all_lat)
    total_errs = sum(errors.values())
    p50 = statistics.median(all_lat) if all_lat else 0.0
    p95 = _percentile(all_lat, 0.95)
    p99 = _percentile(all_lat, 0.99)
    err_rate = (total_errs / total_reqs * 100) if total_reqs else 0.0

    print(f"## Load Test ({users} users, concurrency={concurrency}, elapsed={elapsed:.2f}s)\n")
    print(f"- Total requests: {total_reqs} ({total_reqs / elapsed:.1f} req/s)")
    print(f"- Overall: p50={p50:.1f}ms, p95={p95:.1f}ms, p99={p99:.1f}ms, errors={total_errs} ({err_rate:.2f}%)\n")
    print("| Step | Count | p50 (ms) | p95 (ms) | p99 (ms) | Errors |")
    print("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for step in ("login", "roadmap", "graph", "sources", "recommendations", "reviews"):
        vals = sorted(latencies.get(step, []))
        print(
            f"| `{step}` | {len(vals)} | {statistics.median(vals) if vals else 0:.1f} "
            f"| {_percentile(vals, 0.95):.1f} | {_percentile(vals, 0.99):.1f} | {errors[step]} |"
        )

    ok = p95 < 2000.0 and err_rate < 1.0
    print(f"\nSummary: {'PASS' if ok else 'FAIL'} (overall p95 < 2000ms and errors < 1%)")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://localhost")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--accounts", type=Path, help="JSON file to save or reuse seeded accounts")
    args = parser.parse_args()
    return asyncio.run(
        main_async(args.base_url, args.users, args.concurrency, args.insecure, args.accounts)
    )


if __name__ == "__main__":
    raise SystemExit(main())
