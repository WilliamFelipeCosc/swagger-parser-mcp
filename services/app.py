import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from internal.azure_devops import sync_all_wikis_on_startup
from services.mcp import mcp_app
from services.rest import app as rest_app

logger = logging.getLogger(__name__)


async def _sync_all_wikis_in_background() -> None:
    try:
        await asyncio.to_thread(sync_all_wikis_on_startup)
    except Exception:
        logger.exception("startup wiki cache sync failed")


@asynccontextmanager
async def _combined_lifespan(app: FastAPI):
    async with mcp_app.lifespan(app):
        asyncio.create_task(_sync_all_wikis_in_background())
        yield


combined_app = FastAPI(
    title="Swagger MCP API",
    description=(
        "Combined app: the MCP server (Tools/Resources/Prompts, built with FastMCP) is "
        "served at /mcp; the REST API (independent, hand-written FastAPI app) keeps its "
        "existing paths (/{version}/*, /azure/*). On startup, every wiki in the configured "
        "Azure DevOps project is resynced in the background (non-blocking) — the server "
        "starts accepting requests immediately."
    ),
    version="0.3",
    routes=[
        *mcp_app.routes,
        *rest_app.routes,
    ],
    lifespan=_combined_lifespan,
)
