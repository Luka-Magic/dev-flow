"""質問票の中継: grill-visual(ここでは偽物)の HTML・画像・送信・チャットが board の入口の下で動く。"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from samples import closed_port, inputs
from test_server import FakeCollector, request

import server

pytestmark = pytest.mark.integration


class FakeGrill(BaseHTTPRequestHandler):
    seen: list = []

    def _reply(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeGrill.seen.append(("GET", self.path, None))
        if self.path.startswith("/grill-plan-x.html"):
            self._reply(200, b'<html><img src="assets/plan-x/a.png"></html>', "text/html; charset=utf-8")
        elif self.path == "/assets/plan-x/a.png":
            self._reply(200, b"\x89PNG", "image/png")
        elif self.path.startswith("/api/chat?topic=plan-x"):
            self._reply(200, b'{"messages":[]}', "application/json")
        else:
            self._reply(404, b"no", "text/plain")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeGrill.seen.append(("POST", self.path, json.loads(body)))
        self._reply(200, b'{"ok":true}', "application/json")

    def log_message(self, *a):
        pass


@pytest.fixture
def ports(board_root: Path):
    grill = ThreadingHTTPServer(("127.0.0.1", 0), FakeGrill)
    threading.Thread(target=grill.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    collector = FakeCollector(inputs())
    collector.root = board_root
    app = server.App(root=board_root, collector=collector, grill_url=f"http://127.0.0.1:{grill.server_address[1]}")
    httpd = server.make_server(app, 0)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    FakeGrill.seen = []
    yield httpd.server_address[1]
    for s in (httpd, grill):
        s.shutdown()
        s.server_close()


def test_sheet_html_and_its_relative_image_open_through_board(ports: int):
    status, headers, body = request(ports, "GET", "/grill/grill-plan-x.html?v=3")
    img = request(ports, "GET", "/grill/assets/plan-x/a.png")

    assert status == 200 and b"assets/plan-x/a.png" in body
    assert headers["Content-Type"].startswith("text/html")
    assert img[0] == 200 and img[1]["Content-Type"] == "image/png" and img[2] == b"\x89PNG"
    assert ("GET", "/grill-plan-x.html?v=3", None) in FakeGrill.seen


def test_submit_and_chat_are_passed_to_grill(ports: int):
    submitted = request(ports, "POST", "/submit", {"topic": "plan-x", "round": 1, "answers": {}})
    chat_get = request(ports, "GET", "/api/chat?topic=plan-x")
    chat_post = request(ports, "POST", "/api/chat", {"topic": "plan-x", "q": "Q1", "text": "なぜ?"})

    assert (submitted[0], chat_get[0], chat_post[0]) == (200, 200, 200)
    assert ("POST", "/submit", {"topic": "plan-x", "round": 1, "answers": {}}) in FakeGrill.seen
    assert ("POST", "/api/chat", {"topic": "plan-x", "q": "Q1", "text": "なぜ?"}) in FakeGrill.seen


def test_proxy_reports_when_grill_is_down(board_root: Path):
    collector = FakeCollector(inputs())
    collector.root = board_root
    app = server.App(root=board_root, collector=collector, grill_url=f"http://127.0.0.1:{closed_port()}")
    httpd = server.make_server(app, 0)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    try:
        status, _, body = request(httpd.server_address[1], "GET", "/grill/grill-plan-x.html")
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert status == 502
    assert "grill-visual" in json.loads(body)["error"]
