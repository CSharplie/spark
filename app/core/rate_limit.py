"""A tiny in-memory per-IP rate limiter for login attempts.

Per-process only (resets on restart, doesn't share state across workers) — acceptable
for this app's single-process deployment model (see docs/01-architecture.md). Not a
replacement for a proper distributed limiter if this is ever scaled out.
"""

import time
from collections import defaultdict, deque

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 300  # 5 minutes

_attempts: dict[str, deque[float]] = defaultdict(deque)


def is_rate_limited(key: str) -> bool:
    attempts = _attempts[key]
    _prune(attempts)
    return len(attempts) >= MAX_ATTEMPTS


def record_attempt(key: str) -> None:
    _attempts[key].append(time.monotonic())


def _prune(attempts: deque[float]) -> None:
    cutoff = time.monotonic() - WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
