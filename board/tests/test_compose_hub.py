"""中心の状態と「中心を始める」ボタン(判定は /api/board 側)。"""
from __future__ import annotations

import compose
from samples import inputs, session

PROJECT = {"path": "/work/demo", "hub": "demo_hub", "tmux_session": "demo", "hub_script": "/opt/bin/demo-hub.sh"}


def _hub(board: dict, project: str = "demo") -> dict:
    return next(t for t in board["tabs"] if t["project"] == project)["hub"]


def test_running_hub_is_shown_without_start_button():
    data = inputs(projects={"demo": PROJECT},
                  sessions=[session("demo_hub", "/work/demo", status="busy", sid="sid-hub")])

    hub = _hub(compose.compose(data))

    assert (hub["state"], hub["label"], hub["start"]) == ("running", "動いている", None)
    assert hub["row"]["session"]["name"] == "demo_hub"
    assert hub["attach"] == {"command": "tmux attach -t demo", "window": "hub"}


def test_absent_hub_with_start_script_can_be_started():
    hub = _hub(compose.compose(inputs(projects={"demo": PROJECT})))

    assert (hub["state"], hub["label"]) == ("absent", "いない")
    assert hub["start"] == {"label": "中心を始める", "enabled": True, "reason": None}


def test_absent_hub_without_script_or_command_shows_disabled_button_with_reason():
    conf = {k: v for k, v in PROJECT.items() if k != "hub_script"}

    hub = _hub(compose.compose(inputs(projects={"demo": conf})))

    assert hub["start"] == {"label": "中心を始める", "enabled": False, "reason": "起動スクリプトが無い"}


def test_hub_just_started_is_starting_and_cannot_be_pressed_again():
    from samples import NOW

    hub = _hub(compose.compose(inputs(projects={"demo": PROJECT}, starting={("demo", "hub"): NOW - 5})))

    assert (hub["state"], hub["label"]) == ("starting", "起動中")
    assert hub["start"] == {"label": "中心を始める", "enabled": False, "reason": "起動中"}


def test_hub_record_goes_to_hub_row_not_to_table():
    records = {("demo", "_hub"): [{"ts": "2026-09-01T10:00:00", "kind": "start", "what": "hub", "by": "board"}]}

    board = compose.compose(inputs(projects={"demo": PROJECT}, records=records))

    tab = board["tabs"][0]
    assert tab["rows"] == []
    assert tab["hub"]["row"]["history"][0]["text"] == "中心を始めた(board から)"


def test_child_start_is_offered_only_for_numbered_rows_without_a_session():
    from samples import find_row, issue, step

    conf = {**PROJECT, "wrapper": "/opt/bin/demo-parallel.sh"}
    data = inputs(
        projects={"demo": conf},
        records={("demo", "7"): [step("implement", issue=7)], ("demo", "chore-x"): [step("plan")]},
        gh={"demo": {"issues": [issue(53), issue(7), issue(2, state="CLOSED")], "prs": []}},
        sessions=[session("demo-7", "/work/demo/.claude/worktrees/7-export")],
        worktrees={"demo": ["53-column-width", "other"]},
    )

    board = compose.compose(data)

    assert find_row(board, "demo", "53")["child_start"] == {
        "label": "子を始める", "enabled": True, "reason": None, "slug": "column-width", "fix": False,
        "confirm": "#53 の子を始めます。作業ツリーと窓が作られます"}
    assert find_row(board, "demo", "7")["child_start"] is None       # セッションが動いている
    assert find_row(board, "demo", "2")["child_start"] is None       # 完了
    assert find_row(board, "demo", "chore-x")["child_start"] is None  # 番号が無い


def test_child_start_without_wrapper_is_disabled_with_reason():
    from samples import find_row, issue

    data = inputs(projects={"demo": PROJECT}, gh={"demo": {"issues": [issue(53)], "prs": []}})

    start = find_row(compose.compose(data), "demo", "53")["child_start"]

    assert (start["enabled"], start["reason"], start["slug"]) == (False, "並列運用のラッパーが無い", "")


def test_child_just_started_is_starting_and_cannot_be_pressed_again():
    from samples import NOW, find_row, issue

    conf = {**PROJECT, "wrapper": "/opt/bin/demo-parallel.sh"}
    data = inputs(projects={"demo": conf}, gh={"demo": {"issues": [issue(53)], "prs": []}},
                  starting={("demo", 53): NOW - 3})

    start = find_row(compose.compose(data), "demo", "53")["child_start"]

    assert (start["enabled"], start["reason"]) == (False, "起動中")


def test_refused_child_start_shows_the_first_line_of_the_reason_in_history():
    from samples import find_row, issue

    line = {"ts": "2026-09-01T10:00:00", "kind": "start", "what": "child", "by": "board", "ok": False, "code": 1,
            "arg": "53-column-width", "output_tail": "子の上限 3 を超えます。\nPR が出て…", "issue": 53}
    data = inputs(projects={"demo": PROJECT}, records={("demo", "53"): [line]},
                  gh={"demo": {"issues": [issue(53)], "prs": []}})

    text = find_row(compose.compose(data), "demo", "53")["history"][0]["text"]

    assert text == "子を始められなかった: 53-column-width(board から、子の上限 3 を超えます。)"


def test_other_sessions_in_the_project_root_are_noted_next_to_the_start_button():
    data = inputs(projects={"demo": PROJECT}, sessions=[session("demo-0d", "/work/demo"),
                                                       session("child", "/work/demo/.claude/worktrees/5-x")])

    hub = _hub(compose.compose(data))

    assert hub["start"]["enabled"] is True
    assert hub["note"] == "本体のフォルダで別の名前のセッションが動いている: demo-0d"
