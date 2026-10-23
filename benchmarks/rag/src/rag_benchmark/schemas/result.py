"""
Pydantic V2 Schemas for Benchmark Execution Runs & Evaluation Metrics.
Supports auditing, metric serialization, and comparative reporting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RetrievedChunkResult(BaseModel):
    document_id: str
    chunk_id: Optional[str] = None
    title: Optional[str] = None
    score: float = 0.0
    rank: int = 1
    excerpt: Optional[str] = None


class RetrievalExecution(BaseModel):
    retrieved_chunks: List[RetrievedChunkResult] = Field(default_factory=list)
    latency_ms: float = 0.0


class GenerationExecution(BaseModel):
    answer: str = ""
    latency_ms: float = 0.0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    citations: List[Dict[str, Any]] = Field(default_factory=list)


class EvaluationScores(BaseModel):
    # Standard IR Metrics via ranx (Track B)
    ndcg_at_10: Optional[float] = None
    recall_at_1: Optional[float] = None
    recall_at_3: Optional[float] = None
    recall_at_5: Optional[float] = None
    mrr_at_5: Optional[float] = None
    precision_at_3: Optional[float] = None
    hit_at_3: Optional[float] = None

    # Generation Metrics (Track A & Track B)
    answer_correctness: Optional[float] = None
    completeness: Optional[float] = None
    faithfulness: Optional[float] = None
    answer_relevance: Optional[float] = None
    semantic_correctness: Optional[float] = None
    citation_precision: Optional[float] = None
    abstention_quality: Optional[float] = None
    judge_reasoning: Optional[str] = None

    details: Dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    """Complete audited serialized record of an individual test case run."""
    run_id: str
    case_id: str
    system_id: str
    track: str = Field(..., description="fixed_context or end_to_end")
    is_answerable: bool = True
    config_hash: Optional[str] = None
    git_commit: Optional[str] = None
    dataset_sha256: Optional[str] = None
    evaluator_version: str = "2.0.0-ranx-audited"
    model: Dict[str, Any] = Field(default_factory=dict)
    retrieval: Optional[RetrievalExecution] = None
    generation: Optional[GenerationExecution] = None
    evaluation: EvaluationScores = Field(default_factory=EvaluationScores)
    status: str = "success"  # success, error, timeout
    error: Optional[str] = None
