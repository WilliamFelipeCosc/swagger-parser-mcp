# swagger-parser-mcp

An MCP (Model Context Protocol) server that parses Swagger/OpenAPI JSON files and exposes their enums, modules, and paths as tools. Also includes Azure DevOps integration for querying work items and wiki pages.

The server runs on a single port and serves both a REST API and an MCP endpoint simultaneously.

## Prerequisites

- Python 3.10+
- Access to one or two Swagger/OpenAPI JSON URLs (v1 and/or v2)
- (Optional) An Azure DevOps organization with a Personal Access Token

## Installation

```bash
git clone <repo-url>
cd swagger-mcp-py
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```env
# Required: at least one Swagger URL
SWAGGER_JSON_V1_URL=https://your-api.example.com/swagger/v1/swagger.json
SWAGGER_JSON_V2_URL=https://your-api.example.com/swagger/v2/swagger.json

# Optional: Azure DevOps integration
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/YOUR_ORG
AZURE_DEVOPS_PAT=your_personal_access_token
AZURE_DEVOPS_PROJECT=YourProjectName
```

## Running the Server

```bash
python main.py
```

The server starts on `http://localhost:9876`. The MCP endpoint is at `http://localhost:9876/mcp`.

## Connecting to Claude

Add this server to your Claude Desktop or Claude Code MCP configuration:

```json
{
  "mcpServers": {
    "swagger-parser": {
      "url": "http://localhost:9876/mcp"
    }
  }
}
```

For Claude Code, add it via the CLI:

```bash
claude mcp add swagger-parser --url http://localhost:9876/mcp
```

Once connected, Claude can call any of the tools below directly.

## MCP Tools

### Swagger / OpenAPI

All Swagger tools accept a `version` parameter: `v1` or `v2`.

| Tool | Description |
|---|---|
| `get_enums` | Returns all enums defined in the Swagger schema for the given version |
| `get_all_modules` | Lists all API modules (top-level path segments) for the given version |
| `get_paths_by_module` | Returns all paths, parameters, request bodies, and responses for a specific module |

**Example prompts:**
- *"List all modules in the v1 API"*
- *"Show me the paths for the `users` module in v2"*
- *"What enums are defined in v1?"*

### Azure DevOps

Requires `AZURE_DEVOPS_ORG_URL`, `AZURE_DEVOPS_PAT`, and `AZURE_DEVOPS_PROJECT` to be set.

| Tool | Description |
|---|---|
| `get_azure_devops_tasks` | Fetch Tasks with optional filters |
| `get_azure_devops_pbis` | Fetch Product Backlog Items with optional filters |
| `get_azure_devops_wiki_pages` | Fetch wiki pages from the project |

**Filters available for tasks and PBIs:**

| Parameter | Type | Description |
|---|---|---|
| `id` | int | Fetch a single item by work item ID |
| `assignee` | string | Substring match on assignee display name |
| `team` | string | Sprint board team name |
| `current_sprint` | bool | Filter to current sprint only (`@CurrentIteration`) |
| `sprint` | string | Substring match on iteration path (ignored when `current_sprint=true`) |
| `state` | string | Work item state, e.g. `Active`, `New`, `Closed` |
| `top` | int | Max results to return (default 100) |

Tasks also include a `parent_id` field containing the ID of the parent PBI, or `null` if unset.

**Example prompts:**
- *"Show me all active tasks assigned to Jane in the current sprint"*
- *"Get PBI #1234"*
- *"List all wiki pages in the project"*
- *"What tasks are in the 'Sprint 42' iteration for the Backend team?"*

## REST API

The same functionality is also available as a plain REST API at `http://localhost:9876`:

```
GET /{version}/enums
GET /{version}/modules
GET /{version}/paths/{module_name}

GET /azure/tasks
GET /azure/pbis
GET /azure/wiki
```

Interactive docs are available at `http://localhost:9876/docs`.

## Module Name Convention

Module names are extracted from the third path segment of each API route:

- `/prefix/version/users/...` → module name is `users`
- `/prefix/version/admin/roles/...` → module name is `admin/roles`
