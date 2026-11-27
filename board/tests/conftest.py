"""共通の準備: board/ を import できるようにし、記録の置き場所を一時フォルダにする。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BOARD = Path(__file__).resolve().parents[1]
if str(BOARD) not in sys.path:
    sys.path.insert(0, str(BOARD))


@pytest.fixture
def board_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "devflow"
    root.mkdir()
    monkeypatch.setenv("BOARD_ROOT", str(root))
    return root
