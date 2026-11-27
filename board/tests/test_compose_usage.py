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
    assert [(s["name"], s["context"]) for s in board["other_sessions"]] == [("notes", {"pct": 12, "age_min": 30})]
