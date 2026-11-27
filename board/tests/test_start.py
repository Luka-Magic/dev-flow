"""起動の部品: コマンドの組み立てと値の検査(tmux や起動スクリプトは動かさない。runner は偽物)。"""
from __future__ import annotations

import subprocess

import pytest

import start


class FakeRunner:
    def __init__(self, has_session: bool = True, code: int = 0, stdout: str = ""):
        self.calls, self.has_session, self.code, self.stdout = [], has_session, code, stdout

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:2] == ["tmux", "has-session"]:
            return subprocess.CompletedProcess(cmd, 0 if self.has_session else 1, "", "")
        return subprocess.CompletedProcess(cmd, self.code, self.stdout, "")


def test_hub_opens_a_window_named_hub_in_the_projects_session_with_the_hub_name():
    runner = FakeRunner(has_session=True)
    conf = {"path": "/work/demo", "hub": "demo 中心", "tmux_session": "demo", "hub_script": "/opt/bin/demo-hub.sh"}

    result = start.TmuxLauncher(runner).start_hub(start.hub_plan("demo", conf))

    assert result.ok is True
    assert runner.calls[-1] == ["tmux", "new-window", "-d", "-t", "=demo:", "-n", "hub", "-c", "/work/demo",
                                "/opt/bin/demo-hub.sh", "--name", "demo 中心"]


def test_hub_creates_the_session_when_missing_and_prefers_hub_command():
    runner = FakeRunner(has_session=False)
    conf = {"path": "/work/demo", "hub": "demo_hub", "hub_script": "/opt/bin/demo-hub.sh",
            "hub_command": ["/opt/bin/other-hub", "--model", "opus"]}

    start.TmuxLauncher(runner).start_hub(start.hub_plan("demo", conf))

    assert runner.calls[-1] == ["tmux", "new-session", "-d", "-s", "demo", "-n", "hub", "-c", "/work/demo",
                                "/opt/bin/other-hub", "--model", "opus", "--name", "demo_hub"]


def test_hub_plan_refuses_without_script_or_name():
    with pytest.raises(ValueError, match="起動スクリプトが無い"):
        start.hub_plan("demo", {"hub": "demo_hub"})
    with pytest.raises(ValueError, match="中心の名前"):
        start.hub_plan("demo", {"hub_script": "/opt/bin/demo-hub.sh"})
    with pytest.raises(ValueError, match="tmux"):
        start.hub_plan("demo", {"hub": "h", "hub_script": "/x", "tmux_session": "a:b"})


def test_child_runs_the_wrapper_with_one_checked_argument():
    runner = FakeRunner(stdout="作ります: /work/demo/.claude/worktrees/53-column-width\n")
    plan = start.child_plan({"wrapper": "/opt/bin/demo-parallel.sh", "path": "/nonexistent"}, 53, "column-width", True)

    result = start.TmuxLauncher(runner).start_child(plan)

    assert runner.calls == [["/opt/bin/demo-parallel.sh", "53-column-width@fix"]]
    assert result == start.Result(True, 0, "作ります: /work/demo/.claude/worktrees/53-column-width")


@pytest.mark.parametrize("issue, slug, fix", [
    (0, "ok", False), ("53", "ok", False), (True, "ok", False), (53, "", False), (53, "列幅", False),
    (53, "a b", False), (53, "-x", False), (53, "x;rm -rf ~", False), (53, "x" * 41, False), (53, "ok", "yes"),
])
def test_child_values_that_fail_the_check_are_refused(issue, slug, fix):
    with pytest.raises(ValueError):
        start.child_arg(issue, slug, fix)


def test_long_wrapper_output_is_cut_to_the_tail():
    out = "\n".join(f"line {i}" for i in range(100))

    assert start.tail(out).splitlines() == [f"line {i}" for i in range(80, 100)]
