#!/usr/bin/env python3
"""見本の質問票サーバー(demo.sh 用)。grill-visual の入口のうち board が使うものだけを真似る。

  GET  /api/state        … <フォルダ>/state.json
  GET  /<file>           … <フォルダ> の静的配信(質問票の HTML・画像)
  POST /submit           … 受け取った回答を <フォルダ>/answers/ に置く
  GET/POST /api/chat     … 空の会話

  python3 demo_grill.py <フォルダ> <ポート>   (127.0.0.1 限定)
"""
from __future__ import annotations

import functools
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, directory=str(root), **kwargs)

    def _json(self, doc: dict) -> None:
        body = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._json(json.loads((self.root / "state.json").read_text(encoding="utf-8")))
        elif path == "/api/chat":
            self._json({"messages": []})
        else:
            super().do_GET()

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        if self.path.split("?", 1)[0] == "/submit":
            doc = json.loads(body or b"{}")
            topic = "".join(c for c in str(doc.get("topic", "x")) if c.isalnum() or c in "-_") or "x"
            out = self.root / "answers" / f"{topic}-round-{int(doc.get('round', 0))}.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        self._json({"ok": True, "messages": []})

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    folder, port = Path(sys.argv[1]), int(sys.argv[2])
    ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, root=folder)).serve_forever()
