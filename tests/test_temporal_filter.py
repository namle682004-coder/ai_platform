"""
Unit test suite for Audit Item 6: Temporal Compliance Filter in Qdrant Adapter.
Covers:
- Vấn đề 1: Retrospective query with as_of_date does NOT exclude documents with current status EXPIRED/SUPERSEDED.
- Vấn đề 2: Current query excludes future effective documents (effective_from > now) as well as past expired documents.
- Vấn đề 3: Missing date fields (timeless documents) pass through without being blocked by must_not ranges.
- Resilient date format normalization (supports DD/MM/YYYY and YYYY-MM-DD).
- Invalidation of never-in-force documents (DRAFT, CANCELLED) during retrospective audit.
"""

from datetime import datetime, timezone
import pytest
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter


@pytest.fixture
def adapter():
    return QdrantVectorStoreAdapter(
        base_url="http://mock-qdrant:6333",
        collection_name="test_collection",
    )


def test_retrospective_filter_does_not_exclude_currently_expired_docs(adapter):
    """
    Audit Item 6 Vấn đề 1:
    When as_of_date is provided (retrospective query), documents that are CURRENTLY expired
    must NOT be excluded by an 'effective_status in [EXPIRED...]' filter.
    Only historical boundaries apply.
    """
    filters = adapter._build_filter_conditions(
        tenant_id="tenant_a",
        effective_status="ACTIVE",  # Default caller value
        as_of_date="2023-01-15",
    )

    must_not_clauses = []
    for cond in filters:
        if "must_not" in cond:
            must_not_clauses.extend(cond["must_not"])

    # 1. MUST NOT have status exclusion for EXPIRED or HET_HIEU_LUC
    status_must_nots = [
        c for c in must_not_clauses if c.get("key") == "effective_status"
    ]
    if status_must_nots:
        excluded_statuses = status_must_nots[0]["match"]["any"]
        assert "EXPIRED" not in excluded_statuses, "Retrospective query must not exclude currently EXPIRED documents"
        assert "HET_HIEU_LUC" not in excluded_statuses
        assert "SUPERSEDED" not in excluded_statuses
        # But documents that were never in force should be excluded
        assert "DRAFT" in excluded_statuses
        assert "CANCELLED" in excluded_statuses

    # 2. MUST have temporal range exclusions for as_of_date
    from_gt = next(c for c in must_not_clauses if c.get("key") == "effective_from")
    assert from_gt["range"]["gt"] == "2023-01-15"

    to_lt = next(c for c in must_not_clauses if c.get("key") == "effective_to")
    assert to_lt["range"]["lt"] == "2023-01-15"

    exp_lt = next(c for c in must_not_clauses if c.get("key") == "expiry_date")
    assert exp_lt["range"]["lt"] == "2023-01-15"


def test_retrospective_date_format_normalization(adapter):
    """
    Verify DD/MM/YYYY format is automatically normalized to standard ISO YYYY-MM-DD
    to guarantee correct lexicographical comparisons in Qdrant.
    """
    filters = adapter._build_filter_conditions(
        tenant_id="tenant_a",
        as_of_date="15/04/2023",
    )

    must_not_clauses = []
    for cond in filters:
        if "must_not" in cond:
            must_not_clauses.extend(cond["must_not"])

    from_gt = next(c for c in must_not_clauses if c.get("key") == "effective_from")
    assert from_gt["range"]["gt"] == "2023-04-15"


