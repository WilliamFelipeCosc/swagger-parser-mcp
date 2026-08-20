# swagger-parser-mcp

A native MCP (Model Context Protocol) server exposing Swagger/OpenAPI parsing and Azure
DevOps integration — Tasks/PBIs, live wiki pages, and a local full-text-searchable wiki
cache — as Tools, Resources and Prompts. It speaks **stdio only**: your MCP client
launches it as a subprocess, so there's no port, no HTTP endpoint and no server process
to keep alive.

## Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) for the recommended zero-clone install (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `winget install astral-sh.uv` on Windows)
- Access to one or two Swagger/OpenAPI JSON URLs (v1 and/or v2)
- (Optional) An Azure DevOps organization with a Personal Access Token, for the Azure
  DevOps / wiki features

## Installation

### Recommended: no clone, no venv

The server is a proper Python package with a `swagger-parser-mcp` console script, so
`uvx` can fetch, build and run it straight from git. Nothing to clone, no virtualenv to
activate, no interpreter to keep on `PATH` — see
[Connecting to Claude](#connecting-to-claude) for the `mcpServers` block.

```bash
# one-off smoke test
uvx --from git+https://github.com/WilliamFelipeCosc/swagger-parser-mcp swagger-parser-mcp --help
```

To keep a persistent installed copy instead:

```bash
uv tool install git+https://github.com/WilliamFelipeCosc/swagger-parser-mcp
# or, without uv:
pipx install git+https://github.com/WilliamFelipeCosc/swagger-parser-mcp
```

### Development install

```bash
git clone git@github.com:WilliamFelipeCosc/swagger-parser-mcp.git
cd swagger-parser-mcp

python3 -m venv .venv          # Windows: python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e .               # or: pip install -r requirements.txt
```

`requirements.txt` is just `-e .`; the real dependency list lives in `pyproject.toml`.

## Configuration

Copy the committed template and fill it in:

```bash
cp .env.example .env
```

```env
# Required: at least one Swagger URL
SWAGGER_JSON_V1_URL=https://your-api.example.com/swagger/v1/swagger.json
SWAGGER_JSON_V2_URL=https://your-api.example.com/swagger/v2/swagger.json

# Optional: Azure DevOps integration (Tasks/PBIs, wiki)
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/YOUR_ORG
AZURE_DEVOPS_PAT=your_personal_access_token
AZURE_DEVOPS_PROJECT=YourProjectName

# Optional: wiki cache tuning
WIKI_CACHE_STALE_SECONDS=86400          # default shown (1 day)
WIKI_CACHE_DB_PATH=/custom/path.db      # default: per-user data dir, see below
```

**Where `.env` is looked for** (`internal/env.py`), in order, never overriding a variable
that is already set:

1. Walking up from the current working directory — covers an MCP client that sets `cwd`
   to a checkout.
2. The checkout root next to the installed package — covers an editable/dev install
   launched from an unrelated directory.

An installed copy (`uvx`, `uv tool install`, `pipx`) has no checkout, so **variables must
come from the `env` map in your MCP client config** — see below. Anything in the process
environment always wins over the file, so the client's `env` map overrides `.env`.

**Wiki cache location.** `WIKI_CACHE_DB_PATH` overrides it. Otherwise an existing
`<repo>/data/wiki_cache.db` is reused if present (so a dev checkout keeps its populated
cache), and failing that the default is the per-user data directory:

| OS | Default path |
|---|---|
| Linux | `~/.local/share/swagger-parser-mcp/wiki_cache.db` |
| macOS | `~/Library/Application Support/swagger-parser-mcp/wiki_cache.db` |
| Windows | `%LOCALAPPDATA%\swagger-parser-mcp\wiki_cache.db` |

## Running the Server

```bash
swagger-parser-mcp        # installed console script
python main.py            # equivalent, from a checkout
```

This runs the MCP server over **stdio** — the primary and recommended way to run this
project. There's no port to manage and no separate process to keep alive; your MCP
client launches the command as a subprocess and talks to it directly over stdin/stdout.

If Azure DevOps is configured, every wiki in the project is synced into a local
SQLite+FTS5 cache in the background on startup (non-blocking) — see
[Wiki Cache Internals](docs/wiki-cache.md).

There are no automated tests or lint commands configured for this project.

### `fastmcp run` (dev)

`fastmcp.json` declares the source, uv environment and stdio transport, so a checkout
also runs with:

```bash
fastmcp run
```

Note this loads the `mcp` object directly and never calls `main()`, so it **skips the
background startup wiki sync**. Cached reads still auto-refresh once stale, but a wiki
that has never been synced needs one `sync_azure_devops_wiki_cache` call first.

## Connecting to Claude

**stdio is the primary connection method.** Secrets travel via the `env` map, which the
client puts into the server subprocess's environment before spawning it:

```json
{
  "mcpServers": {
    "swagger-parser": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/WilliamFelipeCosc/swagger-parser-mcp",
        "swagger-parser-mcp"
      ],
      "env": {
        "SWAGGER_JSON_V1_URL": "https://your-api.example.com/swagger/v1/swagger.json",
        "SWAGGER_JSON_V2_URL": "https://your-api.example.com/swagger/v2/swagger.json",
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/YOUR_ORG",
        "AZURE_DEVOPS_PAT": "your_personal_access_token",
        "AZURE_DEVOPS_PROJECT": "YourProjectName"
      }
    }
  }
}
```

For Claude Code, add it via the CLI:

```bash
claude mcp add swagger-parser \
  --env SWAGGER_JSON_V1_URL=https://your-api.example.com/swagger/v1/swagger.json \
  --env AZURE_DEVOPS_ORG_URL=https://dev.azure.com/YOUR_ORG \
  --env AZURE_DEVOPS_PAT=your_personal_access_token \
  --env AZURE_DEVOPS_PROJECT=YourProjectName \
  -- uvx --from git+https://github.com/WilliamFelipeCosc/swagger-parser-mcp swagger-parser-mcp
```

From a checkout, `swagger-parser-mcp` (or `python main.py` with `"cwd"` set) works as the
`command` instead, and the vars can come from `.env` rather than the `env` map.

### Generating the config with FastMCP

From a checkout, `fastmcp install` writes the block above — including the `env` map —
into a client's config for you, reading the values straight out of `.env`:

```bash
fastmcp install claude-code main.py --name "Swagger Parser" --env-file .env
fastmcp install claude-desktop main.py --env-file .env
fastmcp install mcp-json main.py --env-file .env     # prints JSON for any other client
```

Individual values can be passed with repeated `--env KEY=VALUE` flags instead.

## What's exposed

**Resources** (read-only, addressed by URI) — Swagger enums/modules/paths, live wiki
pages, and the cached wiki tree/structure/status/search.

**Tools** — Azure DevOps Tasks/PBIs queries, plus the one mutating operation (wiki cache
resync).

**Prompts** — sprint status report, wiki page digest, PBI breakdown check.

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
- [Wiki Cache Internals](docs/wiki-cache.md) — the local SQLite+FTS5 cache: schema, sync flow, and query functions

## Module Name Convention

Module names are extracted from the third path segment of each API route:

- `/prefix/version/users/...` → module name is `users`
- `/prefix/version/admin/roles/...` → module name is `admin/roles`
