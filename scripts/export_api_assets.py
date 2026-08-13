import json
import os
import sys

# Ensure root import paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages")))

from gateway.main import app

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "openapi"))
os.makedirs(OUT_DIR, exist_ok=True)


def export_openapi_json():
    schema = app.openapi()
    openapi_path = os.path.join(OUT_DIR, "openapi.json")
    with open(openapi_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"[Export] OpenAPI Schema v3.1 saved to: {openapi_path}")
    return schema


def export_postman_collection(schema):
    collection = {
        "info": {
            "name": "AI Inference Platform (AIP) API Collection",
            "description": "Enterprise On-Premise AI Inference Middleware Platform Postman Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": []
    }

    paths = schema.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            item = {
                "name": details.get("summary") or f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{api_key}}", "type": "text"},
                        {"key": "Content-Type", "value": "application/json", "type": "text"}
                    ],
                    "url": {
                        "raw": "{{base_url}}" + path,
                        "host": ["{{base_url}}"],
                        "path": path.strip("/").split("/")
                    }
                }
            }
            collection["item"].append(item)

    postman_path = os.path.join(OUT_DIR, "aip_postman_collection.json")
    with open(postman_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    print(f"[Export] Postman Collection v2.1 saved to: {postman_path}")


def export_html_documentation(schema):
    html_content = """<!DOCTYPE html>
<html>
  <head>
    <title>AI Inference Platform - API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
      body { margin: 0; padding: 0; }
    </style>
  </head>
  <body>
    <redoc spec-url='openapi.json'></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"> </script>
  </body>
</html>
"""
    html_path = os.path.join(OUT_DIR, "aip_documentation.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[Export] Standalone Redoc HTML Documentation saved to: {html_path}")


def main():
    print("=== AIP API Export Assets Generator ===")
    schema = export_openapi_json()
    export_postman_collection(schema)
    export_html_documentation(schema)
    print("=== Export Completed Successfully ===")


if __name__ == "__main__":
    main()
