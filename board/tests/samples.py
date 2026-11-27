"""合成のテストに渡す見本(外への問い合わせの結果の形)。"""
from __future__ import annotations

NOW = 1_790_000_000.0  # 固定の現在時刻(エポック秒)


def inputs(**over) -> dict:
    base = {
        "now": NOW,
        "projects": {"demo": {"hub": "demo_hub", "path": "/work/demo"}},
        "records": {},
        "grill": {"topics": []},
        "gh": {},
        "sessions": [],
        "usage": [],
    }
    return {**base, **over}


def issue(number: int, title: str = "", state: str = "OPEN") -> dict:
    return {"number": number, "title": title or f"issue {number}", "state": state,
            "url": f"https://example.invalid/demo/issues/{number}"}


def pr(number: int, head: str, state: str = "OPEN", body: str = "") -> dict:
    return {"number": number, "title": f"PR {number}", "state": state, "headRefName": head, "body": body,
            "url": f"https://example.invalid/demo/pull/{number}", "statusCheckRollup": []}


def grill_topic(topic: str, state: str = "waiting", project: str | None = "demo", issue: int | None = None,
                kind: str | None = "計画", archived: bool = False) -> dict:
    return {"topic": topic, "title": f"title of {topic}", "kind": kind, "project": project, "issue": issue,
            "state": state, "open_round": 1 if state != "done" else None, "updated_at": "2026-09-01T10:00:00",
            "version": "1", "html_exists": True, "archived": archived, "error": None}


def step(stage: str, ts: str = "2026-09-01T10:00:00", **extra) -> dict:
    return {"ts": ts, "kind": "step", "stage": stage, **extra}


def report(text: str, ts: str = "2026-09-01T10:00:00", **extra) -> dict:
    return {"ts": ts, "kind": "report", "text": text, **extra}


def session(name: str, cwd: str, status: str = "idle", alive: bool = True, minutes_ago: float = 5,
            pane: str | None = None, waiting_for: str | None = None, sid: str | None = None) -> dict:
    doc = {"pid": 4242, "sessionId": sid or f"sid-{name}", "cwd": cwd, "name": name, "kind": "interactive",
           "status": status, "statusUpdatedAt": int((NOW - minutes_ago * 60) * 1000), "alive": alive,
           "tmux": f"demo:@1.%{abs(hash(name)) % 90 + 1}", "pane": pane}
    if waiting_for:
        doc["waitingFor"] = waiting_for
    return doc


def find_row(board: dict, project: str, topic: str) -> dict:
    for tab in board["tabs"]:
        for row in tab["rows"]:
            if row["project"] == project and row["topic"] == topic:
                return row
    raise AssertionError(f"row {project}/{topic} が無い: {[r['id'] for t in board['tabs'] for r in t['rows']]}")


def closed_port() -> int:
    """いま誰も待ち受けていないポート(つながらない相手の見本)。"""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
