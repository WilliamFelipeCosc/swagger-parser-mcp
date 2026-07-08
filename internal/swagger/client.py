import os

import jsonref
import requests
from dotenv import load_dotenv

from services.params import swagger_version

load_dotenv()


def get_swagger_json_url(version: swagger_version):
    if version == swagger_version.v1:
        return os.getenv("SWAGGER_JSON_V1_URL")
    elif version == swagger_version.v2:
        return os.getenv("SWAGGER_JSON_V2_URL")
    else:
        raise ValueError("Invalid swagger version")


def load_json(url: str):
    response = requests.get(url)
    return jsonref.loads(response.text, base_uri=url)
