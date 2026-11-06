"""
Conversation identifiers.

A conversation is named by an opaque random UUID (v4), the way chat products put it in their URLs
(/c/{uuid}): it tells nothing about when it was made or by whom and cannot be guessed from another one.

Conversations created before that carry readable ids ("sess_<time>_<rand>"). They are never shown as
such: their public id is a UUID v5 - a SHA-1 hash of the id under a fixed namespace - which the API
resolves back to the conversation. Stored records are left as they are.
"""

from __future__ import annotations

import uuid
from typing import Iterable, Optional

# Fixed namespace of public ids; changing it would break every link to an older conversation.
PUBLIC_ID_NAMESPACE = uuid.UUID("6f0b8c52-3f1e-5d7a-9a43-2c1e7b9d4a10")


def new_session_id() -> str:
    return str(uuid.uuid4())


def as_uuid(value: str) -> Optional[str]:
    """The canonical (lower-case, hyphenated) form of a UUID string, or None for anything else."""
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (ValueError, AttributeError, TypeError):
        return None


def public_session_id(session_id: str) -> str:
    """The id a URL shows for a conversation: the id itself when it is a UUID, else its UUID v5 hash."""
    return as_uuid(session_id) or str(uuid.uuid5(PUBLIC_ID_NAMESPACE, str(session_id)))


def match_public_id(public_id: str, session_ids: Iterable[str]) -> Optional[str]:
    """The session id among `session_ids` whose public id is `public_id`."""
    wanted = as_uuid(public_id)
    if wanted is None:
        return None
    return next((sid for sid in session_ids if public_session_id(sid) == wanted), None)
