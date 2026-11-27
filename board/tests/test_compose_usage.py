"""R10 使用量。"""
from __future__ import annotations

from samples import NOW, find_row, inputs, issue, session, step

import compose


def _usage(sid: str, pct: float, minutes_ago: float, five: float, week: float) -> dict:
    return {
        "written_at": NOW - minutes_ago * 60,
        "session_id": sid,
        "context_window": {"used_percentage": pct, "context_window_size": 200000},
        "rate_limits": {"five_hour": {"used_percentage": five, "resets_at": NOW + 3600},
                        "seven_day": {"used_percentage": week, "resets_at": NOW + 86400}},
        "model": {"display_name": "Opus"},
        "cwd": "/work",
    }


def test_r10_context_per_session_with_age_and_limits_from_newest_write():
    data = inputs(
        records={("demo", "5"): [step("implement", issue=5)]},
        gh={"demo": {"issues": [issue(5)], "prs": []}},
        sessions=[
            session("demo-5", "/work/demo/.claude/worktrees/5-export", sid="sid-a"),
            session("gone", "/work/elsewhere", sid="sid-b", alive=False),
            session("notes", "/work/elsewhere", sid="sid-c"),
        ],
        usage=[_usage("sid-a", 44.4, 3, 40, 60), _usage("sid-b", 90, 1, 42, 61), _usage("sid-c", 12, 30, 10, 20)],
    )

    board = compose.compose(data)

    assert find_row(board, "demo", "5")["context"] == {"pct": 44, "age_min": 3}
    assert board["limits"]["five_hour"]["pct"] == 42
    assert board["limits"]["seven_day"]["pct"] == 61
    assert board["limits"]["age_min"] == 1
    assert [(s["name"], s["context"]) for s in board["other_sessions"]["top"]] == [("notes", {"pct": 12, "age_min": 30})]
    assert board["other_sessions"]["count"] == 1


def test_other_sessions_show_only_those_with_usage_top_three_by_percentage_and_the_rest():
    names = ["a", "b", "c", "d", "e"]
    pcts = [10, 80, 35, 60, 5]
    data = inputs(
        sessions=[session(n, f"/work/elsewhere/{n}", sid=f"sid-{n}") for n in names] + [session("silent", "/work/x")],
        usage=[_usage(f"sid-{n}", p, 2, 1, 1) for n, p in zip(names, pcts)],
    )

    others = compose.compose(data)["other_sessions"]

    assert others["count"] == 5
    assert [s["name"] for s in others["top"]] == ["b", "d", "c"]
    assert [s["name"] for s in others["rest"]] == ["a", "e"]
    assert others["rest_label"] == "ほか 2 件"


def test_other_sessions_and_limits_are_absent_without_usage():
    data = inputs(sessions=[session("silent", "/work/x")])

    board = compose.compose(data)

    assert board["other_sessions"] is None
    assert board["limits"] is None


def test_limits_are_absent_when_writes_have_no_rate_limit_values():
    doc = _usage("sid-a", 30, 1, 0, 0)
    doc["rate_limits"] = {}
    older = _usage("sid-b", 30, 9, 42, 61)
    data = inputs(usage=[doc])

    assert compose.compose(data)["limits"] is None
    assert compose.compose(inputs(usage=[doc, older]))["limits"]["five_hour"]["pct"] == 42
