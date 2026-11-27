"""R9 承認。"""
from __future__ import annotations

from pathlib import Path

from fakes import FakeCourier, FakeTmux

import actions
import records

HUB = {"name": "demo_hub", "tmux": "%1"}


def _draft(root: Path) -> None:
    records.append(root, "demo", "5", {"kind": "pr_draft", "draft_id": "abc123def456", "title": "feat: 書き出し",
                                       "body": "本文", "issue": 5})


def test_r9_approve_appends_once_and_notifies_hub_once(board_root: Path):
    _draft(board_root)
    courier = FakeCourier(ok=True)

    first = actions.approve(board_root, "demo", "5", "abc123def456", HUB, courier, FakeTmux())
    second = actions.approve(board_root, "demo", "5", "abc123def456", HUB, courier, FakeTmux())

    assert first["already"] is False and first["notified"]["delivered"] is True
    assert second["already"] is True
    approvals = [e for e in records.read(board_root, "demo", "5") if e["kind"] == "approve"]
    assert len(approvals) == 1
    assert approvals[0]["draft_kind"] == "pr_draft"
    [(to, text)] = courier.sent
    assert to == "demo_hub"
    assert "PR 案" in text and "feat: 書き出し" in text and "承認" in text


def test_r9_second_approve_retries_only_the_failed_notice(board_root: Path):
    _draft(board_root)
    down, up = FakeCourier(ok=False), FakeCourier(ok=True)

    first = actions.approve(board_root, "demo", "5", "abc123def456", {"name": "demo_hub", "tmux": None}, down, None)
    second = actions.approve(board_root, "demo", "5", "abc123def456", HUB, up, FakeTmux())
    third = actions.approve(board_root, "demo", "5", "abc123def456", HUB, up, FakeTmux())

    assert first["notified"]["delivered"] is False
    assert (second["already"], second["notified"]["delivered"]) == (True, True)
    assert (third["already"], third["notified"]) == (True, None)
    assert len([e for e in records.read(board_root, "demo", "5") if e["kind"] == "approve"]) == 1
    assert len(up.sent) == 1
