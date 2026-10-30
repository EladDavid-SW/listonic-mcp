# listonic-mcp

<!-- mcp-name: io.github.ArturLys/listonic-mcp -->

[![PyPI](https://img.shields.io/pypi/v/listonic-mcp)](https://pypi.org/project/listonic-mcp/)
[![CI](https://github.com/ArturLys/listonic-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ArturLys/listonic-mcp/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

An [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server that gives AI agents — Claude, Cursor, or any MCP client — hands on your real [Listonic](https://listonic.com/) grocery list. Read it, add to it, check things off, across every device Listonic syncs to.

The obvious win: **meal planning that ends in a shopping list.** Ask your agent to plan the week's dinners, and the missing ingredients land straight on the list on your phone — quantities and all. Or paste a recipe and say "add what I don't have": the server tells the agent which items are checked (already at home) and which aren't.

```
You:   plan me 3 cheap high-protein dinners and put the ingredients on my list
Agent: [reads your list — sees you already have rice, eggs, frozen spinach]
       [adds: 1 kg chicken thighs, 400 g lentils, greek yogurt ×2, ...]
```

> **Unofficial.** Not affiliated with Listonic. Built on their web app's API (reverse-engineered — fully documented in [API.md](API.md)). It may break if Listonic changes their API.

## Install

Requires **Python 3.10+** and a Listonic account (free):

```bash
pip install listonic-mcp
```

## Add to your agent

Point `command` at `listonic-mcp` and pass your Listonic login:

```json
{
  "mcpServers": {
    "listonic": {
      "command": "listonic-mcp",
      "env": {
        "LISTONIC_EMAIL": "you@example.com",
        "LISTONIC_PASSWORD": "your-listonic-password"
      }
    }
  }
}
```

The same values can be passed as `--email` / `--password` args instead — whichever your client makes easier.

<details>
<summary>Claude Code</summary>

```bash
claude mcp add listonic -e LISTONIC_EMAIL=you@example.com -e LISTONIC_PASSWORD=your-password -- listonic-mcp
```

</details>

<details>
<summary>Cursor</summary>

`Cursor Settings` → `MCP` → `New MCP Server`, paste the JSON config above.

</details>

<details>
<summary>Google Antigravity</summary>

Add the JSON config above to `.gemini/antigravity/mcp_config.json`.

</details>

Then just ask:

```
What's on my grocery list? Check off the milk, I just bought it.
```

### Launch params

| Param        | Env var             | Default        | What it does                                        |
| ------------ | ------------------- | -------------- | --------------------------------------------------- |
| `--email`    | `LISTONIC_EMAIL`    | —              | Listonic account email (required).                  |
| `--password` | `LISTONIC_PASSWORD` | —              | Listonic account password (required).               |
| `--list-id`  | `LISTONIC_LIST_ID`  | first list     | Pin a default list; see `get_lists` for the ids.    |

### Remote-mode settings (HTTP transport)

| Param         | Env var                | Default    | What it does                                                          |
| ------------- | ---------------------- | ---------- | --------------------------------------------------------------------- |
| `--transport` | `MCP_TRANSPORT`        | `stdio`    | `stdio` for local clients, `http` for Streamable HTTP at `/mcp`. The Docker image sets `http`. |
| `--host`      | `HOST`                 | `0.0.0.0`  | Bind address.                                                         |
| `--port`      | `PORT`                 | `8000`     | Listen port. Render injects `PORT` automatically.                     |
| —             | `MCP_AUTH_TOKEN`       | —          | **Required for `http`.** Shared secret (≥ 32 chars) clients send as `Authorization: Bearer …`, `X-API-Key: …` or `X-MCP-API-Key: …`. The server refuses to start without it. |
| —             | `MCP_ALLOW_PATH_TOKEN` | `false`    | `true` also accepts `/mcp/<MCP_AUTH_TOKEN>` for clients that can't send headers. See [Authentication](#authentication). |

## Remote deployment (Render Free, Docker)

Runs the server 24/7-ish in the cloud, independent of your computer, on Render's **Free** web service ($0/month). No database or disk needed — the only state is an in-memory Listonic session token that is re-created automatically.

### 1. Generate the MCP auth token (on your computer)

```bash
openssl rand -hex 32
# or: python3 -c "import secrets; print(secrets.token_hex(32))"
```

Keep it in your password manager. You'll paste it into Render (step 2) and into your MCP client (step 4) — **never** into GitHub, an issue, or a commit.

### 2. Configure the Render web service

In the Render dashboard → your new **Web Service** for this repo:

| Setting              | Value                                    |
| -------------------- | ---------------------------------------- |
| Language / Runtime   | **Docker**                               |
| Branch               | `main` (after merging this PR)           |
| Root Directory       | *(empty)*                                |
| Dockerfile Path      | `./Dockerfile`                           |
| Docker Command       | *(empty — the image's entrypoint is used)* |
| Instance Type        | **Free**                                 |
| Health Check Path    | `/health` (under *Advanced*)             |

**Environment** → add these variables (Render stores them encrypted; they never touch the repo):

| Key                    | Value                                   | Required |
| ---------------------- | --------------------------------------- | -------- |
| `MCP_AUTH_TOKEN`       | the token from step 1                   | yes      |
| `LISTONIC_EMAIL`       | your Listonic login email               | yes      |
| `LISTONIC_PASSWORD`    | your Listonic password                  | yes      |
| `LISTONIC_LIST_ID`     | a list id to use by default             | no       |
| `MCP_ALLOW_PATH_TOKEN` | `true` only if your client needs it     | no       |

Don't set `PORT` — Render provides it. `MCP_TRANSPORT=http` is already the image default.

Then click **Deploy Web Service**. Alternatively, deploy via **New → Blueprint** and Render reads [`render.yaml`](render.yaml) (Free plan, Docker, `/health` check) and prompts for the secret values.

> Sign-in note: Listonic accounts created with Google/Facebook sign-in have no password. Set one in the Listonic app (or use an email/password account) — the server only supports the email + password login the original project implements.

### 3. Verify

Your MCP URL is:

```
https://<your-service-name>.onrender.com/mcp
```

(Render shows the exact `onrender.com` hostname at the top of the service page.)

```bash
export MCP_URL=https://<your-service-name>.onrender.com
export MCP_AUTH_TOKEN=<token from step 1>   # in your shell only

# Health — public, touches nothing:
curl -s $MCP_URL/health
# → {"status":"ok","listonic_configured":true}

# Without a token → 401:
curl -s -o /dev/null -w '%{http_code}\n' -X POST $MCP_URL/mcp

# MCP handshake:
curl -s -X POST $MCP_URL/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

# Same handshake with the API-key header claude.ai uses (raw token, no "Bearer") → 200:
curl -s -o /dev/null -w '%{http_code}\n' -X POST $MCP_URL/mcp \
  -H "x-api-key: $MCP_AUTH_TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

# OAuth discovery → 404 (no OAuth server; public, exposes nothing):
curl -s -o /dev/null -w '%{http_code}\n' $MCP_URL/.well-known/oauth-protected-resource

# Read your lists (live Listonic call):
curl -s -X POST $MCP_URL/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_lists","arguments":{}}}'
```

Write test (adds an item, then you can check it off and delete it the same way with `get_items` → `edit_items` → `delete_items`):

```bash
curl -s -X POST $MCP_URL/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add_items","arguments":{"items":[{"name":"MCP test item","quantity":"1"}]}}}'
```

Interactive alternative: `npx @modelcontextprotocol/inspector` → Transport **Streamable HTTP**, URL `$MCP_URL/mcp`, add header `Authorization: Bearer <token>`.

### 4. Connect a client

**Claude Code**

```bash
claude mcp add --transport http listonic https://<your-service-name>.onrender.com/mcp \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

**Cursor / clients with a JSON config that support remote URLs + headers**

```json
{
  "mcpServers": {
    "listonic": {
      "url": "https://<your-service-name>.onrender.com/mcp",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
    }
  }
}
```

**Claude Desktop (stdio-only config) via `mcp-remote`**

```json
{
  "mcpServers": {
    "listonic": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<your-service-name>.onrender.com/mcp",
               "--header", "Authorization:Bearer ${MCP_AUTH_TOKEN}"],
      "env": { "MCP_AUTH_TOKEN": "<MCP_AUTH_TOKEN>" }
    }
  }
}
```

**claude.ai custom connector (request header, recommended)**

*Customize → Connectors → Add custom connector*, then:

| Field | Value |
|---|---|
| URL | `https://<your-service-name>.onrender.com/mcp` (no token in the URL) |
| Authentication | **No sign-in** |
| Request header name | `x-api-key` |
| Request header value | your `MCP_AUTH_TOKEN` — the raw token, **without** a `Bearer ` prefix |

Notes:

- Request headers are a **beta** feature of the claude.ai connector dialog (only shown to some organizations, set by an Owner). If you don't see a **Request headers** section, your account can't send static headers yet — use Claude Code / `mcp-remote` above, or the opt-in secret-path mode below.
- Claude documents `authorization`, `x-api-key` and `x-auth-token` as accepted header names; other names need Anthropic's approval before the dialog saves them. That's why `x-api-key` is the recommended name here. The server also accepts `X-MCP-API-Key` (raw token) for clients that let you choose any name, and `Authorization: Bearer <token>` as before.
- The server answers OAuth discovery (`/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`, `/.well-known/openid-configuration`) with a public `404`: there is no OAuth server, and nothing is exposed there.

**Troubleshooting claude.ai.** Watch the Render logs while you click *Connect*. Every rejected request logs the *names* (never values) of credential headers that arrived:

- `POST /mcp -> 401 (credential headers: none)` — claude.ai did not deliver the header. Re-check that the connector uses *No sign-in* and that the header was saved; if it still arrives empty, it's on the claude.ai side (see [anthropics/claude-ai-mcp#644](https://github.com/anthropics/claude-ai-mcp/issues/644)), not the server — test the server itself with `curl -H "x-api-key: $MCP_AUTH_TOKEN" …` as in step 3.
- `POST /mcp -> 401 (credential headers: x-api-key)` — the header arrived but the value is wrong (extra `Bearer ` prefix, whitespace, or an old token).
- `GET /.well-known/oauth-… -> 404` — expected: Claude probing for OAuth and finding none.

**ChatGPT** — see [ChatGPT limitations](#chatgpt-limitations).

### Authentication

- Every request except `GET /health` (and the OAuth discovery `404`s) needs the token in one of these headers; anything else gets `401`. Tokens are compared in constant time.
  - `Authorization: Bearer <MCP_AUTH_TOKEN>`
  - `X-API-Key: <MCP_AUTH_TOKEN>` (raw token, no `Bearer`) — use this for claude.ai
  - `X-MCP-API-Key: <MCP_AUTH_TOKEN>` (raw token, no `Bearer`)
- OAuth discovery paths return a public `404` with no body beyond `Not Found` — there is no OAuth, so clients are told so instead of getting a `401` that looks like a locked authorization server.
- The server **refuses to start** in HTTP mode if `MCP_AUTH_TOKEN` is missing or shorter than 32 characters, so the endpoint is never exposed unauthenticated.
- Logs show method, path and status only (plus, on a `401`, the *names* of credential headers that arrived). Passwords, Listonic session tokens and the MCP token are never logged (the Listonic email is masked, uvicorn's access log is off).
- **Secret-path mode (opt-in):** some clients (ChatGPT, claude.ai without request headers) can only do OAuth or "no auth". For those, set `MCP_ALLOW_PATH_TOKEN=true` and use `https://<host>/mcp/<MCP_AUTH_TOKEN>` as the URL. Trade-off: the URL itself becomes the credential — anyone who sees it (screenshots, shared configs, client-side history) can manage your list. Wrong paths return `404`. Only enable it if you need it.
- **Rotate** the token by changing `MCP_AUTH_TOKEN` in Render (it redeploys) and updating your clients.
- Full OAuth 2.1 is not implemented — intentionally, to keep this single-user server simple.

### Render Free limitations

- **Spin-down:** a Free web service spins down after 15 minutes without inbound traffic. The next request wakes it, which takes about a minute; the first MCP call after idle may time out in some clients — just retry (or open `/health` first to wake it).
- **750 free instance hours** per workspace per month (spun-down time doesn't count). If they run out, Free services are suspended until the next month.
- 512 MB RAM / shared CPU — this server idles at roughly 60 MB.
- No persistent disk — not needed; the Listonic token is re-obtained after each cold start.
- Render may restart Free services at any time; the server is stateless (`stateless_http`), so clients simply reconnect.
- Don't set up an external "keep-alive" pinger — it burns instance hours and Render may suspend services with unusual traffic.

### ChatGPT limitations

- ChatGPT connects to remote MCP servers via **Developer Mode** / Apps, which depends on your plan and workspace settings (write actions may be limited to some plans).
- ChatGPT's connector UI offers **OAuth** or **No authentication** — it can't send a static `Authorization` header. Use the opt-in secret-path mode (`MCP_ALLOW_PATH_TOKEN=true`, URL `https://<host>/mcp/<token>`, auth = *No authentication*) and accept the trade-off above.
- Render's cold start can make ChatGPT report the connector as unavailable on first use; retry after the service wakes (open `/health` in a browser to wake it).

### Unofficial API caveats

The Listonic API is reverse-engineered from their web app ([API.md](API.md)). It can change or rate-limit without notice; logins from a cloud IP could trigger extra security checks on your account. The embedded `client_id`/`client_secret` are Listonic's public web-app values, not secrets.

### Local testing of the HTTP mode

```bash
pip install -e ".[test]"
pytest -q                                   # offline tests: /health, auth, MCP handshake, tools/list
cp .env.example .env                        # fill in real values locally; .env is git-ignored
docker build -t listonic-mcp .
docker run --rm -p 8000:8000 --env-file .env listonic-mcp
curl -s localhost:8000/health
```

## Tools

| Tool           | What it does                                                              |
| -------------- | ------------------------------------------------------------------------- |
| `get_lists`    | All your shopping lists with their ids.                                    |
| `get_items`    | Items on a list — checked (already have) vs unchecked (to buy).            |
| `add_items`    | Add one or many items in a single call (name, quantity, unit).             |
| `edit_items`   | Check/uncheck, rename, or re-quantity items — batched.                     |
| `delete_items` | Remove items entirely.                                                     |

Every tool takes an optional `list_id`, so multiple lists ("weekend BBQ", "pharmacy") work naturally.

## Good to know

- **Your password goes to Listonic only.** The server logs in against `api.listonic.com` directly and talks to nothing else — no telemetry, nothing stored beyond an in-memory session token (auto-refreshed when it expires). In remote mode the password lives only in your host's encrypted environment variables.
- The client id/secret in the source are Listonic's own web-app credentials, embedded in their public JS bundle and shared by every web user — they are not personal secrets.
- The full reverse-engineered API is documented in [API.md](API.md) — lists, items, categories, account endpoints — if you want to extend the server.

## Make it yours

A single readable file with no framework magic. Fork it and edit anything — add price tracking, category sorting, a recipe parser. Run from source:

```bash
git clone https://github.com/ArturLys/listonic-mcp.git
cd listonic-mcp
pip install -e .
listonic-mcp --email you@example.com --password your-password
```

## Credits

- [Listonic](https://listonic.com/) — the shopping list app this talks to. Go pay them for premium if you live off it.

## License

MIT
