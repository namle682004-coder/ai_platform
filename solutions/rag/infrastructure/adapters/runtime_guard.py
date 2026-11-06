"""
Overload protection for calls to model runtimes (chat LLM, embedding, rerank).

A small model host has a fixed capacity: a 7B llama-server answers a few requests at a time and every
request beyond that only queues, holds memory and makes all answers late. Each runtime kind therefore
gets, per process:

  bulkhead        – at most `max_concurrent` calls in flight; a caller waits at most `queue_timeout`
                    for a slot and is then refused (RuntimeOverloadedError) instead of piling up.
  circuit breaker – after `failure_threshold` consecutive failures (timeouts, connection errors, 5xx)
                    the runtime is presumed overloaded or down: calls fail fast for `cooldown` seconds,
                    then a single trial call decides whether to close the breaker again.

Refusing early ("busy, retry in N seconds") is what keeps the host alive: the alternative is a growing
queue of work on a machine that is already out of memory.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict

from ...config import rag_settings
from ...domain.exceptions import ServiceOverloadedError

logger = logging.getLogger("aip-rag.adapter.runtime-guard")

CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"
MAX_ADOPTED_SLOTS = 16  # upper bound on a runtime-reported slot count taken as the bulkhead size
RELAX_AFTER_SUCCESSES = 8  # successful calls before a throttled runtime gets one more concurrent call
MAX_RELAX_AFTER_SUCCESSES = 256  # ceiling of that count after repeated overflows (it doubles on each)


class RuntimeOverloadedError(ServiceOverloadedError):
    """The runtime is at capacity or its breaker is open; retry after `retry_after` seconds."""

    def __init__(self, kind: str, reason: str, retry_after: int) -> None:
        super().__init__(f"{kind} runtime overloaded: {reason}", retry_after)
        self.kind = kind
        self.reason = reason


@dataclass
class GuardLimits:
    max_concurrent: int
    queue_timeout: float
    failure_threshold: int
    cooldown: float


@dataclass
class RuntimeGuard:
    kind: str
    limits: GuardLimits
    _semaphore: asyncio.Semaphore = field(init=False, repr=False)
    _state: str = field(default=CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _trial_running: bool = field(default=False, init=False)
    in_flight: int = field(default=0, init=False)
    rejected: int = field(default=0, init=False)
    # Adaptive limit: a runtime that reports it is out of KV space with the current parallelism gets
    # fewer concurrent calls (down to one) and earns them back after a run of successes.
    _penalty: int = field(default=0, init=False)
    _successes_since_throttle: int = field(default=0, init=False)
    _relax_after: int = field(default=RELAX_AFTER_SUCCESSES, init=False)
    _relaxed_since_throttle: bool = field(default=False, init=False)
    _cond: asyncio.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._cond = asyncio.Condition()

    @property
    def effective_limit(self) -> int:
        return max(1, self.limits.max_concurrent - self._penalty)

    def throttle(self) -> None:
        """The runtime ran out of room with this many calls in flight: serialize until it recovers."""
        if self._penalty < self.limits.max_concurrent - 1:
            logger.warning("%s runtime out of KV space: concurrency %d -> 1 until it recovers",
                           self.kind, self.effective_limit)
            if self._relaxed_since_throttle:
                # Overflowed again after earning concurrency back: that parallelism does not fit this
                # runtime, so it is retried less and less often instead of failing calls on a cycle.
                self._relax_after = min(self._relax_after * 2, MAX_RELAX_AFTER_SUCCESSES)
        self._penalty = self.limits.max_concurrent - 1
        self._successes_since_throttle = 0
        self._relaxed_since_throttle = False

    def _relax(self) -> None:
        if self._penalty <= 0:
            return
        self._successes_since_throttle += 1
        if self._successes_since_throttle >= self._relax_after:
            self._penalty -= 1
            self._successes_since_throttle = 0
            self._relaxed_since_throttle = True

    @property
    def state(self) -> str:
        if self._state == OPEN and time.monotonic() - self._opened_at >= self.limits.cooldown:
            return HALF_OPEN
        return self._state

    def _retry_after(self) -> int:
        if self._state == OPEN:
            return int(max(1.0, self.limits.cooldown - (time.monotonic() - self._opened_at)) + 0.999)
        return int(max(1.0, self.limits.queue_timeout))

    def _admit(self) -> bool:
        """Breaker check; True when this call is the half-open trial."""
        state = self.state
        if state == OPEN:
            self.rejected += 1
            raise RuntimeOverloadedError(self.kind, "circuit open after repeated failures", self._retry_after())
        if state == HALF_OPEN:
            if self._trial_running:
                self.rejected += 1
                raise RuntimeOverloadedError(self.kind, "recovering, trial call in progress", self._retry_after())
            self._trial_running = True
            return True
        return False

    def record_success(self) -> None:
        if self._state != CLOSED:
            logger.info("%s runtime recovered: circuit closed", self.kind)
        self._state, self._failures, self._trial_running = CLOSED, 0, False
        self._relax()

    def record_failure(self, trial: bool = False) -> None:
        self._failures += 1
        if trial or self._failures >= max(1, self.limits.failure_threshold):
            if self._state != OPEN or trial:
                logger.error("%s runtime failing (%d consecutive): circuit open for %.0fs",
                             self.kind, self._failures, self.limits.cooldown)
            self._state, self._opened_at = OPEN, time.monotonic()
        self._trial_running = False

    @asynccontextmanager
    async def slot(self) -> AsyncIterator["RuntimeGuard"]:
        """
        One call to the runtime. The caller reports the outcome with record_success / record_failure;
        a call that raises without reporting counts as a failure.
        """
        trial = self._admit()

        async def acquire() -> None:
            async with self._cond:
                await self._cond.wait_for(lambda: self.in_flight < self.effective_limit)
                self.in_flight += 1

        try:
            await asyncio.wait_for(acquire(), timeout=self.limits.queue_timeout)
        except asyncio.TimeoutError:
            if trial:
                self._trial_running = False
            self.rejected += 1
            raise RuntimeOverloadedError(
                self.kind, f"{self.effective_limit} calls in flight, no slot within "
                           f"{self.limits.queue_timeout:.0f}s", self._retry_after()) from None
        reported_before = (self._failures, self._state)
        try:
            yield self
        except RuntimeOverloadedError:
            raise
        except BaseException as exc:
            if getattr(exc, "capacity_refusal", False):
                raise  # the runtime was busy, not failing: the breaker is left as it is
            if (self._failures, self._state) == reported_before:
                self.record_failure(trial)
            raise
        finally:
            async with self._cond:
                self.in_flight -= 1
                self._cond.notify_all()
            if trial and self._trial_running:
                self._trial_running = False

    @property
    def saturated(self) -> bool:
        """Every slot is taken: a new call will wait in the queue first."""
        return self.in_flight >= self.effective_limit

    def adopt_capacity(self, slots: int) -> None:
        """
        Raise the bulkhead to the parallel slots the runtime reports (llama-server --parallel): a lower limit
        only queues work the runtime could batch. Never lowered here; if the runtime's KV cache cannot hold
        that many requests at once, throttle() brings the effective limit back down.
        """
        target = min(int(slots), MAX_ADOPTED_SLOTS)
        if target <= self.limits.max_concurrent:
            return
        logger.info("%s runtime: concurrency %d -> %d (runtime slots)", self.kind, self.limits.max_concurrent, target)
        self.limits.max_concurrent = target
        if self._penalty:
            self._penalty = target - 1  # still throttled: stay at one call until successes relax it

    def snapshot(self) -> Dict[str, object]:
        return {"kind": self.kind, "state": self.state, "in_flight": self.in_flight,
                "max_concurrent": self.limits.max_concurrent, "effective_limit": self.effective_limit,
                "consecutive_failures": self._failures, "rejected": self.rejected}


def _limits(kind: str) -> GuardLimits:
    s = rag_settings
    concurrency = {"llm": s.llm_max_concurrent, "embedding": s.embedding_max_concurrent,
                   "rerank": s.rerank_max_concurrent}.get(kind, s.llm_max_concurrent)
    return GuardLimits(max_concurrent=concurrency, queue_timeout=s.runtime_queue_timeout_seconds,
                       failure_threshold=s.runtime_breaker_failures, cooldown=s.runtime_breaker_cooldown_seconds)


_guards: Dict[str, RuntimeGuard] = {}


def runtime_guard(kind: str) -> RuntimeGuard:
    """The process-wide guard of a runtime kind ('llm', 'embedding', 'rerank')."""
    guard = _guards.get(kind)
    if guard is None:
        guard = _guards[kind] = RuntimeGuard(kind, _limits(kind))
    return guard


def queue_allowance(kind: str) -> float:
    """
    Extra seconds a caller's own timeout must allow when the runtime is saturated: waiting for a slot is
    not the model being slow, and timing out on it would silently degrade the answer (fallback routing).
    The wait itself stays bounded by the guard's queue timeout, which then refuses with "busy".
    """
    guard = _guards.get(kind)
    return rag_settings.runtime_queue_timeout_seconds if guard is not None and guard.saturated else 0.0


def guards_snapshot() -> Dict[str, Dict[str, object]]:
    return {k: g.snapshot() for k, g in _guards.items()}


def reset_guards() -> None:
    """Tests / configuration reload: fresh guards built from the current settings."""
    _guards.clear()
