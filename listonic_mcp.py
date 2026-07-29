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

Unofficial: not affiliated with Listonic. The API is reverse-engineered from
their web app (see API.md) — the embedded client id/secret below are the web
app's own public ones, not personal credentials.

It's a small, single-purpose server — feel free to edit anything.
"""

import argparse
import base64
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
    args, _ = p.parse_known_args()
    return args


def main() -> None:
    """Console entry point (``listonic-mcp``) and ``python server.py`` launcher."""
    global client
    args = _parse_args()
    if args.email and args.password:
        client = ListonicClient(args.email, args.password, args.list_id)
        status = f"account {args.email}" + (
            f", pinned list {args.list_id}" if args.list_id else ", default = first list"
        )
    else:
        status = "no credentials — tools will report this until restarted with --email/--password"
    print(f"listonic-mcp · {status}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
