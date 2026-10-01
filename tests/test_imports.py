"""
Import verification test for all Data-Plane app.py entrypoints.
"""

import sys
import os

BASE_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform"
if os.path.join(BASE_DIR, "packages/common") not in sys.path:
    sys.path.insert(0, os.path.join(BASE_DIR, "packages/common"))
if os.path.join(BASE_DIR, "packages/contracts") not in sys.path:
    sys.path.insert(0, os.path.join(BASE_DIR, "packages/contracts"))

def test_all_data_plane_imports():
    services = ["vllm-engine", "translation-server", "stt-server", "tts-adapter", "ocr-server"]
    for srv in services:
        path = os.path.join(BASE_DIR, "apps/data-plane", srv)
        sys.path.insert(0, path)
        try:
            mod = __import__("app")
            assert mod is not None
        finally:
            sys.path.pop(0)
            sys.modules.pop("app", None)
            sys.modules.pop("grpc_server", None)
            sys.modules.pop("config", None)
