"""中心(hub)の 1 行と「中心を始める」ボタンの判定(純粋関数)。

中心は、そのプロジェクトの設定の hub(並列運用のラッパーの PARALLEL_HUB)と同じ名前の、生きているセッション。
始める手段は、設定の hub_command(引数の配列)か、自動で見つけた起動スクリプト(~/bin/<名前>-hub.sh)。
"""
from __future__ import annotations

from typing import Callable

import sessions
from rows import Topic

HUB_KEY = "_hub"           # 中心の記録の題材のキー(<BOARD_ROOT>/records/<project>/_hub.jsonl)
HUB_WINDOW = "hub"         # 中心を始める tmux の窓の名前
STARTING_SECONDS = 120     # 押してから、この秒数の間は「起動中」として二重に始めない
START_LABEL = "中心を始める"


def tmux_session(project: str, conf: dict) -> str:
    return str(conf.get("tmux_session") or project)


def hub_command(conf: dict) -> list[str] | None:
    """中心の起動コマンド: 設定の hub_command(文字列の配列)→ 起動スクリプト → None。"""
    cmd = conf.get("hub_command")
    if isinstance(cmd, list) and cmd and all(isinstance(x, str) and x for x in cmd):
        return list(cmd)
    script = conf.get("hub_script")
    return [str(script)] if isinstance(script, str) and script else None


def find_hub_session(name: str | None, alive: list[dict]) -> dict | None:
    if not name:
        return None
    return next((s for s in alive if s.get("name") == name), None)


def is_starting(data: dict, project: str, now: float, what: object = "hub") -> bool:
    started = (data.get("starting") or {}).get((project, what))
    return isinstance(started, (int, float)) and now - started < STARTING_SECONDS


def root_note(project: str, conf: dict, name: str | None, alive: list[dict], projects: dict) -> str | None:
    """中心がいないのに、本体のフォルダで別の名前のセッションが動いているとき(名前を付け忘れた中心かもしれない)。"""
    others = [s.get("name") or str(s.get("sessionId", ""))[:8] for s in alive
              if s.get("name") != name and sessions.locate(s.get("cwd", ""), projects) == (project, None, None)]
    return f"本体のフォルダで別の名前のセッションが動いている: {'、'.join(others)}" if others else None


def start_button(project: str, conf: dict, running: bool, starting: bool) -> dict | None:
    """「中心を始める」ボタン。中心が動いていれば出さない(None)。押せないときは理由を添える。"""
    if running:
        return None
    reason = None
    if starting:
        reason = "起動中"
    elif not conf.get("hub"):
        reason = "中心の名前(PARALLEL_HUB)が分からない"
    elif hub_command(conf) is None:
        reason = "起動スクリプトが無い"
    return {"label": START_LABEL, "enabled": reason is None, "reason": reason}


def hub_view(project: str, conf: dict, data: dict, alive: list[dict], build_row: Callable[[Topic], dict]) -> dict:
    """タブの上に出す中心の 1 行。押すとほかの行と同じ枠が開く(row)。"""
    now = data["now"]
    name = conf.get("hub")
    found = find_hub_session(name, alive)
    view = sessions.session_view(found, now) if found else None
    starting = view is None and is_starting(data, project, now)
    topic = Topic(project=project, key=HUB_KEY, records=list(data.get("records", {}).get((project, HUB_KEY), [])),
                  sessions=[view] if view else [])
    row = {**build_row(topic), "title": f"中心({name})" if name else "中心", "is_hub": True}
    if view:
        state, label = view["state"], view["label"]
    elif starting:
        state, label = "starting", "起動中"
    else:
        state, label = "absent", "いない"
    session = tmux_session(project, conf)
    return {
        "note": root_note(project, conf, name, alive, data.get("projects", {})) if view is None else None,
        "name": name,
        "state": state,
        "label": label,
        "context": row.get("context"),
        "row": row,
        "start": start_button(project, conf, view is not None, starting),
        "attach": {"command": f"tmux attach -t {session}", "window": HUB_WINDOW},
    }


CHILD_LABEL = "子を始める"


def default_slug(issue: int, folders: list[str]) -> str:
    """既にある作業ツリー(<番号>-<slug>)の slug。無ければ空(日本語の題からは作れないので人が書く)。"""
    prefix = f"{issue}-"
    for name in sorted(folders):
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix):]
    return ""


def child_button(row: dict, conf: dict | None, folders: list[str], starting: bool = False) -> dict | None:
    """行の枠の「子を始める」。番号があり、完了でなく、動いているセッションが無い行だけ。"""
    if conf is None or row.get("issue") is None or row.get("status") == "done" or row.get("session"):
        return None
    issue = row["issue"]
    reason = "起動中" if starting else (None if conf.get("wrapper") else "並列運用のラッパーが無い")
    return {
        "label": CHILD_LABEL,
        "enabled": reason is None,
        "reason": reason,
        "slug": default_slug(issue, folders),
        "fix": False,
        "confirm": f"#{issue} の子を始めます。作業ツリーと窓が作られます",
    }
