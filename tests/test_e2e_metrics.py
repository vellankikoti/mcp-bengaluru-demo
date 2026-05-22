"""
E2E tests for live observability stack — Prometheus, Alertmanager, audit log writes.
Requires: kind cluster running, port-forwards alive (make agent or kubectl port-forward).
Skip automatically if endpoints are unreachable.

Covers TEST_PLAN IDs: E-01 through E-05
"""
import pytest
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

PROM_URL = "http://localhost:9092"
AM_URL   = "http://localhost:9093"


def _prom_reachable() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"{PROM_URL}/-/ready", timeout=2)
        return True
    except Exception:
        return False


def _am_reachable() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"{AM_URL}/-/ready", timeout=2)
        return True
    except Exception:
        return False


requires_prom = pytest.mark.skipif(not _prom_reachable(), reason="Prometheus port-forward not running")
requires_am   = pytest.mark.skipif(not _am_reachable(),   reason="Alertmanager port-forward not running")


# ── E-01: prometheus_query returns real data ──────────────────────────────────

@requires_prom
@pytest.mark.asyncio
async def test_e01_prometheus_query_returns_data():
    """prometheus_query('up') should return at least one series from the live cluster."""
    import tools
    result = await tools.prometheus_query("up")
    assert "Query: up" in result, f"E-01 FAIL: unexpected response format:\n{result}"
    assert "Results" in result and "series" in result, f"E-01 FAIL: no results:\n{result}"
    # Must have at least 1 series (node-exporter, kube-state-metrics, etc.)
    import re
    m = re.search(r"Results \((\d+) series\)", result)
    assert m and int(m.group(1)) >= 1, f"E-01 FAIL: zero series returned:\n{result}"


# ── E-02: prometheus_query for production memory ──────────────────────────────

@requires_prom
@pytest.mark.asyncio
async def test_e02_prometheus_query_production_memory():
    """container_memory_working_set_bytes for production namespace should return pod data."""
    import tools
    result = await tools.prometheus_query(
        'container_memory_working_set_bytes{namespace="production"}'
    )
    # Either real data or explicit "no data" response — not an error
    assert "Prometheus unreachable" not in result, f"E-02 FAIL: Prometheus unreachable:\n{result}"
    assert "Prometheus error" not in result, f"E-02 FAIL: Prometheus error:\n{result}"
    # Should have production pod metrics
    assert "production" in result or "No data returned" in result, (
        f"E-02 FAIL: unexpected result:\n{result}"
    )


# ── E-03: prometheus_range returns time-series summary ────────────────────────

@requires_prom
@pytest.mark.asyncio
async def test_e03_prometheus_range_returns_summary():
    """prometheus_range('up', '5m') should return a formatted range table."""
    import tools
    result = await tools.prometheus_range("up", duration="5m", step="30s")
    assert "Prometheus unreachable" not in result, f"E-03 FAIL: Prometheus unreachable:\n{result}"
    assert "Prometheus error" not in result, f"E-03 FAIL: Prometheus error:\n{result}"
    # Either a range table or "no range data"
    assert "Range query: up" in result or "No range data" in result, (
        f"E-03 FAIL: unexpected format:\n{result}"
    )


# ── E-04: get_alerts reaches Alertmanager ────────────────────────────────────

@requires_am
@pytest.mark.asyncio
async def test_e04_get_alerts_reaches_alertmanager():
    """get_alerts() must reach Alertmanager and return formatted output (not an error)."""
    import tools
    result = await tools.get_alerts()
    assert "Alertmanager unreachable" not in result, f"E-04 FAIL: {result}"
    # Either alerts or healthy message
    assert "ALERT" in result or "No firing alerts" in result or "firing" in result.lower(), (
        f"E-04 FAIL: unexpected response format:\n{result}"
    )


# ── E-05: get_alerts returns known background alerts ─────────────────────────

@requires_am
@pytest.mark.asyncio
async def test_e05_get_alerts_watchdog_present():
    """Watchdog alert should always be firing in a healthy cluster."""
    import tools
    result = await tools.get_alerts()
    assert "Alertmanager unreachable" not in result, f"E-05 FAIL: {result}"
    # Watchdog fires in all kube-prometheus-stack installs — confirms real AM connection
    assert "Watchdog" in result, (
        f"E-05 FAIL: Watchdog alert not present — is Alertmanager connected to Prometheus?\n{result}"
    )


# ── E-06: Audit log writes on tool execution ─────────────────────────────────

