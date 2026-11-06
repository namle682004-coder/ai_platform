"""Run provenance: dataset hash and code version recorded with every benchmark run."""

from __future__ import annotations

import hashlib
import subprocess
from typing import Optional


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit() -> Optional[str]:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            dirty = subprocess.run(["git", "status", "--porcelain"], stdout=subprocess.PIPE, text=True, check=False)
            return res.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except Exception:
        pass
    return "untracked"