def test_current_active_query_excludes_future_and_expired_docs(adapter):
    """
    Audit Item 6 Vấn đề 2:
    When searching currently active documents (as_of_date=None, effective_status='ACTIVE'):
    1. Must exclude expired statuses.
    2. Must exclude future effective documents (effective_from > today, effective_date > today).
    3. Must exclude past expiry dates (expiry_date < today, effective_to < today).
    """
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filters = adapter._build_filter_conditions(
        tenant_id="tenant_b",
        effective_status="ACTIVE",
        as_of_date=None,
    )

    must_not_clauses = []
    for cond in filters:
        if "must_not" in cond:
            must_not_clauses.extend(cond["must_not"])

    # 1. Must exclude expired statuses
    status_clause = next(c for c in must_not_clauses if c.get("key") == "effective_status")
    assert "EXPIRED" in status_clause["match"]["any"]
    assert "HET_HIEU_LUC" in status_clause["match"]["any"]

    # 2. Must exclude future effective_from and effective_date
    from_clause = next(c for c in must_not_clauses if c.get("key") == "effective_from")
    assert from_clause["range"]["gt"] == today_iso

    date_clause = next(c for c in must_not_clauses if c.get("key") == "effective_date")
    assert date_clause["range"]["gt"] == today_iso

    # 3. Must exclude past expiry_date and effective_to
    exp_clause = next(c for c in must_not_clauses if c.get("key") == "expiry_date")
    assert exp_clause["range"]["lt"] == today_iso

    to_clause = next(c for c in must_not_clauses if c.get("key") == "effective_to")
    assert to_clause["range"]["lt"] == today_iso


def test_explicit_non_active_status_filter(adapter):
    """When an explicit status like 'DRAFT' or 'ARCHIVED' is queried, it should match that exact status."""
    filters = adapter._build_filter_conditions(
        tenant_id="tenant_c",
        effective_status="ARCHIVED",
        as_of_date=None,
    )

    status_match = next(f for f in filters if f.get("key") == "effective_status")
    assert status_match["match"]["value"] == "ARCHIVED"


def test_missing_date_fields_pass_through_semantic():
    """
    Audit Item 6 Vấn đề 3:
    Simulates Qdrant's evaluation engine for missing fields.
    In Qdrant, if a payload does NOT contain effective_from or effective_to:
    The range query evaluates to False. Under must_not, this evaluates to:
    NOT (False) == True (document passes through).
    """
    def simulate_qdrant_must_not_filter(payload, must_not_conditions):
        for cond in must_not_conditions:
            key = cond["key"]
            if key not in payload or payload[key] is None:
                # Qdrant behavior: missing field never matches range or match filter
                continue
            val = payload[key]
            if "match" in cond and "any" in cond["match"]:
                if val in cond["match"]["any"]:
                    return False  # Excluded!
            if "range" in cond:
                r = cond["range"]
                if "gt" in r and val > r["gt"]:
                    return False  # Excluded!
                if "lt" in r and val < r["lt"]:
                    return False  # Excluded!
        return True  # Passes through

    must_not_rules = [
        {"key": "effective_status", "match": {"any": ["EXPIRED", "HET_HIEU_LUC"]}},
        {"key": "effective_from", "range": {"gt": "2026-10-20"}},
        {"key": "effective_to", "range": {"lt": "2026-10-20"}},
    ]

    # Doc 1: Timeless document (general policy, no dates) -> PASS
    doc_timeless = {"effective_status": "ACTIVE"}
    assert simulate_qdrant_must_not_filter(doc_timeless, must_not_rules) is True

    # Doc 2: Future document -> EXCLUDED
    doc_future = {"effective_status": "ACTIVE", "effective_from": "2027-01-01"}
    assert simulate_qdrant_must_not_filter(doc_future, must_not_rules) is False

    # Doc 3: Expired document -> EXCLUDED
    doc_expired = {"effective_status": "EXPIRED", "effective_from": "2020-01-01", "effective_to": "2024-01-01"}
    assert simulate_qdrant_must_not_filter(doc_expired, must_not_rules) is False

    # Doc 4: Currently active document -> PASS
    doc_active = {"effective_status": "ACTIVE", "effective_from": "2024-01-01", "effective_to": "2030-01-01"}
    assert simulate_qdrant_must_not_filter(doc_active, must_not_rules) is True
