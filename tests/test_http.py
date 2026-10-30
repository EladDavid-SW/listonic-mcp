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


# --------------------------------------------------------------------------- #
# API-key headers (claude.ai "Request headers" / other clients)
# --------------------------------------------------------------------------- #

API_KEY_HEADER_NAMES = ["X-API-Key", "x-api-key", "X-MCP-API-Key", "x-mcp-api-key"]


@pytest.mark.parametrize("name", API_KEY_HEADER_NAMES)
def test_api_key_header_valid(name):
    with _client() as c:
        r = c.post("/mcp", json=INIT, headers={**MCP_HEADERS, name: TOKEN})
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "listonic"
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                   headers={**MCP_HEADERS, name: TOKEN})
        assert r.status_code == 200, r.text


@pytest.mark.parametrize("name", API_KEY_HEADER_NAMES)
@pytest.mark.parametrize("value", [
    "wrong", "", " ", TOKEN[:-1], TOKEN + "x", f"Bearer {TOKEN}",  # no Bearer prefix allowed
])
def test_api_key_header_invalid(name, value):
    with _client() as c:
        r = c.post("/mcp", json=INIT, headers={**MCP_HEADERS, name: value})
        assert r.status_code == 401


def test_api_key_missing():
    with _client() as c:
        r = c.post("/mcp", json=INIT, headers=MCP_HEADERS)
        assert r.status_code == 401
        assert c.get("/mcp", headers={"X-Unrelated": TOKEN}).status_code == 401


def test_api_key_does_not_unlock_other_paths_without_token():
    with _client() as c:
        assert c.get("/", headers={"X-API-Key": "wrong"}).status_code == 401


def test_bearer_still_works_alongside_wrong_api_key():
    with _client() as c:
        r = c.post("/mcp", json=INIT, headers={
            **MCP_HEADERS, "Authorization": f"Bearer {TOKEN}", "X-API-Key": "wrong"})
        assert r.status_code == 200


@pytest.mark.parametrize("path", [
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/mcp",
    "/.well-known/openid-configuration",
])
def test_oauth_discovery_is_404_and_exposes_nothing(path):
    with _client() as c:
        r = c.get(path)
        assert r.status_code == 404
        assert r.text == "Not Found"
        # A valid key changes nothing — there is no OAuth metadata to serve.
        assert c.get(path, headers={"X-API-Key": TOKEN}).status_code == 404


def test_other_well_known_paths_still_require_auth():
    with _client() as c:
        assert c.get("/.well-known/anything").status_code == 401


def test_logs_header_names_but_never_values(caplog):
    secret_guess = "s" * 40
    with caplog.at_level("INFO", logger="listonic_mcp"), _client() as c:
        c.post("/mcp", json=INIT, headers={**MCP_HEADERS, "X-API-Key": secret_guess})
        c.post("/mcp", json=INIT, headers=MCP_HEADERS)
        c.post("/mcp", json=INIT, headers={**MCP_HEADERS, "X-MCP-API-Key": TOKEN})
    text = caplog.text
    assert "credential headers: x-api-key" in text
    assert "credential headers: none" in text
    assert secret_guess not in text
    assert TOKEN not in text
