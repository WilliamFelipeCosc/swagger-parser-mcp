# swagger-parser-mcp

Exposes Swagger/OpenAPI parsing and Azure DevOps integration (Tasks/PBIs, live wiki
pages, and a local full-text-searchable wiki cache) through two independent surfaces
served on a single port: a native MCP (Model Context Protocol) server and a
hand-written REST API. Neither surface is derived from the other.

## Prerequisites

- Python 3.10+
- Access to one or two Swagger/OpenAPI JSON URLs (v1 and/or v2)
- (Optional) An Azure DevOps organization with a Personal Access Token, for the Azure
  DevOps / wiki features

## Installation

### Windows

```powershell
git clone git@github.com:WilliamFelipeCosc/swagger-parser-mcp.git
cd swagger-parser-mcp

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

### macOS / Linux

```bash
git clone git@github.com:WilliamFelipeCosc/swagger-parser-mcp.git
cd swagger-parser-mcp

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

> The virtual environment must be active whenever you run the server. To reactivate it
> in a new terminal session, run `.venv\Scripts\activate` (Windows) or
> `source .venv/bin/activate` (macOS/Linux).

## Configuration

Create a `.env` file in the project root:

```env
# Required: at least one Swagger URL
SWAGGER_JSON_V1_URL=https://your-api.example.com/swagger/v1/swagger.json
SWAGGER_JSON_V2_URL=https://your-api.example.com/swagger/v2/swagger.json

# Optional: Azure DevOps integration (Tasks/PBIs, wiki)
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/YOUR_ORG
AZURE_DEVOPS_PAT=your_personal_access_token
AZURE_DEVOPS_PROJECT=YourProjectName

# Optional: wiki cache tuning
WIKI_CACHE_DB_PATH=data/wiki_cache.db   # default shown
WIKI_CACHE_STALE_SECONDS=86400          # default shown (1 day)
```

## Running the Server

```bash
python main.py
```

This runs the MCP server over **stdio** — the primary and recommended way to run this
project. There's no port to manage and no separate process to keep alive; your MCP
client launches `python main.py` as a subprocess and talks to it directly over
stdin/stdout.

If Azure DevOps is configured, every wiki in the project is synced into a local
SQLite+FTS5 cache in the background on startup (non-blocking) — see
[Wiki Cache Internals](docs/wiki-cache.md).

There are no automated tests or lint commands configured for this project.

### HTTP mode (fallback)

Only needed if your MCP client can't spawn subprocesses, or you also want the REST API:

```bash
python main.py --http

# or directly with uvicorn
uvicorn services.app:combined_app --host localhost --port 9876 --reload
```

The server starts on `http://localhost:9876`. The MCP endpoint is at
`http://localhost:9876/mcp`; interactive REST docs are at
`http://localhost:9876/docs`.

## Connecting to Claude

**stdio is the primary connection method.** Add this server to your Claude Desktop or
Claude Code MCP configuration to have it launch `python main.py` as a subprocess:

```json
{
  "mcpServers": {
    "swagger-parser": {
      "command": "python",
      "args": ["main.py"],
      "cwd": "/path/to/swagger-parser-mcp"
    }
  }
}
```

For Claude Code, add it via the CLI:

```bash
claude mcp add swagger-parser -- python /path/to/swagger-parser-mcp/main.py
```

Make sure the virtual environment created above is the one on `PATH` (or invoked with
its full path, e.g. `/path/to/swagger-parser-mcp/.venv/bin/python`) so dependencies
resolve correctly.

### HTTP mode (fallback)

Only if you're running the server with `--http` (see above):

```json
{
  "mcpServers": {
    "swagger-parser": {
      "url": "http://localhost:9876/mcp"
    }
  }
}
```

```bash
claude mcp add --transport http swagger-parser http://localhost:9876/mcp
```

## What's exposed

**MCP server** (`/mcp`) — Resources (read-only, addressed by URI: Swagger enums/modules/
paths, live wiki pages, cached wiki tree/structure/status/search), Tools (Azure DevOps
Tasks/PBIs queries, and the one mutating operation — wiki cache resync), and Prompts
(sprint status report, wiki page digest, PBI breakdown check).

**REST API** (`/{version}/*`, `/azure/*`) — the same underlying functionality as a plain
FastAPI surface; not derived from or exposed as MCP tools.

**Example prompts to try in Claude:**
- *"List all modules in the v1 API"*
- *"Show me the paths for the `users` module in v2"*
- *"Show me all active tasks assigned to Jane in the current sprint"*
- *"Get PBI #1234 and check whether its Task breakdown is complete"*
- *"Search the wiki cache for onboarding docs"*

See the full reference docs for exact URIs/parameters:

- [Documentation index](docs/README.md)
- [Architecture](docs/architecture.md) — layers, module boundaries, entry point, environment variables
- [MCP Reference](docs/mcp-reference.md) — every Tool, Resource, and Prompt, with URIs/parameters
- [REST API Reference](docs/rest-api.md) — every REST endpoint, with query parameters and response shapes
- [Wiki Cache Internals](docs/wiki-cache.md) — the local SQLite+FTS5 cache: schema, sync flow, and query functions

## Module Name Convention

Module names are extracted from the third path segment of each API route:

- `/prefix/version/users/...` → module name is `users`
- `/prefix/version/admin/roles/...` → module name is `admin/roles`
