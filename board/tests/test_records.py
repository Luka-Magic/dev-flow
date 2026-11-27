"""記録(題材ごとの追記専用 JSONL)の読み書き。"""
from __future__ import annotations

from pathlib import Path

import pytest

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
    with pytest.raises(ValueError):
        records.append(board_root, "demo", "../../etc/passwd", {"kind": "report", "text": "x"})
    with pytest.raises(ValueError):
        records.append(board_root, "de mo", "12", {"kind": "report", "text": "x"})
    assert not (board_root / "records").exists()


def test_r11_key_with_trailing_newline_is_rejected(board_root: Path):
    with pytest.raises(ValueError):
        records.append(board_root, "demo", "12\n", {"kind": "report", "text": "x"})


def test_r7_long_lines_from_parallel_writers_stay_whole(board_root: Path):
    import threading

    body = "あ" * 60_000  # バッファより大きい 1 行

    def write(i: int) -> None:
        for _ in range(5):
            records.append(board_root, "demo", "9", {"kind": "report", "text": f"{i}{body}"})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(records.read(board_root, "demo", "9")) == 20
