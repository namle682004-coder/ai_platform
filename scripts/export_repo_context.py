#!/usr/bin/env python3
"""
AIP Codebase Context Exporter (Repomix Native Adapter)
Bundles the entire AI Inference Platform architecture into a single, clean markdown context document.
"""

import os

EXCLUDE_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".idea", ".vscode",
    "node_modules", "dist", "build", ".gemini"
}

EXCLUDE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz"
}

EXCLUDE_FILES = {
    "package-lock.json", "poetry.lock", "uv.lock", "AIP_CODEBASE_CONTEXT.md"
}


def is_text_file(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    return ext not in EXCLUDE_EXTENSIONS


def bundle_codebase(root_dir: str, output_file: str):
    print(f"=== Repomix Adapter: Bundling AIP Codebase Context from {root_dir} ===")
    
    file_count = 0
    total_bytes = 0

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("# AI Inference Platform (AIP) - Complete Codebase Context\n\n")
        out.write("This document contains the consolidated codebase context for Antigravity & Claude AI Agents.\n\n")
        out.write("## Directory Tree & Included Artifacts\n\n")

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            for file in sorted(files):
                if file in EXCLUDE_FILES or not is_text_file(file):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    out.write(f"### File: `{rel_path}`\n\n")
                    out.write("```python\n" if rel_path.endswith(".py") else "```html\n" if rel_path.endswith(".html") else "```\n")
                    out.write(content)
                    out.write("\n```\n\n")

                    file_count += 1
                    total_bytes += len(content.encode("utf-8"))
                except Exception as e:
                    print(f"[Warning] Failed to read {rel_path}: {e}")

    size_kb = total_bytes / 1024
    print(f"=== Export Completed: {file_count} files bundled into {output_file} ({size_kb:.2f} KB) ===")


if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_path = os.path.join(project_root, "AIP_CODEBASE_CONTEXT.md")
    bundle_codebase(project_root, out_path)
