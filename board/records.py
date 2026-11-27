"""記録: 題材ごとの追記専用 JSONL(1 行 1 件)。

置き場所: <BOARD_ROOT>/records/<project>/<topic>.jsonl
書くのは追記だけ(既存の行は書き換えない)。読むときは壊れた行を飛ばし、ほかの行は読む。
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import time
from pathlib import Path

RECORDS_DIR = "records"
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
LEADING_NUMBER_RE = re.compile(r"^(\d{1,6})(?:-|$)")
DEFAULT_ROOT = Path.home() / ".agent" / "devflow"
TIME_FMT = "%Y-%m-%dT%H:%M:%S"


def resolve_root() -> Path:
    """記録の置き場所。BOARD_ROOT があればそれ、無ければ ~/.agent/devflow。"""
    return Path(os.environ.get("BOARD_ROOT") or DEFAULT_ROOT).expanduser()


def sanitize_key(text: str) -> str:
    """フォルダ名・ブランチ名を題材のキーに使える形にする(使えない文字は - に寄せる)。"""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")[:80]


def check_key(value: object, what: str) -> str:
    """プロジェクト名・題材のキーは英数字と - _ だけ(1〜80 文字)。"""
    if not isinstance(value, str) or not KEY_RE.match(value):
        raise ValueError(f"{what} に使えない文字がある: {value!r}")
    return value


def record_path(root: Path, project: str, topic: str) -> Path:
    """記録のファイル。置き場所の外に出るパスは拒む。"""
    base = (Path(root) / RECORDS_DIR).resolve()
    path = (base / check_key(project, "プロジェクト名") / f"{check_key(topic, '題材')}.jsonl").resolve()
    if base not in path.parents:
        raise ValueError(f"記録の置き場所の外を指している: {path}")
    return path


def now_text(ts: float | None = None) -> str:
    return time.strftime(TIME_FMT, time.localtime(time.time() if ts is None else ts))


def append(root: Path, project: str, topic: str, entry: dict) -> dict:
    """1 件を追記して、書いた内容(時刻つき)を返す。"""
    if not isinstance(entry, dict) or not isinstance(entry.get("kind"), str):
        raise ValueError("entry には kind が要る")
    path = record_path(root, project, topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"ts": now_text(), **entry}
    data = json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # 並行した追記が 1 行の途中で混ざらないように
        try:
            fh.write(data)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    return line


def parse_lines(text: str) -> list[dict]:
    """JSONL の本文を読む。壊れた行・オブジェクトでない行・kind の無い行は飛ばす。"""
    out: list[dict] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if isinstance(doc, dict) and isinstance(doc.get("kind"), str):
            out.append(doc)
    return out


def read(root: Path, project: str, topic: str) -> list[dict]:
    path = record_path(root, project, topic)
    try:
        return parse_lines(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError:
        return []


def read_all(root: Path) -> dict[tuple[str, str], list[dict]]:
    """{(project, topic): 記録} を全部読む。キーの規則に合わないファイルは無視する。"""
    base = Path(root) / RECORDS_DIR
    out: dict[tuple[str, str], list[dict]] = {}
    if not base.is_dir():
        return out
    for pdir in sorted(base.iterdir()):
        if not pdir.is_dir() or not KEY_RE.match(pdir.name):
            continue
        for f in sorted(pdir.glob("*.jsonl")):
            if KEY_RE.match(f.stem):
                out[(pdir.name, f.stem)] = read(root, pdir.name, f.stem)
    return out
