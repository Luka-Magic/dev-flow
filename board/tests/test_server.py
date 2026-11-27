"""server.py の結合テスト: 一時フォルダと見本を相手に、空きポートで起動して HTTP で叩く。"""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest
from fakes import FakeCourier, FakeTmux
from samples import closed_port, inputs, issue, session

import records
import server

pytestmark = pytest.mark.integration


class FakeCollector:
    def __init__(self, data: dict):
        self.data = data

    def inputs(self) -> dict:
        return {**self.data, "records": records.read_all(Path(self.root))}


@pytest.fixture
def app(board_root: Path):
    collector = FakeCollector(inputs(
        gh={"demo": {"issues": [issue(5)], "prs": []}},
        sessions=[session("demo-5", "/work/demo/.claude/worktrees/5-export", pane="> \n"),
                  session("demo_hub", "/work/demo")],
    ))
    collector.root = board_root
    records.append(board_root, "demo", "5", {"kind": "step", "stage": "review", "issue": 5})
    app = server.App(root=board_root, collector=collector, courier=FakeCourier(ok=True), tmux=FakeTmux(),
                     grill_url=f"http://127.0.0.1:{closed_port()}", allowed_hosts=frozenset())
    return app


@pytest.fixture
def base(app):
    httpd = server.make_server(app, 0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def request(port: int, method: str, path: str, body: bytes | dict | None = None, headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    hdrs = {"Host": f"127.0.0.1:{port}"}
    if data is not None:
        hdrs.update({"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
    hdrs.update(headers or {})
    conn.request(method, path, body=data, headers=hdrs)
    res = conn.getresponse()
    out = res.status, dict(res.getheaders()), res.read()
    conn.close()
    return out


def test_get_board_returns_all_projects_as_json(base: int):
    status, headers, body = request(base, "GET", "/api/board")

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    doc = json.loads(body)
    assert [t["label"] for t in doc["tabs"]] == ["demo"]
    assert doc["tabs"][0]["rows"][0]["stage"] == "review"


def test_r11_post_must_be_json(base: int):
    status, _, _ = request(base, "POST", "/api/send", b"project=demo", {"Content-Type": "application/x-www-form-urlencoded"})

    assert status == 415


def test_r11_post_from_another_origin_is_refused(base: int):
    body = {"project": "demo", "topic": "5", "text": "やあ"}

    status, _, _ = request(base, "POST", "/api/send", body, {"Origin": "http://evil.example"})
    no_origin = request(base, "POST", "/api/send", body, {"Origin": ""})[0]

    assert status == 403
    assert no_origin == 403


def test_r11_unknown_host_name_is_refused(base: int):
    status, _, _ = request(base, "GET", "/api/board", headers={"Host": f"rebind.example:{base}"})

    assert status == 403


def test_r11_bad_topic_key_is_refused(base: int, board_root: Path):
    status, _, body = request(base, "POST", "/api/send", {"project": "demo", "topic": "../../x", "text": "a"})

    assert status == 400
    assert "題材" in json.loads(body)["error"]


def test_send_goes_to_the_rows_session_and_is_recorded(base: int, app, board_root: Path):
    status, _, body = request(base, "POST", "/api/send", {"project": "demo", "topic": "5", "text": "CI を見て"})

    assert status == 200
    assert json.loads(body) == {"ok": True, "delivered": True, "via": "courier", "error": None}
    assert app.courier.sent == [("demo-5", "CI を見て")]
    assert records.read(board_root, "demo", "5")[-1]["kind"] == "sent"


def test_approve_over_http_is_idempotent(base: int, app, board_root: Path):
    records.append(board_root, "demo", "5", {"kind": "pr_draft", "draft_id": "d1d1d1d1d1d1", "title": "t", "body": "b"})
    body = {"project": "demo", "topic": "5", "draft_id": "d1d1d1d1d1d1"}

    first = json.loads(request(base, "POST", "/api/approve", body)[2])
    second = json.loads(request(base, "POST", "/api/approve", body)[2])

    assert (first["already"], second["already"]) == (False, True)
    assert app.courier.sent == [("demo_hub", first_text(board_root))]


def first_text(root: Path) -> str:
    return next(e["text"] for e in records.read(root, "demo", "5") if e["kind"] == "sent" and e.get("to") == "hub")
