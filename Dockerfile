FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

ARG VERSION=dev
ENV MCP_SERVER_VERSION=${VERSION}
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV PATH=/app/.venv/bin:$PATH

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY cashew_mcp_server.py app.py auth_gate.py ./

# /data: the Cashew backup, mounted read-only. /state: login state, the only writable path.
RUN useradd --create-home --uid 10001 appuser && mkdir -p /data /state && chown appuser:appuser /state
USER appuser
ENV CASHEW_DB_PATH=/data/cashew.sqlite FASTMCP_HOME=/state PORT=8000

# Declared so /state stays writable under a read-only root filesystem even with no volume mounted
VOLUME ["/state"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app:create_app --factory --host 0.0.0.0 --port ${PORT}"]
