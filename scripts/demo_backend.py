"""Run the core workflow against a disposable database with a simulated clock.

No server, account, provider API key or network request is needed:
    python scripts/demo_backend.py
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assistant.backend.config import Settings
from assistant.backend.main import create_app


def main():
    clock = [datetime.now(UTC).replace(second=0, microsecond=0)]
    start = clock[0] + timedelta(minutes=15)
    end = start + timedelta(hours=3)
    stamp = lambda value: value.isoformat()
    with TemporaryDirectory(prefix="pathly-demo-") as folder:
        app = create_app(
            Settings(
                database_url="sqlite:///" + (Path(folder) / "demo.db").as_posix(),
                session_minutes=1440,  # the simulated clock jumps past 60 minutes
            ),
            now=lambda: clock[0],
        )
        with TestClient(app) as client:

            def call(method, path, body=None, headers=None):
                response = client.request(method, path, json=body, headers=headers)
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"{method} {path}: {response.status_code} {response.text}"
                    )
                return response.json() if response.content else None

            auth = call(
                "POST",
                "/api/v1/auth/register",
                {
                    "email": "minh@example.com",
                    "name": "Minh",
                    "password": "demo-password-123",
                    "birth_year": 2004,
                },
            )
            headers = {"Authorization": "Bearer " + auth["access_token"]}
            goal = call(
                "POST", "/api/v1/goals", {"title": "Finish CS252 revision"}, headers
            )
            task = call(
                "POST",
                "/api/v1/tasks",
                {
                    "title": "Review scheduling algorithms",
                    "duration_minutes": 90,
                    "priority": 1,
                    "due_at": stamp(end),
                    "goal_id": goal["id"],
                },
                headers,
            )
            call(
                "PUT",
                "/api/v1/availability",
                {
                    "windows": [
                        {"starts_at": stamp(start), "ends_at": stamp(end)},
                    ]
                },
                headers,
            )
            call(
                "POST",
                "/api/v1/busy-blocks",
                {
                    "starts_at": stamp(start + timedelta(minutes=60)),
                    "ends_at": stamp(start + timedelta(minutes=90)),
                    "title": "Class",
                },
                headers,
            )
            request = {"starts_at": stamp(clock[0]), "ends_at": stamp(end)}
            preview = call("POST", "/api/v1/schedule/plan", request, headers)
            assert (
                not preview["committed"]
                and len(call("GET", "/api/v1/schedule", headers=headers)) == 0
            )
            call("POST", "/api/v1/schedule/plan", {**request, "commit": True}, headers)
            entries = call("GET", "/api/v1/schedule", headers=headers)
            first = entries[0]
            clock[0] = datetime.fromisoformat(first["ends_at"])
            checkin = {"status": "completed", "actual_minutes": 30}
            for _ in range(2):
                call("POST", f"/api/v1/schedule/{first['id']}/check-in", checkin, headers)
            call(
                "POST",
                "/api/v1/schedule/replan",
                {
                    "starts_at": stamp(clock[0]),
                    "ends_at": stamp(end),
                    "commit": True,
                },
                headers,
            )
            updated = call("GET", f"/api/v1/tasks/{task['id']}", headers=headers)
            assert updated["completed_minutes"] == 30
            companion = call(
                "POST",
                "/api/v1/ai/chat",
                {"message": "How am I doing?", "mood": "tired"},
                headers,
            )
            team = call("POST", "/api/v1/teams", {"name": "Group 04"}, headers)
            other = call(
                "POST",
                "/api/v1/auth/register",
                {
                    "email": "thang@example.com",
                    "name": "Thang",
                    "password": "demo-password-456",
                    "birth_year": 2004,
                },
            )
            other_headers = {"Authorization": "Bearer " + other["access_token"]}
            invite = call(
                "POST",
                f"/api/v1/teams/{team['id']}/invitations",
                {"email": "thang@example.com"},
                headers,
            )
            call(
                "POST",
                f"/api/v1/invitations/{invite['id']}/accept",
                {"code": invite["code"]},
                other_headers,
            )
            print(
                json.dumps(
                    {
                        "result": "passed",
                        "database": "temporary; removed after this demo",
                        "clock": "simulated",
                        "preview_sessions": len(preview["entries"]),
                        "completed_minutes_after_repeated_checkin": 30,
                        "ai_provider": companion["provider"],
                        "team_members": len(
                            call(
                                "GET",
                                f"/api/v1/teams/{team['id']}/members",
                                headers=headers,
                            )
                        ),
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
