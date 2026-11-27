"""R2 自分の番。"""
from __future__ import annotations

from samples import find_row, grill_topic, inputs, issue, session, step

import compose


def test_r2_waiting_question_sheet_is_my_turn():
    data = inputs(
        records={("demo", "5"): [step("plan", issue=5)]},
        gh={"demo": {"issues": [issue(5)], "prs": []}},
        grill={"topics": [grill_topic("5-export-plan", issue=5)]},
    )

    row = find_row(compose.compose(data), "demo", "5")

    assert row["my_turn"] == "質問票に答える"


def _draft(kind: str, draft_id: str, title: str = "feat: 書き出し") -> dict:
    return {"ts": "2026-09-01T11:00:00", "kind": kind, "draft_id": draft_id, "title": title, "body": "本文", "issue": 5}


def test_r2_pr_draft_waiting_for_approval_is_my_turn_until_approved():
    pending = inputs(records={("demo", "5"): [step("review", issue=5), _draft("pr_draft", "aaa111")]},
                     gh={"demo": {"issues": [issue(5)], "prs": []}})
    approved = inputs(records={("demo", "5"): [step("review", issue=5), _draft("pr_draft", "aaa111"),
                                               {"ts": "2026-09-01T12:00:00", "kind": "approve", "draft_id": "aaa111"}]},
                      gh={"demo": {"issues": [issue(5)], "prs": []}})

    assert find_row(compose.compose(pending), "demo", "5")["my_turn"] == "PR 案を承認する"
    assert find_row(compose.compose(approved), "demo", "5")["my_turn"] is None


def test_r2_unanswered_briefing_is_my_turn():
    brief = {"ts": "2026-09-01T11:00:00", "kind": "report", "text": "実装前の説明を出した", "issue": 5,
             "links": {"実装前の説明": "http://127.0.0.1:8787/20260901-plan-export.html"}}
    data = inputs(records={("demo", "5"): [step("briefing", issue=5), brief]},
                  gh={"demo": {"issues": [issue(5)], "prs": []}})

    assert find_row(compose.compose(data), "demo", "5")["my_turn"] == "実装前の説明に答える"


def test_r2_session_stopped_at_confirmation_is_my_turn():
    pane = "Bash command\n  rm -rf build\nDo you want to proceed?\n❯ 1. Yes\n  2. No\n"
    data = inputs(
        records={("demo", "5"): [step("implement", issue=5)]},
        gh={"demo": {"issues": [issue(5)], "prs": []}},
        sessions=[session("demo-5", "/work/demo/.claude/worktrees/5-export", status="idle", pane=pane)],
    )

    row = find_row(compose.compose(data), "demo", "5")

    assert row["my_turn"] == "確認の選択肢で止まっている"
    assert row["session"]["state"] == "confirm"
