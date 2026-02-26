from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_perf_check_passes():
    root = Path(__file__).resolve().parents[1]
    py = root / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run([str(py), "perf_check.py"], cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["failed"] == []
