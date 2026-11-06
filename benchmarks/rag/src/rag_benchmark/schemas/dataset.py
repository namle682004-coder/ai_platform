"""
Pydantic V2 Schemas for Enterprise RAG Golden Benchmark Dataset.
Compliant with Track A (Fixed Context) & Track B (End-to-End) requirements.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    SINGLE_HOP = "single_hop"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    SUMMARIZATION = "summarization"
    UNANSWERABLE = "unanswerable"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ReviewStatus(str, Enum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class EvidenceChunk(BaseModel):
    """Specific grounded chunk required to prove the answer (used for Retrieval Recall@K)."""
    document_id: str = Field(..., description="Target document ID or title")
    chunk_id: Optional[str] = Field(None, description="Granular chunk identifier")
    quote: str = Field(..., description="Exact textual evidence snippet")
    relevance: str = Field(default="direct", description="relevance level: direct, supporting, indirect")


class ReferenceContext(BaseModel):
    """Context block provided to Track A (Fixed-context generation)."""
    document_id: str
    chunk_id: Optional[str] = None
    text: str


class ReviewMetadata(BaseModel):
    """Audit metadata ensuring only peer-reviewed enterprise cases enter official benchmark runs."""
    status: ReviewStatus = Field(default=ReviewStatus.APPROVED)
    reviewer: Optional[str] = Field(default="human_expert")
    notes: Optional[str] = Field(default="")


class SessionMode(str, Enum):
    SINGLE = "single"  # one question
    MULTI_TURN = "multi_turn"  # `turns` asked in order in one conversation; graded as a whole
    SEPARATE_SESSIONS = "separate_sessions"  # each turn in a fresh conversation; every one must pass


class GoldenCase(BaseModel):
    """A single gold-standard test case in the Golden Benchmark Dataset (JSONL row)."""
    case_id: str = Field(..., description="Unique case identifier e.g. internal_hr_0001")
    dataset_version: str = Field(default="1.0.0")
    source_dataset: str = Field(default="enterprise_internal")
    domain: str = Field(default="general")
    question: str = Field(..., description="User query / prompt")
    question_type: QuestionType = Field(default=QuestionType.SINGLE_HOP)
    difficulty: Difficulty = Field(default=Difficulty.EASY)
    answerable: bool = Field(default=True, description="True if answerable from corpus, False if OOD/unanswerable")
    expected_answer: str = Field(..., description="Gold-standard ground truth answer or refusal expectation")
    required_facts: List[str] = Field(default_factory=list, description="Key factual assertions that must appear in the answer")
    evidence: List[EvidenceChunk] = Field(default_factory=list, description="Ground truth evidence chunks for retrieval metrics")
    reference_context: List[ReferenceContext] = Field(default_factory=list, description="Gold context supplied to Track A")
    tags: List[str] = Field(default_factory=list)
    review: ReviewMetadata = Field(default_factory=ReviewMetadata)

    # Acceptance-suite fields (end-to-end suite runner, judge rubric, go-live gate).
    group: str = Field(default="", description="Test group / problem class, the unit of per-group pass rates")
    category: str = Field(default="", description="Human-readable name of the group")
    session_mode: SessionMode = Field(default=SessionMode.SINGLE)
    turns: List[str] = Field(default_factory=list, description="Conversation turns; empty = [question]")
    required_identifiers: List[str] = Field(
        default_factory=list, description="Codes / document numbers the graded answer must contain verbatim"
    )
    fail_conditions: str = Field(default="", description="What makes the answer fail (judge rubric)")
    must_pass: bool = Field(default=False, description="Critical case: any failure blocks go-live")

    def is_approved(self) -> bool:
        return self.review.status == ReviewStatus.APPROVED

    def conversation(self) -> List[str]:
        return list(self.turns) or [self.question]

    def evidence_needles(self) -> List[str]:
        """
        Strings the supporting passages must contain: required identifiers, else the short required facts,
        else evidence quotes (a long verbatim quote rarely survives chunking / paraphrase intact).
        """
        return (list(self.required_identifiers) or list(self.required_facts)
                or [e.quote for e in self.evidence if e.quote])
