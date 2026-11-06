"""
Stability under concurrent users: the bulkhead uses the runtime's real slot count, and waiting for a slot
does not count against a call's own timeout (which would silently degrade routing to the fallback).
"""

import asyncio
import json

from solutions.rag.application.components.query_analyzer import ANALYZER_MARKER, QueryAnalyzer
from solutions.rag.infrastructure.adapters import runtime_guard as rg


def test_the_bulkhead_grows_to_the_runtime_slots_but_never_shrinks():
    rg.reset_guards()
    guard = rg.runtime_guard("llm")
    base = guard.limits.max_concurrent
    guard.adopt_capacity(base + 2)
    assert guard.limits.max_concurrent == base + 2

    async def hold_all():
        # Every adopted slot can really be taken at once.
        ctxs = [guard.slot() for _ in range(base + 2)]
        for c in ctxs:
            await c.__aenter__()
        busy = guard.saturated
        for c in ctxs:
            await c.__aexit__(None, None, None)
        return busy

    assert asyncio.run(hold_all())
    guard.adopt_capacity(1)
    assert guard.limits.max_concurrent == base + 2
    guard.adopt_capacity(10_000)
    assert guard.limits.max_concurrent == rg.MAX_ADOPTED_SLOTS
    rg.reset_guards()


def test_queue_wait_is_allowed_only_when_the_runtime_is_full():
    rg.reset_guards()
    guard = rg.runtime_guard("llm")
    assert rg.queue_allowance("llm") == 0.0

    async def saturate():
        ctxs = [guard.slot() for _ in range(guard.limits.max_concurrent)]
        for c in ctxs:
            await c.__aenter__()
        allowed = rg.queue_allowance("llm")
        for c in ctxs:
            await c.__aexit__(None, None, None)
        return allowed

    assert asyncio.run(saturate()) > 0
    assert rg.queue_allowance("llm") == 0.0
    rg.reset_guards()


class QueuedLLM:
    """Answers after `delay` seconds (time spent waiting for a slot); reports the allowance to add."""

    def __init__(self, delay, allowance):
        self.delay, self.allowance = delay, allowance

    def queue_allowance(self):
        return self.allowance

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None):
        assert ANALYZER_MARKER in messages[0]["content"]
        await asyncio.sleep(self.delay)
        return json.dumps({"intent": "document_question", "standalone_query": "Lớp 10 học gì?", "wants_list": True}), 1, 1


def test_analysis_waiting_for_a_slot_is_not_cut_off_into_the_fallback():
    analyzer = QueryAnalyzer(timeout=0.2)
    queued = asyncio.run(analyzer.analyze("Lớp 10 học gì?", [], QueuedLLM(delay=0.4, allowance=1.0), "m"))
    assert queued.source == "llm" and queued.wants_list  # waited, then got the real analysis
    stuck = asyncio.run(analyzer.analyze("Lớp 10 học gì?", [], QueuedLLM(delay=0.4, allowance=0.0), "m"))
    assert stuck.source != "llm"  # a slow runtime with free slots still falls back on time


def test_concurrent_callers_refused_for_kv_space_are_serialized_and_all_succeed(monkeypatch):
    """
    Two callers on a runtime whose shared KV cache holds one request: both fail together once, the guard
    drops to one call at a time, and the retries then succeed one after the other (no outage reply).
    """
    from solutions.rag.infrastructure.adapters import model_registry as mr

    rg.reset_guards()
    rg.runtime_guard("llm").adopt_capacity(4)

    class Res:
        def __init__(self, code, body=""):
            self.status_code, self.text, self.headers = code, body, {}

        def json(self):
            return {"ok": True}

    class SharedKV:
        """Fits one request at a time: a request overlapping another fails with llama.cpp's message."""

        def __init__(self):
            self.active, self.calls = 0, 0

        async def post(self, url, json, headers, timeout):
            self.calls += 1
            self.active += 1
            try:
                await asyncio.sleep(0.05)
                if self.active > 1:
                    return Res(500, '{"error":{"code":500,"message":"Context size has been exceeded."}}')
                return Res(200)
            finally:
                self.active -= 1

    real_sleep = asyncio.sleep

    async def fast_sleep(s):
        await real_sleep(min(s, 0.01))

    monkeypatch.setattr(mr.asyncio, "sleep", fast_sleep)
    kv = SharedKV()

    async def run():
        return await asyncio.gather(*[mr.post_json_with_retry(kv, "u", {}, {}, 5.0, kind="llm") for _ in range(3)])

    assert asyncio.run(run()) == [{"ok": True}] * 3
    guard = rg.runtime_guard("llm")
    assert guard.effective_limit == 1 and guard.state == rg.CLOSED  # throttled, never treated as an outage
    for _ in range(rg.RELAX_AFTER_SUCCESSES * 3):
        guard.record_success()
    assert guard.effective_limit == 4  # earns its concurrency back
    rg.reset_guards()


