"""listonic-mcp — unofficial Listonic (grocery list) MCP server.

Tools:
  get_lists    — all your shopping lists with their ids
  get_items    — items on a list (checked = already have, unchecked = to buy)
  add_items    — add one or many items
  edit_items   — check/uncheck/rename/re-quantity items
  delete_items — remove items entirely

Config comes from launch params — pass --email and --password in the server's
"args", or set LISTONIC_EMAIL / LISTONIC_PASSWORD env vars. Optional --list-id
(LISTONIC_LIST_ID) pins a default list; otherwise the first list on the account
is used. No .env needed.

Transports:
  stdio (default)  — for local MCP clients that launch the process themselves.
  http             — Streamable HTTP at /mcp for remote hosting (e.g. Render),
                     selected with --transport http or MCP_TRANSPORT=http. Binds
                     to HOST (default 0.0.0.0) and PORT (default 8000), serves an
                     unauthenticated GET /health, and requires MCP_AUTH_TOKEN
                     (Authorization: Bearer, X-API-Key or X-MCP-API-Key) for
                     everything else (see README → "Remote deployment").

Unofficial: not affiliated with Listonic. The API is reverse-engineered from
their web app (see API.md) — the embedded client id/secret below are the web
app's own public ones, not personal credentials.

It's a small, single-purpose server — feel free to edit anything.
"""

import argparse
import base64
import hmac
import logging
import os
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import requests
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

try:
    __version__ = _pkg_version("listonic-mcp")
except PackageNotFoundError:  # running from a source checkout, not installed
    __version__ = "0.0.0-dev"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("listonic_mcp")

API_BASE = "https://api.listonic.com/api"
# Listonic's own web-app client credentials (embedded in their public JS bundle,
# shared by every web user) — NOT a personal secret. See API.md.
CLIENT_ID = "listonicv2"
CLIENT_SECRET = "fjdfsoj9874jdfhjkh34jkhffdfff"

SERVER_INSTRUCTIONS = """\
This server manages the user's real grocery lists on Listonic (a shopping-list app).

Reading a list: checked items ([x]) are things the user most likely already HAS at
home; unchecked items ([ ]) still need to be bought. Keep that in mind when meal
planning or answering "what do I need?".

Habits that make you useful here:
- Batch your changes: add_items / edit_items / delete_items all take lists — one
  call for the whole recipe, not one call per ingredient.
- Before editing or deleting, call get_items to grab current ItemIDs.
- When the user plans meals, offer to put the missing ingredients straight on the
  list — that's the whole point of having hands.
"""

mcp = FastMCP("listonic", instructions=SERVER_INSTRUCTIONS)


class ListonicClient:
    """Thin wrapper around the reverse-engineered Listonic API: password login,
    bearer-token auth with one automatic re-login on 401 (tokens expire ~24h)."""

    def __init__(self, email: str, password: str, list_id: str | None = None):
        self.email = email
        self.password = password
        self._pinned_list_id = list_id or None
        self._default_list_id: str | None = None
        self._token: str | None = None

    def _login(self) -> str:
        b64 = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        resp = requests.post(
            f"{API_BASE}/loginextended?provider=password&autoMerge=1&autoDestruct=1",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "clientauthorization": f"Bearer {b64}",
            },
            data={
                "username": self.email,
                "password": self.password,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": "https://listonicv2api.jestemkucharzem.pl",
            },
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Listonic login response carried no access_token.")
        self._token = token
        return token

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Authenticated request; on 401 (expired token) re-logins once and retries."""
        token = self._token or self._login()
        resp = requests.request(
            method, f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"}, timeout=10, **kwargs,
        )
        if resp.status_code == 401:
            token = self._login()
            resp = requests.request(
                method, f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"}, timeout=10, **kwargs,
            )
        resp.raise_for_status()
        return resp

    def lists(self) -> list[dict]:
        resp = self.request("GET", "/lists?includeShares=false&archive=false&includeItems=false")
        return resp.json() or []

    def default_list_id(self) -> str:
        """The pinned --list-id if given, else the account's first list."""
        if self._pinned_list_id:
            return self._pinned_list_id
        if self._default_list_id is None:
            all_lists = self.lists()
            if not all_lists:
                raise RuntimeError("No lists on this Listonic account — create one in the app first.")
            self._default_list_id = str(all_lists[0].get("Id"))
        return self._default_list_id


# Built in main() from the launch params, so importing this module never needs
# credentials — required for registry introspection and the console entry point.
client: ListonicClient | None = None

