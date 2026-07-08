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
# Install dependencies
pip install -r requirements.txt

# Run the server (REST + MCP combined on localhost:9876)
python main.py

# Run with uvicorn directly
uvicorn services.app:combined_app --host localhost --port 9876 --reload
```

There are no automated tests or lint commands configured for this project.

## At a Glance

| Surface | Path | Built with |
|---|---|---|
| MCP server (Tools/Resources/Prompts) | `/mcp` | `fastmcp.FastMCP`, defined natively in `services/mcp/` |
| REST API | `/{version}/*`, `/azure/*` | FastAPI, defined by hand in `services/rest/app.py` |

Both are mounted into a single `combined_app` (`services/app.py`), which `main.py` runs on
`localhost:9876`.
