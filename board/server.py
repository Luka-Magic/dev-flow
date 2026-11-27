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
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import actions
import compose
import hub
import records
import sessions
import start

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
UI_COMMENTS_OVERLAY = "/ui-comments/overlay.js"
UI_COMMENTS_API = "/api/threads"
UI_COMMENTS_PROJECT = os.environ.get("BOARD_UI_COMMENTS_PROJECT") or "devflow-board"
if not records.KEY_RE.fullmatch(UI_COMMENTS_PROJECT):  # HTML の属性に入るので、キーの規則に合うものだけ
    print(f"board: BOARD_UI_COMMENTS_PROJECT が規則に合わないので devflow-board を使う: {UI_COMMENTS_PROJECT!r}",
          file=sys.stderr)
    UI_COMMENTS_PROJECT = "devflow-board"
DEFAULT_UI_COMMENTS_PORT = 4321  # 4319 は RoomLab、4320 は grill-visual のお試し用が使う


@dataclass
class App:
    """サーバーが使う部品。テストでは集め役と配達を偽物に差し替える。"""
    root: Path
    collector: Any                  # .inputs() -> dict
    courier: Any = None             # deliver.Sender
    tmux: Any = None                # deliver.PaneSender
    grill_url: str = DEFAULT_GRILL_URL
    allowed_hosts: frozenset[str] = field(default_factory=frozenset)
    ui_comments_port: int | None = None  # ui-comments の専用サーバー。None なら差し込みも中継もしない
    launcher: Any = None            # start.TmuxLauncher(テストと見本では偽物)。None なら始められない
    starting: dict = field(default_factory=dict)  # {(project, "hub" | issue): 押した時刻}。二重に始めない
    start_lock: threading.Lock = field(default_factory=threading.Lock)


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

    def _check_post(self, allow_empty: bool = False) -> None:
        """書き込みの要求: 本文は JSON だけ(allow_empty なら本文なしも可)、Origin は同じ出所だけ。"""
        ctype = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        empty = (self.headers.get("Content-Length") or "0").strip() == "0"
        if ctype != "application/json" and not (allow_empty and empty):
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
            if self.headers.get("Transfer-Encoding"):  # 本文は Content-Length で受ける(chunked は読まない)
                raise HttpError(400, "Transfer-Encoding は受け付けない")
            ui_comments = self._is_ui_comments(path)
            if self.command in ("POST", "PATCH", "DELETE"):
                self._check_post(allow_empty=ui_comments)  # ui-comments は本文なしの POST・DELETE を使う
            handler = routes.get(path)
            if handler is None and ui_comments:
                handler = self._proxy_ui_comments
            elif handler is None and (path.startswith(GRILL_PREFIX) or path in GRILL_PASSTHROUGH):
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
        self._dispatch({"/api/send": self._post_send, "/api/approve": self._post_approve, "/api/start": self._post_start})

    def do_PATCH(self) -> None:
        self._dispatch({})  # ui-comments の中継だけ

    def do_DELETE(self) -> None:
        self._dispatch({})

    # ---------------------------------------------------------------- 画面と表

    def _page(self) -> None:
        try:
            body = PAGE.read_bytes()
        except OSError as exc:
            raise HttpError(500, "board.html が無い") from exc
        if self.app.ui_comments_port is not None:  # 差し込むのは board の画面だけ(中継する質問票には入れない)
            body = inject_before_body_end(body, ui_comments_tag(UI_COMMENTS_PROJECT))
        self._send(200, body, "text/html; charset=utf-8")

    def _inputs(self) -> dict:
        with self.app.start_lock:
            starting = dict(self.app.starting)
        return {**self.app.collector.inputs(), "starting": starting}

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

    # ---------------------------------------------------------------- 開始

    def _post_start(self) -> None:
        """中心か子を始める。判定は /api/board と同じ合成の結果で行い、起動するのは設定と自動検出で決まったものだけ。"""
        doc = self._read_json()
        project = records.check_key(doc.get("project"), "プロジェクト名")
        kind = doc.get("kind")
        if kind not in ("hub", "child"):
            raise HttpError(400, "kind は hub か child")
        if self.app.launcher is None:
            raise HttpError(409, "この board では起動できない")
        data = self._inputs()
        conf = data.get("projects", {}).get(project)
        if conf is None:
            raise HttpError(404, "そのプロジェクトの設定が無い")
        board = compose.compose(data)
        if kind == "hub":
            self._start_hub(project, conf, board)
        else:
            self._start_child(project, conf, board, doc)

    def _claim(self, key: tuple) -> None:
        """押した直後の二重押しを断る(起動中の印を付ける)。"""
        ttl = hub.STARTING_SECONDS if key[1] == "hub" else start.CHILD_STARTING_SECONDS
        with self.app.start_lock:
            started = self.app.starting.get(key)
            if started is not None and time.time() - started < ttl:
                raise HttpError(409, "起動中")
            self.app.starting[key] = time.time()

    def _release(self, key: tuple) -> None:
        with self.app.start_lock:
            self.app.starting.pop(key, None)

    def _start_hub(self, project: str, conf: dict, board: dict) -> None:
        tab = next((t for t in board.get("tabs", []) if t.get("project") == project), None)
        view = (tab or {}).get("hub")
        if view is None or view["start"] is None:
            raise HttpError(409, "中心は動いている")
        if not view["start"]["enabled"]:
            raise HttpError(409, view["start"]["reason"] or "始められない")
        plan = start.hub_plan(project, conf)
        result = self._launch((project, "hub"), lambda: self.app.launcher.start_hub(plan))
        self._record(project, hub.HUB_KEY, "hub", result)
        self._json({**result, "attach": view["attach"]})

    def _start_child(self, project: str, conf: dict, board: dict, doc: dict) -> None:
        arg = start.child_arg(doc.get("issue"), doc.get("slug"), doc.get("fix"))  # 値の検査が先
        row = _find_row(board, project, str(doc["issue"]))
        button = (row or {}).get("child_start")
        if button is None:
            raise HttpError(409, "この行では子を始められない(セッションが動いているか、完了している)")
        if not button["enabled"]:
            raise HttpError(409, button["reason"] or "始められない")
        if button["slug"] and doc["slug"] != button["slug"]:  # 同じ issue に 2 つ目の作業ツリーを作らない
            raise HttpError(409, f"#{doc['issue']} には作業ツリー {doc['issue']}-{button['slug']} がある。slug を {button['slug']} にする")
        plan = start.child_plan(conf, doc["issue"], doc["slug"], doc["fix"])
        result = self._launch((project, doc["issue"]), lambda: self.app.launcher.start_child(plan))
        self._record(project, str(doc["issue"]), "child", result, arg)
        self._json(result)

    def _launch(self, key: tuple, run) -> dict:
        """起動中の印を付けて動かす。確かに終わって失敗したとき(上限で断られたなど)だけ印を外し、もう一度押せるようにする。
        途中で待つのをやめたとき(settled=False)は、何が作られたか分からないので印を残す。"""
        self._claim(key)
        try:
            result = run().to_dict()
        except Exception:
            self._release(key)
            raise
        if not result["ok"] and result.get("settled", True):
            self._release(key)
        return result

    def _record(self, project: str, topic: str, what: str, result: dict, arg: str | None = None) -> None:
        """記録に失敗しても、起動の結果は返す(起動は済んでいるので、押し直させない)。"""
        try:
            actions.record_start(self.app.root, project, topic, what, result, arg)
        except OSError as exc:
            self.log_error("開始の記録を書けない: %s", exc)
            result["record_error"] = "記録を書けなかった"

    # ---------------------------------------------------------------- 質問票の中継

    def _proxy_grill(self) -> None:
        """grill-visual へそのまま渡す(/grill/<path> は /<path> に、/submit と /api/chat は同じパスに)。"""
        target = self.path[len(GRILL_PREFIX) - 1:] if self.path.startswith(GRILL_PREFIX) else self.path
        if self.command not in ("GET", "HEAD", "POST"):
            raise HttpError(405, "使えないメソッド")
        url = urlsplit(self.app.grill_url)
        self._relay(url.hostname or "127.0.0.1", url.port or 80, target, "質問票のサーバー(grill-visual)が動いていない")

    def _is_ui_comments(self, path: str) -> bool:
        if self.app.ui_comments_port is None:
            return False  # 無効のときは中継しない(/api/threads は 404 になる)
        return path in (UI_COMMENTS_OVERLAY, UI_COMMENTS_API) or path.startswith(UI_COMMENTS_API + "/")

    def _proxy_ui_comments(self) -> None:
        """ui-comments の専用サーバーへ渡す。Host は 127.0.0.1、Origin は渡さない
        (出所の確かめは board が済ませた。tailnet の名前ごしでも専用サーバーに断られないように)。"""
        is_overlay = self.path.split("?", 1)[0] == UI_COMMENTS_OVERLAY
        if is_overlay and self.command not in ("GET", "HEAD"):
            raise HttpError(405, "使えないメソッド")
        target = "/overlay.js" if is_overlay else self.path
        self._relay("127.0.0.1", self.app.ui_comments_port, target, "ui-comments の専用サーバーが動いていない")

    def _relay(self, host: str, port: int, target: str, down_message: str) -> None:
        if ".." in target.split("?", 1)[0].split("/"):
            raise HttpError(400, "パスに .. は使えない")
        body = self._read_body() if self.command in ("POST", "PATCH", "DELETE") else None
        headers = {"Content-Type": self.headers.get("Content-Type") or "application/json"} if body else {}
        conn = http.client.HTTPConnection(host, port, timeout=PROXY_TIMEOUT)
        try:
            conn.request(self.command, target, body=body if body else None, headers=headers)
            res = conn.getresponse()
            data = res.read()
        except OSError as exc:
            raise HttpError(502, down_message) from exc
        finally:
            conn.close()
        self._send(res.status, data, res.getheader("Content-Type", "application/octet-stream"))

    def log_message(self, *args) -> None:
        pass  # アクセスログは残さない(常駐で大きくしない)

    def log_error(self, fmt: str, *args) -> None:
        print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {fmt % args}", file=sys.stderr, flush=True)


