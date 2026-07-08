from fastmcp import FastMCP

mcp = FastMCP(
    name="swagger_parser",
    instructions=(
        "This MCP provides tools, resources, and prompts to parse Swagger JSON files "
        "(enums, paths, modules) and to work with Azure DevOps: Tasks/PBIs, live wiki "
        "pages, and a local full-text-searchable wiki cache."
    ),
)

# Imported for their registration side effects (each module decorates `mcp` on import).
# Must come after `mcp` is defined above, since these modules do `from ..server import mcp`.
from . import resources  # noqa: E402,F401
from . import tools  # noqa: E402,F401
from . import prompts  # noqa: E402,F401

mcp_app = mcp.http_app(path="/mcp")
