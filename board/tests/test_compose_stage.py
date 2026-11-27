"""R1 段階の決め方 / R6 食い違いの印。"""
from __future__ import annotations

from samples import find_row, inputs, issue, step

import compose


def test_r1_last_step_in_record_is_the_stage():
    data = inputs(
        records={("demo", "12"): [step("plan", issue=12), step("spec", issue=12), step("test_review", issue=12)]},
        gh={"demo": {"issues": [issue(12)], "prs": []}},
    )

    row = find_row(compose.compose(data), "demo", "12")

    assert row["stage"] == "test_review"
    assert row["stage_label"] == "テストレビュー"
    assert row["issue"] == 12


def test_r1_without_record_open_issue_is_todo_and_closed_issue_is_done():
    data = inputs(gh={"demo": {"issues": [issue(3), issue(4, state="CLOSED")], "prs": []}})

    board = compose.compose(data)

    assert find_row(board, "demo", "3")["stage"] == "todo"
    assert find_row(board, "demo", "3")["status"] == "todo"
    assert find_row(board, "demo", "4")["stage"] == "done"
    assert find_row(board, "demo", "4")["status"] == "done"


def test_r6_record_behind_evidence_gets_mismatch_mark():
    from samples import grill_topic, pr

    behind = inputs(
        records={("demo", "8"): [step("plan", issue=8)]},
        gh={"demo": {"issues": [issue(8)], "prs": [pr(21, "feat/#8-export")]}},
    )
    in_step = inputs(
        records={("demo", "8"): [step("test_review", issue=8)]},
        grill={"topics": [grill_topic("8-export-rules", issue=8, kind="test-review", state="answered")]},
        gh={"demo": {"issues": [issue(8)], "prs": []}},
    )

    row = find_row(compose.compose(behind), "demo", "8")
    assert row["stage"] == "plan"
    assert row["mismatch"] == "記録は「計画」だが、PR からは「レビュー」まで進んでいる"
    assert find_row(compose.compose(in_step), "demo", "8")["mismatch"] is None
