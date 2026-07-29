"""Compat shim — the real module is listonic_mcp.py (unique name so it can't
collide with other MCP packages' top-level modules). This file only keeps
`python server.py` launch configs working."""
from listonic_mcp import main

if __name__ == "__main__":
    main()
