import os
from msrest.authentication import BasicAuthentication
from azure.devops.connection import Connection
from fastmcp.exceptions import ToolError

from internal.env import load_env

load_env()


def _get_connection() -> Connection:
    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    pat = os.getenv("AZURE_DEVOPS_PAT")
    if not org_url or not pat:
        raise ToolError("AZURE_DEVOPS_ORG_URL and AZURE_DEVOPS_PAT must be set")
    credentials = BasicAuthentication("", pat)
    return Connection(base_url=org_url, creds=credentials)


def _get_project() -> str:
    project = os.getenv("AZURE_DEVOPS_PROJECT")
    if not project:
        raise ToolError("AZURE_DEVOPS_PROJECT must be set")
    return project
