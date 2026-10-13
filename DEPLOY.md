# Deploying the Cashew MCP server

Anyone with this file and the image can run the server on any Docker host.

## What it is

A **read-only** analysis server over a [Cashew](https://cashewapp.web.app/) expense-tracker backup, spoken over MCP Streamable HTTP at `/mcp`, behind a GitHub login.

- Tools: `execute_sql_query`, `get_table_sample`, `get_table_count`
- Resources: `cashew://schema`, `cashew://schema/{table_name}`
- Prompts: `analyze_spending_patterns`, `budget_analysis`, `income_vs_expenses`, `expense_anomaly_detection`

## Image

| | |
|---|---|
| Image | `ghcr.io/justadaworld/cashew-mcp-server` |
| Current tag | `0.2.0` |
| Digest | _recorded here after the `v0.2.0` release_ |
| Built by | `.github/workflows/release.yml` on a `vX.Y.Z` tag, after `scripts/smoke-test.sh` passes |
| Base | `python:3.13-slim`, runs as uid 10001 |

Always deploy a pinned tag or `@sha256` digest. Never `:latest`, and no auto-update.

## Configuration

Set in `.env` next to `compose.yml` (`chmod 600 .env`). Template: `.env.example`.

| Variable | Required | Example | Meaning |
|---|---|---|---|
| `MCP_BASE_URL` | yes | `https://cashew.lilrkt.net` | Public URL, no trailing slash. Also the only accepted `Host` |
| `MCP_GITHUB_CLIENT_ID` | yes | `Ov23li...` | GitHub OAuth App client ID (not secret) |
| `MCP_GITHUB_CLIENT_SECRET` | yes | — | GitHub OAuth App client secret. Only ever in `.env` on the server |
| `MCP_ALLOWED_GITHUB_USERS` | yes | `justadaworld` | Comma-separated GitHub logins or numeric IDs allowed to sign in |
| `CASHEW_DB_PATH` | no | `/data/cashew.sqlite` | Default set in the image |

If any required variable is missing, the server refuses to start.

## Data

- `/data/cashew.sqlite` is the Cashew backup, mounted **read-only** from `./data/`.
- Cashew is a phone app, so there is no live sync. To refresh: export a backup in Cashew, then copy it to `./data/cashew.sqlite` on the host (never by email). Each query opens the file fresh, so no restart is needed.
- With no file, the container exits with `Database file not found` and restarts until one is in place.
- `/state` holds login state only. Losing it means signing in again.
- Data, state and logs are not backed up.

## Login

- A GitHub OAuth App owned by Ada. Homepage `https://<host>`, callback `https://<host>/auth/callback`.
- Only accounts in `MCP_ALLOWED_GITHUB_USERS` get in; the check runs on every request.
- For local testing, create a second OAuth App with callback `http://localhost:8100/auth/callback` and set `MCP_BASE_URL=http://localhost:8100` (GitHub allows one callback per app).

## Run it

```bash
mkdir -p data && cp /path/to/cashew-backup.sqlite data/cashew.sqlite
cp .env.example .env && chmod 600 .env   # then fill in .env
docker compose pull && docker compose up -d
```

`compose.yml` binds to `127.0.0.1:8100` only; route your tunnel or reverse proxy to it.

Then check:

```bash
curl -sS http://localhost:8100/health
# {"status":"ok","version":"0.2.0"}. A 503 means the backup is missing, corrupt or empty

curl -sS -o /dev/null -w '%{http_code}\n' -X POST -H "Host: <host>" http://localhost:8100/mcp
# 401. A 200 means there is no login: stop
```

OAuth metadata is at `/.well-known/oauth-protected-resource/mcp` (the bare path without `/mcp` is a 404 by design). Docker reports the container `unhealthy` whenever `/health` fails.

## Connect Claude

claude.ai → Settings → Connectors → Add custom connector → `https://<host>/mcp`. Sign in with GitHub, then try `get_table_count` on `transactions`.

## Update

Bump the pinned tag in `compose.yml`, then `docker compose pull && docker compose up -d`.

## Move it without a registry

```bash
docker save ghcr.io/justadaworld/cashew-mcp-server:<tag> | gzip > cashew-<tag>.tar.gz
gunzip -c cashew-<tag>.tar.gz | docker load   # on the new host
```

## Release a new version

Merge to `main`, then push a tag: `git tag v0.2.1 && git push origin v0.2.1`. The release workflow builds, smoke-tests, publishes to GHCR and creates a GitHub Release naming the digest.

## Known limits

- Read-only: it can analyse budgets, not change them.
- One database per deployment.
- Data is only as fresh as the last export.
