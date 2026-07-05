from fastapi import FastAPI

from services.mcp import mcp_app
from services.rest import app as rest_app

combined_app = FastAPI(
    title="Swagger MCP API",
    description=(
        "Combined app: the MCP server (Tools/Resources/Prompts, built with FastMCP) is "
        "served at /mcp; the REST API (independent, hand-written FastAPI app) keeps its "
        "existing paths (/{version}/*, /azure/*)."
    ),
    version="0.3",
    routes=[
        *mcp_app.routes,
        *rest_app.routes,
    ],
    lifespan=mcp_app.lifespan,
)
