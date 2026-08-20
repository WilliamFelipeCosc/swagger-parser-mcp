"""Dev shim: `python main.py` keeps working from a checkout.

The installed console script is `swagger-parser-mcp` (see pyproject.toml), which
calls the same `services.cli:main`. `mcp` is re-exported at module level so
`fastmcp run main.py:mcp` — and fastmcp.json's `source.entrypoint` — resolve.
"""

from services.cli import main
from services.mcp.server import mcp  # noqa: F401

if __name__ == "__main__":
    main()
