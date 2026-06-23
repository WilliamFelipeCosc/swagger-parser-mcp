from fastapi import FastAPI
from services.params import swagger_version
from internal.main import get_enums, get_modules, get_paths

app = FastAPI()

@app.get("/{version}/enums", operation_id="get_enums", description="Get all enums defined in the Swagger JSON for the specified version.")
async def get_enums_endpoint(version: swagger_version):
    enums = get_enums(version)
    return enums

@app.get("/{version}/paths/{module_name}", operation_id="get_paths_by_module", description="Get all paths for a specified module in the Swagger JSON for the specified version.")
async def get_paths_endpoint(version: swagger_version, module_name: str):
    paths = get_paths(version, module_name)
    return paths

@app.get("/{version}/modules", operation_id="get_all_modules", description="Get all modules defined in the Swagger JSON for the specified version.")
async def get_modules_endpoint(version: swagger_version):
    modules = get_modules(version)
    return modules