# Documentation

This project exposes Swagger/OpenAPI parsing and Azure DevOps integration through two
independent surfaces, served together on one port: a native MCP (Model Context Protocol)
server and a hand-written REST API. Neither surface is derived from the other.

## Contents

- [Architecture](architecture.md) — technical structure: layers, module boundaries, entry point, environment variables
- [MCP Reference](mcp-reference.md) — every Tool, Resource, and Prompt exposed by the MCP server, with URIs/parameters
- [REST API Reference](rest-api.md) — every REST endpoint, with query parameters and response shapes
- [Wiki Cache Internals](wiki-cache.md) — the local SQLite+FTS5 cache: schema, sync flow, and query functions

## Quickstart

```bash
# Development install (`http` extra = FastAPI + uvicorn, needed only for --http)
pip install -e ".[http]"

# Run the MCP server over stdio (default)
swagger-parser-mcp          # or, from a checkout: python main.py

# Run REST + MCP combined on localhost:9876 instead
swagger-parser-mcp --http

# Run with uvicorn directly (HTTP mode only)
uvicorn services.app:combined_app --host localhost --port 9876 --reload
```

For installing on another machine without a clone, see the `uvx` recipe in the
[top-level README](../README.md#installation).

There are no automated tests or lint commands configured for this project.

## At a Glance

| Surface | Path | Built with |
|---|---|---|
| MCP server (Tools/Resources/Prompts) | `/mcp` | `fastmcp.FastMCP`, defined natively in `services/mcp/` |
| REST API | `/{version}/*`, `/azure/*` | FastAPI, defined by hand in `services/rest/app.py` |

Both are mounted into a single `combined_app` (`services/app.py`), which the entry point
runs on `localhost:9876` — but only in `--http` mode. The default is MCP over stdio, with
no HTTP surface at all.
