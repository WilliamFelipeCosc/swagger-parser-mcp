# Documentation

This project exposes Swagger/OpenAPI parsing and Azure DevOps integration as a native MCP
(Model Context Protocol) server, spoken over **stdio only** — no port, no HTTP endpoint.

## Contents

- [Architecture](architecture.md) — technical structure: layers, module boundaries, entry point, environment variables
- [MCP Reference](mcp-reference.md) — every Tool, Resource, and Prompt exposed by the MCP server, with URIs/parameters
- [Wiki Cache Internals](wiki-cache.md) — the local SQLite+FTS5 cache: schema, sync flow, and query functions

## Quickstart

```bash
# Development install
pip install -e .

# Run the MCP server over stdio
swagger-parser-mcp          # or, from a checkout: python main.py
```

For installing on another machine without a clone, see the `uvx` recipe in the
[top-level README](../README.md#installation).

There are no automated tests or lint commands configured for this project.

## At a Glance

| Surface | Transport | Built with |
|---|---|---|
| MCP server (Tools/Resources/Prompts) | stdio | `fastmcp.FastMCP`, defined natively in `services/mcp/` |

`services/cli.py:main` calls `mcp.run(transport="stdio")`. There is no HTTP surface and no
REST API — the MCP Tools/Resources cover everything.
