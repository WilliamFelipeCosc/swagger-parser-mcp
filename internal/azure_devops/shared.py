import os
from dotenv import load_dotenv
from msrest.authentication import BasicAuthentication
from azure.devops.connection import Connection

load_dotenv()


def _get_connection() -> Connection:
    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    pat = os.getenv("AZURE_DEVOPS_PAT")
    if not org_url or not pat:
        raise ValueError("AZURE_DEVOPS_ORG_URL and AZURE_DEVOPS_PAT must be set")
    credentials = BasicAuthentication("", pat)
    return Connection(base_url=org_url, creds=credentials)


def _get_project() -> str:
    project = os.getenv("AZURE_DEVOPS_PROJECT")
    if not project:
        raise ValueError("AZURE_DEVOPS_PROJECT must be set")
    return project
