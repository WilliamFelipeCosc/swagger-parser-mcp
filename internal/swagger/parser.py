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

def show_single_path(resolved_data, module_name, path):
    paths_info = show_paths(resolved_data, module_name)

    normalized_path = path if path.startswith('/') else f'/{path}'
    for full_path, operations in paths_info.items():
        if full_path.endswith(normalized_path):
            return {full_path: operations}

    raise ValueError(f"Path '{path}' not found for module '{module_name}'")

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

def get_module_names(resolved_data):
    paths = resolved_data.get('paths', {})
    module_names = set()

    for path in paths.keys():
        parts = path.strip('/').split('/')
        if len(parts) > 2:
            if parts[2] == 'admin' and len(parts) > 3:
                module_names.add(f"{parts[2]}/{parts[3]}")
            else:
                module_names.add(parts[2])

    return list(module_names)
