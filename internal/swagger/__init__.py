from services.params import swagger_version

from .client import get_swagger_json_url, load_json
from .parser import get_module_names, show_enums, show_paths, show_single_path


def get_enums(version: swagger_version):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")

    resolved_data = load_json(url)
    return show_enums(resolved_data)


def get_enum(version: swagger_version, enum_name: str):
    if not enum_name:
        raise ValueError("Enum name must be provided")

    enums = get_enums(version)

    if enum_name not in enums:
        raise ValueError(f"Enum '{enum_name}' not found")

    return enums[enum_name]


def get_paths(version: swagger_version, module_name: str):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")

    if not module_name:
        raise ValueError("Module name must be provided")

    resolved_data = load_json(url)
    return show_paths(resolved_data, module_name)


def get_path(version: swagger_version, module_name: str, path: str):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")

    if not module_name:
        raise ValueError("Module name must be provided")

    if not path:
        raise ValueError("Path must be provided")

    resolved_data = load_json(url)
    return show_single_path(resolved_data, module_name, path)


def get_modules(version: swagger_version):
    url = get_swagger_json_url(version)

    if not url:
        raise ValueError(f"URL for version {version} not found in environment variables")

    resolved_data = load_json(url)
    return get_module_names(resolved_data)


__all__ = ["get_enums", "get_enum", "get_paths", "get_path", "get_modules"]
