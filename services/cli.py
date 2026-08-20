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
    load_env()

    parser = argparse.ArgumentParser(prog="swagger-parser-mcp")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve REST + MCP over HTTP on :9876 instead of MCP over stdio",
    )
    args = parser.parse_args()

    if args.http:
        # Imported lazily: FastAPI/uvicorn (and the whole services.rest tree)
        # are only needed for this branch, which is why they live in the
        # optional `http` extra rather than the base dependencies.
        import uvicorn

        from services.app import combined_app

        uvicorn.run(combined_app, host="localhost", port=9876)
    else:
        threading.Thread(target=sync_all_wikis_on_startup, daemon=True).start()
        mcp.run(transport="stdio")
