import sys
from pathlib import Path

# Ensure generated proto directory is in sys.path for protoc-generated imports (e.g. import common_pb2)
_GENERATED_DIR = str(Path(__file__).resolve().parent)
if _GENERATED_DIR not in sys.path:
    sys.path.insert(0, _GENERATED_DIR)
