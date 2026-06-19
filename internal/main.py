import requests
import jsonref

from backend.params import swagger_version

def show_paths(resolved_data, module_name=None):
    paths = resolved_data.get('paths', {})

    if module_name:
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

def get_enums(version: swagger_version):
    url = "https://api-homolog.b2.club/swagger/v2/swagger.json" if version == swagger_version.v2 else "https://api-homolog.b2.club/swagger/v1/swagger.json"
    resolved_data = load_json(url)
    return show_enums(resolved_data)

def get_paths(version: swagger_version, module_name=None):
    url = "https://api-homolog.b2.club/swagger/v2/swagger.json" if version == swagger_version.v2 else "https://api-homolog.b2.club/swagger/v1/swagger.json"
    resolved_data = load_json(url)
    return show_paths(resolved_data, module_name)