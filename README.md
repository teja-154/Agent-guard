# agent-guard

A minimal, stdlib-only circuit breaker for AI agent tool calls. Stops an
agent that's stuck failing the same (or a reworded) action in a silent,
token-burning loop.

**Not a novel idea** — see [Similar Projects](#similar-projects) below.
This one's differentiator is size: one file, zero dependencies, no server,
no framework lock-in.

## The problem

An agent doesn't get a 500 error when it's stuck. It calls `search(q)`,
gets an empty result, rewords the query, gets another empty result, and
repeats — burning tokens on calls that all "succeed" individually.

## Install

```bash
pip install git+https://github.com/teja-154/Agent-guard.git
```

or just copy `agent_guard.py` into your project — it's one file, stdlib only.

## Usage

### Decorator (closest thing to zero-integration)

```python
from agent_guard import guarded, GuardTripped

@guarded(threshold=3)
def search(query: str):
    ok, result = call_your_api(query)
    return ok, result          # (success, payload)

try:
    search("some query")
except GuardTripped:
    print("Agent stuck in a loop — stopping.")
```

### Manual (full control)

```python
from agent_guard import CircuitBreaker

cb = CircuitBreaker(window=20, threshold=3, budget=0)
v = cb.check(tool="search", args={"q": query}, success=ok)

if v.action == "WARN":
    inject_into_agent_context(v.hint)
elif v.action == "TRIP":
    stop_agent_loop()
```

## States

| State | Meaning |
|---|---|
| `CONTINUE` | Normal — call is fine |
| `WARN` | Same (or reworded) call failed `threshold` times — injects a hint |
| `TRIP` | Failed `threshold*2` times — stop the agent |

## How it detects loops

- **Exact repeats**: same tool + same args, hashed.
- **Fuzzy repeats**: reworded queries to the *same tool* bucket together via
  Jaccard word-similarity (≥0.75), so "python tutorial" and "tutorial
  python" count as the same failing action. Never buckets across different
  tools.
- **Recovery**: a success removes exactly one failure from its bucket
  (partial decay) — not a full reset. A mostly-broken API (e.g. 75% failure
  rate) still trips; a genuinely flaky one (~50% success) plateaus instead
  of tripping.
- **Budget**: optional hard token cap, independent of the loop logic.

## Testing

```bash
python test_agent_guard.py
```

16 assertions: exact-repeat escalation, fuzzy bucketing, cross-tool
isolation, decay math on both 25% and 50% success rates, decorator
behavior, thread safety, and budget enforcement.

`demo_integration.py` runs the guard against real (intentionally failing)
HTTP requests, not synthetic data, so you can watch it trip on an actual
network failure.

## Similar projects

This category is already well-covered. Worth looking at before you build
on top of this:

- [AgentCircuit](https://github.com/simranmultani197/AgentCircuit) — decorator-based, works with LangGraph/LangChain/CrewAI/AutoGen
- [aura-guard](https://github.com/auraguardhq/aura-guard) — multi-tool sequence loop detection (A→B→A→B patterns)
- [LoopGuard](https://pkg.go.dev/github.com/loop-eng/loopguard) — daemon that monitors Claude Code/Codex/Gemini CLI sessions live
- [AgentBreaker](https://pypi.org/project/agentbreaker-sdk/) — orchestration-layer breaker with a dashboard

This project is smaller and has no runtime dependencies, which is the
tradeoff: less capability, easier to read end-to-end and drop into a
student project.

## License

MIT