_NO_CREDS = (
    "listonic-mcp was started without credentials — restart it with --email and "
    "--password (or set LISTONIC_EMAIL / LISTONIC_PASSWORD). These are your normal "
    "Listonic account login details."
)


def _fmt_items(items: list[dict]) -> str:
    if not items:
        return "The list is currently empty."
    out = []
    for item in items:
        checked = "[x]" if str(item.get("Checked")) == "1" else "[ ]"
        amount = item.get("Amount", "")
        unit = item.get("Unit", "")
        out.append(
            f"{checked} (ItemID: {item.get('Id', '')}) {amount} {unit} {item.get('Name', '')}".strip()
        )
    return "\n".join(out)


@mcp.tool()
def get_lists() -> str:
    """All shopping lists on the account, with their ListIDs.

    Use when the user has several lists ("weekend BBQ", "pharmacy") — every other
    tool takes an optional list_id to target one; without it they use the default
    list (the pinned --list-id, or the account's first list).
    """
    if client is None:
        return _NO_CREDS
    all_lists = client.lists()
    if not all_lists:
        return "No lists on this account — create one in the Listonic app first."
    default = client.default_list_id()
    return "\n".join(
        f"(ListID: {l.get('Id')}) {l.get('Name', '?')}"
        + ("  ← default" if str(l.get("Id")) == default else "")
        for l in all_lists
    )


@mcp.tool()
def get_items(list_id: str = "") -> str:
    """Fetch the grocery list. Call this FIRST before editing/deleting, to get ItemIDs.

    Checked items ([x]) = the user most likely already HAS them at home.
    Unchecked items ([ ]) = still to buy.

    Args:
        list_id: which list (from get_lists). Empty = the default list.
    """
    if client is None:
        return _NO_CREDS
    lid = list_id.strip() or client.default_list_id()
    items = client.request("GET", f"/lists/{lid}/items").json()
    return _fmt_items(items)


class AddItemParams(BaseModel):
    name: str = Field(description="The name of the item to add")
    quantity: str = Field(default="1", description="The quantity of the item")
    unit: str = Field(default="", description="The unit (e.g. 'kg', 'liters', 'pieces')")


@mcp.tool()
def add_items(items: list[AddItemParams], list_id: str = "") -> str:
    """Add one or MANY items in a single call — batch whole recipes, don't loop.

    Args:
        items: the items to add.
        list_id: which list (from get_lists). Empty = the default list.
    """
    if client is None:
        return _NO_CREDS
    lid = list_id.strip() or client.default_list_id()
    results = []
    for item in items:
        if not item.name:
            results.append("Failed: missing 'name'.")
            continue
        try:
            client.request(
                "POST", f"/lists/{lid}/items",
                json={"name": item.name, "quantity": item.quantity, "unit": item.unit},
            )
            results.append(f"Added '{item.name}'.")
        except requests.exceptions.RequestException as e:
            results.append(f"Failed to add '{item.name}': {e}")
    return "\n".join(results)


class EditItemParams(BaseModel):
    item_id: str = Field(description="The ItemID to edit (from get_items)")
    is_checked: bool | None = Field(
        default=None, description="true = check off (user has it), false = uncheck"
    )
    name: str | None = Field(default=None, description="New name for the item")
    quantity: str | None = Field(default=None, description="New quantity")


@mcp.tool()
def edit_items(items: list[EditItemParams], list_id: str = "") -> str:
    """Edit one or MANY items in a single call — most often to check/uncheck while
    shopping ("got the milk").

    Args:
        items: edits to apply; only the fields you set are changed.
        list_id: which list (from get_lists). Empty = the default list.
    """
    if client is None:
        return _NO_CREDS
    lid = list_id.strip() or client.default_list_id()
    results = []
    for item in items:
        if not item.item_id:
            results.append("Failed: missing 'item_id'.")
            continue
        data = {}
        if item.is_checked is not None:
            data["isChecked"] = item.is_checked
        if item.name is not None:
            data["name"] = item.name
        if item.quantity is not None:
            data["quantity"] = item.quantity
        if not data:
            results.append(f"No changes given for item {item.item_id}.")
            continue
        try:
            client.request("PATCH", f"/lists/{lid}/items/{item.item_id}", json=data)
            results.append(f"Updated item {item.item_id}.")
        except requests.exceptions.RequestException as e:
            results.append(f"Failed to update item {item.item_id}: {e}")
    return "\n".join(results)


