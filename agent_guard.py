"""
agent_guard.py - AI Agent Circuit Breaker
Single file, stdlib only, zero deps.

Detects when an agent is stuck failing the same (or reworded) action
repeatedly, and trips before it burns budget in a silent loop.

Quick use (decorator):
    from agent_guard import guarded, GuardTripped

    @guarded()
    def search(query: str):
        ok, result = call_api(query)
        return ok, result   # (success, payload)

Direct use (manual):
    from agent_guard import CircuitBreaker
    cb = CircuitBreaker()
    v = cb.check("search", {"q": query}, success=ok)

License: MIT
"""

import functools
import hashlib
import json
import re
import threading
from collections import deque
from typing import NamedTuple


class Verdict(NamedTuple):
    action: str   # CONTINUE | WARN | TRIP
    reason: str
    hint: str


class GuardTripped(Exception):
    """Raised by @guarded when the circuit breaker trips."""


class CircuitBreaker:
    """Thread-safe, failure-aware circuit breaker for AI agent tool calls."""

    def __init__(self, window: int = 20, threshold: int = 3, budget: int = 0,
                 fuzzy_threshold: float = 0.75):
        if window < threshold * 2:
            raise ValueError(f"window ({window}) must be >= threshold*2 ({threshold*2})")
        if threshold <= 0:
            raise ValueError(f"threshold must be > 0, got {threshold}")

        self.window = deque(maxlen=window)   # entries: (bucket_fp, norm, tool)
        self.threshold = threshold
        self.budget = budget
        self.fuzzy_threshold = fuzzy_threshold
        self.used = 0
        self._warned = set()
        self._lock = threading.Lock()

    @staticmethod
    def _normalize(s: str) -> str:
        s = re.sub(r'[^\w\s]', '', s.lower())
        return ' '.join(s.split())

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        s1, s2 = set(a.split()), set(b.split())
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)

    def _fp(self, tool: str, args: dict) -> str:
        payload = json.dumps({str(k): v for k, v in args.items()}, sort_keys=True)
        return hashlib.sha256(f"{tool}:{payload}".encode()).hexdigest()[:16]

    def _norm_args(self, args: dict) -> str:
        return ' '.join(self._normalize(v) for v in args.values() if isinstance(v, str))

    def _find_bucket(self, tool: str, norm: str):
        """Find an existing same-tool bucket fuzzy-similar to norm. Used by
        BOTH the failure path (to group) and the success path (to decay the
        right bucket even when the successful call is a reworded variant)."""
        for fp, prev_norm, prev_tool in self.window:
            if prev_tool == tool and self._jaccard(norm, prev_norm) >= self.fuzzy_threshold:
                return fp
        return None

    def check(self, tool: str, args: dict, success: bool = True, tokens: int = 0) -> Verdict:
        if tokens < 0:
            raise ValueError(f"tokens cannot be negative, got {tokens}")

        with self._lock:
            self.used += tokens
            if self.budget and self.used >= self.budget:
                return Verdict("TRIP", "budget_exhausted", "")

            fp = self._fp(tool, args)
            norm = self._norm_args(args)

            if success:
                target = fp if any(f == fp for f, _, _ in self.window) else self._find_bucket(tool, norm)
                if target is not None:
                    for idx, (f, _, _) in enumerate(self.window):
                        if f == target:
                            l = list(self.window)
                            del l[idx]
                            self.window = deque(l, maxlen=self.window.maxlen)
                            break
                    count = sum(1 for f, _, _ in self.window if f == target)
                    if target in self._warned and count < self.threshold:
                        self._warned.discard(target)
                return Verdict("CONTINUE", "", "")

            bucket = self._find_bucket(tool, norm) or fp
            self.window.append((bucket, norm, tool))
            count = sum(1 for f, _, _ in self.window if f == bucket)

            if count >= self.threshold * 2:
                return Verdict("TRIP", f"failure_loop:{tool}", "")
            if count >= self.threshold and bucket not in self._warned:
                self._warned.add(bucket)
                return Verdict("WARN", f"failure_repeat:{tool}",
                                f"You failed {tool} {count} times with similar inputs. Change strategy.")
            return Verdict("CONTINUE", "", "")

    def reset(self):
        with self._lock:
            self.window.clear()
            self._warned.clear()
            self.used = 0

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "used_tokens": self.used,
                "window_usage": len(self.window),
                "budget": self.budget,
                "active_warnings": len(self._warned),
            }


def guarded(tool_name: str = None, breaker: CircuitBreaker = None, **breaker_kwargs):
    """Decorator: wraps any tool function with a CircuitBreaker.

    The wrapped function may return either:
      - a (success: bool, result) tuple, or
      - a plain result (treated as always success=True).

    On WARN, prints the hint (swap `print` for your own logger/context-injector).
    On TRIP, raises GuardTripped -- catch it in your agent loop and stop.
    """
    cb = breaker or CircuitBreaker(**breaker_kwargs)

    def deco(fn):
        name = tool_name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            success, payload = (result if isinstance(result, tuple) and len(result) == 2
                                 and isinstance(result[0], bool) else (True, result))
            call_args = {**{f"arg{i}": a for i, a in enumerate(args)}, **kwargs}
            v = cb.check(name, call_args, success=success)
            if v.action == "WARN":
                print(f"[agent_guard] WARN: {v.hint}")
            elif v.action == "TRIP":
                raise GuardTripped(f"{v.reason} -- tool '{name}' stuck in a loop")
            return payload

        wrapper.breaker = cb
        return wrapper
    return deco
