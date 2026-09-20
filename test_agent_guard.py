from agent_guard import CircuitBreaker, guarded, GuardTripped

failures = []
def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        failures.append(name)

# 1-3: exact repeat -> WARN -> TRIP, no duplicate WARN
cb = CircuitBreaker(window=10, threshold=3)
r = [cb.check("search", {"q": "x"}, success=False) for _ in range(6)]
check("exact repeat WARN at 3rd", r[2].action == "WARN")
check("no duplicate WARN at 4th/5th", r[3].action == "CONTINUE" and r[4].action == "CONTINUE")
check("exact repeat TRIP at 6th", r[5].action == "TRIP")

# 4: success on a different tool doesn't touch another bucket
cb.reset()
cb.check("search", {"q": "x"}, success=False)
cb.check("search", {"q": "x"}, success=False)
v = cb.check("read", {"file": "a"}, success=True)
check("success on different tool is CONTINUE, doesn't wipe other bucket",
      v.action == "CONTINUE" and cb.get_stats()["window_usage"] == 2)

# 5-6: fuzzy bucketing, same tool, reworded/case/punctuation variants
cb.reset()
cb.check("search", {"q": "python tutorial"}, success=False)
v = cb.check("search", {"q": "tutorial python"}, success=False)
check("fuzzy reorder buckets together", cb.get_stats()["window_usage"] == 2 and v.action == "CONTINUE")
v = cb.check("search", {"q": "Python Tutorial!"}, success=False)
check("fuzzy case/punct buckets & WARNs at count 3", v.action == "WARN")

# 7: cross-tool false positive check (same words, different tool)
cb.reset()
cb.check("search", {"q": "delete old file"}, success=False)
cb.check("read", {"file": "delete_old_file.log"}, success=False)
check("cross-tool does NOT bucket", cb.get_stats()["window_usage"] == 2)

# 8: a mostly-failing (25% success) API SHOULD eventually trip
cb.reset()
tripped_at = None
for i in range(1, 21):
    v = cb.check("api", {"req": "data"}, success=(i % 4 == 0))
    if v.action == "TRIP":
        tripped_at = i
        break
check("25% success API eventually trips", tripped_at is not None)

# 9: a 50%-success API should plateau and never trip
cb.reset()
tripped = any(
    cb.check("api", {"req": "data"}, success=(i % 2 == 0)).action == "TRIP"
    for i in range(1, 41)
)
check("50% success API plateaus, never trips", not tripped)

# 10: success on a REWORDED variant still decays the fuzzy bucket
cb.reset()
cb.check("search", {"q": "python tutorial"}, success=False)
cb.check("search", {"q": "tutorial python"}, success=False)
cb.check("search", {"q": "tutorial python"}, success=True)
count_after = sum(1 for f, _, _ in cb.window if f == cb._fp("search", {"q": "python tutorial"}))
check("success on reworded variant decays the fuzzy bucket", count_after == 1)

# 11: warning gate resets and can re-fire after recovery
cb.reset()
for _ in range(3):
    cb.check("api", {"req": "y"}, success=False)
cb.check("api", {"req": "y"}, success=True)
v = cb.check("api", {"req": "y"}, success=False)
check("warning re-fires after recovery + re-hitting threshold", v.action == "WARN")

# 12-13: budget trip + get_stats shape
cb2 = CircuitBreaker(window=10, threshold=3, budget=50)
v = None
for _ in range(6):
    v = cb2.check("api", {}, success=True, tokens=10)
    if v.action == "TRIP":
        break
check("budget trips", v.action == "TRIP" and v.reason == "budget_exhausted")
check("get_stats has expected keys",
      set(cb2.get_stats()) == {"used_tokens", "window_usage", "budget", "active_warnings"})

# 14: thread safety smoke test
import threading as th
cb3 = CircuitBreaker(window=50, threshold=5)
def hammer():
    for _ in range(200):
        cb3.check("t", {"q": "same"}, success=False)
threads = [th.Thread(target=hammer) for _ in range(8)]
[t.start() for t in threads]
[t.join() for t in threads]
check("concurrent access doesn't crash", True)

# 15-16: decorator, tuple-return convention
@guarded(threshold=3)
def always_fails(q):
    return (False, None)
tripped = False
for _ in range(6):
    try:
        always_fails("x")
    except GuardTripped:
        tripped = True
        break
check("decorator raises GuardTripped on loop (tuple style)", tripped)

@guarded(threshold=3)
def always_ok(q):
    return "fine"
r = None
for _ in range(10):
    r = always_ok("x")
check("decorator passes through plain (non-tuple) return", r == "fine")

# 17-18: decorator, exception-raising convention (the real-world case)
@guarded(threshold=3)
def raises_on_call(q):
    raise ValueError("boom")
propagated_ok = 0
tripped = False
for _ in range(6):
    try:
        raises_on_call("x")
    except ValueError:
        propagated_ok += 1
    except GuardTripped:
        tripped = True
        break
check("exceptions propagate normally before TRIP", propagated_ok == 5)
check("exception-based failures still trip the breaker", tripped)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):", failures)
    raise SystemExit(1)
print("ALL 18 TESTS PASSED")
