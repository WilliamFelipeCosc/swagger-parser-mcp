import requests
import jsonref
import os

from services.params import swagger_version
from dotenv import load_dotenv

load_dotenv()

def get_swagger_json_url(version: swagger_version):
    if version == swagger_version.v1:
        return os.getenv("SWAGGER_JSON_V1_URL")
    elif version == swagger_version.v2:
        return os.getenv("SWAGGER_JSON_V2_URL")
    else:
        raise ValueError("Invalid swagger version")

def show_paths(resolved_data, module_name):
    paths = resolved_data.get('paths', {})

    if not module_name:
        raise ValueError("Module name must be provided")

    paths = {path: ops for path, ops in paths.items() if path.find(f"/{module_name}/") != -1}

    paths_info = {}
    for path, operations in paths.items():

        paths_info[path] = {}
        for method, details in operations.items():
                       
            parameters = details.get('parameters', [])
            requestBody = details.get('requestBody', {})
            responses = details.get('responses', {})

            paths_info[path][method] = {
                "summary": details.get('summary', 'No summary provided'),
                "tags": details.get('tags', 'No tags provided'),
                "parameters": parameters,
                "responses": {}
            }

            if requestBody:
                paths_info[path][method]["requestBody"] = requestBody.get('content', {}).get('application/json', {}).get('schema', 'No schema provided')
            for status_code, response in responses.items():
                if status_code == 400: continue  # Skip 400 responses
                
                paths_info[path][method]["responses"][status_code] = {
                    "description": response.get('description', 'No description provided'),
                    "schema": response.get('content', {}).get('application/json', {}).get('schema', 'No schema provided')
                }

    return paths_info

def show_enums(resolved_data):
    components = resolved_data.get('components', {})
    schemas = components.get('schemas', {})
    enums = {key: value for key, value in schemas.items() if 'enum' in value}

    formattedEnums = {}
    for enum_name, enum_details in enums.items():
        formattedEnums[enum_name] = {
            "enum": enum_details['enum'],
            "description": enum_details.get('description', 'No description provided')
        }

    return formattedEnums
  
def load_json(url: str):
    response = requests.get(url)
    return jsonref.loads(response.text, base_uri=url)

def get_module_names(resolved_data):
    paths = resolved_data.get('paths', {})
    module_names = set()

    for path in paths.keys():
        parts = path.strip('/').split('/')
        if len(parts) > 1:
            if parts[2] == 'admin':
                module_names.add(f"{parts[2]}/{parts[3]}")
            else:
                module_names.add(parts[2])

    return list(module_names)

def get_enums(version: swagger_version):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")
    
    resolved_data = load_json(url)
    return show_enums(resolved_data)

def get_paths(version: swagger_version, module_name: str):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")

    if not module_name:
        raise ValueError("Module name must be provided")
    
    resolved_data = load_json(url)
    return show_paths(resolved_data, module_name)

def get_modules(version: swagger_version):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")
    
    resolved_data = load_json(url)
    return get_module_names(resolved_data)