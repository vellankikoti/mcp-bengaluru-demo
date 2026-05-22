"""
Integration tests for FastAPI agent server.
Covers TEST_PLAN IDs: I-01 through I-10

These tests start the server in-process using httpx.AsyncClient with FastAPI's ASGI transport.
No cluster required — tools that would call k8s are not invoked in these tests.
"""
import pytest
import pytest_asyncio
import sys
import json
from pathlib import Path
from unittest import mock

# Mock kubernetes before importing server
import types
import unittest.mock as umock

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
class _FakeApiException(Exception):
    def __init__(self, status=500, reason="error"):
        self.status = status
        self.reason = reason
_fake_k8s.client.exceptions.ApiException = _FakeApiException

_fake_k8s.client.exceptions.ApiException = _FakeApiException
_fake_k8s.ApiException = _FakeApiException

# Register all submodule paths so from-imports resolve correctly
sys.modules["kubernetes"] = _fake_k8s
sys.modules["kubernetes.client"] = _fake_k8s.client
sys.modules["kubernetes.config"] = _fake_k8s.config
sys.modules["kubernetes.client.exceptions"] = _fake_k8s.client.exceptions

agent_dir = str(Path(__file__).parent.parent / "agent")
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

import httpx
from httpx import AsyncClient, ASGITransport

# Import app after patching
import importlib
import tools as _tools_mod
import server as server_mod

app = server_mod.app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── I-01: Health endpoint ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_i01_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model" in data


# ── I-02: Security ON by default ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_i02_security_on_by_default(client):
    resp = await client.get("/api/demo/security")
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_on"] is True, (
        f"I-02 CRITICAL FAIL: server must start with security_on=True, got {data['security_on']}"
    )


# ── I-03: Toggle security off ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_i03_toggle_security_off(client):
    resp = await client.post("/api/demo/security", json={"security_on": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["security_on"] is False

    # restore
    await client.post("/api/demo/security", json={"security_on": True})


# ── I-04: Toggle security on → token created ─────────────────────────────────

@pytest.mark.asyncio
async def test_i04_toggle_security_on_creates_token(client):
    # First turn off, then on
    await client.post("/api/demo/security", json={"security_on": False})
    resp = await client.post("/api/demo/security", json={"security_on": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_on"] is True
    assert data["token"] is not None
    token = data["token"]
    assert "id" in token
    assert "scope" in token
    assert "ttl_s" in token
    assert token["ttl_s"] == 300


# ── I-05: Audit endpoint returns list ────────────────────────────────────────

@pytest.mark.asyncio
async def test_i05_audit_returns_entries(client):
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data
    assert isinstance(data["entries"], list)


# ── I-06: Replay list returns recordings ─────────────────────────────────────

@pytest.mark.asyncio
async def test_i06_replay_list_not_empty(client):
    resp = await client.get("/api/replay")
    assert resp.status_code == 200
    data = resp.json()
    assert "recordings" in data
    names = [r["name"] for r in data["recordings"]]
    assert "cascade" in names, f"I-06 FAIL: cascade recording missing. Found: {names}"
    assert "dangerous-agent" in names, f"I-06 FAIL: dangerous-agent recording missing. Found: {names}"


# ── I-07: Cascade replay returns SSE stream ───────────────────────────────────

@pytest.mark.asyncio
async def test_i07_cascade_replay_is_sse(client):
    async with client.stream("GET", "/api/replay/cascade") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Read first chunk
        first_chunk = None
        async for chunk in resp.aiter_text():
            if chunk.strip():
                first_chunk = chunk
                break
        assert first_chunk is not None
        assert first_chunk.startswith("data: ")


# ── I-08: Dangerous-agent replay returns SSE stream ──────────────────────────

@pytest.mark.asyncio
async def test_i08_dangerous_agent_replay_is_sse(client):
    async with client.stream("GET", "/api/replay/dangerous-agent") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        first_chunk = None
        async for chunk in resp.aiter_text():
            if chunk.strip():
                first_chunk = chunk
                break
        assert first_chunk is not None


# ── I-09: Nonexistent replay returns 404 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_i09_nonexistent_replay_404(client):
    resp = await client.get("/api/replay/does-not-exist")
    assert resp.status_code == 404


# ── I-10: Approval of nonexistent request returns 404 ────────────────────────

@pytest.mark.asyncio
async def test_i10_approval_nonexistent_returns_404(client):
    resp = await client.post("/api/approval/nonexistent-id-xyz", json={"approved": True})
    assert resp.status_code == 404


# ── Security regression: list_secrets does not execute when denied ────────────

@pytest.mark.asyncio
async def test_s02_list_secrets_not_executed_when_denied(client):
    """S-02: When policy DENY, the tool function must not be called."""
    # Ensure security is on
    await client.post("/api/demo/security", json={"security_on": True})

    call_count = {"n": 0}
    original = _tools_mod.list_secrets

    async def _spy(*args, **kwargs):
        call_count["n"] += 1
        return await original(*args, **kwargs)

    with mock.patch.object(_tools_mod, "list_secrets", side_effect=_spy):
        # Trigger via the policy engine directly (not via full chat loop)
        import policy as p
        result = p.evaluate("list_secrets", {"namespace": "production"}, security_on=True)
        assert result.action == p.PolicyAction.DENY
        # The tool should not have been called by the policy evaluation
        assert call_count["n"] == 0, "S-02 FAIL: list_secrets was called despite DENY"
