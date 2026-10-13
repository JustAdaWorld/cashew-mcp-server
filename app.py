"""HTTP entry point: GitHub login in front, read-only Cashew DB behind.

    uvicorn app:create_app --factory --host 0.0.0.0 --port 8000

stdio (local Claude Desktop) is unchanged: `uv run python cashew_mcp_server.py`.
"""

import os
import sqlite3
from contextlib import closing
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse

import cashew_mcp_server as server
from auth_gate import build_github_gate, parse_allowlist

VERSION = os.getenv("MCP_SERVER_VERSION", "dev")
REQUIRED = (
    "CASHEW_DB_PATH",
    "MCP_BASE_URL",
    "MCP_GITHUB_CLIENT_ID",
    "MCP_GITHUB_CLIENT_SECRET",
    "MCP_ALLOWED_GITHUB_USERS",
)


def database_ready(path: str) -> bool:
    """True if the backup opens read-only and has at least one table."""
    try:
        with closing(
            sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        ) as conn:
            (tables,) = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()
        return tables > 0
    except sqlite3.Error:
        return False


def create_app():
    # Fail closed: there is no way to serve HTTP without a login.
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:
        raise SystemExit("Refusing to serve HTTP. Missing: " + ", ".join(missing))

    db_path = os.environ["CASHEW_DB_PATH"]
    server.init_database(db_path)

    base_url = os.environ["MCP_BASE_URL"].rstrip("/")
    server.mcp.auth = build_github_gate(
        client_id=os.environ["MCP_GITHUB_CLIENT_ID"],
        client_secret=os.environ["MCP_GITHUB_CLIENT_SECRET"],
        base_url=base_url,
        allowed=parse_allowlist(os.environ["MCP_ALLOWED_GITHUB_USERS"]),
    )

    @server.mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        """Unauthenticated. Reports ok/error and the version, nothing from the data."""
        if database_ready(db_path):
            return JSONResponse({"status": "ok", "version": VERSION})
        return JSONResponse({"status": "error", "version": VERSION}, status_code=503)

    return server.mcp.http_app(path="/mcp", allowed_hosts=[urlparse(base_url).netloc])
