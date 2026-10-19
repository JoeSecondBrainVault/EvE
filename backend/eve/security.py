"""Local API protection.

Threats addressed (see implementation plan STRIDE table):
* Other websites in your browser calling http://127.0.0.1 (CSRF) -> Origin allowlist.
* DNS-rebinding attacks that make a remote hostname resolve to 127.0.0.1 -> Host allowlist.
* Other local processes / users reading transcripts -> per-install bearer token.
"""

from __future__ import annotations

import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

TOKEN_FILENAME = "api_token"


def load_or_create_token(data_dir: Path) -> str:
    """Return the per-install API token, creating it on first run."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / TOKEN_FILENAME
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    return token


def token_matches(expected: str, provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(expected.encode(), provided.encode())


def require_token(request: Request) -> None:
    """FastAPI dependency: enforce ``Authorization: Bearer <token>`` or ?token=<token> for audio playback."""
    provided: str | None = None
    header = request.headers.get("authorization", "")
    if header:
        scheme, _, bearer_val = header.partition(" ")
        if scheme.lower() == "bearer":
            provided = bearer_val.strip()
    if not provided:
        # Fallback to query param ONLY for HTML5 audio streaming where custom headers cannot be set
        path = request.url.path
        if path.startswith("/api/sessions/") and "/audio/" in path:
            provided = request.query_params.get("token")

    if not provided or not token_matches(request.app.state.api_token, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def allowed_hosts(port: int) -> set[str]:
    names = ("127.0.0.1", "localhost", "[::1]")
    return {f"{n}:{port}" for n in names} | set(names)


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Host or Origin is not a known-local value."""

    def __init__(self, app, *, port: int, origins: list[str]) -> None:
        super().__init__(app)
        self._hosts = allowed_hosts(port) | {"testserver"}
        self._origins = set(origins) | {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        if host not in self._hosts:
            return JSONResponse({"detail": "Host not allowed"}, status_code=400)
        origin = request.headers.get("origin")
        if origin is not None and origin not in self._origins:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)


def websocket_origin_ok(origin: str | None, port: int, origins: list[str]) -> bool:
    """WebSockets bypass CORS, so the Origin must be checked by hand."""
    if origin is None:  # non-browser clients (CLI) send no Origin
        return True
    return origin in set(origins) | {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
