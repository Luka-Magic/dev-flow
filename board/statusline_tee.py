#!/usr/bin/env python3
"""ステータス行の包み: 受け取った JSON から使用量を書き出し、元のコマンドへそのまま渡す。

  statusline_tee.py -- <元のステータス行のコマンド> [引数...]

書き出し先: <BOARD_ROOT>/usage/<session_id>.json(BOARD_ROOT の既定は ~/.agent/devflow)。
一時ファイルに書いてから置き換える(読み手が途中の内容を見ない)。書き出しに失敗しても、
元のコマンドには必ず渡す(ステータス行を止めない)。残すのは使用量に要る値だけ。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from records import KEY_RE, resolve_root

USAGE_DIR = "usage"
LIMIT_KEYS = ("five_hour", "seven_day")


def _pick(doc: object, keys: tuple[str, ...]) -> dict:
    return {k: doc[k] for k in keys if isinstance(doc, dict) and k in doc}


def extract(status: dict) -> dict | None:
    """ステータス行の JSON から、書き出す値だけを抜く。session_id が無ければ None。"""
    sid = status.get("session_id")
    if not isinstance(sid, str) or not KEY_RE.match(sid):
        return None
    limits = status.get("rate_limits") if isinstance(status.get("rate_limits"), dict) else {}
    return {
        "written_at": time.time(),
        "session_id": sid,
        "context_window": _pick(status.get("context_window"), ("used_percentage", "context_window_size")),
        "rate_limits": {k: _pick(limits.get(k), ("used_percentage", "resets_at")) for k in LIMIT_KEYS if k in limits},
        "model": _pick(status.get("model"), ("display_name",)),
        "cwd": status.get("cwd") if isinstance(status.get("cwd"), str) else "",
    }


def write_atomic(folder: Path, name: str, doc: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        os.replace(tmp, folder / f"{name}.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def record_usage(raw: bytes) -> None:
    try:
        status = json.loads(raw)
    except ValueError:
        return
    doc = extract(status) if isinstance(status, dict) else None
    if doc is None:
        return
    try:
        write_atomic(resolve_root() / USAGE_DIR, doc["session_id"], doc)
    except OSError as exc:
        print(f"statusline_tee: 書き出せない: {exc}", file=sys.stderr)


def main(argv: list[str]) -> int:
    command = argv[1:] if argv and argv[0] == "--" else argv
    raw = sys.stdin.buffer.read()
    record_usage(raw)
    if not command:
        return 0
    try:
        res = subprocess.run(command, input=raw, stdout=sys.stdout.buffer, check=False)
    except OSError as exc:
        print(f"statusline_tee: 元のコマンドを動かせない: {exc}", file=sys.stderr)
        return 1
    return res.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