def ui_comments_port(raw: str | None, board_port: int) -> int:
    """専用サーバーのポート。数でない・範囲外・board 自身と同じなら起動をやめる(自分へ中継し続けないように)。"""
    try:
        value = int(raw) if raw else DEFAULT_UI_COMMENTS_PORT
    except ValueError:
        sys.exit(f"board: BOARD_UI_COMMENTS_PORT が数でない: {raw!r}")
    if not 1 <= value <= 65535 or value == board_port:
        sys.exit(f"board: BOARD_UI_COMMENTS_PORT が使えない値: {value}")
    return value


def ui_comments_tag(project: str) -> str:
    return f'<script src="{UI_COMMENTS_OVERLAY}" data-project="{project}" defer></script>\n'


def inject_before_body_end(html: bytes, snippet: str) -> bytes:
    """</body> の直前に snippet を入れる。</body> が無ければ末尾に足す。"""
    data = snippet.encode("utf-8")
    i = html.rfind(b"</body>")
    return html + data if i < 0 else html[:i] + data + html[i:]


def _keys(doc: dict) -> tuple[str, str]:
    project = records.check_key(doc.get("project"), "プロジェクト名")
    topic = records.check_key(doc.get("topic"), "題材")
    return project, topic


def _find_row(board: dict, project: str, topic: str) -> dict | None:
    for tab in board.get("tabs", []):
        hub_row = (tab.get("hub") or {}).get("row")
        if hub_row and hub_row["project"] == project and hub_row["topic"] == topic:
            return hub_row
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
    from deliver import Courier, TmuxSender, resolve_model

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
        courier=None if os.environ.get("BOARD_NO_COURIER") else Courier(model=resolve_model(None, conf)),
        tmux=tmux,
        grill_url=grill_url,
        allowed_hosts=frozenset(str(h).strip().lower() for h in [*hosts, *env_hosts]),
    )
    if os.environ.get("BOARD_DEMO_LAUNCH") == "1":  # 見本: 実物を起動しない偽物(demo.sh が付ける)
        from demo_launcher import DemoLauncher

        app.launcher = DemoLauncher(app.collector.sessions_dir, config.discover_projects(conf))
    else:
        app.launcher = start.TmuxLauncher()
    port = int(os.environ.get("BOARD_PORT") or DEFAULT_PORT)
    if os.environ.get("BOARD_UI_COMMENTS") == "1":  # ui-comments を差し込む(serve.sh / demo.sh が専用サーバーも起こす)
        app.ui_comments_port = ui_comments_port(os.environ.get("BOARD_UI_COMMENTS_PORT"), port)
    make_server(app, port).serve_forever()


if __name__ == "__main__":
    main()
