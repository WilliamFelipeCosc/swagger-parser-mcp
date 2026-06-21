from fastapi import FastAPI
from services.params import swagger_version
from internal.main import get_enums, get_paths

app = FastAPI()

@app.get("/{version}/enums")
async def get_enums_endpoint(version: swagger_version):
    enums = get_enums(version)
    return enums

@app.get("/{version}/paths/{module_name}")
async def get_paths_endpoint(version: swagger_version, module_name: str | None = None):
    paths = get_paths(version, module_name)
    return paths