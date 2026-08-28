def _resolve(value):
    """Deep-copy `value` into plain dicts/lists, forcing any jsonref lazy
    proxies it contains to dereference. Only called on the small, already
    module/path-filtered slice a caller is about to return, so this never
    touches $refs outside that slice."""
    if isinstance(value, dict):
        return {key: _resolve(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item) for item in value]
    return value


def _build_operation_info(details):
    parameters = details.get('parameters', [])
    requestBody = details.get('requestBody', {})
    responses = details.get('responses', {})

    operation_info = {
        "summary": details.get('summary', 'No summary provided'),
        "tags": details.get('tags', 'No tags provided'),
        "parameters": parameters,
        "responses": {}
    }

    if requestBody:
        operation_info["requestBody"] = requestBody.get('content', {}).get('application/json', {}).get('schema', 'No schema provided')
    for status_code, response in responses.items():
        if status_code == 400: continue  # Skip 400 responses

        operation_info["responses"][status_code] = {
            "description": response.get('description', 'No description provided'),
            "schema": response.get('content', {}).get('application/json', {}).get('schema', 'No schema provided')
        }

    return _resolve(operation_info)


def show_paths(resolved_data, module_name):
    if not module_name:
        raise ValueError("Module name must be provided")

    paths = resolved_data.get('paths', {})
    matched_paths = {path: ops for path, ops in paths.items() if path.find(f"/{module_name}/") != -1}

    return {
        path: {method: _build_operation_info(details) for method, details in operations.items()}
        for path, operations in matched_paths.items()
    }

def show_single_path(resolved_data, module_name, path):
    if not module_name:
        raise ValueError("Module name must be provided")

    paths = resolved_data.get('paths', {})
    normalized_path = path if path.startswith('/') else f'/{path}'

    for full_path, operations in paths.items():
        if full_path.find(f"/{module_name}/") == -1:
            continue
        if full_path.endswith(normalized_path):
            return {full_path: {method: _build_operation_info(details) for method, details in operations.items()}}

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

    return _resolve(formattedEnums)

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
