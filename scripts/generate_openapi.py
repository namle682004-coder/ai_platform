import json
import os
import sys

# Ensure PYTHONPATH includes services & packages
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages"))

from gateway.main import app


def export_openapi():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "openapi")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "openapi.json")

    openapi_schema = app.openapi()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"[OpenAPI Exporter] Successfully exported OpenAPI v3.1 schema to: {output_file}")


if __name__ == "__main__":
    export_openapi()
