import json

from internal.swagger import get_enums, get_modules, get_paths
from services.params import swagger_version

from ..server import mcp


@mcp.resource(
    "swagger://{version}/enums",
    name="SwaggerEnums",
    description="All enums defined in the Swagger JSON for the given version (v1 or v2).",
    mime_type="application/json",
)
def swagger_enums(version: str) -> str:
    return json.dumps(get_enums(swagger_version(version)))


@mcp.resource(
    "swagger://{version}/modules",
    name="SwaggerModules",
    description="All modules defined in the Swagger JSON for the given version (v1 or v2).",
    mime_type="application/json",
)
def swagger_modules(version: str) -> str:
    return json.dumps(get_modules(swagger_version(version)))


@mcp.resource(
    "swagger://{version}/paths/{module_name}",
    name="SwaggerModulePaths",
    description="All paths for a specific module in the Swagger JSON for the given version.",
    mime_type="application/json",
)
def swagger_module_paths(version: str, module_name: str) -> str:
    return json.dumps(get_paths(swagger_version(version), module_name))
