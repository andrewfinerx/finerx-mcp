"""Per-person rate limits for the hosted endpoint (in-process, one worker).

The API key behind the hosted MCP is shared by every assistant user, so the
API's own per-key window cannot tell one heavy user from ten thousand light
ones. This limiter can: ChatGPT sends ``openai/subject`` (an anonymous per-user
id) on every call, and ``hosts.subject_key`` turns it into an HMAC.

* model-facing tools: token bucket **30/min** + a UTC-day cap of **400** per subject;
* app-only ``ui_*`` tools (chips, ZIP field — a person clicking): **90/min**;
* no subject (Claude and every other host): ONE shared bucket, **300/min**,
  and a SEPARATE shared one of **600/min** for the typeahead (``ui_suggest``,
  kind ``suggest``) so people typing in Claude cannot starve each other's
  prices; with a subject the typeahead shares the person's ``ui`` bucket;
* and, over ALL callers together — subjects and the anonymous bucket alike —
  a ceiling of **600/min** on model tools and **1200/min** on ``ui_*``. A
  per-subject bucket alone is free to whoever mints subjects: rotating
  ``openai/subject`` hands out a fresh 30/min (and 400/day) each time. The
  ceilings are held by the limiter itself, never by a subject's entry, so
  evicting subjects (below) cannot reset them. They sit under the API's own
  window for the ``mcp`` key tier (1200/min), so a flood is refused here — with
  the card — before it spends the shared key.

A refused call gets ``retry_after`` seconds; the tool answers "busy, try again
in N s" — with the card, like every other answer. Memory is bounded: at most
``MAX_KEYS`` subjects are tracked, least-recently-seen evicted first.
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

MODEL_PER_MIN = 30
MODEL_PER_DAY = 400
UI_PER_MIN = 90
ANON_PER_MIN = 300
ANON_SUGGEST_PER_MIN = 600
MODEL_GLOBAL_PER_MIN = 600
UI_GLOBAL_PER_MIN = 1200
MAX_KEYS = 20_000


@dataclass
class TokenBucket:
    capacity: float
    per_second: float
    tokens: float = -1.0
    stamp: float | None = None  # set by the first take()

    def __post_init__(self) -> None:
        if self.tokens < 0:
            self.tokens = self.capacity

    def take(self, now: float) -> float:
        """0 when a token was taken, else the seconds until one is free."""
        elapsed = 0.0 if self.stamp is None else max(0.0, now - self.stamp)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.per_second)
        self.stamp = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        return (1.0 - self.tokens) / self.per_second

    def give_back(self) -> None:
        """Return the token a call took when a later check refused it."""
        self.tokens = min(self.capacity, self.tokens + 1.0)


def _per_min(n: int) -> TokenBucket:
    return TokenBucket(capacity=float(n), per_second=n / 60.0)


@dataclass
class _Subject:
    model: TokenBucket = field(default_factory=lambda: _per_min(MODEL_PER_MIN))
    ui: TokenBucket = field(default_factory=lambda: _per_min(UI_PER_MIN))
    day: str = ""
    day_count: int = 0


def _utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


class Limiter:
    def __init__(self) -> None:
        self._subjects: OrderedDict[str, _Subject] = OrderedDict()
        self._anon = _per_min(ANON_PER_MIN)
        self._anon_suggest = _per_min(ANON_SUGGEST_PER_MIN)
        self._ceiling = {"model": _per_min(MODEL_GLOBAL_PER_MIN), "ui": _per_min(UI_GLOBAL_PER_MIN)}

    def reset(self) -> None:  # tests
        self._subjects.clear()
        self._anon = _per_min(ANON_PER_MIN)
        self._anon_suggest = _per_min(ANON_SUGGEST_PER_MIN)
        self._ceiling = {"model": _per_min(MODEL_GLOBAL_PER_MIN), "ui": _per_min(UI_GLOBAL_PER_MIN)}

    def _subject(self, key: str) -> _Subject:
        entry = self._subjects.get(key)
        if entry is None:
            entry = _Subject()
            self._subjects[key] = entry
            while len(self._subjects) > MAX_KEYS:
                self._subjects.popitem(last=False)
        else:
            self._subjects.move_to_end(key)
        return entry

    def _within_ceiling(self, kind: str, mono: float, own: TokenBucket) -> int:
        """The all-callers ceiling of ``kind``, checked after the caller's own
        bucket let the call through; on a refusal the caller's token goes back
        (a call that did not run should not count against the person)."""
        wait = self._ceiling["ui" if kind in ("ui", "suggest") else "model"].take(mono)
        if wait:
            own.give_back()
            return max(1, math.ceil(wait))
        return 0

    def check(self, kind: str, subject: str | None, *, now: float | None = None) -> int:
        """Admit one call of ``kind`` ("model" | "ui" | "suggest"). 0 = go, N =
        retry in N s. ``suggest`` is a ``ui`` call with its own anonymous bucket."""
        mono = time.monotonic() if now is None else now
        if subject is None:
            bucket = self._anon_suggest if kind == "suggest" else self._anon
            wait = bucket.take(mono)
            if wait:
                return math.ceil(wait)
            return self._within_ceiling(kind, mono, bucket)
        entry = self._subject(subject)
        if kind in ("ui", "suggest"):
            wait = entry.ui.take(mono)
            if wait:
                return math.ceil(wait)
            return self._within_ceiling("ui", mono, entry.ui)
        today = _utc_day(time.time())
        if entry.day != today:
            entry.day, entry.day_count = today, 0
        if entry.day_count >= MODEL_PER_DAY:
            tomorrow = (math.floor(time.time() / 86400) + 1) * 86400
            return max(1, math.ceil(tomorrow - time.time()))
        wait = entry.model.take(mono)
        if wait:
            return math.ceil(wait)
        if wait := self._within_ceiling("model", mono, entry.model):
            return wait
        entry.day_count += 1
        return 0


LIMITER = Limiter()
