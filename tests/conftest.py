"""
Test configuration — adds agent/ to sys.path so imports work without installation.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
AGENT_DIR = REPO_ROOT / "agent"

sys.path.insert(0, str(AGENT_DIR))
