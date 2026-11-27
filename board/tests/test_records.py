"""記録(題材ごとの追記専用 JSONL)の読み書き。"""
from __future__ import annotations

from pathlib import Path

import records


def test_r7_broken_line_is_skipped_and_other_lines_are_read(board_root: Path):
    records.append(board_root, "demo", "12", {"kind": "step", "stage": "plan"})
    path = records.record_path(board_root, "demo", "12")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{this is not json\n")
    records.append(board_root, "demo", "12", {"kind": "report", "text": "計画の質問票を出した"})

    lines = records.read(board_root, "demo", "12")

    assert [e["kind"] for e in lines] == ["step", "report"]
    assert lines[1]["text"] == "計画の質問票を出した"


def test_r11_key_with_path_separator_is_rejected(board_root: Path):
    import pytest

    with pytest.raises(ValueError):
        records.append(board_root, "demo", "../../etc/passwd", {"kind": "report", "text": "x"})
    with pytest.raises(ValueError):
        records.append(board_root, "de mo", "12", {"kind": "report", "text": "x"})
    assert not any((board_root / "records").rglob("*.jsonl")) if (board_root / "records").exists() else True
