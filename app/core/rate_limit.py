"""A tiny in-memory per-IP rate limiter for login attempts.

Per-process only (resets on restart, doesn't share state across workers) — acceptable
for this app's single-process deployment model (see docs/01-architecture.md). Not a
replacement for a proper distributed limiter if this is ever scaled out.
"""

import time
from collections import defaultdict, deque
from math import ceil

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 300  # 5 minutes
MAX_FAILED_ATTEMPTS = 3
FAILED_ATTEMPT_WINDOW_SECONDS = 300
FAILURE_COOLDOWN_SECONDS = 300

_attempts: dict[str, deque[float]] = defaultdict(deque)
_failed_attempts: dict[str, deque[float]] = defaultdict(deque)
_failure_cooldowns: dict[str, float] = {}


def is_rate_limited(key: str) -> bool:
    attempts = _attempts[key]
    _prune(attempts, WINDOW_SECONDS)
    return len(attempts) >= MAX_ATTEMPTS


def record_attempt(key: str) -> None:
    _attempts[key].append(time.monotonic())


def failed_attempt_cooldown_remaining(key: str) -> int:
    cooldown_until = _failure_cooldowns.get(key)
    if cooldown_until is None:
        return 0

    remaining = cooldown_until - time.monotonic()
    if remaining <= 0:
        del _failure_cooldowns[key]
        _failed_attempts.pop(key, None)
        return 0
    return ceil(remaining)


def record_failed_attempt(key: str) -> None:
    attempts = _failed_attempts[key]
    _prune(attempts, FAILED_ATTEMPT_WINDOW_SECONDS)
    attempts.append(time.monotonic())
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        _failure_cooldowns[key] = time.monotonic() + FAILURE_COOLDOWN_SECONDS
        attempts.clear()


def clear_failed_attempts(key: str) -> None:
    _failed_attempts.pop(key, None)
    _failure_cooldowns.pop(key, None)


def _prune(attempts: deque[float], window_seconds: int) -> None:
    cutoff = time.monotonic() - window_seconds
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
