from fastmcp import FastMCP
from fastapi import FastAPI

from services.main import http_app

mcp = FastMCP.from_fastapi(app=http_app, name="swagger_parser", instructions="This MCP provides an API to parse Swagger JSON files and extract information about enums, paths, and modules.")

mcp_app = mcp.http_app(path="/mcp")

combined_app = FastAPI(
  title="Swagger MCP API",
  description="API for the Swagger MCP, which provides endpoints to extract information from Swagger JSON files.",
  version="0.2",
  routes=[
    *mcp_app.routes,
    *http_app.routes
  ],
  lifespan=mcp_app.lifespan
)

