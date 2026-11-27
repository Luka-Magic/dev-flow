#!/usr/bin/env python3
"""board: dev-flow の進み具合を 1 画面で見るサーバー(127.0.0.1 限定、既定ポート 8792)。

GET  /               … 画面(board.html。毎回読む)
GET  /api/board      … 全プロジェクトの表(compose.compose の結果)
POST /api/send       … {"project", "topic", "text"} その題材のセッションへ指示を送る(配達係 → tmux)
POST /api/approve    … {"project", "topic", "draft_id"} PR 案・issue 案を承認して中心へ知らせる
GET  /grill/<path>   … grill-visual(BOARD_GRILL_URL)への中継。質問票の HTML・画像など
POST /submit、GET/POST /api/chat … 質問票の JS が叩く入口。そのまま grill-visual へ中継する

POST は JSON だけを受け、Origin が同じ出所のものだけ通す。Host は 127.0.0.1 / localhost と
設定の allowed_hosts だけ(よその名前を向けた DNS の付け替えで読まれないように)。

環境変数: BOARD_PORT(既定 8792)、BOARD_ROOT(記録の置き場所)、BOARD_GRILL_URL(既定 http://127.0.0.1:8787)、
  BOARD_CONFIG(設定ファイル)、BOARD_SESSIONS_DIR、BOARD_ALLOWED_HOSTS(カンマ区切り)、
  BOARD_NO_TMUX / BOARD_NO_COURIER(配達を切る。demo.sh 用)、BOARD_GH_FIXTURE(GitHub の見本。demo.sh 用)
"""
from __future__ import annotations

import functools
import http.client
import json
import os
import sys
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import actions
import compose
import records
import sessions

BIND = "127.0.0.1"
DEFAULT_PORT = 8792
DEFAULT_GRILL_URL = "http://127.0.0.1:8787"
HERE = Path(__file__).resolve().parent
PAGE = HERE / "board.html"
MAX_BODY_BYTES = 1_000_000
LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "[::1]"})
GRILL_PREFIX = "/grill/"
GRILL_PASSTHROUGH = ("/submit", "/api/chat")  # 質問票の JS が絶対パスで叩くもの
PROXY_TIMEOUT = 30


@dataclass
class App:
    """サーバーが使う部品。テストでは集め役と配達を偽物に差し替える。"""
    root: Path
    collector: Any                  # .inputs() -> dict
    courier: Any = None             # deliver.Sender
    tmux: Any = None                # deliver.PaneSender
    grill_url: str = DEFAULT_GRILL_URL
    allowed_hosts: frozenset[str] = field(default_factory=frozenset)


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def host_name(value: str) -> str:
    """Host ヘッダから名前の部分(ポートを除く)。"""
    value = value.strip().lower()
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class Handler(BaseHTTPRequestHandler):
    timeout = 30
    server_version = "board"

    def __init__(self, *args, app: App, **kwargs):
        self.app = app
        super().__init__(*args, **kwargs)

    # ---------------------------------------------------------------- 応答

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, doc: dict, status: int = 200) -> None:
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"ok": False, "error": message}, status)

    # ---------------------------------------------------------------- 検査

    def _check_host(self) -> None:
        name = host_name(self.headers.get("Host", ""))
        if name not in LOOPBACK_NAMES and name not in self.app.allowed_hosts:
            raise HttpError(403, "この名前では開けない(設定の allowed_hosts に足す)")

    def _check_post(self) -> None:
        ctype = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise HttpError(415, "JSON だけを受け付ける")
        origin = self.headers.get("Origin")
        if not origin or urlsplit(origin).netloc.lower() != self.headers.get("Host", "").strip().lower():
            raise HttpError(403, "同じ出所からの要求だけを受け付ける")

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise HttpError(400, "Content-Length が数でない") from exc
        if not 0 <= length <= MAX_BODY_BYTES:
            raise HttpError(413, "本文が大きすぎる")
        return self.rfile.read(length) if length else b""

    def _read_json(self) -> dict:
        try:
            doc = json.loads(self._read_body() or b"null")
        except ValueError as exc:
            raise HttpError(400, "JSON として読めない") from exc
        if not isinstance(doc, dict):
            raise HttpError(400, "本文は JSON のオブジェクト")
        return doc

    # ---------------------------------------------------------------- 入口

    def _dispatch(self, routes: dict) -> None:
        path = self.path.split("?", 1)[0]
        try:
            self._check_host()
            if self.command == "POST":
                self._check_post()
            handler = routes.get(path)
            if handler is None and (path.startswith(GRILL_PREFIX) or path in GRILL_PASSTHROUGH):
                handler = self._proxy_grill
            if handler is None:
                raise HttpError(404, "見つからない")
            handler()
        except HttpError as exc:
            self._error(exc.status, exc.message)
        except ValueError as exc:  # 入力の問題(キーの規則違反など)
            self._error(400, str(exc))
        except Exception as exc:
            self.log_error("%s %s: %s: %s", self.command, path, type(exc).__name__, exc)
            self._error(500, "サーバーの中で失敗した")

    def do_GET(self) -> None:
        self._dispatch({"/": self._page, "/index.html": self._page, "/api/board": self._board})

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        self._dispatch({"/api/send": self._post_send, "/api/approve": self._post_approve})

    # ---------------------------------------------------------------- 画面と表

    def _page(self) -> None:
        try:
            body = PAGE.read_bytes()
        except OSError as exc:
            raise HttpError(500, "board.html が無い") from exc
        self._send(200, body, "text/html; charset=utf-8")

    def _inputs(self) -> dict:
        return self.app.collector.inputs()

    def _board(self) -> None:
        self._json(compose.compose(self._inputs()))

    # ---------------------------------------------------------------- 操作

    def _post_send(self) -> None:
        doc = self._read_json()
        project, topic = _keys(doc)
        text = doc.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HttpError(400, "送る文が空")
        data = self._inputs()
        row = _find_row(compose.compose(data), project, topic)
        session = (row or {}).get("session")
        target = {"name": session.get("name"), "tmux": session.get("tmux")} if session else None
        result = actions.send_instruction(self.app.root, project, topic, target, text, self.app.courier, self.app.tmux)
        self._json({"ok": result["delivered"], **result})

    def _post_approve(self) -> None:
        doc = self._read_json()
        project, topic = _keys(doc)
        draft_id = doc.get("draft_id")
        if not isinstance(draft_id, str) or not records.KEY_RE.fullmatch(draft_id):
            raise HttpError(400, "draft_id が正しくない")
        hub = _hub_target(self._inputs(), project)
        result = actions.approve(self.app.root, project, topic, draft_id, hub, self.app.courier, self.app.tmux)
        self._json(result)

    # ---------------------------------------------------------------- 質問票の中継

    def _proxy_grill(self) -> None:
        """grill-visual へそのまま渡す(/grill/<path> は /<path> に、/submit と /api/chat は同じパスに)。"""
        target = self.path[len(GRILL_PREFIX) - 1:] if self.path.startswith(GRILL_PREFIX) else self.path
        if ".." in target.split("?", 1)[0].split("/"):
            raise HttpError(400, "パスに .. は使えない")
        if self.command not in ("GET", "HEAD", "POST"):
            raise HttpError(405, "使えないメソッド")
        body = self._read_body() if self.command == "POST" else None
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")} if body is not None else {}
        url = urlsplit(self.app.grill_url)
        conn = http.client.HTTPConnection(url.hostname or "127.0.0.1", url.port or 80, timeout=PROXY_TIMEOUT)
        try:
            conn.request(self.command, target, body=body, headers=headers)
            res = conn.getresponse()
            data = res.read()
        except OSError as exc:
            raise HttpError(502, "質問票のサーバー(grill-visual)が動いていない") from exc
        finally:
            conn.close()
        self._send(res.status, data, res.getheader("Content-Type", "application/octet-stream"))

    def log_message(self, *args) -> None:
        pass  # アクセスログは残さない(常駐で大きくしない)

    def log_error(self, fmt: str, *args) -> None:
        print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {fmt % args}", file=sys.stderr, flush=True)


