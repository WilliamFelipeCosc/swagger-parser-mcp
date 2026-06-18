
import requests
import jsonref
from pprint import pprint

def show_paths(resolved_data, module_name=None):
    paths = resolved_data.get('paths', {})

    if module_name:
        print(f"Paths for module: {module_name}")
        paths = {path: ops for path, ops in paths.items() if path.find(f"/{module_name}/") != -1}

    for path, operations in paths.items():
        print(f"Path: {path}")
        for method, details in operations.items():
            print(f"  Method: {method.upper()}")
            print(f"    Summary: {details.get('summary', 'No summary provided')}")
            print(f"    Tags: {details.get('tags', 'No tags provided')}")
            
            parameters = details.get('parameters', [])
            requestBody = details.get('requestBody', {})
            responses = details.get('responses', {})

            for param in parameters:
                print(f"    Parameter: {param.get('name', 'Unnamed')} (in: {param.get('in', 'unknown')})")
            if requestBody:
                print(f"    Request Body: {requestBody}")
            for status_code, response in responses.items():
                print(f"    Response {status_code}: {response.get('description', 'No description provided')}")
                print(f"      Schema: {response.get('content', {}).get('application/json', {}).get('schema', 'No schema provided')}")

def show_enums(resolved_data):
    components = resolved_data.get('components', {})
    schemas = components.get('schemas', {})
    enums = {key: value for key, value in schemas.items() if 'enum' in value}
    
    print("Enums found in components:")
    for enum_name, enum_details in enums.items():
        print(f"Enum Name: {enum_name}")
        print(f"  Values: {enum_details['enum']}")
        print(f"  Description: {enum_details.get('description', 'No description provided')}")
        print()

def main():
  response = requests.get("https://api-homolog.b2.club/swagger/v2/swagger.json")
  # response = requests.get("https://api-homolog.b2.club/swagger/v1/swagger.json")

  resolved_data = jsonref.loads(response.text, base_uri="https://api-homolog.b2.club/swagger/v2/swagger.json")

  # show_paths(resolved_data, "Dashboard")
  show_enums(resolved_data)
  

if __name__ == '__main__':
    main()