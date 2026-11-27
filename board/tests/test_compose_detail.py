"""行を押したときに出すもの(今見るもの・報告の履歴・成果物・リンク)。"""
from __future__ import annotations

from samples import find_row, grill_topic, inputs, issue, pr, report, step

import compose


def test_row_detail_has_latest_report_history_links_artifacts_and_focus():
    draft = {"ts": "2026-09-01T13:00:00", "kind": "pr_draft", "draft_id": "abc123def456", "title": "feat: 書き出し",
             "body": "## 変更\n- 書き出し", "issue": 9}
    data = inputs(
        records={("demo", "9"): [
            step("plan", ts="2026-09-01T09:00:00", issue=9),
            report("計画の質問票を出した", ts="2026-09-01T09:05:00", issue=9),
            step("review", ts="2026-09-01T12:00:00", issue=9),
            report("PR 案を送った", ts="2026-09-01T13:00:00", issue=9, links={"プレビュー": "http://127.0.0.1:5173/"}),
            draft,
        ]},
        grill={"topics": [grill_topic("9-export-plan", issue=9, state="done")]},
        gh={"demo": {"issues": [issue(9)], "prs": [pr(30, "feat/#9-export")]}},
    )

    row = find_row(compose.compose(data), "demo", "9")

    assert row["latest"] == "PR 案を送った"
    assert [h["text"] for h in row["history"]][:2] == ["PR 案: feat: 書き出し", "PR 案を送った"]
    assert {(link["label"], link["url"]) for link in row["links"]} == {
        ("質問票", "/grill/grill-9-export-plan.html"),
        ("issue", "https://example.invalid/demo/issues/9"),
        ("PR", "https://example.invalid/demo/pull/30"),
        ("プレビュー", "http://127.0.0.1:5173/"),
    }
    plan = next(a for a in row["artifacts"] if a["stage"] == "plan")
    assert plan["items"] == [{"label": "title of 9-export-plan", "url": "/grill/grill-9-export-plan.html"}]
    assert row["focus"] == {"type": "draft", "draft_kind": "pr_draft", "label": "PR 案", "draft_id": "abc123def456",
                            "title": "feat: 書き出し", "body": "## 変更\n- 書き出し"}
