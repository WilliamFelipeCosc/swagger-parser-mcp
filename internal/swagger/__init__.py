from services.params import swagger_version

from .client import get_swagger_json_url, load_json
from .parser import get_module_names, show_enums, show_paths


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


__all__ = ["get_enums", "get_paths", "get_modules"]
