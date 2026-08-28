import os

import jsonref
import requests

from internal.env import load_env
from services.params import swagger_version

load_env()


def get_swagger_json_url(version: swagger_version):
    if version == swagger_version.v1:
        return os.getenv("SWAGGER_JSON_V1_URL")
    elif version == swagger_version.v2:
        return os.getenv("SWAGGER_JSON_V2_URL")
    else:
        raise ValueError("Invalid swagger version")


def load_json(url: str):
    response = requests.get(url)
    # Lazy proxies (jsonref's default): $refs are only dereferenced when the
    # caller actually accesses that part of the document, instead of eagerly
    # resolving every $ref in the whole spec up front.
    return jsonref.loads(response.text, base_uri=url)
