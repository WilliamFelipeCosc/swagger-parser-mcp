"""Console-script entry point (`swagger-parser-mcp`).

The launch logic lives here rather than in `main.py` so it can be reached from
an installed package. `main.py` stays as a dev shim that calls into this.
"""

import argparse
import threading

from internal.azure_devops import sync_all_wikis_on_startup
from internal.env import load_env
from services.mcp.server import mcp


def main() -> None:
    argparse.ArgumentParser(
        prog="swagger-parser-mcp",
        description=(
            "MCP server for Swagger/OpenAPI parsing and Azure DevOps "
            "(Tasks/PBIs, wiki, cached full-text search). Speaks MCP over "
            "stdio; launch it from an MCP client rather than by hand."
        ),
    ).parse_args()

    load_env()

    # No ASGI lifespan to hook into on stdio, so the startup resync runs in a
    # plain daemon thread. Non-blocking: the server starts serving immediately.
    threading.Thread(target=sync_all_wikis_on_startup, daemon=True).start()

    mcp.run(transport="stdio")
