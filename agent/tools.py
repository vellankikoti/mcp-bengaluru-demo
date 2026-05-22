"""
MCP Kubernetes tools — sync k8s client wrapped in asyncio.to_thread,
async httpx for Prometheus/Alertmanager.
Auto-detects in-cluster vs kubeconfig.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

import httpx
from kubernetes import client as k8s, config as k8s_config
from kubernetes.client.exceptions import ApiException

# ── Environment detection ────────────────────────────────────────────────────

IN_CLUSTER = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")

# Observability endpoints — always via local port-forwards (start.sh binds these)
PROMETHEUS_URL = (
    "http://kube-prometheus-stack-prometheus.observability:9090"
    if IN_CLUSTER
    else "http://localhost:9092"
)
ALERTMANAGER_URL = (
    "http://kube-prometheus-stack-alertmanager.observability:9093"
    if IN_CLUSTER
    else "http://localhost:9093"
)


def get_observability_urls() -> dict:
    """Return prometheus/alertmanager/grafana URLs.
    Outside the cluster these are always the local port-forwards started by start.sh.
    """
    if IN_CLUSTER:
        return {
            "prometheus":   PROMETHEUS_URL,
            "alertmanager": ALERTMANAGER_URL,
            "grafana":      "http://localhost:3000",
        }
    return {
        "prometheus":   "http://localhost:9092",
        "alertmanager": "http://localhost:9093",
        "grafana":      "http://localhost:3002",
    }


def _default_context() -> str:
    """Return the current kubectl context, or empty string if none."""
    env_ctx = os.environ.get("KUBE_CONTEXT", "")
    if env_ctx:
        return env_ctx
    try:
        import subprocess
        return subprocess.check_output(
            ["kubectl", "config", "current-context"], text=True
        ).strip()
    except Exception:
        return ""


_active_context: str = _default_context()


def _kubeconfig_path() -> str:
    # Use KUBECONFIG env var if set; otherwise default kubeconfig location
    kc = os.environ.get("KUBECONFIG", "")
    if kc:
        return kc.split(":")[0]  # first path if colon-separated
    return os.path.expanduser("~/.kube/config")


def _init_k8s(context: str = "") -> None:
    if IN_CLUSTER:
        k8s_config.load_incluster_config()
    else:
        k8s_config.load_kube_config(
            config_file=_kubeconfig_path(),
            context=context or _active_context,
        )


_init_k8s()


def get_k8s_contexts() -> dict:
    """Return all kubeconfig contexts and the currently active one."""
    if IN_CLUSTER:
        return {"contexts": ["in-cluster"], "active": "in-cluster"}
    try:
        contexts, active = k8s_config.list_kube_config_contexts(
            config_file=_kubeconfig_path()
        )
        return {
            "contexts": [c["name"] for c in (contexts or [])],
            "active": active["name"] if active else _active_context,
        }
    except Exception as e:
        return {"contexts": [_active_context], "active": _active_context, "error": str(e)}


def switch_k8s_context(context: str) -> None:
    """Switch the global k8s client to a different kubeconfig context."""
    global _active_context
    if IN_CLUSTER:
        raise ValueError("Cannot switch context when running in-cluster")
    _init_k8s(context)
    _active_context = context

# ── Helpers ──────────────────────────────────────────────────────────────────

def _age(ts) -> str:
    if ts is None:
        return "?"
    delta = datetime.now(timezone.utc) - ts
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _pod_display_status(pod) -> str:
    if pod.status is None:
        return "Unknown"
    if pod.metadata.deletion_timestamp:
        return "Terminating"
    if pod.status.container_statuses:
        for cs in pod.status.container_statuses:
            if cs.state:
                if cs.state.waiting and cs.state.waiting.reason:
                    return cs.state.waiting.reason
                if cs.state.terminated and cs.state.terminated.reason:
                    return f"Terminated({cs.state.terminated.reason})"
    return pod.status.phase or "Unknown"


# ── Tool implementations ─────────────────────────────────────────────────────

async def list_pods(namespace: str = "production", label_selector: str = "") -> str:
    def _sync():
        v1 = k8s.CoreV1Api()
        kwargs = {"namespace": namespace}
        if label_selector:
            kwargs["label_selector"] = label_selector
        pods = v1.list_namespaced_pod(**kwargs)
        if not pods.items:
            return f"No pods found in namespace '{namespace}'"
        hdr = f"{'POD':<52} {'STATUS':<24} {'READY':<7} {'RESTARTS':<10} {'AGE'}"
        rows = [hdr, "─" * 105]
        for p in pods.items:
            status = _pod_display_status(p)
            total = len(p.spec.containers)
            ready, restarts = 0, 0
            if p.status.container_statuses:
                for cs in p.status.container_statuses:
                    restarts += cs.restart_count
                    if cs.ready:
                        ready += 1
            age = _age(p.metadata.creation_timestamp)
            rows.append(
                f"{p.metadata.name:<52} {status:<24} {ready}/{total:<5} {restarts:<10} {age}"
            )
        return "\n".join(rows)

    return await asyncio.to_thread(_sync)


async def get_pod_logs(
    pod_name: str,
    namespace: str = "production",
    container: str = "",
    tail_lines: int = 80,
    grep: str = "",
) -> str:
    def _sync():
        v1 = k8s.CoreV1Api()
        kwargs = dict(name=pod_name, namespace=namespace, tail_lines=tail_lines, timestamps=True)
        if container:
            kwargs["container"] = container
        # Also try previous container if pod is in CrashLoopBackOff
        try:
            logs = v1.read_namespaced_pod_log(**kwargs) or "(empty logs)"
        except ApiException as e:
            if e.status == 400:
                try:
                    kwargs["previous"] = True
                    logs = v1.read_namespaced_pod_log(**kwargs) or "(empty previous logs)"
                    logs = "[PREVIOUS CONTAINER LOGS]\n" + logs
                except Exception:
                    return f"Cannot read logs: {e.reason}"
            else:
                return f"API error {e.status}: {e.reason}"
        if grep:
            lines = [l for l in logs.splitlines() if grep.lower() in l.lower()]
            logs = "\n".join(lines) or f"(no lines matching '{grep}')"
        return logs

    return await asyncio.to_thread(_sync)


async def describe_pod(pod_name: str, namespace: str = "production") -> str:
    def _sync():
        v1 = k8s.CoreV1Api()
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            return f"Pod not found: {e.reason}"

        lines = [f"Name:      {pod.metadata.name}",
                 f"Namespace: {pod.metadata.namespace}",
                 f"Node:      {pod.spec.node_name or '<unscheduled>'}",
                 f"Phase:     {pod.status.phase}",
                 f"Age:       {_age(pod.metadata.creation_timestamp)}",
                 ""]

        lines.append("Containers:")
        for c in pod.spec.containers:
            lines.append(f"  {c.name}")
            if c.resources:
                req = c.resources.requests or {}
                lim = c.resources.limits or {}
                lines.append(f"    requests: cpu={req.get('cpu','?')}  memory={req.get('memory','?')}")
                lines.append(f"    limits:   cpu={lim.get('cpu','?')}  memory={lim.get('memory','?')}")
            if c.env:
                fault = {e.name: e.value for e in c.env if "FAULT" in e.name}
                if fault:
                    lines.append(f"    fault-env: {fault}")

        if pod.status.container_statuses:
            lines.append("\nContainer Status:")
            for cs in pod.status.container_statuses:
                lines.append(f"  {cs.name}: ready={cs.ready}  restarts={cs.restart_count}")
                if cs.last_state and cs.last_state.terminated:
                    t = cs.last_state.terminated
                    lines.append(f"    last-exit: reason={t.reason}  exitCode={t.exit_code}  at={t.finished_at}")

        # Pod events
        try:
            events = v1.list_namespaced_event(
                namespace,
                field_selector=f"involvedObject.name={pod_name}",
            )
            if events.items:
                lines.append("\nEvents:")
                for ev in sorted(events.items, key=lambda e: e.last_timestamp or datetime.min.replace(tzinfo=timezone.utc)):
                    lines.append(f"  {ev.reason:<22} {ev.message}")
        except Exception:
            pass

        return "\n".join(lines)

    return await asyncio.to_thread(_sync)


async def get_deployments(namespace: str = "production") -> str:
    def _sync():
        apps = k8s.AppsV1Api()
        deps = apps.list_namespaced_deployment(namespace)
        if not deps.items:
            return f"No deployments in '{namespace}'"
        hdr = f"{'DEPLOYMENT':<35} {'DESIRED':<9} {'READY':<7} {'AVAILABLE':<11} {'IMAGE'}"
        rows = [hdr, "─" * 100]
        for d in deps.items:
            spec = d.spec
            status = d.status
            image = spec.template.spec.containers[0].image if spec.template.spec.containers else "?"
            image = image.split("/")[-1]  # trim registry prefix
            rows.append(
                f"{d.metadata.name:<35} {spec.replicas or 0:<9} "
                f"{status.ready_replicas or 0:<7} {status.available_replicas or 0:<11} {image}"
            )
        return "\n".join(rows)

    return await asyncio.to_thread(_sync)


async def get_events(
    namespace: str = "production", event_type: str = "", reason: str = "", limit: int = 30
) -> str:
    def _sync():
        v1 = k8s.CoreV1Api()
        kwargs = {"namespace": namespace}
        field_parts = []
        if event_type:
            field_parts.append(f"type={event_type}")
        if reason:
            field_parts.append(f"reason={reason}")
        if field_parts:
            kwargs["field_selector"] = ",".join(field_parts)

        events = v1.list_namespaced_event(**kwargs)
        items = sorted(
            events.items,
            key=lambda e: e.last_timestamp or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:limit]

        if not items:
            return f"No events in '{namespace}'" + (f" type={event_type}" if event_type else "")

        rows = [f"{'TYPE':<10} {'REASON':<24} {'OBJECT':<40} {'MESSAGE'}"]
        rows.append("─" * 120)
        for ev in items:
            obj = f"{ev.involved_object.kind}/{ev.involved_object.name}"
            rows.append(
                f"{ev.type or '':<10} {ev.reason or '':<24} {obj:<40} {ev.message or ''}"
            )
        return "\n".join(rows)

    return await asyncio.to_thread(_sync)


async def get_node_status() -> str:
    def _sync():
        v1 = k8s.CoreV1Api()
        nodes = v1.list_node()
        lines = []
        for node in nodes.items:
            name = node.metadata.name
            alloc = node.status.allocatable or {}
            cap = node.status.capacity or {}
            lines.append(f"Node: {name}")
            lines.append(f"  CPU allocatable: {alloc.get('cpu','?')}  capacity: {cap.get('cpu','?')}")
            lines.append(f"  Memory allocatable: {alloc.get('memory','?')}  capacity: {cap.get('memory','?')}")
            lines.append(f"  Pods allocatable: {alloc.get('pods','?')}")

            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            ready = conditions.get("Ready", "Unknown")
            mem_pressure = conditions.get("MemoryPressure", "Unknown")
            disk_pressure = conditions.get("DiskPressure", "Unknown")
            pid_pressure = conditions.get("PIDPressure", "Unknown")
            lines.append(f"  Ready={ready}  MemoryPressure={mem_pressure}  DiskPressure={disk_pressure}  PIDPressure={pid_pressure}")

            taints = node.spec.taints or []
            if taints:
                taint_strs = [f"{t.key}={t.value}:{t.effect}" for t in taints]
                lines.append(f"  Taints: {', '.join(taint_strs)}")
            lines.append("")
        return "\n".join(lines) if lines else "No nodes found"

    return await asyncio.to_thread(_sync)


async def get_hpa_status(namespace: str = "production") -> str:
    def _sync():
        auto = k8s.AutoscalingV1Api()
        try:
            hpas = auto.list_namespaced_horizontal_pod_autoscaler(namespace)
        except ApiException:
            return "No HPAs found (or autoscaling/v1 not available)"
        if not hpas.items:
            return f"No HPAs in '{namespace}'"
        rows = [f"{'HPA':<35} {'MIN':<6} {'MAX':<6} {'CURRENT':<9} {'DESIRED':<9} {'TARGET'}"]
        rows.append("─" * 90)
        for h in hpas.items:
            spec = h.spec
            status = h.status
            rows.append(
                f"{h.metadata.name:<35} {spec.min_replicas or '?':<6} {spec.max_replicas:<6} "
                f"{status.current_replicas or 0:<9} {status.desired_replicas or 0:<9} "
                f"CPU {spec.target_cpu_utilization_percentage or '?'}%"
            )
        return "\n".join(rows)

    return await asyncio.to_thread(_sync)


async def prometheus_query(query: str) -> str:
    prom_url = get_observability_urls()["prometheus"]
    async with httpx.AsyncClient(timeout=10) as http:
        try:
            resp = await http.get(f"{prom_url}/api/v1/query", params={"query": query})
            data = resp.json()
        except Exception as e:
            return f"Prometheus unreachable: {e}"

    if data.get("status") != "success":
        return f"Prometheus error: {data.get('error', 'unknown')}"

    results = data["data"]["result"]
    if not results:
        return f"No data returned for query: {query}"

    rows = []
    for r in results[:20]:
        metric = {k: v for k, v in r["metric"].items() if k != "__name__"}
        label_str = " ".join(f'{k}="{v}"' for k, v in sorted(metric.items()))
        value = r["value"][1]
        try:
            value = f"{float(value):.4f}"
        except Exception:
            pass
        rows.append(f"  {label_str}  →  {value}")

    return f"Query: {query}\nResults ({len(results)} series):\n" + "\n".join(rows)


async def prometheus_range(query: str, duration: str = "15m", step: str = "30s") -> str:
    import time
    prom_url = get_observability_urls()["prometheus"]
    end = int(time.time())
    duration_map = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
    start = end - duration_map.get(duration, 900)

    async with httpx.AsyncClient(timeout=10) as http:
        try:
            resp = await http.get(
                f"{prom_url}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
            )
            data = resp.json()
        except Exception as e:
            return f"Prometheus unreachable: {e}"

    if data.get("status") != "success":
        return f"Prometheus error: {data.get('error', 'unknown')}"

    results = data["data"]["result"]
    if not results:
        return f"No range data for: {query} over last {duration}"

    summary = []
    for r in results[:5]:
        metric = r["metric"]
        values = [float(v[1]) for v in r["values"]]
        if values:
            summary.append(
                f"  {metric.get('pod', metric.get('app', str(metric)))[:40]:<40} "
                f"min={min(values):.3f}  max={max(values):.3f}  last={values[-1]:.3f}"
            )

    return (
        f"Range query: {query}  ({duration}, step={step})\n"
        f"{'SERIES':<42} MIN          MAX          LAST\n"
        + "─" * 80 + "\n"
        + "\n".join(summary)
    )


async def get_alerts() -> str:
    am_url = get_observability_urls()["alertmanager"]
    async with httpx.AsyncClient(timeout=8) as http:
        try:
            resp = await http.get(
                f"{am_url}/api/v2/alerts",
                params={"active": "true", "silenced": "false", "inhibited": "false"},
            )
            alerts = resp.json()
        except Exception as e:
            return f"Alertmanager unreachable: {e}"

    if not alerts:
        return "No firing alerts — cluster is healthy"

    rows = [f"{'ALERT':<45} {'SEVERITY':<12} {'NAMESPACE':<15} {'SINCE'}"]
    rows.append("─" * 100)
    for a in alerts[:20]:
        labels = a.get("labels", {})
        name = labels.get("alertname", "?")
        sev = labels.get("severity", "?")
        ns = labels.get("namespace", "-")
        since = a.get("startsAt", "?")[:19].replace("T", " ")
        rows.append(f"{name:<45} {sev:<12} {ns:<15} {since}")

    return f"{len(alerts)} firing alert(s):\n" + "\n".join(rows)


async def list_secrets(namespace: str = "production") -> str:
    """List secret names and types in a namespace (no values — names only)."""
    def _sync():
        v1 = k8s.CoreV1Api()
        try:
            secrets = v1.list_namespaced_secret(namespace)
        except ApiException as e:
            return f"Cannot list secrets: {e.reason} (status={e.status})"
        if not secrets.items:
            return f"No secrets found in namespace '{namespace}'"
        hdr = f"{'SECRET NAME':<50} {'TYPE':<45} {'KEYS'}"
        rows = [hdr, "─" * 110]
        for s in secrets.items:
            keys = len(s.data or {})
            rows.append(f"{s.metadata.name:<50} {s.type:<45} {keys} key(s)")
        return (
            f"⚠  {len(secrets.items)} secret(s) found in namespace '{namespace}' "
            f"— agent has unrestricted read access to ALL secrets:\n\n"
            + "\n".join(rows)
        )
    return await asyncio.to_thread(_sync)


async def restart_deployment(deployment_name: str, namespace: str = "production") -> str:
    def _sync():
        apps = k8s.AppsV1Api()
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now
                        }
                    }
                }
            }
        }
        try:
            apps.patch_namespaced_deployment(deployment_name, namespace, body)
            return f"Rollout restart triggered for {deployment_name} in {namespace} at {now}"
        except ApiException as e:
            return f"Failed to restart {deployment_name}: {e.reason} (status={e.status})"

    return await asyncio.to_thread(_sync)


async def scale_deployment(deployment_name: str, replicas: int, namespace: str = "production") -> str:
    def _sync():
        apps = k8s.AppsV1Api()
        body = {"spec": {"replicas": replicas}}
        try:
            apps.patch_namespaced_deployment_scale(deployment_name, namespace, body)
            return f"Scaled {deployment_name} to {replicas} replica(s) in {namespace}"
        except ApiException as e:
            return f"Failed to scale {deployment_name}: {e.reason} (status={e.status})"

    return await asyncio.to_thread(_sync)


async def draft_postmortem(
    incident_title: str,
    severity: str,
    affected_services: list,
    root_cause: str,
    timeline: list,
    impact: str,
    remediation: str,
    action_items: list,
) -> str:
    """Generate a structured incident postmortem document."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    severity_label = severity.upper()

    timeline_lines = "\n".join(
        f"  {t.get('time', '?'):>8}  {t.get('event', '')}" for t in (timeline or [])
    )
    action_lines = "\n".join(
        f"  [{i+1}] {a.get('action', str(a))} — owner: {a.get('owner', 'TBD')}, due: {a.get('due', 'next sprint')}"
        for i, a in enumerate(action_items or [])
    )
    services_str = ", ".join(affected_services) if affected_services else "unknown"

    return f"""# Incident Postmortem — {incident_title}
Generated: {now}  |  Severity: {severity_label}

## Impact
{impact}

## Affected Services
{services_str}

## Timeline
{timeline_lines or "  (not provided)"}

## Root Cause
{root_cause}

## Remediation
{remediation}

## Action Items
{action_lines or "  (none specified)"}

---
*Drafted by MCP Incident Agent. Review and edit before publishing to the team wiki.*"""