def test_breaker_ignores_a_stream_cut_off_for_lack_of_room():
    from solutions.rag.domain.exceptions import LLMStreamInterruptedError

    rg.reset_guards()
    guard = rg.runtime_guard("llm")

    async def cut_off():
        for _ in range(guard.limits.failure_threshold + 2):
            try:
                async with guard.slot():
                    raise LLMStreamInterruptedError("cut off")
            except LLMStreamInterruptedError:
                pass

    asyncio.run(cut_off())
    assert guard.state == rg.CLOSED and guard._failures == 0
    rg.reset_guards()


def test_parallelism_that_overflows_again_is_retried_less_often():
    rg.reset_guards()
    guard = rg.runtime_guard("llm")
    guard.adopt_capacity(2)
    guard.throttle()
    for _ in range(rg.RELAX_AFTER_SUCCESSES):
        guard.record_success()
    assert guard.effective_limit == 2
    guard.throttle()  # the same overflow again once concurrency came back
    for _ in range(rg.RELAX_AFTER_SUCCESSES):
        guard.record_success()
    assert guard.effective_limit == 1  # needs twice the successes now
    for _ in range(rg.RELAX_AFTER_SUCCESSES):
        guard.record_success()
    assert guard.effective_limit == 2
    rg.reset_guards()


ANSWER = "Mỗi năm có 12 ngày phép theo HR.A2.1 [1]."


def _interrupting_llm(cut_after_chars):
    from solutions.rag.domain.exceptions import LLMStreamInterruptedError
    from tests.test_rag_answer_pipeline import ScriptedLLM

    class InterruptedOnce(ScriptedLLM):
        """The runtime cuts the first answer off part-way (out of KV space), the second one completes."""

        streams = 0

        async def stream_generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None):
            self.streams += 1
            if self.streams == 1:
                for i in range(0, cut_after_chars, 5):
                    yield self.answer[i:min(i + 5, cut_after_chars)]
                raise LLMStreamInterruptedError("runtime out of KV space under load")
            async for t in super().stream_generate(messages, model, temperature, max_tokens, authorization):
                yield t

    return InterruptedOnce({"intent": "document_question", "standalone_query": "Mỗi năm có bao nhiêu ngày phép?"},
                           ANSWER)


def _stream(llm):
    from solutions.rag.application.dtos import RagChatRequestDTO
    from tests.test_rag_answer_pipeline import _use_case

    uc, _, _ = _use_case(llm)

    async def run():
        return [e async for e in uc.stream_execute(
            RagChatRequestDTO(query="Mỗi năm có bao nhiêu ngày phép?", stream=True, similarity_threshold=0.65))]

    return asyncio.run(run())


def test_an_answer_cut_off_before_the_user_saw_it_is_generated_again():
    llm = _interrupting_llm(cut_after_chars=15)  # still held back by the verifier (sentence not finished)
    events = _stream(llm)
    tokens = "".join(json.loads(e[6:])["token"] for e in events if '"token"' in e)
    assert not any(e.startswith("event: error") for e in events)
    assert llm.streams == 2 and "12 ngày phép" in tokens and tokens.count("Mỗi năm") == 1
    assert json.loads(events[-1][6:])["done"] is True


TWO_SENTENCES = "Mỗi năm có 12 ngày phép theo HR.A2.1 [1].\n\nNgày phép theo HR.A2.1 được tính theo năm [1]."


def test_an_answer_cut_off_after_text_was_shown_is_withdrawn_and_generated_again():
    llm = _interrupting_llm(cut_after_chars=len(TWO_SENTENCES) - 10)
    llm.answer = TWO_SENTENCES
    events = _stream(llm)
    assert not any(e.startswith("event: error") for e in events)
    payloads = [json.loads(e[6:]) for e in events if e.startswith("data: ")]
    resets = [i for i, p in enumerate(payloads) if p.get("reset")]
    assert len(resets) == 1 and any(p.get("token") for p in payloads[:resets[0]])  # partial text was shown
    shown = "".join(p.get("token", "") for p in payloads[resets[0] + 1:])  # what the client keeps
    assert llm.streams == 2 and shown.count("Mỗi năm có 12 ngày phép") == 1
    assert payloads[-1]["done"] is True
