"""Claude Code のセッションの状態と、どのプロジェクト・題材のものかの見分け(純粋関数)。

窓の状態の見分け方は dev-flow の parallel/state.sh と同じ:
  実行中   … 画面に "esc to interrupt" がある
  確認待ち … 選択肢(❯ Yes / No / 1. など)か "Do you want" などが出ている
  入力待ち … どちらでもない
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from records import LEADING_NUMBER_RE, sanitize_key

RUNNING_RE = re.compile(r"esc to interrupt", re.IGNORECASE)
CHOICE_RE = re.compile(r"^\s*[❯>]\s*(Yes|No|[0-9]\.)", re.MULTILINE)
ASK_RE = re.compile(r"Do you want|trust this folder|approve")
ASKING_LINES = 8


def pane_state(text: str | None) -> str | None:
    """tmux の窓の表示から running / confirm / idle。表示が無ければ None。"""
    if not text:
        return None
    if RUNNING_RE.search(text):
        return "running"
    if CHOICE_RE.search(text) or ASK_RE.search(text):
        return "confirm"
    return "idle"


def asking_text(text: str | None, waiting_for: str | None) -> str | None:
    """確認の選択肢で何を求めているか(窓の末尾の数行)。画面からは答えない。"""
    lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
    tail = "\n".join(lines[-ASKING_LINES:])
    parts = [p for p in (waiting_for, tail) if p]
    return "\n".join(parts) if parts else None


def _minutes(now: float, ms: object) -> int | None:
    if isinstance(ms, (int, float)) and not isinstance(ms, bool) and ms > 0:
        return max(0, int((now - ms / 1000) // 60))
    return None


def session_view(s: dict, now: float) -> dict:
    """1 つのセッションの状態(表の「セッション」の欄に出す値)。"""
    by_pane = pane_state(s.get("pane"))
    status = s.get("status")
    if status == "waiting" or by_pane == "confirm":
        state = "confirm"
    elif status == "busy" or by_pane == "running":
        state = "running"
    else:
        state = "idle"
    minutes = _minutes(now, s.get("statusUpdatedAt") or s.get("updatedAt"))
    if state == "running":
        label = "動いている"
    else:
        head = "確認待ち" if state == "confirm" else "止まって"
        label = f"{head} {minutes} 分" if minutes is not None else head
    return {
        "name": s.get("name") or "",
        "session_id": s.get("sessionId") or "",
        "state": state,
        "label": label,
        "minutes": minutes,
        "asking": asking_text(s.get("pane"), s.get("waitingFor")) if state == "confirm" else None,
        "tmux": tmux_target(s.get("tmux")),
        "cwd": s.get("cwd") or "",
    }


def tmux_target(value: object) -> str | None:
    """セッション一覧の tmux 欄("セッション:@窓.%ペイン")から send-keys の宛先(%ペイン)。"""
    if not isinstance(value, str):
        return None
    m = re.search(r"(%\d+)$", value)
    return m.group(1) if m else None


def _under(path: PurePosixPath, base: PurePosixPath) -> PurePosixPath | None:
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def locate(cwd: str, projects: dict[str, dict]) -> tuple[str, str | None, int | None] | None:
    """作業フォルダから (プロジェクト, 題材のキー, issue 番号)。本体そのものなら題材は None(中心)。"""
    if not cwd:
        return None
    path = PurePosixPath(cwd)
    for name, conf in sorted(projects.items(), key=lambda kv: -len(str(kv[1].get("path") or ""))):
        root = conf.get("path")
        if not root:
            continue
        base = PurePosixPath(root)
        wt_dirs = [PurePosixPath(conf["worktree_dir"])] if conf.get("worktree_dir") else []
        wt_dirs.append(base / ".claude" / "worktrees")
        for wt in wt_dirs:
            rel = _under(path, wt)
            if rel is not None and rel.parts:
                return (name, *_topic_of(rel.parts[0]))
        sibling = _under(path, base.parent)
        if sibling is not None and sibling.parts and sibling.parts[0].startswith(base.name + "-"):
            return (name, *_topic_of(sibling.parts[0][len(base.name) + 1:]))
        if _under(path, base) is not None:
            return name, None, None
    return None


def _topic_of(folder: str) -> tuple[str, int | None]:
    m = LEADING_NUMBER_RE.match(folder)
    if m:
        return m.group(1), int(m.group(1))
    return sanitize_key(folder), None
