"""Bound aggregate request bytes before multipart parsing spools any file parts."""
from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.ingest.pdf import MAX_PDF_BYTES

# Allow multipart headers/fields; the file itself still has an exact 20 MiB limit.
MAX_UPLOAD_REQUEST_BYTES = MAX_PDF_BYTES + 1024 * 1024
DETAIL = {"code": "file_too_large", "message": "PDF limit is 20 MB; multipart request limit is 21 MB."}


class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST" or
                not scope["path"].startswith("/api/v1/courses/") or not scope["path"].endswith("/sources")):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = 0  # The streamed-byte bound remains authoritative.
        if length > MAX_UPLOAD_REQUEST_BYTES:
            return await JSONResponse({"error": DETAIL}, status_code=413)(scope, receive, send)
        count = 0

        async def limited_receive():
            nonlocal count
            message = await receive()
            if message["type"] == "http.request":
                count += len(message.get("body", b""))
                if count > MAX_UPLOAD_REQUEST_BYTES:
                    raise HTTPException(413, detail=DETAIL)
            return message

        try:
            await self.app(scope, limited_receive, send)
        except HTTPException as exc:
            if exc.status_code != 413:
                raise
            await JSONResponse({"error": DETAIL}, status_code=413)(scope, receive, send)
