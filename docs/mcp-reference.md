# MCP Reference

The MCP server is built with `fastmcp.FastMCP`, defined in `services/mcp/`, and served
over streamable HTTP at `/mcp` (not stdio).

## How it's wired

`services/mcp/server.py` creates a single instance:

```python
mcp = FastMCP(name="swagger_parser", instructions="...")
```

then imports the `resources`, `tools`, and `prompts` sub-packages purely for their import
side effects — each module in those packages decorates the shared `mcp` instance with
`@mcp.resource`, `@mcp.tool`, or `@mcp.prompt` at import time. `mcp_app = mcp.http_app(path="/mcp")`
is the ASGI app that `services/app.py` mounts.

```
services/mcp/
  server.py           # creates `mcp`, imports the packages below, exposes mcp_app
  resources/           # read-only, addressed by URI
    swagger.py
    wiki_live.py
    wiki_cache.py
  tools/                # actions and heavily-filtered queries
    azure_work_items.py
    wiki_cache_sync.py
  prompts/
    sprint_status_report.py
    wiki_page_digest.py
    pbi_breakdown_check.py
```

**Why this split:** anything that's a pure read with no side effects and a natural
identity (a Swagger version, a wiki page, a cache subtree) is a **Resource**, addressed
by URI. Anything with side effects (rewriting the cache) or accepting many independent
optional filters that don't map cleanly to a single URI identity (Tasks/PBIs queries) is
a **Tool**. **Prompts** package up one or more Tool/Resource calls into a ready-to-send
message for an LLM.

## Resources

Resource functions must return `str` or `bytes` (a FastMCP constraint), so every resource
below `json.dumps()`s its result and declares `mime_type="application/json"`.

Query-string template parameters (the `{?param}` part of a URI template) must have a
default value in the function signature — also a FastMCP constraint. Where a parameter is
logically required (e.g. `path` on a page lookup, `q` on search), it defaults to `None`
and the function raises `ValueError` if the caller omits it.

### `services/mcp/resources/swagger.py`

| URI Template | Params | Description |
|---|---|---|
| `swagger://{version}/enums` | `version` (`v1`\|`v2`) | All enums defined in the Swagger JSON for that version |
| `swagger://{version}/modules` | `version` | All modules defined in the Swagger JSON for that version |
| `swagger://{version}/paths/{module_name}` | `version`, `module_name` | All paths for a specific module |

### `services/mcp/resources/wiki_live.py`

Always hits the live Azure DevOps API (never the cache).

| URI Template | Params | Description |
|---|---|---|
| `wiki://pages{?top}` | `top` (default 100) | List pages from every wiki in the project (metadata only) |
| `wiki://{wiki_id}/pages{?top,continuation_token}` | `wiki_id`, `top`, `continuation_token` | List pages from one wiki; returns `{pages, continuation_token}` — pass the token back to page forward |
| `wiki://page-by-path{?path}` | `path` (required) | Get a page's content + subpages, by path, from the project's default wiki |
| `wiki://{wiki_id}/page-by-path{?path}` | `wiki_id`, `path` (required) | Same, from a specific wiki |
| `wiki://page-by-id/{page_id}` | `page_id` | Get a page's content + subpages, by ID, from the project's default wiki |
| `wiki://{wiki_id}/page-by-id/{page_id}` | `wiki_id`, `page_id` | Same, from a specific wiki |

Page-lookup results mirror the `get_wiki_page_by_path`/`get_wiki_page_by_id` shape: `wiki_id`,
`wiki_name`, `page_id`, `path`, `content`, `is_parent_page`, `order`, `url`, `sub_pages`
(recursively nested, capped at `MAX_SUBPAGES_FETCHED` = 50 total descendants), and
`sub_pages_truncated`.

### `services/mcp/resources/wiki_cache.py`

Reads only from the local SQLite cache — no Azure API calls, no live-ness guarantee.
Requires a prior `sync_azure_devops_wiki_cache` tool call for the target wiki.

| URI Template | Params | Description |
|---|---|---|
| `wiki-cache://tree{?wiki_id}` | `wiki_id` (optional — all wikis if omitted) | Full cached page hierarchy as a nested tree |
| `wiki-cache://{wiki_id}/structure{?root_page_id,root_path}` | `wiki_id`, one of `root_page_id`/`root_path` | Folder/path subtree (no content) rooted at one page |
| `wiki-cache://status{?wiki_id}` | `wiki_id` (optional) | Page count, pages-with-content, last sync time per wiki |
| `wiki-cache://search{?q,wiki_id,limit}` | `q` (required, FTS5 syntax), `wiki_id` (optional), `limit` (default 20) | Full-text search over cached path+content |

## Tools

### `services/mcp/tools/azure_work_items.py`

| Tool | Parameters | Description |
|---|---|---|
| `get_azure_devops_tasks` | `id?`, `parent_id?`, `assignee?`, `team?`, `current_sprint?`, `sprint?`, `state?`, `top?` (default 100) | Fetch Tasks. `parent_id` filters by the parent PBI's work item ID |
| `get_azure_devops_pbis` | `id?`, `assignee?`, `team?`, `current_sprint?`, `sprint?`, `state?`, `top?` | Fetch Product Backlog Items (same filters, no `parent_id`) |

Filter semantics: `id` is an exact work-item-ID lookup; `assignee` is a substring match on
display name; `team` scopes `@CurrentIteration` to the right team's board; `current_sprint`
takes priority over `sprint` (a substring match on iteration path); `state` is an exact
match (`Active`, `New`, `Closed`, ...).

### `services/mcp/tools/wiki_cache_sync.py`

| Tool | Parameters | Description |
|---|---|---|
| `sync_azure_devops_wiki_cache` | `wiki_id` (required), `fetch_content?` (default `true`) | Rebuilds the local cache for one wiki. The only mutating MCP operation — everything else is a read. Can take 20–120s+ for large wikis with `fetch_content=true` (one API call per page) |

## Prompts

Prompts return a rendered string (or list of `Message`s) built from one or more Tool/
internal calls — they don't call the LLM themselves, they assemble what gets sent to it.

| Prompt | Parameters | Description |
|---|---|---|
| `sprint_status_report` | `team?`, `sprint?`, `current_sprint?` (default `true`) | Pulls Tasks + PBIs for the sprint and builds a report prompt asking for grouping by assignee/state and flagging stalled/unassigned items |
| `wiki_page_digest` | `path?` or `page_id?` (one required), `wiki_id?` | Fetches a wiki page and all its subpages' content, and builds a summarization prompt |
| `pbi_breakdown_check` | `pbi_id` (required) | Fetches one PBI and its child Tasks (via `get_tasks(parent_id=pbi_id)`) and builds a prompt asking whether the breakdown looks complete/consistent |

## Example client calls

```python
# Resource: cache tree for one wiki
await client.read_resource("wiki-cache://tree?wiki_id=MyProject.wiki")

# Resource: search the cache
await client.read_resource("wiki-cache://search?q=onboarding&wiki_id=MyProject.wiki")

# Tool: tasks for a given PBI, in the current sprint
await client.call_tool("get_azure_devops_tasks", {"parent_id": 1234, "current_sprint": True})

# Prompt: sprint report for a team
await client.get_prompt("sprint_status_report", {"team": "Platform"})
```
