"""画面からの操作: 指示を送る(R8)・案を承認する(R9)。結果は題材の記録に残す。"""
from __future__ import annotations

import threading
from pathlib import Path

import records
from deliver import PaneSender, Sender, clean_text, deliver
from rows import DRAFT_KINDS

_APPROVE_LOCK = threading.Lock()


def send_instruction(root: Path, project: str, topic: str, target: dict | None, text: str,
                     courier: Sender | None, tmux: PaneSender | None) -> dict:
    """指示を 1 件送り、送った文と結果を記録に足す。宛先が無くても記録は残す。"""
    records.check_key(project, "プロジェクト名")
    records.check_key(topic, "題材")
    line = clean_text(text)
    if target:
        result = deliver(target, line, courier, tmux).to_dict()
    else:
        result = {"delivered": False, "via": None, "error": "この題材のセッションが見つからない"}
    records.append(root, project, topic, {"kind": "sent", "text": line, **result})
    return result


def approval_message(project: str, topic: str, draft: dict) -> str:
    label = DRAFT_KINDS.get(str(draft.get("kind")), "案")
    where = f"#{draft['issue']}" if isinstance(draft.get("issue"), int) else topic
    return (f"board: {project} {where} の{label}「{draft.get('title', '')}」が承認された"
            f"(draft {draft['draft_id']})。記録の全文で GitHub に作ってください")


def approve(root: Path, project: str, topic: str, draft_id: str, hub: dict | None,
            courier: Sender | None, tmux: PaneSender | None) -> dict:
    """R9: 記録に承認を足し、中心へ知らせる。同じ案を 2 回承認しても 1 回分(2 回目は何もしない)。"""
    records.check_key(project, "プロジェクト名")
    records.check_key(topic, "題材")
    with _APPROVE_LOCK:
        lines = records.read(root, project, topic)
        draft = next((x for x in reversed(lines) if x.get("kind") in DRAFT_KINDS and x.get("draft_id") == draft_id), None)
        if draft is None:
            raise ValueError(f"その案が記録に無い: {draft_id!r}")
        already = any(x.get("kind") == "approve" and x.get("draft_id") == draft_id for x in lines)
        if already and notice_delivered(lines, draft_id):
            return {"ok": True, "already": True, "notified": None}
        if not already:
            records.append(root, project, topic, {"kind": "approve", "draft_id": draft_id, "draft_kind": draft["kind"],
                                                  "title": str(draft.get("title", ""))})
    # 承認は 1 回分だけ。中心への知らせが届いていなければ、もう一度押したときに送り直す
    text = approval_message(project, topic, draft)
    if hub:
        notified = deliver(hub, text, courier, tmux).to_dict()
    else:
        notified = {"delivered": False, "via": None, "error": "中心のセッションが分からない"}
    records.append(root, project, topic, {"kind": "sent", "to": "hub", "draft_id": draft_id, "text": text, **notified})
    return {"ok": True, "already": already, "notified": notified}


def notice_delivered(lines: list[dict], draft_id: str) -> bool:
    return any(x.get("kind") == "sent" and x.get("to") == "hub" and x.get("draft_id") == draft_id
               and x.get("delivered") for x in lines)


def record_start(root: Path, project: str, topic: str, what: str, result: dict, arg: str | None = None) -> None:
    """始めたことを記録に 1 件残す(誰が・いつ・結果)。失敗も残す。"""
    entry = {"kind": "start", "what": what, "by": "board", "ok": bool(result.get("ok")), "code": result.get("code")}
    if arg:
        entry["arg"] = arg
    if result.get("output"):
        entry["output_tail"] = str(result["output"])[-500:]
    records.append(root, project, topic, entry)
