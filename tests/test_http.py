"""Offline smoke tests for the Streamable HTTP transport.

No Listonic credentials or network needed: they cover /health, the auth guard
and MCP initialize/tools/list. Run with:  pip install -e ".[test]" && pytest
"""

import pytest
from starlette.testclient import TestClient

import listonic_mcp

TOKEN = "t" * 40
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "pytest", "version": "0"}},
}


def _client(allow_path_token=False):
    app = listonic_mcp.build_http_app(TOKEN, allow_path_token)
    return TestClient(app, base_url="https://example.onrender.com")


def test_health_is_public():
    with _client() as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.parametrize("headers", [
    {}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN},
    {"Authorization": f"Basic {TOKEN}"},
])
def test_mcp_rejects_missing_or_bad_token(headers):
    with _client() as c:
        r = c.post("/mcp", json=INIT, headers={**MCP_HEADERS, **headers})
        assert r.status_code == 401
        assert "bearer" in r.headers["www-authenticate"].lower()


def test_other_paths_require_auth():
    with _client() as c:
        assert c.get("/").status_code == 401


def test_initialize_and_list_tools_with_bearer():
    auth = {**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}"}
    with _client() as c:
        r = c.post("/mcp", json=INIT, headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "listonic"
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                   headers=auth)
        assert r.status_code == 200, r.text
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert names == {"get_lists", "get_items", "add_items", "edit_items", "delete_items"}


def test_path_token_disabled_by_default():
    with _client() as c:
        r = c.post(f"/mcp/{TOKEN}", json=INIT, headers=MCP_HEADERS)
        assert r.status_code == 401


def test_path_token_when_enabled():
    with _client(allow_path_token=True) as c:
        assert c.post(f"/mcp/{TOKEN}", json=INIT, headers=MCP_HEADERS).status_code == 200
        assert c.post("/mcp/wrong", json=INIT, headers=MCP_HEADERS).status_code == 404


def test_http_refuses_to_start_without_strong_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "short")
    with pytest.raises(SystemExit):
        listonic_mcp._run_http("127.0.0.1", 0)
