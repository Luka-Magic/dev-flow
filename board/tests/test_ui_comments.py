"""ui-comments(画面の要素を指してコメントする道具)の差し込みと中継。BOARD_UI_COMMENTS=1 のときだけ。"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import server
from samples import closed_port, inputs
from test_proxy import FakeGrill
from test_server import FakeCollector, request

pytestmark = pytest.mark.integration
OVERLAY_TAG = b'<script src="/ui-comments/overlay.js"'


class FakeUiComments(BaseHTTPRequestHandler):
    seen: list = []

    def _reply(self, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        FakeUiComments.seen.append((self.command, self.path, self.headers.get("Host"), self.headers.get("Origin"), body))

    def do_GET(self):
        self._record()
        if self.path == "/overlay.js":
            self._reply(b"/* overlay */", "text/javascript")
        else:
            self._reply(b'{"threads":[]}')

    def do_POST(self):
        self._record()
        self._reply(b'{"ok":true}')

    do_PATCH = do_POST
    do_DELETE = do_POST

    def log_message(self, *a):
        pass


def _start(httpd):
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return httpd


@pytest.fixture
def servers(board_root: Path):
    started = []

    def make(enabled: bool) -> int:
        uic = _start(ThreadingHTTPServer(("127.0.0.1", 0), FakeUiComments))
        grill = _start(ThreadingHTTPServer(("127.0.0.1", 0), FakeGrill))
        collector = FakeCollector(inputs())
        collector.root = board_root
        app = server.App(root=board_root, collector=collector, grill_url=f"http://127.0.0.1:{grill.server_address[1]}",
                         allowed_hosts=frozenset({"board.example.ts.net"}),
                         ui_comments_port=uic.server_address[1] if enabled else None)
        httpd = _start(server.make_server(app, 0))
        started.extend([uic, grill, httpd])
        FakeUiComments.seen = []
        return httpd.server_address[1]

    yield make
    for s in started:
        s.shutdown()
        s.server_close()


def test_disabled_neither_injects_nor_relays(servers):
    port = servers(False)

    _, _, page = request(port, "GET", "/")
    overlay = request(port, "GET", "/ui-comments/overlay.js")[0]
    threads = request(port, "GET", "/api/threads")[0]

    assert OVERLAY_TAG not in page
    assert (overlay, threads) == (404, 404)
    assert FakeUiComments.seen == []


def test_enabled_injects_overlay_into_board_page_only(servers):
    port = servers(True)

    _, _, page = request(port, "GET", "/")
    _, _, sheet = request(port, "GET", "/grill/grill-plan-x.html")

    assert OVERLAY_TAG in page
    assert page.index(OVERLAY_TAG) < page.rindex(b"</body>")
    assert OVERLAY_TAG not in sheet


def test_enabled_relays_overlay_and_thread_api_through_tailnet_name(servers):
    port = servers(True)
    tail = {"Host": f"board.example.ts.net:{port}", "Origin": f"https://board.example.ts.net:{port}"}

    overlay = request(port, "GET", "/ui-comments/overlay.js", headers={"Host": tail["Host"]})
    listed = request(port, "GET", "/api/threads", headers={"Host": tail["Host"]})
    created = request(port, "POST", "/api/threads", {"page": "/", "text": "ここを広く"}, tail)
    seen = request(port, "POST", "/api/threads/t1/seen", b"", {**tail, "Content-Type": ""})
    edited = request(port, "PATCH", "/api/threads/t1/messages/m1", {"text": "直した"}, tail)
    deleted = request(port, "DELETE", "/api/threads/t1/messages/m1", None, tail)

    assert overlay[0] == 200 and overlay[2] == b"/* overlay */"
    assert [r[0] for r in (listed, created, seen, edited, deleted)] == [200, 200, 200, 200, 200]
    methods = [(m, p) for m, p, *_ in FakeUiComments.seen]
    assert methods == [("GET", "/overlay.js"), ("GET", "/api/threads"), ("POST", "/api/threads"),
                       ("POST", "/api/threads/t1/seen"), ("PATCH", "/api/threads/t1/messages/m1"),
                       ("DELETE", "/api/threads/t1/messages/m1")]
    assert all(host.startswith("127.0.0.1") and origin is None for _, _, host, origin, _ in FakeUiComments.seen)
    assert json.loads(FakeUiComments.seen[2][4]) == {"page": "/", "text": "ここを広く"}


def test_enabled_still_refuses_other_origins(servers):
    port = servers(True)

    status = request(port, "POST", "/api/threads", {"text": "x"}, {"Origin": "http://evil.example"})[0]
    patched = request(port, "PATCH", "/api/threads/t1/messages/m1", {"text": "x"}, {"Origin": "http://evil.example"})[0]

    assert (status, patched) == (403, 403)
    assert FakeUiComments.seen == []
