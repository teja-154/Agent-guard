import urllib.request
import urllib.error
from agent_guard import CircuitBreaker

cb = CircuitBreaker(window=10, threshold=3)

def mock_agent_tool_call(query: str):
    """Real network call to a non-existent API endpoint to simulate failure."""
    url = f"https://api.github.com/nonexistent_endpoint_for_test_{hash(query)}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return True, response.read().decode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}"
    except Exception as e:
        return False, str(e)

queries = [
    "install python",
    "python install",
    "install python",
    "python install",
    "install python",
    "python install",
]

print("Starting Agent Loop with Guardrail on REAL API FAILURES...\n")
for i, query in enumerate(queries, 1):
    success, result = mock_agent_tool_call(query)
    v = cb.check(tool="search", args={"q": query}, success=success)

    print(f"Step {i}: query='{query}' | Net Success={success} | Action={v.action}")

    if v.action == "WARN":
        print(f"  [GUARD ACTION] Injected warning: '{v.hint}'")
    elif v.action == "TRIP":
        print(f"  [GUARD ACTION] Tripped! Stopping agent execution loop. Reason: {v.reason}")
        break
