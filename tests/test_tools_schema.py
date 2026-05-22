"""
Unit tests for agent/tools.py — schema validation only.
No cluster, no network required.
Covers TEST_PLAN IDs: U-11 through U-16
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

# Import only the schema definitions — not the k8s client (which needs a cluster)
# We do this by importing the constants before the module tries to connect
import importlib.util
import ast

TOOLS_PATH = Path(__file__).parent.parent / "agent" / "tools.py"
AGENT_DIR = Path(__file__).parent.parent / "agent"


def _get_tool_definitions():
    """Extract TOOL_DEFINITIONS and TOOL_REGISTRY from tools.py without running k8s client init."""
    source = TOOLS_PATH.read_text()
    # The tool definitions are pure Python dicts — we can extract them safely
    # by importing with mocked k8s modules
    import unittest.mock as mock
    import types

    # Build a minimal fake kubernetes module
    fake_k8s = types.ModuleType("kubernetes")
    fake_k8s.client = types.ModuleType("kubernetes.client")
    fake_k8s.config = types.ModuleType("kubernetes.config")
    fake_k8s.config.load_kube_config = lambda **kwargs: None
    fake_k8s.config.load_incluster_config = lambda: None
    fake_k8s.config.list_kube_config_contexts = lambda **kwargs: ([], {"name": "test"})
    fake_k8s.client.CoreV1Api = mock.MagicMock
    fake_k8s.client.AppsV1Api = mock.MagicMock
    fake_k8s.client.AutoscalingV1Api = mock.MagicMock
    fake_k8s.client.exceptions = types.ModuleType("kubernetes.client.exceptions")

    class FakeApiException(Exception):
        def __init__(self, status=500, reason="error"):
            self.status = status
            self.reason = reason
    fake_k8s.client.exceptions.ApiException = FakeApiException

    with mock.patch.dict("sys.modules", {
        "kubernetes": fake_k8s,
        "kubernetes.client": fake_k8s.client,
        "kubernetes.config": fake_k8s.config,
        "kubernetes.client.exceptions": fake_k8s.client.exceptions,
        "httpx": mock.MagicMock(),
    }):
        spec = importlib.util.spec_from_file_location("tools_test", TOOLS_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.TOOL_DEFINITIONS, mod.TOOL_REGISTRY


TOOL_DEFINITIONS, TOOL_REGISTRY = _get_tool_definitions()
EXPECTED_TOOL_COUNT = 14


# ── U-11: All tools have name, description, input_schema ─────────────────────

def test_u11_all_tools_have_required_fields():
    assert len(TOOL_DEFINITIONS) == EXPECTED_TOOL_COUNT, (
        f"U-11 FAIL: expected {EXPECTED_TOOL_COUNT} tools, got {len(TOOL_DEFINITIONS)}"
    )
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool, f"Tool missing 'name': {tool}"
        assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
        assert "input_schema" in tool, f"Tool {tool.get('name')} missing 'input_schema'"
        assert isinstance(tool["description"], str) and len(tool["description"]) > 20, (
            f"Tool {tool['name']} description too short: {tool['description']}"
        )


# ── U-12: TOOL_REGISTRY and TOOL_DEFINITIONS are consistent ──────────────────

def test_u12_registry_matches_definitions():
    def_names = {t["name"] for t in TOOL_DEFINITIONS}
    reg_names = set(TOOL_REGISTRY.keys())
    assert def_names == reg_names, (
        f"U-12 FAIL: mismatch between definitions and registry.\n"
        f"  Only in definitions: {def_names - reg_names}\n"
        f"  Only in registry:   {reg_names - def_names}"
    )


# ── U-13: restart_deployment requires deployment_name ────────────────────────

def test_u13_restart_deployment_requires_deployment_name():
    restart_def = next(t for t in TOOL_DEFINITIONS if t["name"] == "restart_deployment")
    schema = restart_def["input_schema"]
    assert "required" in schema, "U-13 FAIL: restart_deployment should have required fields"
    assert "deployment_name" in schema["required"], (
        "U-13 FAIL: deployment_name should be required for restart_deployment"
    )


# ── U-14: scale_deployment replicas max=20 ───────────────────────────────────

def test_u14_scale_deployment_replicas_max():
    scale_def = next(t for t in TOOL_DEFINITIONS if t["name"] == "scale_deployment")
    replicas_prop = scale_def["input_schema"]["properties"]["replicas"]
    assert replicas_prop.get("maximum") == 20, (
        f"U-14 FAIL: scale_deployment replicas maximum should be 20, "
        f"got {replicas_prop.get('maximum')}"
    )
    assert replicas_prop.get("minimum") == 0, (
        f"U-14 FAIL: scale_deployment replicas minimum should be 0"
    )


# ── U-15: list_secrets description explicitly says no secret values ───────────

def test_u15_list_secrets_description_mentions_no_values():
    secrets_def = next(t for t in TOOL_DEFINITIONS if t["name"] == "list_secrets")
    desc = secrets_def["description"].lower()
    assert "not" in desc and "value" in desc, (
        f"U-15 FAIL: list_secrets description must say it does NOT return values.\n"
        f"Got: {secrets_def['description']}"
    )


# ── U-16: draft_postmortem required fields ────────────────────────────────────

def test_u16_draft_postmortem_required_fields():
    pm_def = next(t for t in TOOL_DEFINITIONS if t["name"] == "draft_postmortem")
    required = set(pm_def["input_schema"].get("required", []))
    expected_required = {"incident_title", "severity", "affected_services", "root_cause", "remediation"}
    assert expected_required.issubset(required), (
        f"U-16 FAIL: draft_postmortem missing required fields.\n"
        f"  Expected (subset): {expected_required}\n"
        f"  Got: {required}"
    )


# ── Additional: severity enum validated ──────────────────────────────────────

def test_draft_postmortem_severity_enum():
    pm_def = next(t for t in TOOL_DEFINITIONS if t["name"] == "draft_postmortem")
    severity_prop = pm_def["input_schema"]["properties"]["severity"]
    assert "enum" in severity_prop, "severity should have enum constraint"
    assert set(severity_prop["enum"]) == {"critical", "high", "medium", "low"}


# ── Additional: all registries are callable ───────────────────────────────────

def test_all_registry_functions_are_callable():
    for name, fn in TOOL_REGISTRY.items():
        assert callable(fn), f"TOOL_REGISTRY['{name}'] is not callable"
