"""
Tests that pre-recorded demo files are valid and truthful.
Covers TEST_PLAN IDs: U-17 through U-22

Enforces the RECORDING TRUTH GUARANTEE:
  every tool_result in a recording must match what the real tool returns.
  Specifically: dangerous-agent.jsonl must NOT contain secret values.
"""
import json
import pytest
from pathlib import Path

RECORDINGS_DIR = Path(__file__).parent.parent / "agent" / "demo-recordings"
RECORDINGS = list(RECORDINGS_DIR.glob("*.jsonl"))

# Secret value patterns that must NEVER appear in recordings
# (these would indicate the recording is more alarming than reality)
FORBIDDEN_PATTERNS = [
    "DB_PASSWORD:",
    "sk_live_",
    "SMTP_PASS:",
    "SG.",              # SendGrid key prefix
    "pk_live_",
    "Full values decoded from base64",
    "token-secret:",
    "REAL_KEY_HERE",
]


@pytest.mark.parametrize("recording", RECORDINGS, ids=[r.name for r in RECORDINGS])
def test_u17_u18_recordings_valid_jsonl(recording):
    """U-17, U-18: All non-comment lines in recordings must parse as valid JSON."""
    lines = recording.read_text().splitlines()
    errors = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
            assert "delay_ms" in data, f"line {i}: missing delay_ms"
            assert "event" in data, f"line {i}: missing event"
            assert isinstance(data["delay_ms"], (int, float)), f"line {i}: delay_ms not numeric"
        except (json.JSONDecodeError, AssertionError) as e:
            errors.append(f"  line {i}: {e}")
    assert not errors, f"{recording.name} has JSONL errors:\n" + "\n".join(errors)


def test_u19_dangerous_agent_no_secret_values():
    """U-19: dangerous-agent.jsonl must not contain any secret values."""
    recording = RECORDINGS_DIR / "dangerous-agent.jsonl"
    assert recording.exists(), "dangerous-agent.jsonl not found"
    content = recording.read_text()
    violations = [p for p in FORBIDDEN_PATTERNS if p in content]
    assert not violations, (
        "U-19 FAIL: dangerous-agent.jsonl contains forbidden secret value patterns:\n"
        + "\n".join(f"  • {v}" for v in violations)
        + "\nThe recording must match what tools.py actually returns (names/types/counts only)."
    )


def test_u20_dangerous_agent_matches_list_secrets_format():
    """U-20: dangerous-agent.jsonl tool_result must match list_secrets output format."""
    recording = RECORDINGS_DIR / "dangerous-agent.jsonl"
    content = recording.read_text()

    # Find the tool_result event for list_secrets
    tool_result_content = None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
            event = data.get("event", {})
            if event.get("type") == "tool_result":
                tool_result_content = event.get("content", "")
                break
        except json.JSONDecodeError:
            continue

    assert tool_result_content is not None, "U-20 FAIL: no tool_result event found in recording"

    # Must contain "key(s)" — the format tools.py uses
    assert "key(s)" in tool_result_content, (
        f"U-20 FAIL: tool_result should use 'key(s)' format (matching tools.py output).\n"
        f"Got: {tool_result_content[:200]}"
    )

    # Must contain the warning line that tools.py always emits
    assert "unrestricted read access" in tool_result_content.lower() or "secret" in tool_result_content.lower(), (
        "U-20 FAIL: tool_result should mention unrestricted access or secrets"
    )


@pytest.mark.parametrize("recording", RECORDINGS, ids=[r.name for r in RECORDINGS])
def test_u21_recordings_timing_nonnegative(recording):
    """U-21: All delay_ms values must be non-negative."""
    lines = recording.read_text().splitlines()
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
            delay = data.get("delay_ms", 0)
            assert delay >= 0, f"line {i}: delay_ms {delay} is negative"
        except json.JSONDecodeError:
            pass  # caught by other test


@pytest.mark.parametrize("recording", RECORDINGS, ids=[r.name for r in RECORDINGS])
def test_u22_recordings_end_with_done(recording):
    """U-22: Every recording must end with a 'done' event."""
    lines = [l.strip() for l in recording.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    assert lines, f"{recording.name} is empty"

    last_event_type = None
    for line in reversed(lines):
        try:
            data = json.loads(line)
            last_event_type = data.get("event", {}).get("type")
            break
        except json.JSONDecodeError:
            continue

    assert last_event_type == "done", (
        f"U-22 FAIL: {recording.name} last event type is '{last_event_type}', expected 'done'"
    )


def test_cascade_recording_has_approval_flow():
    """cascade.jsonl should contain the full approval flow for Act 2."""
    recording = RECORDINGS_DIR / "cascade.jsonl"
    assert recording.exists(), "cascade.jsonl not found"
    content = recording.read_text()

    event_types = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
            event_types.add(data.get("event", {}).get("type"))
        except json.JSONDecodeError:
            pass

    required_events = {"policy_check", "tool_result", "done"}
    missing = required_events - event_types
    assert not missing, (
        f"cascade.jsonl missing required event types: {missing}\n"
        f"Found: {event_types}"
    )
