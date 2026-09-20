# agent-guard

**Stops an AI agent from silently looping on a failing action and burning
your token budget.**

One file. Zero dependencies. Not novel — see [Similar projects](#similar-projects).

## 30-second example

```python
from agent_guard import guarded, GuardTripped

@guarded(threshold=3)
def search(query: str):
    return call_your_api(query)   # raises, or returns normally — both work

try:
    search("some query")
except GuardTripped:
    print("Agent is stuck in a loop — stopping.")
```

That's the whole integration. No config file, no server, no framework to adopt.

## Who this is for

- **Just want it to work:** copy `agent_guard.py` into your project, add
  `@guarded()` above any function your agent calls repeatedly. Done.
- **Building an agent:** it catches both failure styles real code actually
  uses — a function that `raise`s, and one that returns `(success, result)`
  — so you don't have to restructure your API client to use this.
- **Reviewing it for correctness:** see [How it works](#how-it-works) below
  for the exact matching/decay algorithm and its known limitation.

## The problem

An agent doesn't get a clean error when it's stuck. It calls `search(q)`,
gets an empty result, rewords the query, gets another empty result, and
repeats — burning tokens on calls that each "succeed" individually.

## Two ways to fail (both are caught)

```python
# Style 1: your function raises on failure (e.g. requests, most SDKs)
@guarded(threshold=3)
def call_api(query):
    return requests.get(url, params={"q": query}).json()  # raises on error

# Style 2: your function returns (success, result)
@guarded(threshold=3)
def call_api(query):
    ok, data = my_client.search(query)
    return ok, data
```

Either way, `@guarded` counts it as a failure and applies the same loop
detection.

## Manual API (full control)

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

## How it works

- **Exact repeats**: same tool + same args, hashed.
- **Fuzzy repeats**: reworded queries to the *same tool* bucket together via
  Jaccard word-similarity (≥0.75) — "python tutorial" and "tutorial python"
  count as the same failing action. Never buckets across different tools.
- **Recovery**: a success removes exactly one failure from its bucket
  (partial decay), not a full reset. A mostly-broken API (e.g. 75% failure
  rate) still trips; a genuinely flaky one (~50% success) plateaus instead
  of tripping.
- **Budget**: optional hard token cap, independent of the loop logic.
- **Known limitation**: fuzzy similarity is word-overlap based (Jaccard),
  not semantic — it won't catch a rephrasing with zero shared words
  (e.g. "find hotels" vs "lodging near me"). It's a cheap heuristic, not NLP.

## Install

```bash
pip install git+https://github.com/teja-154/Agent-guard.git
```

or copy `agent_guard.py` directly into your project — it's one file, stdlib only.

## Testing

```bash
python test_agent_guard.py
```

18 assertions: exact-repeat escalation, fuzzy bucketing, cross-tool
isolation, decay math on both 25% and 50% success rates, decorator
behavior with both tuple-returns and raised exceptions, thread safety,
and budget enforcement.

`demo_integration.py` runs the guard against real (intentionally failing)
HTTP requests, not synthetic data, so you can watch it trip on an actual
network failure.

## Similar projects

This category is well-covered already. Worth a look before building on top
of this one:

- [AgentCircuit](https://github.com/simranmultani197/AgentCircuit) — decorator-based, works with LangGraph/LangChain/CrewAI/AutoGen
- [aura-guard](https://github.com/auraguardhq/aura-guard) — multi-tool sequence loop detection (A→B→A→B patterns)
- [LoopGuard](https://pkg.go.dev/github.com/loop-eng/loopguard) — daemon that monitors Claude Code/Codex/Gemini CLI sessions live
- [AgentBreaker](https://pypi.org/project/agentbreaker-sdk/) — orchestration-layer breaker with a dashboard

This one is smaller and dependency-free, which is the tradeoff: less
capability, but you can read the entire thing in five minutes.

## License

MIT
