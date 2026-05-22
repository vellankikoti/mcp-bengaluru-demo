"""
Unit tests for agent/policy.py
Covers TEST_PLAN IDs: U-01 through U-10

No cluster, no LLM, no network required.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

import policy as p


# ── U-01: Read tools ALLOW when security on ──────────────────────────────────

READ_TOOLS = [
    "list_pods", "get_pod_logs", "describe_pod", "get_deployments",
    "get_events", "get_node_status", "get_hpa_status",
    "prometheus_query", "prometheus_range", "get_alerts", "draft_postmortem",
]

@pytest.mark.parametrize("tool", READ_TOOLS)
def test_u01_read_tools_allow_when_secure(tool):
    result = p.evaluate(tool, {}, security_on=True)
    assert result.action == p.PolicyAction.ALLOW, (
        f"U-01 FAIL: {tool} should ALLOW with security_on=True, got {result.action}"
    )


# ── U-02: list_secrets DENY when security on ─────────────────────────────────

def test_u02_list_secrets_deny():
    result = p.evaluate("list_secrets", {"namespace": "production"}, security_on=True)
    assert result.action == p.PolicyAction.DENY, (
        f"U-02 FAIL: list_secrets should DENY, got {result.action}"
    )
    assert result.rule == "k8s.read.secrets"


# ── U-03: restart_deployment REQUIRE_APPROVAL ────────────────────────────────

def test_u03_restart_deployment_requires_approval():
    result = p.evaluate("restart_deployment", {"deployment_name": "payment-service"}, security_on=True)
    assert result.action == p.PolicyAction.REQUIRE_APPROVAL, (
        f"U-03 FAIL: restart_deployment should REQUIRE_APPROVAL, got {result.action}"
    )
    assert result.rule == "k8s.write.deployments"


def test_u03b_scale_deployment_requires_approval():
    result = p.evaluate("scale_deployment", {"deployment_name": "payment-service", "replicas": 3}, security_on=True)
    assert result.action == p.PolicyAction.REQUIRE_APPROVAL


# ── U-04: All tools ALLOW when security_on=False ─────────────────────────────

ALL_KNOWN_TOOLS = READ_TOOLS + ["list_secrets", "restart_deployment", "scale_deployment"]

@pytest.mark.parametrize("tool", ALL_KNOWN_TOOLS)
def test_u04_all_tools_allow_when_insecure(tool):
    result = p.evaluate(tool, {}, security_on=False)
    assert result.action == p.PolicyAction.ALLOW, (
        f"U-04 FAIL: {tool} should ALLOW with security_on=False, got {result.action}"
    )


# ── U-05: Unknown tool → DENY (fail-closed) ──────────────────────────────────

def test_u05_unknown_tool_denied():
    result = p.evaluate("delete_all_pods", {}, security_on=True)
    assert result.action == p.PolicyAction.DENY, "U-05 FAIL: unknown tool should be denied"
    assert result.rule == "default.deny-unknown"


def test_u05b_unknown_tool_denied_even_security_off():
    """Even with security off, unknown tools get the allow-all pass.
    This tests that the no-policy path doesn't crash on unknown tools."""
    result = p.evaluate("totally_unknown_tool", {}, security_on=False)
    assert result.action == p.PolicyAction.ALLOW  # no-policy mode allows all


# ── U-06: request_id is 8-char string ────────────────────────────────────────

def test_u06_request_id_format():
    result = p.evaluate("list_pods", {}, security_on=True)
    assert isinstance(result.request_id, str)
    assert len(result.request_id) == 8, f"U-06 FAIL: request_id should be 8 chars, got {len(result.request_id)}"


def test_u06b_request_ids_unique():
    r1 = p.evaluate("list_pods", {}, security_on=True)
    r2 = p.evaluate("list_pods", {}, security_on=True)
    assert r1.request_id != r2.request_id, "U-06b FAIL: consecutive calls must produce unique request IDs"


# ── U-07: blast_radius populated for write tools ─────────────────────────────

def test_u07_write_tools_have_blast_radius():
    for tool in ["restart_deployment", "scale_deployment"]:
        result = p.evaluate(tool, {}, security_on=True)
        assert result.blast_radius is not None, (
            f"U-07 FAIL: {tool} should have blast_radius, got None"
        )
        assert len(result.blast_radius) > 10, "blast_radius should be a meaningful string"


# ── U-08: blast_radius is None for read tools ────────────────────────────────

@pytest.mark.parametrize("tool", READ_TOOLS)
def test_u08_read_tools_no_blast_radius(tool):
    result = p.evaluate(tool, {}, security_on=True)
    assert result.blast_radius is None, (
        f"U-08 FAIL: {tool} should have blast_radius=None, got {result.blast_radius}"
    )


# ── U-09: security_on=False reason contains "DISABLED" ───────────────────────

def test_u09_insecure_reason_mentions_disabled():
    result = p.evaluate("list_pods", {}, security_on=False)
    assert "DISABLED" in result.reason, (
        f"U-09 FAIL: insecure mode reason should mention DISABLED, got: {result.reason}"
    )


# ── U-10: evaluated_at is a float ────────────────────────────────────────────

def test_u10_evaluated_at_is_float():
    result = p.evaluate("list_pods", {}, security_on=True)
    assert isinstance(result.evaluated_at, float), (
        f"U-10 FAIL: evaluated_at should be float, got {type(result.evaluated_at)}"
    )


# ── Critical security invariant: the default must be policy ON ───────────────

def test_security_invariant_server_default():
    """
    CRITICAL: server.py must default _security_on=True.
    This test reads the source file directly to catch regressions.
    If this test fails, the demo will silently bypass all policy gates.
    """
    import ast
    server_path = Path(__file__).parent.parent / "agent" / "server.py"
    source = server_path.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "_security_on":
                value = node.value
                assert isinstance(value, ast.Constant) and value.value is True, (
                    "CRITICAL SECURITY FAIL: _security_on in server.py must default to True. "
                    f"Found: {ast.dump(value)}"
                )
                return
    pytest.fail("CRITICAL: _security_on variable not found in server.py")
