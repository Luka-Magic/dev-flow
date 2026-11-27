"""POST /api/start: 中心と子を始める(起動の部品は偽物)。"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import records
import server
from fakes import FakeLauncher
from samples import closed_port, inputs, issue, session
from test_server import FakeCollector, request

pytestmark = pytest.mark.integration
CONF = {"path": "/work/demo", "hub": "demo_hub", "tmux_session": "demo", "hub_script": "/opt/bin/demo-hub.sh",
        "wrapper": "/opt/bin/demo-parallel.sh"}


@pytest.fixture
def make(board_root: Path):
    started = []

    def build(sessions=(), conf=CONF, launcher=None):
        collector = FakeCollector(inputs(projects={"demo": conf}, sessions=list(sessions),
                                         gh={"demo": {"issues": [issue(53), issue(7)], "prs": []}}))
        collector.root = board_root
        app = server.App(root=board_root, collector=collector, grill_url=f"http://127.0.0.1:{closed_port()}",
                         launcher=launcher or FakeLauncher())
        httpd = server.make_server(app, 0)
        threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        started.append(httpd)
        return app, httpd.server_address[1]

    yield build
    for h in started:
        h.shutdown()
        h.server_close()


def test_start_hub_launches_records_and_then_shows_starting(make, board_root: Path):
    app, port = make()

    status, _, body = request(port, "POST", "/api/start", {"project": "demo", "kind": "hub"})

    assert status == 200 and json.loads(body)["ok"] is True
    [plan] = app.launcher.hubs
    assert plan.argv == ("/opt/bin/demo-hub.sh", "--name", "demo_hub")
    [entry] = records.read(board_root, "demo", "_hub")
    assert (entry["kind"], entry["what"], entry["by"], entry["ok"]) == ("start", "hub", "board", True)
    board = json.loads(request(port, "GET", "/api/board")[2])
    assert board["tabs"][0]["hub"]["label"] == "起動中"


def test_hub_is_not_started_twice(make):
    running_app, running = make(sessions=[session("demo_hub", "/work/demo", status="busy")])
    app, port = make()

    already = request(running, "POST", "/api/start", {"project": "demo", "kind": "hub"})
    first = request(port, "POST", "/api/start", {"project": "demo", "kind": "hub"})[0]
    second = request(port, "POST", "/api/start", {"project": "demo", "kind": "hub"})

    assert already[0] == 409 and "動いている" in json.loads(already[2])["error"]
    assert running_app.launcher.hubs == []
    assert (first, second[0]) == (200, 409)
    assert len(app.launcher.hubs) == 1


def test_hub_without_script_is_refused_with_reason(make):
    conf = {k: v for k, v in CONF.items() if k != "hub_script"}
    app, port = make(conf=conf)

    status, _, body = request(port, "POST", "/api/start", {"project": "demo", "kind": "hub"})

    assert (status, json.loads(body)["error"]) == (409, "起動スクリプトが無い")
    assert app.launcher.hubs == []


def test_child_start_records_and_returns_wrapper_output(make, board_root: Path):
    app, port = make()

    status, _, body = request(port, "POST", "/api/start",
                              {"project": "demo", "kind": "child", "issue": 53, "slug": "column-width", "fix": False})

    assert status == 200
    assert app.launcher.children[0].arg == "53-column-width"
    [entry] = records.read(board_root, "demo", "53")
    assert (entry["kind"], entry["what"], entry["arg"], entry["ok"]) == ("start", "child", "53-column-width", True)


def test_child_refused_by_the_limit_shows_the_wrappers_reason(make, board_root: Path):
    refusal = "子の上限 3 を超えます（動いている: 3、起動しようとした: 1）。"
    app, port = make(launcher=FakeLauncher(ok=False, code=1, output=refusal))

    status, _, body = request(port, "POST", "/api/start",
                              {"project": "demo", "kind": "child", "issue": 53, "slug": "column-width", "fix": True})
    again = request(port, "POST", "/api/start",
                    {"project": "demo", "kind": "child", "issue": 53, "slug": "column-width", "fix": True})[0]

    assert status == 200
    assert json.loads(body) == {"ok": False, "code": 1, "output": refusal, "settled": True}
    assert again == 200  # 断られたら、もう一度押せる
    entry = records.read(board_root, "demo", "53")[0]
    assert (entry["ok"], entry["arg"], entry["output_tail"]) == (False, "53-column-width@fix", refusal)


@pytest.mark.parametrize("body", [
    {"project": "demo", "kind": "child", "issue": 53, "slug": "x; rm -rf ~", "fix": False},
    {"project": "demo", "kind": "child", "issue": "53", "slug": "ok", "fix": False},
    {"project": "demo", "kind": "child", "issue": 53, "slug": "ok", "fix": "no"},
    {"project": "demo", "kind": "shell", "cmd": "ls"},
    {"project": "../x", "kind": "hub"},
])
def test_bad_values_are_refused_before_anything_runs(make, board_root: Path, body):
    app, port = make()

    status = request(port, "POST", "/api/start", body)[0]

    assert status == 400
    assert (app.launcher.hubs, app.launcher.children) == ([], [])
    assert not (board_root / "records").exists()


def test_child_is_not_started_where_a_session_runs(make):
    app, port = make(sessions=[session("demo-7", "/work/demo/.claude/worktrees/7-export")])

    status = request(port, "POST", "/api/start", {"project": "demo", "kind": "child", "issue": 7, "slug": "e", "fix": False})[0]

    assert status == 409
    assert app.launcher.children == []


def test_send_to_hub_row_goes_to_the_hub(make, board_root: Path):
    from fakes import FakeCourier, FakeTmux

    app, port = make(sessions=[session("demo_hub", "/work/demo")])
    app.courier, app.tmux = FakeCourier(ok=True), FakeTmux()

    status = request(port, "POST", "/api/send", {"project": "demo", "topic": "_hub", "text": "main を取り込んで"})[0]

    assert status == 200
    assert app.courier.sent == [("demo_hub", "main を取り込んで")]
    assert records.read(board_root, "demo", "_hub")[-1]["kind"] == "sent"


def test_child_whose_wrapper_did_not_finish_stays_starting(make):
    from start import Result

    launcher = FakeLauncher()
    launcher.result = Result(False, None, "ラッパーが 180 秒で終わらなかった", settled=False)
    app, port = make(launcher=launcher)
    body = {"project": "demo", "kind": "child", "issue": 53, "slug": "column-width", "fix": False}

    first = request(port, "POST", "/api/start", body)[0]
    again = request(port, "POST", "/api/start", body)[0]

    assert (first, again) == (200, 409)
    assert len(launcher.children) == 1


def test_child_with_an_existing_worktree_must_use_its_slug(make):
    app, port = make()
    app.collector.data["worktrees"] = {"demo": ["53-column-width"]}

    other = request(port, "POST", "/api/start", {"project": "demo", "kind": "child", "issue": 53, "slug": "widths", "fix": False})
    same = request(port, "POST", "/api/start", {"project": "demo", "kind": "child", "issue": 53, "slug": "column-width", "fix": False})

    assert other[0] == 409 and "column-width" in json.loads(other[2])["error"]
    assert same[0] == 200
    assert [c.arg for c in app.launcher.children] == ["53-column-width"]