@mcp.tool()
def delete_items(item_ids: list[str], list_id: str = "") -> str:
    """Delete items entirely (not check off — that's edit_items with is_checked).

    Args:
        item_ids: ItemIDs to delete (from get_items).
        list_id: which list (from get_lists). Empty = the default list.
    """
    if client is None:
        return _NO_CREDS
    lid = list_id.strip() or client.default_list_id()
    results = []
    for item_id in item_ids:
        try:
            client.request("DELETE", f"/lists/{lid}/items/{item_id}")
            results.append(f"Deleted item {item_id}.")
        except requests.exceptions.RequestException as e:
            results.append(f"Failed to delete item {item_id}: {e}")
    return "\n".join(results)



# --------------------------------------------------------------------------- #
# Remote (Streamable HTTP) mode
# --------------------------------------------------------------------------- #

MCP_PATH = "/mcp"
HEALTH_PATH = "/health"
MIN_TOKEN_LENGTH = 32


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _mask_email(email: str) -> str:
    """'someone@example.com' -> 'so***@example.com' — keeps logs useful, not revealing."""
    name, _, domain = email.partition("@")
    return f"{name[:2]}***@{domain}" if domain else "***"


class AuthMiddleware:
    """Pure-ASGI guard in front of the MCP app.

    - ``GET /health`` is public (no Listonic access, no data).
    - OAuth discovery paths (``/.well-known/oauth-*``, ``openid-configuration``)
      answer a public ``404``: this server has no OAuth authorization server, and
      a 404 is the standard "no metadata here" signal. They expose nothing.
    - Everything else needs the shared secret ``MCP_AUTH_TOKEN`` in one of:
        ``Authorization: Bearer <token>``  (original method, unchanged)
        ``X-API-Key: <token>``             (claude.ai "Request headers" — a
                                            standard name the dialog accepts)
        ``X-MCP-API-Key: <token>``         (custom name for other clients)
      The API-key headers carry the raw token, without a ``Bearer`` prefix.
    - Optionally (``MCP_ALLOW_PATH_TOKEN=true``) ``/mcp/<MCP_AUTH_TOKEN>`` is also
      accepted, for MCP clients that cannot send custom headers. The token is
      stripped from the path before the request reaches the MCP app.

    Tokens are compared in constant time and never logged. On a 401 the log
    line lists only the *names* of credential headers that arrived (never their
    values), so you can tell "client sent no header" from "header had a wrong value".
    """

    def __init__(self, app, token: str, allow_path_token: bool = False):
        self.app = app
        self._token = token.encode()
        self._allow_path_token = allow_path_token

    def _matches(self, candidate: str) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self._token)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan etc. pass straight through
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        log_path = path
        log_note = ""
        status_holder = {"status": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            if path == HEALTH_PATH:
                await self.app(scope, receive, send_wrapper)
                return

            if self._allow_path_token and path.startswith(MCP_PATH + "/"):
                log_path = MCP_PATH + "/<redacted>"
                if self._matches(path[len(MCP_PATH) + 1:].rstrip("/")):
                    scope = dict(scope, path=MCP_PATH, raw_path=MCP_PATH.encode())
                    await self.app(scope, receive, send_wrapper)
                else:
                    await _plain(send_wrapper, 404, b"Not Found")
                return

            if _is_oauth_discovery(path):
                # No OAuth here. Public 404 (not 401) so clients stop looking for
                # an authorization server instead of treating discovery as "locked".
                await _plain(send_wrapper, 404, b"Not Found")
                return

            presented = _credential_headers(scope)
            if any(self._matches(c) for _, c in presented):
                await self.app(scope, receive, send_wrapper)
            else:
                log_note = " (credential headers: %s)" % (
                    ", ".join(sorted({n for n, _ in presented})) or "none")
                await _plain(
                    send_wrapper, 401, b"Unauthorized",
                    extra_headers=[(b"www-authenticate", b'Bearer realm="listonic-mcp"')],
                )
        finally:
            logger.info("%s %s -> %s%s", scope.get("method", "?"), log_path,
                        status_holder["status"], log_note)


API_KEY_HEADERS = (b"x-api-key", b"x-mcp-api-key")
OAUTH_DISCOVERY_PREFIXES = (
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-authorization-server",
    "/.well-known/openid-configuration",
)


def _is_oauth_discovery(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in OAUTH_DISCOVERY_PREFIXES)


def _credential_headers(scope) -> list[tuple[str, str]]:
    """(header name, candidate token) for every credential header on the request.

    ``Authorization`` counts only with the ``Bearer`` scheme; API-key headers carry
    the raw token. Values are only ever compared, never logged.
    """
    found: list[tuple[str, str]] = []
    for key, value in scope.get("headers", []):
        key = key.lower()
        if key == b"authorization":
            scheme, _, credential = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and credential.strip():
                found.append(("authorization", credential.strip()))
            else:
                found.append(("authorization(non-bearer)", ""))
        elif key in API_KEY_HEADERS:
            credential = value.decode("latin-1").strip()
            found.append((key.decode(), credential))
    return found


async def _plain(send, status: int, body: bytes, extra_headers=None) -> None:
    headers = [(b"content-type", b"text/plain; charset=utf-8"),
               (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status,
                "headers": headers + (extra_headers or [])})
    await send({"type": "http.response.body", "body": body})


def build_http_app(auth_token: str, allow_path_token: bool = False):
    """The Streamable HTTP ASGI app: MCP at /mcp, /health, wrapped in AuthMiddleware."""
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    # Stateless + plain-JSON responses: no server-side session to lose when the
    # Render Free instance spins down/restarts, and no long-lived SSE streams.
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.streamable_http_path = MCP_PATH
    # FastMCP's DNS-rebinding guard only allows localhost Host headers by default,
    # which would reject *.onrender.com. That guard protects unauthenticated local
    # servers; here every MCP request must carry the bearer token instead.
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )

    async def health(_request):
        return JSONResponse({"status": "ok", "listonic_configured": client is not None})

    # A session manager can only run once; start fresh so the builder is reusable
    # (tests build several apps in one process).
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    app.router.routes.append(Route(HEALTH_PATH, health, methods=["GET", "HEAD"]))
    return AuthMiddleware(app, auth_token, allow_path_token)