@pytest.mark.asyncio
async def test_e06_audit_log_written_on_deny():
    """A DENY policy decision must write an entry to the audit log."""
    import types, unittest.mock as umock
    _fake_k8s = types.ModuleType("kubernetes")
    _fake_k8s.client = types.ModuleType("kubernetes.client")
    _fake_k8s.config = types.ModuleType("kubernetes.config")
    _fake_k8s.config.load_kube_config = lambda **kwargs: None
    _fake_k8s.config.load_incluster_config = lambda: None
    _fake_k8s.config.list_kube_config_contexts = lambda **kwargs: ([], {"name": "test"})
    _fake_k8s.client.CoreV1Api = umock.MagicMock
    _fake_k8s.client.AppsV1Api = umock.MagicMock
    _fake_k8s.client.AutoscalingV1Api = umock.MagicMock
    _fake_k8s.client.exceptions = types.ModuleType("kubernetes.client.exceptions")
    class _FakeEx(Exception):
        def __init__(self, status=500, reason="err"):
            self.status = status; self.reason = reason
    _fake_k8s.client.exceptions.ApiException = _FakeEx
    _fake_k8s.ApiException = _FakeEx
    sys.modules.setdefault("kubernetes", _fake_k8s)
    sys.modules.setdefault("kubernetes.client", _fake_k8s.client)
    sys.modules.setdefault("kubernetes.config", _fake_k8s.config)
    sys.modules.setdefault("kubernetes.client.exceptions", _fake_k8s.client.exceptions)

    import httpx
    from httpx import AsyncClient, ASGITransport
    import server as server_mod

    # Reset audit log and security state
    server_mod._audit_log.clear()
    server_mod._security_on = True

    app = server_mod.app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Consume the full SSE stream for list_secrets (will be DENY)
        events = []
        async with client.stream("POST", "/api/chat", json={
            "messages": [{"role": "user", "content": "list secrets in production"}],
            "tool_choice": {"type": "tool", "name": "list_secrets"},
        }) as resp:
            if resp.status_code == 200:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        events.append(line[6:])

    # Whether or not chat endpoint is available, the policy evaluate + audit write
    # is tested directly here:
    import policy as p
    import server as s

    before = len(s._audit_log)
    # Manually drive _run_tool_with_policy for list_secrets
    gen = s._run_tool_with_policy("list_secrets", {"namespace": "production"})
    async for _ in gen:
        pass
    after = len(s._audit_log)

    assert after > before, (
        f"E-06 FAIL: audit log not written after DENY. before={before}, after={after}"
    )
    last = s._audit_log[-1]
    assert last["tool"] == "list_secrets", f"E-06 FAIL: wrong tool in audit: {last}"
    assert last["action"] == "deny", f"E-06 FAIL: expected action=deny, got {last['action']}"
    assert "rule" in last, "E-06 FAIL: audit entry missing 'rule'"
    assert "ts" in last, "E-06 FAIL: audit entry missing timestamp"


# ── E-07: Audit entry for ALLOW includes duration_ms and result_preview ───────

@pytest.mark.asyncio
async def test_e07_audit_entry_allow_has_duration_and_preview():
    """An ALLOW tool execution must write duration_ms and result_preview to the audit log."""
    import types, unittest.mock as umock
    _fake_k8s = types.ModuleType("kubernetes")
    _fake_k8s.client = types.ModuleType("kubernetes.client")
    _fake_k8s.config = types.ModuleType("kubernetes.config")
    _fake_k8s.config.load_kube_config = lambda **kwargs: None
    _fake_k8s.config.load_incluster_config = lambda: None
    _fake_k8s.config.list_kube_config_contexts = lambda **kwargs: ([], {"name": "test"})
    _fake_k8s.client.CoreV1Api = umock.MagicMock
    _fake_k8s.client.AppsV1Api = umock.MagicMock
    _fake_k8s.client.AutoscalingV1Api = umock.MagicMock
    _fake_k8s.client.exceptions = types.ModuleType("kubernetes.client.exceptions")
    class _FakeEx(Exception):
        def __init__(self, status=500, reason="err"):
            self.status = status; self.reason = reason
    _fake_k8s.client.exceptions.ApiException = _FakeEx
    _fake_k8s.ApiException = _FakeEx
    sys.modules.setdefault("kubernetes", _fake_k8s)
    sys.modules.setdefault("kubernetes.client", _fake_k8s.client)
    sys.modules.setdefault("kubernetes.config", _fake_k8s.config)
    sys.modules.setdefault("kubernetes.client.exceptions", _fake_k8s.client.exceptions)

    import server as s
    import tools as t

    s._security_on = True

    # Patch list_pods to return a known string without hitting the cluster
    async def _fake_list_pods(namespace="production"):
        return "pod-a Running\npod-b Running"

    original = t.list_pods
    t.list_pods = _fake_list_pods
    # Also patch in server's TOOL_REGISTRY (it holds a reference)
    s.TOOL_REGISTRY["list_pods"] = _fake_list_pods

    before = len(s._audit_log)
    gen = s._run_tool_with_policy("list_pods", {"namespace": "production"})
    async for _ in gen:
        pass
    after = len(s._audit_log)

    # Restore
    t.list_pods = original
    s.TOOL_REGISTRY["list_pods"] = original

    assert after > before, "E-07 FAIL: audit log not written after ALLOW"
    entry = s._audit_log[-1]
    assert entry["tool"] == "list_pods", f"E-07 FAIL: wrong tool: {entry}"
    assert entry["action"] == "allow", f"E-07 FAIL: expected allow, got {entry['action']}"
    assert "duration_ms" in entry, "E-07 FAIL: duration_ms missing from audit entry"
    assert isinstance(entry["duration_ms"], int), "E-07 FAIL: duration_ms not int"
    assert "result_preview" in entry, "E-07 FAIL: result_preview missing from audit entry"
    assert "pod-a" in entry["result_preview"], "E-07 FAIL: result_preview doesn't contain tool output"
