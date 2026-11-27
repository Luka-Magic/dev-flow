"""ステータス行の包み: 使用量を書き出し、元のコマンドへそのまま渡す。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BOARD = Path(__file__).resolve().parents[1]
STATUS = {
    "session_id": "0f0e-demo",
    "cwd": "/work/demo",
    "model": {"display_name": "Opus"},
    "context_window": {"used_percentage": 37.5, "context_window_size": 200000, "other": 1},
    "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": 1790003600},
                    "seven_day": {"used_percentage": 61, "resets_at": 1790500000}},
    "transcript_path": "/somewhere/secret.jsonl",
}


def test_writes_usage_file_and_passes_input_to_original_command(tmp_path: Path):
    payload = json.dumps(STATUS).encode()
    echo = [sys.executable, "-c", "import sys; d=sys.stdin.read(); print('LINE', len(d))"]

    res = subprocess.run([sys.executable, str(BOARD / "statusline_tee.py"), "--", *echo], input=payload,
                         capture_output=True, env={"BOARD_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"})

    assert res.returncode == 0
    assert res.stdout.decode().strip() == f"LINE {len(payload)}"
    doc = json.loads((tmp_path / "usage" / "0f0e-demo.json").read_text())
    assert doc["context_window"] == {"used_percentage": 37.5, "context_window_size": 200000}
    assert doc["rate_limits"]["five_hour"] == {"used_percentage": 42, "resets_at": 1790003600}
    assert doc["model"] == {"display_name": "Opus"} and doc["cwd"] == "/work/demo"
    assert "transcript_path" not in doc and isinstance(doc["written_at"], float)
    assert not list((tmp_path / "usage").glob("*.tmp"))


def test_bad_input_still_reaches_original_command(tmp_path: Path):
    echo = [sys.executable, "-c", "import sys; print(sys.stdin.read())"]

    res = subprocess.run([sys.executable, str(BOARD / "statusline_tee.py"), "--", *echo], input=b"not json",
                         capture_output=True, env={"BOARD_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"})

    assert res.stdout.decode().strip() == "not json"
    assert not (tmp_path / "usage").exists() or not list((tmp_path / "usage").iterdir())
