import os
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from assistant.backend.config import Settings
from assistant.backend.main import create_app

# Offline even when a test loads .env: load_dotenv never overrides a variable already set.
os.environ["LLM_PROVIDER"] = "fake"


@pytest.fixture
def clock():
    return [datetime(2030, 1, 7, 0, 0, tzinfo=UTC)]


@pytest.fixture(
    params=["sqlite", "postgres"]
    if os.getenv("PATHLY_TEST_DATABASE_URL")
    else ["sqlite"]
)
def database_url(request):
    if request.param == "sqlite":
        yield "sqlite://"
        return
    # Every test owns a fresh schema; existing tables in the test database are untouched.
    url = make_url(os.environ["PATHLY_TEST_DATABASE_URL"])
    schema = "pathly_test_" + uuid4().hex
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(CreateSchema(schema))
        yield url.update_query_dict(
            {"options": "-csearch_path=" + schema}
        ).render_as_string(hide_password=False)
    finally:
        with engine.connect() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.fixture
def app(clock, database_url):
    return create_app(
        # Scheduling tests move the clock by days; expiry is tested in test_auth.py.
        Settings(database_url=database_url, session_minutes=43200),
        now=lambda: clock[0],
    )


@pytest.fixture
def client(app):
    with TestClient(app) as instance:
        yield instance


def register(client, name="Minh", email="minh@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "correct-horse-123",
            "birth_year": 2004,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def account(client):
    return register(client)


@pytest.fixture
def headers(account):
    return {"Authorization": "Bearer " + account["access_token"]}

# Fixtures for Issue #16 integration tests: two isolated accounts for access-control tests.
@pytest.fixture
def user_a(client):
    return register(client, name="Lan", email="lan@example.com")


@pytest.fixture
def headers_a(user_a):
    return {"Authorization": "Bearer " + user_a["access_token"]}


@pytest.fixture
def user_b(client):
    return register(client, name="Han", email="han@example.com")


@pytest.fixture
def headers_b(user_b):
    return {"Authorization": "Bearer " + user_b["access_token"]}


def task(client, headers, **changes):
    response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": "Review algebra",
            "duration_minutes": 90,
            "priority": 2,
            "due_at": "2030-01-07T18:00:00+07:00",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def availability(
    client, headers, start="2030-01-07T09:00:00+07:00", end="2030-01-07T12:00:00+07:00"
):
    response = client.put(
        "/api/v1/availability",
        headers=headers,
        json={
            "windows": [{"starts_at": start, "ends_at": end}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def plan(client, headers, **changes):
    response = client.post(
        "/api/v1/schedule/plan",
        headers=headers,
        json={
            "starts_at": "2030-01-07T08:00:00+07:00",
            "ends_at": "2030-01-08T00:00:00+07:00",
            "commit": True,
            **changes,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def make_pdf(*page_texts):
    """A real PDF with one page per text; "" gives an empty (scanned-like) page."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in page_texts:
        page = writer.add_blank_page(612, 792)
        if text:
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
            )
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode())
            page.replace_contents(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def sample_pdf():
    return make_pdf("alpha   lecture", "beta lecture", "gamma lecture")
