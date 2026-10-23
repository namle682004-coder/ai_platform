"""
BGE inference engine: BGE-M3 dense/sparse embeddings and BGE-Reranker-v2-m3 cross-encoder scores.

Model calls are synchronous GPU work. Each model is guarded by its own lock and the
server runs them in a worker thread so the asyncio event loop is never blocked.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

try:
    from .config import EmbeddingServerSettings
except ImportError:  # executed as a script from the runtime directory
    from config import EmbeddingServerSettings

logger = logging.getLogger("aip-embedding-server.engine")


class ModelNotReadyError(RuntimeError):
    """Raised when inference is requested before the weights finished loading."""


class BgeEngine:
    def __init__(self, settings: EmbeddingServerSettings) -> None:
        self.settings = settings
        self._embedder: Any = None
        self._reranker: Any = None
        self._embed_lock = threading.Lock()
        self._rerank_lock = threading.Lock()
        self.load_error: Optional[str] = None
        self.loaded_at: Optional[float] = None

    @property
    def ready(self) -> bool:
        return self._embedder is not None and self._reranker is not None

    def load(self) -> None:
        """Load both models. Failure is recorded (readiness stays false) instead of crashing the process."""
        try:
            from FlagEmbedding import BGEM3FlagModel, FlagReranker

            t0 = time.perf_counter()
            self._embedder = BGEM3FlagModel(self.settings.embedding_model_path, use_fp16=self.settings.use_fp16)
            self._reranker = FlagReranker(self.settings.reranker_model_path, use_fp16=self.settings.use_fp16)
            self.loaded_at = time.time()
            self.load_error = None
            logger.info(
                "Loaded BGE-M3 (%s) and reranker (%s) in %.1fs",
                self.settings.embedding_model_path,
                self.settings.reranker_model_path,
                time.perf_counter() - t0,
            )
        except Exception as exc:  # surfaced through /health/ready
            self.load_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Model loading failed")

    def embed(self, texts: List[str], return_sparse: bool = False) -> Dict[str, Any]:
        if self._embedder is None:
            raise ModelNotReadyError(self.load_error or "Embedding model is still loading")
        with self._embed_lock:
            out = self._embedder.encode(
                texts,
                batch_size=self.settings.embedding_batch_size,
                max_length=self.settings.embedding_max_length,
                return_dense=True,
                return_sparse=return_sparse,
                return_colbert_vecs=False,
            )
        dense = [vec.tolist() for vec in out["dense_vecs"]]
        sparse: Optional[List[Dict[str, List]]] = None
        if return_sparse:
            sparse = []
            for weights in out["lexical_weights"]:
                indices = [int(token_id) for token_id in weights.keys()]
                values = [float(w) for w in weights.values()]
                sparse.append({"indices": indices, "values": values})
        token_count = sum(len(self._embedder.tokenizer.encode(t, add_special_tokens=False)) for t in texts)
        return {"dense": dense, "sparse": sparse, "prompt_tokens": token_count}

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        if self._reranker is None:
            raise ModelNotReadyError(self.load_error or "Reranker model is still loading")
        pairs = [[query, doc] for doc in documents]
        with self._rerank_lock:
            scores = self._reranker.compute_score(
                pairs,
                normalize=True,  # sigmoid -> [0, 1], the scale the RAG confidence gate is calibrated on
                batch_size=self.settings.reranker_batch_size,
                max_length=self.settings.reranker_max_length,
            )
        if isinstance(scores, (int, float)):
            scores = [scores]
        return [float(s) for s in scores]

    def status(self) -> Dict[str, Any]:
        gpu: Dict[str, Any] = {}
        try:
            import torch

            if torch.cuda.is_available():
                gpu = {
                    "device": torch.cuda.get_device_name(0),
                    "memory_allocated_mb": round(torch.cuda.memory_allocated(0) / 1024**2, 1),
                }
        except Exception:
            gpu = {}
        return {
            "status": "ready" if self.ready else ("failed" if self.load_error else "loading"),
            "embedding_model": self.settings.embedding_model_path,
            "reranker_model": self.settings.reranker_model_path,
            "loaded_at": self.loaded_at,
            "error": self.load_error,
            "gpu": gpu,
        }
