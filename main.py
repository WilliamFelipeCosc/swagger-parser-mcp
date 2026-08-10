import argparse
import threading

from internal.azure_devops import sync_all_wikis_on_startup
from services.app import combined_app
from services.mcp.server import mcp

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve REST + MCP over HTTP on :9876 instead of MCP over stdio",
    )
    args = parser.parse_args()

    if args.http:
        import uvicorn

        uvicorn.run(combined_app, host="localhost", port=9876)
    else:
        threading.Thread(target=sync_all_wikis_on_startup, daemon=True).start()
        mcp.run(transport="stdio")