# ── Tool registry used by server.py ─────────────────────────────────────────

TOOL_REGISTRY = {
    "list_pods": list_pods,
    "get_pod_logs": get_pod_logs,
    "describe_pod": describe_pod,
    "get_deployments": get_deployments,
    "get_events": get_events,
    "get_node_status": get_node_status,
    "get_hpa_status": get_hpa_status,
    "prometheus_query": prometheus_query,
    "prometheus_range": prometheus_range,
    "get_alerts": get_alerts,
    "list_secrets": list_secrets,
    "restart_deployment": restart_deployment,
    "scale_deployment": scale_deployment,
    "draft_postmortem": draft_postmortem,
}

TOOL_DEFINITIONS = [
    {
        "name": "list_pods",
        "description": "List all pods in a namespace with phase, restart count and age. Always start here when diagnosing an incident.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "production", "description": "Kubernetes namespace"},
                "label_selector": {"type": "string", "description": "Label selector e.g. 'app=payment-service'"},
            },
        },
    },
    {
        "name": "get_pod_logs",
        "description": "Fetch recent logs from a pod. Automatically tries previous container logs for CrashLoopBackOff pods.",
        "input_schema": {
            "type": "object",
            "required": ["pod_name"],
            "properties": {
                "pod_name": {"type": "string", "description": "Full pod name"},
                "namespace": {"type": "string", "default": "production"},
                "container": {"type": "string", "description": "Container name if pod has multiple"},
                "tail_lines": {"type": "integer", "default": 80, "description": "Number of log lines to fetch"},
                "grep": {"type": "string", "description": "Filter lines containing this string (case-insensitive)"},
            },
        },
    },
    {
        "name": "describe_pod",
        "description": "Full pod details — resource limits, container states, last exit reason, and associated events. Use after finding a problematic pod with list_pods.",
        "input_schema": {
            "type": "object",
            "required": ["pod_name"],
            "properties": {
                "pod_name": {"type": "string"},
                "namespace": {"type": "string", "default": "production"},
            },
        },
    },
    {
        "name": "get_deployments",
        "description": "List deployments with desired/ready/available replica counts and image versions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "production"},
            },
        },
    },
    {
        "name": "get_events",
        "description": "Cluster events filtered by namespace, type (Normal/Warning), or reason. Use to see OOMKill, BackOff, FailedScheduling etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "production"},
                "event_type": {"type": "string", "description": "'Warning' or 'Normal'"},
                "reason": {"type": "string", "description": "e.g. 'OOMKilling', 'BackOff', 'FailedScheduling'"},
                "limit": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "get_node_status",
        "description": "Node conditions, allocatable CPU/memory, and any taints. Check when pods are Pending or to verify resource headroom.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_hpa_status",
        "description": "Horizontal Pod Autoscaler current vs desired replica counts and target CPU.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "production"},
            },
        },
    },
    {
        "name": "prometheus_query",
        "description": "Run a PromQL instant query. Use for exact metric values — error rates, memory usage, latency percentiles, RPS.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Valid PromQL expression"},
            },
        },
    },
    {
        "name": "prometheus_range",
        "description": "Run a PromQL range query to see a metric trend over time. Returns min/max/last per series.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "duration": {"type": "string", "default": "15m", "description": "5m, 15m, 30m, or 1h"},
                "step": {"type": "string", "default": "30s"},
            },
        },
    },
    {
        "name": "get_alerts",
        "description": "Get all currently firing Alertmanager alerts with severity and start time. Good first step for incident triage.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_secrets",
        "description": "List all Kubernetes secrets in a namespace by name and type. Does NOT return secret values. Use to audit what secrets exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "production", "description": "Kubernetes namespace"},
            },
        },
    },
    {
        "name": "restart_deployment",
        "description": "Trigger a rolling restart of a deployment (equivalent to kubectl rollout restart). Use only when explicitly asked or as a confirmed remediation step.",
        "input_schema": {
            "type": "object",
            "required": ["deployment_name"],
            "properties": {
                "deployment_name": {"type": "string"},
                "namespace": {"type": "string", "default": "production"},
            },
        },
    },
    {
        "name": "scale_deployment",
        "description": "Scale a deployment to a specific replica count. Use only when explicitly asked or as a confirmed remediation step.",
        "input_schema": {
            "type": "object",
            "required": ["deployment_name", "replicas"],
            "properties": {
                "deployment_name": {"type": "string"},
                "replicas": {"type": "integer", "minimum": 0, "maximum": 20},
                "namespace": {"type": "string", "default": "production"},
            },
        },
    },
    {
        "name": "draft_postmortem",
        "description": "Generate a structured incident postmortem document. Call this after an incident is resolved to produce a wiki-ready postmortem with timeline, root cause, and action items.",
        "input_schema": {
            "type": "object",
            "required": ["incident_title", "severity", "affected_services", "root_cause", "remediation"],
            "properties": {
                "incident_title": {"type": "string", "description": "Short incident title e.g. 'payment-service OOMKill cascade'"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"], "description": "Incident severity"},
                "affected_services": {"type": "array", "items": {"type": "string"}, "description": "List of affected service names"},
                "root_cause": {"type": "string", "description": "Technical root cause analysis"},
                "timeline": {
                    "type": "array",
                    "description": "Ordered list of incident timeline events",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "string", "description": "Relative time e.g. 'T-42m', 'T+0s', 'T+30s'"},
                            "event": {"type": "string"},
                        },
                    },
                },
                "impact": {"type": "string", "description": "Business/user impact description"},
                "remediation": {"type": "string", "description": "What was done to resolve the incident"},
                "action_items": {
                    "type": "array",
                    "description": "Follow-up action items to prevent recurrence",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "owner": {"type": "string"},
                            "due": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
]
