import asyncio

import httpx

from app.ingest.pdf import MAX_PDF_BYTES


def test_streaming_limit_stops_before_remaining_body_is_received():
    from app.api.upload_limit import UploadLimitMiddleware

    received = []
    sent = []

    async def consumer(scope, receive, send):
        while (await receive())["more_body"]:
            pass
        raise AssertionError("Oversized body reached the endpoint")

    async def receive():
        received.append(True)
        return {"type": "http.request", "body": b"x" * (1024 * 1024), "more_body": True}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/v1/courses/c/sources", "headers": []}
    asyncio.run(UploadLimitMiddleware(consumer)(scope, receive, send))
    assert len(received) == MAX_PDF_BYTES // (1024 * 1024) + 2
    assert sent[0]["status"] == 413


def test_chunked_multipart_is_limited_by_the_real_app_before_auth(tmp_path):
    from app.api.main import create_app

    read_chunks = []

    async def body():
        for part in range(2):
            yield (f'--boundary\r\nContent-Disposition: form-data; name="file{part}"; '
                   f'filename="part{part}.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode()
            for _ in range(12):
                read_chunks.append(True)
                yield b"x" * (1024 * 1024)
            yield b"\r\n"
        yield b"--boundary--\r\n"

    async def run():
        app = create_app(f"sqlite:///{(tmp_path / 'unused.db').as_posix()}")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/courses/c/sources", content=body(),
                                         headers={"Content-Type": "multipart/form-data; boundary=boundary"})
            assert response.status_code == 413, response.text
            assert response.json()["error"]["code"] == "file_too_large"

    asyncio.run(run())
    assert len(read_chunks) < 24


def test_content_length_limit_rejects_before_reading_unauthenticated_multipart():
    from app.api.upload_limit import UploadLimitMiddleware

    sent = []

    async def consumer(*args):
        raise AssertionError("Oversized request reached multipart parser")

    async def receive():
        raise AssertionError("Body should not be read")

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/v1/courses/c/sources",
             "headers": [(b"content-length", b"999999999"), (b"content-type", b"multipart/form-data")]}
    asyncio.run(UploadLimitMiddleware(consumer)(scope, receive, send))
    assert sent[0]["status"] == 413
