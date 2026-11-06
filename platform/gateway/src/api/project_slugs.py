"""
Human-readable project slugs for console URLs: /projects/{slug}/services/{service}.

A slug is derived from the project name (Vietnamese diacritics removed, kebab-case). Projects created
before slugs existed get theirs derived when they are listed, in creation order, so the result is
stable without rewriting stored records: the first project with a name keeps the plain slug and later
namesakes get "-2", "-3", ... New projects store their slug when they are created.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Set

# Path words that a project slug must never shadow. "shared" is the shared knowledge scope (tenant
# "global"), shown to everyone; the others are console routes or reserved for later use.
SHARED_PROJECT_SLUG = "shared"
SHARED_PROJECT_ID = "global"
RESERVED_PROJECT_SLUGS = frozenset({
    SHARED_PROJECT_SLUG, SHARED_PROJECT_ID, "new", "current", "settings", "projects", "services",
    "dashboard", "keys", "usage", "billing", "admin", "api", "v1",
})
MAX_SLUG_LENGTH = 48


def slugify(name: str) -> str:
    text = (name or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:MAX_SLUG_LENGTH].strip("-")
    return slug or "project"


def _claim(base: str, taken: Set[str]) -> str:
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def assign_slugs(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fills `slug` on every project of one owner (in place); stored slugs are kept as they are."""
    taken: Set[str] = set(RESERVED_PROJECT_SLUGS)
    taken.update(p["slug"] for p in projects if p.get("slug"))
    pending = [p for p in projects if not p.get("slug")]
    for project in sorted(pending, key=lambda p: (str(p.get("created_at") or ""), str(p.get("project_id") or ""))):
        project["slug"] = _claim(slugify(project.get("project_name") or ""), taken)
    return projects


def new_project_slug(name: str, existing: Iterable[Dict[str, Any]]) -> str:
    """Slug for a project about to be created next to `existing` (whose slugs are derived first)."""
    taken: Set[str] = set(RESERVED_PROJECT_SLUGS)
    taken.update(p["slug"] for p in assign_slugs([dict(p) for p in existing]))
    return _claim(slugify(name), taken)
