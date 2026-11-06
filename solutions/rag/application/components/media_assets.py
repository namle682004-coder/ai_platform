"""
Images of documents: where they are stored, how passages reference them, how answers show them.

At ingestion the parsers anchor every embedded image right after its paragraph as a markdown tag and
return its bytes; the bytes are stored in MinIO under the document's tenant and the tag is rewritten to
a stable, host-independent path ``{prefix}/{doc_id}/{hash}.{ext}``. Passages indexed before images were
stored carry a placeholder host; those are mapped to the same path from the passage's doc_id.

A browser ``<img>`` request carries no tenant headers, so the URLs placed in answers are capability
URLs: an HMAC over tenant, document and file (and an expiry when configured), verified by the media
endpoint before it streams the object from MinIO. Nothing here knows a particular document.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote, urlsplit

# A stored image file: content hash (16 hex) + extension, as the parsers name them.
FILE_RE = r"[0-9a-f]{16}\.[a-z0-9]{2,5}"
_LEGACY_URL_RE = re.compile(rf"https?://storage\.enterprise\.internal/media/({FILE_RE})")
_IMAGE_TAG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
IMAGE_TYPES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff", "emf": "image/emf", "wmf": "image/wmf",
}
_SAFE_ID_RE = re.compile(r"^[\w.-]{1,128}$")
_FILE_ONLY_RE = re.compile(rf"^{FILE_RE}$")


def object_key(tenant_id: str, doc_id: str, filename: str) -> str:
    return f"media/{tenant_id}/{doc_id}/{filename}"


def doc_prefix(tenant_id: str, doc_id: str) -> str:
    return f"media/{tenant_id}/{doc_id}/"


def content_type(filename: str) -> str:
    return IMAGE_TYPES.get(filename.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def valid_ref(doc_id: str, filename: str) -> bool:
    """Path components of a media request: no traversal, only image files named by content hash."""
    return bool(_SAFE_ID_RE.match(doc_id or "") and _FILE_ONLY_RE.match(filename or "")
                and filename.rsplit(".", 1)[-1] in IMAGE_TYPES)


def media_path(prefix: str, doc_id: str, filename: str) -> str:
    return f"{prefix.rstrip('/')}/{quote(doc_id)}/{filename}"


def rewrite_legacy_urls(text: str, prefix: str, doc_id: str) -> str:
    """Placeholder-host image URLs of a passage -> the served path of that document's image."""
    return _LEGACY_URL_RE.sub(lambda m: media_path(prefix, doc_id, m.group(1)), text or "")


# ------------------------------------------------------------------ signing
def signature(secret: str, tenant_id: str, doc_id: str, filename: str, expires: int) -> str:
    msg = f"{tenant_id}\n{doc_id}\n{filename}\n{expires}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]


def signed_url(secret: str, prefix: str, tenant_id: str, doc_id: str, filename: str, ttl_seconds: int = 0,
               now: Optional[float] = None) -> str:
    expires = int((now or time.time()) + ttl_seconds) if ttl_seconds > 0 else 0
    sig = signature(secret, tenant_id, doc_id, filename, expires)
    query = f"t={quote(tenant_id)}&s={sig}" + (f"&e={expires}" if expires else "")
    return f"{media_path(prefix, doc_id, filename)}?{query}"


def verify(secret: str, tenant_id: str, doc_id: str, filename: str, sig: str, expires: int,
           now: Optional[float] = None) -> bool:
    if not (secret and tenant_id and sig):
        return False
    if expires and expires < (now or time.time()):
        return False
    return hmac.compare_digest(signature(secret, tenant_id, doc_id, filename, expires), sig)


# ------------------------------------------------------------------ passages & answers
@dataclass
class PassageImage:
    alt: str
    doc_id: str
    tenant_id: str
    filename: str


def _ref_of(url: str, prefix: str) -> Optional[Tuple[Optional[str], str]]:
    """(doc_id or None for a placeholder URL, filename) of an image URL that points to a stored image."""
    m = _LEGACY_URL_RE.fullmatch(url)
    if m:
        return None, m.group(1)
    parts = urlsplit(url)
    path = parts.path
    head = prefix.rstrip("/") + "/"
    if not path.startswith(head):
        return None
    rest = path[len(head):].split("/")
    if len(rest) != 2 or not valid_ref(rest[0], rest[1]):
        return None
    return rest[0], rest[1]


def passage_images(passages: Iterable[Dict[str, Any]], prefix: str) -> List[PassageImage]:
    """Stored images referenced by passages (citation dicts or chunk payloads), in order, once each."""
    out: List[PassageImage] = []
    seen = set()
    for p in passages:
        payload = p.get("payload") if isinstance(p.get("payload"), dict) else p
        text = str(payload.get("text") or "")
        doc_id = str(payload.get("doc_id") or "")
        tenant = str(payload.get("tenant_id") or "")
        for m in _IMAGE_TAG_RE.finditer(text):
            ref = _ref_of(m.group(2), prefix)
            if not ref:
                continue
            ref_doc, filename = ref
            ref_doc = ref_doc or doc_id
            if not ref_doc or filename in seen:
                continue
            seen.add(filename)
            out.append(PassageImage(alt=m.group(1).strip() or "Ảnh minh họa", doc_id=ref_doc, tenant_id=tenant,
                                    filename=filename))
    return out


def shown_files(text: str, prefix: str) -> set:
    """Image files an answer already shows."""
    files = set()
    for m in _IMAGE_TAG_RE.finditer(text or ""):
        ref = _ref_of(m.group(2), prefix)
        if ref:
            files.add(ref[1])
    return files


def url_mapper(passages: Sequence[Dict[str, Any]], secret: str, prefix: str, ttl_seconds: int = 0,
               default_tenant: str = "") -> Callable[[str], str]:
    """
    Maps an image URL a passage contains (as the model copies it) to the signed URL the browser can load.
    The tenant signed is the one of the passage's document (shared-knowledge images live under it).
    """
    tenants: Dict[str, str] = {}
    for img in passage_images(passages, prefix):
        tenants.setdefault(img.filename, img.tenant_id or default_tenant)
    docs = {img.filename: img.doc_id for img in passage_images(passages, prefix)}

    def mapper(url: str) -> str:
        ref = _ref_of(url, prefix)
        if not ref or parse_qs(urlsplit(url).query).get("s"):
            return url
        doc_id, filename = ref
        doc_id = doc_id or docs.get(filename, "")
        tenant = tenants.get(filename, default_tenant)
        if not (doc_id and tenant):
            return url
        return signed_url(secret, prefix, tenant, doc_id, filename, ttl_seconds)

    return mapper


def images_section(images: Sequence[PassageImage], mapper: Callable[[str], str], prefix: str,
                   source_of: Optional[Dict[str, int]] = None) -> str:
    """Markdown block showing the images of the passages an answer is based on."""
    if not images:
        return ""
    lines = ["", "", "**Hình ảnh trong tài liệu:**", ""]
    for img in images:
        url = mapper(media_path(prefix, img.doc_id, img.filename))
        src = (source_of or {}).get(img.filename)
        lines.append(f"![{img.alt}]({url})" + (f"\n*({img.alt} – nguồn [{src}])*" if src else ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