def _keys(doc: dict) -> tuple[str, str]:
    project = records.check_key(doc.get("project"), "プロジェクト名")
    topic = records.check_key(doc.get("topic"), "題材")
    return project, topic


def _find_row(board: dict, project: str, topic: str) -> dict | None:
    for tab in board.get("tabs", []):
        for row in tab["rows"]:
            if row["project"] == project and row["topic"] == topic:
                return row
    return None


def _hub_target(data: dict, project: str) -> dict | None:
    """中心のセッション(設定の hub の名前)。生きていれば tmux の宛先も添える。"""
    name = (data.get("projects", {}).get(project) or {}).get("hub")
    if not name:
        return None
    live = [s for s in data.get("sessions", []) if s.get("alive") and s.get("name") == name]
    pane = sessions.tmux_target(live[0].get("tmux")) if live else None
    return {"name": name, "tmux": pane}


def make_server(app: App, port: int) -> ThreadingHTTPServer:
    """127.0.0.1 だけで待ち受ける。port=0 で空きポート(テスト用)。"""
    return ThreadingHTTPServer((BIND, port), functools.partial(Handler, app=app))


def main() -> None:
    import collect
    import config
    from deliver import Courier, TmuxSender

    root = records.resolve_root()
    conf = config.load_config()
    grill_url = os.environ.get("BOARD_GRILL_URL") or conf.get("grill_url") or DEFAULT_GRILL_URL
    hosts = conf.get("allowed_hosts") if isinstance(conf.get("allowed_hosts"), list) else []
    env_hosts = [h for h in os.environ.get("BOARD_ALLOWED_HOSTS", "").split(",") if h.strip()]
    # BOARD_NO_TMUX / BOARD_NO_COURIER: 配達を切る(demo.sh が付ける。見本から実物へ送らないため)
    tmux = None if os.environ.get("BOARD_NO_TMUX") else TmuxSender()
    app = App(
        root=root,
        collector=collect.Collector(root, grill_url, pane_reader=tmux.pane_text if tmux else None),
        courier=None if os.environ.get("BOARD_NO_COURIER") else Courier(),
        tmux=tmux,
        grill_url=grill_url,
        allowed_hosts=frozenset(str(h).strip().lower() for h in [*hosts, *env_hosts]),
    )
    port = int(os.environ.get("BOARD_PORT") or DEFAULT_PORT)
    make_server(app, port).serve_forever()


if __name__ == "__main__":
    main()
