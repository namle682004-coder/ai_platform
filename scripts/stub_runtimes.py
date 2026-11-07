"""
Stand-in model runtimes (chat, embedding, rerank) speaking the llama-server HTTP API, to exercise the RAG
service end to end without a GPU: load tests, overload protection, ingestion under load.

Each runtime has a fixed number of slots, like `llama-server --parallel N`: requests beyond them wait in a
queue, so the RAG service meets the same back-pressure as on the model host. Latencies are configurable to
match the measured host (defaults: Qwen2.5-7B Q4 on a TITAN Xp, from the iter5 run).

    python scripts/stub_runtimes.py [--chat-port 8011 --embed-port 8012 --rerank-port 8013]
        [--chat-slots 2] [--prefill 1.2] [--tokens-per-s 25] [--answer-tokens 120]
        [--embed-ms 40] [--rerank-ms-per-doc 6] [--fail-rate 0.0]

Point the RAG service at it: RAG_LLM_URL=http://<host>:8011/v1 RAG_EMBEDDING_URL=http://<host>:8012/v1
RAG_RERANKER_URL=http://<host>:8013/v1 (and EMBEDDING_DIM to --dim). Answers are placeholders: this measures
the system's behaviour under load, never answer quality.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import random
import re
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

ANALYZER_MARKER = "[QUERY_ANALYZER]"
WORD = re.compile(r"\w+", re.UNICODE)


def _vector(text: str, dim: int) -> List[float]:
    """Deterministic bag-of-words embedding: shared words give similar vectors."""
    v = [0.0] * dim
    for w in WORD.findall(text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 20) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _overlap(query: str, doc: str) -> float:
    q, d = set(WORD.findall(query.lower())), set(WORD.findall(doc.lower()))
    return len(q & d) / (len(q) or 1)


class Stats:
    def __init__(self) -> None:
        self.calls: Dict[str, int] = {}
        self.max_queue: Dict[str, int] = {}
        self.waiting: Dict[str, int] = {}

    def enter(self, kind: str) -> None:
        self.calls[kind] = self.calls.get(kind, 0) + 1
        self.waiting[kind] = self.waiting.get(kind, 0) + 1
        self.max_queue[kind] = max(self.max_queue.get(kind, 0), self.waiting[kind])

    def leave(self, kind: str) -> None:
        self.waiting[kind] -= 1


def build_app(kind: str, args: argparse.Namespace, stats: Stats) -> FastAPI:
    app = FastAPI()
    slots = asyncio.Semaphore(args.chat_slots if kind == "chat" else args.aux_slots)
    total_slots = args.chat_slots if kind == "chat" else args.aux_slots

    async def maybe_fail() -> Any:
        if args.fail_rate and random.random() < args.fail_rate:
            return JSONResponse({"error": {"message": "injected failure", "code": 500}}, status_code=500)
        return None

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "kind": kind, "stats": {"calls": stats.calls, "max_queue": stats.max_queue}}

    @app.get("/props")
    async def props() -> Dict[str, Any]:
        return {"total_slots": total_slots, "default_generation_settings": {"n_ctx": args.n_ctx}}

    @app.post("/tokenize")
    async def tokenize(req: Request) -> Dict[str, Any]:
        body = await req.json()
        text = body.get("content") or body.get("prompt") or ""
        return {"tokens": list(range(max(1, len(text) // 4)))}

    @app.post("/v1/embeddings")
    async def embeddings(req: Request) -> Any:
        body = await req.json()
        inputs = body.get("input")
        inputs = [inputs] if isinstance(inputs, str) else list(inputs or [])
        stats.enter("embedding")
        try:
            async with slots:
                if (fail := await maybe_fail()) is not None:
                    return fail
                await asyncio.sleep(args.embed_ms / 1000 * max(1, len(inputs)))
                return {"data": [{"index": i, "embedding": _vector(t, args.dim)} for i, t in enumerate(inputs)]}
        finally:
            stats.leave("embedding")

    @app.post("/v1/rerank")
    async def rerank(req: Request) -> Any:
        body = await req.json()
        docs = body.get("documents") or []
        stats.enter("rerank")
        try:
            async with slots:
                if (fail := await maybe_fail()) is not None:
                    return fail
                await asyncio.sleep(args.rerank_ms_per_doc / 1000 * max(1, len(docs)))
                return {"results": [{"index": i, "relevance_score": 6 * _overlap(body.get("query", ""), d) - 3}
                                    for i, d in enumerate(docs)]}
        finally:
            stats.leave("rerank")

    @app.post("/v1/chat/completions")
    async def chat(req: Request) -> Any:
        body = await req.json()
        messages = body.get("messages") or []
        system = str(messages[0].get("content", "")) if messages else ""
        last_user = next((str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), "")
        if ANALYZER_MARKER in system:
            question = last_user.split("TIN NHẮN MỚI NHẤT:")[-1].split("\n")[0].strip() or last_user[-200:]
            text = json.dumps({"intent": "document_question", "standalone_query": question}, ensure_ascii=False)
            n_tokens = 40
        else:
            text = ("Theo tài liệu, nội dung liên quan được trình bày tại mục tương ứng [1]. " * 20)
            n_tokens = args.answer_tokens
        stats.enter("chat")
        await slots.acquire()  # a request beyond the slots waits here, as in llama-server
        streaming = False
        try:
            if (fail := await maybe_fail()) is not None:
                return fail
            await asyncio.sleep(args.prefill)
            if not body.get("stream"):
                await asyncio.sleep(n_tokens / args.tokens_per_s)
                return {"choices": [{"message": {"role": "assistant", "content": text}}],
                        "usage": {"prompt_tokens": len(str(messages)) // 4, "completion_tokens": n_tokens}}

            async def stream():
                try:
                    words = text.split(" ")
                    per = max(1, len(words) // n_tokens)
                    for i in range(0, len(words), per):
                        await asyncio.sleep(1 / args.tokens_per_s)
                        chunk = {"choices": [{"delta": {"content": " ".join(words[i:i + per]) + " "}}]}
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                finally:  # the slot is held until the last token, as in llama-server
                    slots.release()
                    stats.leave("chat")

            streaming = True
            return StreamingResponse(stream(), media_type="text/event-stream")
        finally:
            if not streaming:
                slots.release()
                stats.leave("chat")

    return app


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--chat-port", type=int, default=8011)
    p.add_argument("--embed-port", type=int, default=8012)
    p.add_argument("--rerank-port", type=int, default=8013)
    p.add_argument("--chat-slots", type=int, default=2, help="= llama-server --parallel of the chat runtime")
    p.add_argument("--aux-slots", type=int, default=2, help="slots of the embedding / rerank runtimes")
    p.add_argument("--prefill", type=float, default=1.2, help="seconds before the first token")
    p.add_argument("--tokens-per-s", type=float, default=25.0)
    p.add_argument("--answer-tokens", type=int, default=120)
    p.add_argument("--embed-ms", type=float, default=40.0, help="per input text")
    p.add_argument("--rerank-ms-per-doc", type=float, default=6.0)
    p.add_argument("--n-ctx", type=int, default=8192)
    p.add_argument("--dim", type=int, default=1024)
    p.add_argument("--fail-rate", type=float, default=0.0, help="share of calls answered with HTTP 500")
    args = p.parse_args()
    stats = Stats()
    servers = [
        uvicorn.Server(uvicorn.Config(build_app(kind, args, stats), host=args.host, port=port, log_level="warning"))
        for kind, port in (("chat", args.chat_port), ("embedding", args.embed_port), ("rerank", args.rerank_port))
    ]
    print(f"stub runtimes: chat :{args.chat_port} ({args.chat_slots} slots), embedding :{args.embed_port}, "
          f"rerank :{args.rerank_port}", flush=True)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
