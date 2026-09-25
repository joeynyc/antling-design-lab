"""Keep the unauthenticated Lab confined to trusted local browser requests."""

from urllib.parse import urlsplit

from starlette.responses import JSONResponse


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
        "connect-src 'self' http://127.0.0.1:8766; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}


class LocalAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value.decode("latin-1") for key, value in scope["headers"]}

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status, headers=SECURITY_HEADERS)(scope, receive, send)

        try:
            host = urlsplit("http://" + headers.get(b"host", ""))
            if host.hostname not in LOCAL_HOSTS or host.username or host.password or host.path or host.query or host.fragment:
                return await reject(400, "Use the Lab through localhost or an SSH tunnel")
            host_port = host.port  # Validate even when the request has no Origin.
            origin = headers.get(b"origin")
            if origin:
                source = urlsplit(origin)
                port = host_port or (443 if scope["scheme"] == "https" else 80)
                source_port = source.port or (443 if source.scheme == "https" else 80)
                if source.scheme != scope["scheme"] or source.hostname != host.hostname or source_port != port or source.username or source.password or source.path or source.query or source.fragment:
                    return await reject(403, "Cross-origin requests are not allowed")
        except ValueError:
            return await reject(400, "Invalid host or origin")
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"} and headers.get(b"sec-fetch-site") == "cross-site":
            return await reject(403, "Cross-site requests are not allowed")

        # Bound requests before multipart parsing can spool unbounded data to disk.
        limit = (21 if scope["path"] in {"/api/jobs", "/v1/images/edits"} else 4) * 1024 * 1024
        try:
            declared_size = int(headers.get(b"content-length", "0"))
        except ValueError:
            return await reject(400, "Invalid content length")
        if declared_size < 0 or declared_size > limit:
            return await reject(413, "Request exceeds the size limit")
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                return await reject(413, "Request exceeds the size limit")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (key.encode("ascii"), value.encode("ascii")) for key, value in SECURITY_HEADERS.items()
                ]
            await send(message)

        await self.app(scope, bounded_receive, secure_send)
