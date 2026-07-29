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

- **Your password goes to Listonic only.** The server logs in against `api.listonic.com` directly and talks to nothing else — no telemetry, nothing stored beyond an in-memory session token (auto-refreshed when it expires).
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
