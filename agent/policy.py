"""
Policy engine — simulates OPA (Open Policy Agent) evaluation for this demo.

─────────────────────────────────────────────────────────────
DEMO vs PRODUCTION — READ THIS BEFORE PRESENTING
─────────────────────────────────────────────────────────────
What this file IS:
  A Python dict lookup that demonstrates the CONCEPT of a policy gate.
  Each tool has exactly one rule. `evaluate()` is called before every
  tool execution. When security_on=False the engine returns ALLOW for
  everything, showing the audience what an over-permissioned agent looks like.

What this file IS NOT:
  • Real OPA (Open Policy Agent) — no Rego policies, no OPA binary
  • A sidecar / out-of-process policy engine
  • Cryptographically enforced — the Python process trusts itself

What production requires (show this slide during the talk):
  • OPA sidecar (or OPA Gatekeeper) as a separate process
  • Rego policy files (.rego) versioned in git
  • Policy bundle distribution (OPA bundle server or ConfigMap)
  • mTLS between agent and OPA sidecar
  • Policy decision logs shipped to a SIEM

The architecture diagram for this talk uses "OPA-style" deliberately.
This implementation teaches the INTERFACE and SEMANTICS correctly.
The production path is additive — not a rewrite.
─────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PolicyAction(str, Enum):
    ALLOW            = "allow"
    DENY             = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyResult:
    action:       PolicyAction
    tool:         str
    input:        dict
    reason:       str
    rule:         str
    request_id:   str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    blast_radius: Optional[str] = None
    evaluated_at: float = field(default_factory=time.monotonic)


# ── Rule table ────────────────────────────────────────────────────────────────
# One entry per tool.  Keys: action, rule, reason (optional), blast_radius (optional).
_RULES: dict[str, dict] = {
    # ── Read-only / observability ─────────────────────────────────────────────
    "list_pods":         {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.pods",
                          "reason": "Read-only pod list — permitted"},
    "get_pod_logs":      {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.logs",
                          "reason": "Read-only log access — permitted"},
    "describe_pod":      {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.pods",
                          "reason": "Read-only pod describe — permitted"},
    "get_deployments":   {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.deployments",
                          "reason": "Read-only deployment list — permitted"},
    "get_events":        {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.events",
                          "reason": "Read-only event list — permitted"},
    "get_node_status":   {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.nodes",
                          "reason": "Read-only node status — permitted"},
    "get_hpa_status":    {"action": PolicyAction.ALLOW,
                          "rule":   "k8s.read.hpa",
                          "reason": "Read-only HPA status — permitted"},
    "prometheus_query":  {"action": PolicyAction.ALLOW,
                          "rule":   "observability.metrics.read",
                          "reason": "Metrics read — permitted"},
    "prometheus_range":  {"action": PolicyAction.ALLOW,
                          "rule":   "observability.metrics.read",
                          "reason": "Metrics range read — permitted"},
    "get_alerts":        {"action": PolicyAction.ALLOW,
                          "rule":   "observability.alerts.read",
                          "reason": "Alert read — permitted"},

    # ── Documentation / postmortem ────────────────────────────────────────────
    "draft_postmortem":  {"action": PolicyAction.ALLOW,
                          "rule":   "docs.postmortem.write",
                          "reason": "Postmortem generation — permitted (local, no cluster writes)"},

    # ── Sensitive read — DENY (the problem the talk is about) ─────────────────
    "list_secrets":      {"action": PolicyAction.DENY,
                          "rule":   "k8s.read.secrets",
                          "reason": "Secrets access DENIED — agent ServiceAccount lacks "
                                    "get/list on secrets. "
                                    "Use a dedicated secrets manager (Vault, ESO)."},

    # ── Write / destructive — require human approval ──────────────────────────
    "restart_deployment":{"action": PolicyAction.REQUIRE_APPROVAL,
                          "rule":   "k8s.write.deployments",
                          "reason": "Destructive write — human approval required",
                          "blast_radius": "Rolling restart terminates all running pods. "
                                          "Expect brief traffic disruption during rollout."},
    "scale_deployment":  {"action": PolicyAction.REQUIRE_APPROVAL,
                          "rule":   "k8s.write.deployments",
                          "reason": "Destructive write — human approval required",
                          "blast_radius": "Replica count change may reduce availability "
                                          "or cause resource contention."},
}


def evaluate(tool: str, tool_input: dict, security_on: bool) -> PolicyResult:
    """Evaluate a proposed tool call against the policy rule set."""
    if not security_on:
        return PolicyResult(
            action=PolicyAction.ALLOW,
            tool=tool,
            input=tool_input,
            reason="⚠ Security policy DISABLED — all tools permitted (demo: no-policy mode)",
            rule="demo.no-policy",
        )

    rule = _RULES.get(tool)
    if rule is None:
        return PolicyResult(
            action=PolicyAction.DENY,
            tool=tool,
            input=tool_input,
            reason=f"No policy rule for '{tool}' — denied by default (fail-closed)",
            rule="default.deny-unknown",
        )

    return PolicyResult(
        action=rule["action"],
        tool=tool,
        input=tool_input,
        reason=rule.get("reason", f"Rule matched: {rule['rule']}"),
        rule=rule["rule"],
        blast_radius=rule.get("blast_radius"),
    )