def _run_http(host: str, port: int) -> None:
    import uvicorn

    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if len(token) < MIN_TOKEN_LENGTH:
        sys.exit(
            f"listonic-mcp: refusing to start HTTP transport — set MCP_AUTH_TOKEN to a random "
            f"secret of at least {MIN_TOKEN_LENGTH} characters (e.g. `openssl rand -hex 32`)."
        )
    allow_path_token = _truthy(os.environ.get("MCP_ALLOW_PATH_TOKEN"))
    app = build_http_app(token, allow_path_token)
    print(
        f"listonic-mcp · Streamable HTTP on {host}:{port}{MCP_PATH} · auth: bearer / x-api-key / x-mcp-api-key"
        + (" + secret path" if allow_path_token else ""),
        file=sys.stderr,
    )
    # access_log off: our middleware logs method/path/status with the token redacted.
    uvicorn.run(
        app, host=host, port=port, access_log=False, log_level="info",
        proxy_headers=True, forwarded_allow_ips="*",
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="listonic-mcp", description="Unofficial Listonic (grocery list) MCP server."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--email", default=os.environ.get("LISTONIC_EMAIL"),
        help="Listonic account email. Falls back to the LISTONIC_EMAIL env var.",
    )
    p.add_argument(
        "--password", default=os.environ.get("LISTONIC_PASSWORD"),
        help="Listonic account password. Falls back to LISTONIC_PASSWORD.",
    )
    p.add_argument(
        "--list-id", default=os.environ.get("LISTONIC_LIST_ID", ""),
        help="Pin a default list id (see get_lists). Falls back to LISTONIC_LIST_ID; "
             "empty = the account's first list.",
    )
    p.add_argument(
        "--transport", choices=["stdio", "http"],
        default=(os.environ.get("MCP_TRANSPORT") or "stdio").strip().lower(),
        help="stdio (local clients, default) or http (Streamable HTTP at /mcp). "
             "Falls back to MCP_TRANSPORT.",
    )
    p.add_argument(
        "--host", default=os.environ.get("HOST", "0.0.0.0"),
        help="HTTP bind address (http transport). Falls back to HOST; default 0.0.0.0.",
    )
    p.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT") or 8000),
        help="HTTP port (http transport). Falls back to PORT (set by Render); default 8000.",
    )
    args, _ = p.parse_known_args()
    return args


def main() -> None:
    """Console entry point (``listonic-mcp``) and ``python server.py`` launcher."""
    global client
    args = _parse_args()
    if args.email and args.password:
        client = ListonicClient(args.email, args.password, args.list_id)
        status = f"account {_mask_email(args.email)}" + (
            f", pinned list {args.list_id}" if args.list_id else ", default = first list"
        )
    else:
        status = "no credentials — tools will report this until restarted with --email/--password"
    print(f"listonic-mcp · {status}", file=sys.stderr)
    if args.transport == "http":
        _run_http(args.host, args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
