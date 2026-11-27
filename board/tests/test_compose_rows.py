"""R3 並び / R4 番号のない行 / R5「その他」/ R12 gh が無くても出る。"""
from __future__ import annotations

from samples import grill_topic, inputs, issue, step

import compose


def _tab(board: dict, project: str) -> dict:
    return next(t for t in board["tabs"] if t["project"] == project)


def test_r3_order_is_done_then_numberless_active_then_numbered():
    data = inputs(
        records={
            ("demo", "10"): [step("implement", issue=10)],
            ("demo", "fix-readme"): [step("review", ts="2026-09-02T09:00:00")],
            ("demo", "old-chore"): [step("done", ts="2026-08-01T09:00:00")],
            ("demo", "7"): [step("plan", issue=7)],
        },
        gh={"demo": {"issues": [issue(3), issue(7), issue(10), issue(2, state="CLOSED")], "prs": []}},
    )

    tab = _tab(compose.compose(data), "demo")

    assert [r["topic"] for r in tab["rows"]] == ["2", "old-chore", "fix-readme", "3", "7", "10"]
    assert tab["first_active"] == 2


def test_r4_question_sheet_without_issue_becomes_its_own_row_with_empty_number():
    data = inputs(grill={"topics": [grill_topic("demo-next-version", project="demo", issue=None)]})

    tab = _tab(compose.compose(data), "demo")

    [row] = tab["rows"]
    assert row["topic"] == "demo-next-version"
    assert row["issue"] is None
    assert row["title"] == "title of demo-next-version"
    assert row["my_turn"] == "質問票に答える"


def test_r5_question_sheet_with_unknown_project_goes_to_other_tab():
    data = inputs(grill={"topics": [grill_topic("naming-ideas", project=None, issue=None, kind=None)]})

    board = compose.compose(data)

    other = board["tabs"][-1]
    assert other["project"] is None
    assert other["label"] == "その他"
    assert [r["topic"] for r in other["rows"]] == ["naming-ideas"]
    assert other["my_turn"] == 1


def test_r12_rows_appear_from_records_and_sheets_when_gh_fails():
    data = inputs(
        records={("demo", "4"): [step("spec", issue=4)]},
        grill={"topics": [grill_topic("4-export-plan", issue=4, state="done")]},
        gh={"demo": {"error": "gh が見つからない"}},
    )

    tab = _tab(compose.compose(data), "demo")

    assert [(r["topic"], r["stage"]) for r in tab["rows"]] == [("4", "spec")]
    assert tab["notes"] == ["GitHub の一覧を取れない: gh が見つからない"]


def test_tabs_are_configured_projects_and_projects_with_work_in_progress():
    data = inputs(
        projects={"demo": {"path": "/work/demo"}},
        grill={"topics": [grill_topic("old-idea", project="finished_app", state="done"),
                          grill_topic("new-idea", project="busy_app", state="waiting")]},
    )

    labels = [t["label"] for t in compose.compose(data)["tabs"]]

    assert labels == ["busy_app", "demo"]


def test_r4_pr_without_issue_joins_the_record_of_its_branch():
    from samples import pr

    data = inputs(
        records={("demo", "fix-readme"): [step("review", title="README の誤字を直す")]},
        gh={"demo": {"issues": [], "prs": [pr(61, "chore/fix-readme")]}},
    )

    [row] = _tab(compose.compose(data), "demo")["rows"]

    assert (row["topic"], row["title"], row["issue"]) == ("fix-readme", "README の誤字を直す", None)
    assert {"label": "PR", "url": "https://example.invalid/demo/pull/61"} in row["links"]
