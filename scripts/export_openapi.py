"""Export deterministic OpenAPI schema to docs/openapi.json."""

import json
import sys
from pathlib import Path

# Ensure backend package is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def export_openapi() -> Path:
    """Generate and write deterministic docs/openapi.json."""
    output_path = REPO_ROOT / "docs" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    openapi_schema = app.openapi()
    # Sort keys recursively via json.dumps(sort_keys=True)
    schema_json = json.dumps(openapi_schema, indent=2, sort_keys=True) + "\n"

    output_path.write_text(schema_json, encoding="utf-8")
    paths_count = len(openapi_schema.get("paths", {}))
    print(f"Exported OpenAPI schema ({paths_count} paths) to {output_path}")
    return output_path


if __name__ == "__main__":
    export_openapi()
