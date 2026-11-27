"""全プロジェクトの表を合成する(純粋関数。外への問い合わせは collect.py が行う)。

入力(dict):
  now       … 現在時刻(エポック秒)
  projects  … {名前: {"path", "hub", "github", ...}}
  records   … {(project, topic): [記録の行]}
  grill     … grill-visual の /api/state の形(取れなければ None)
  gh        … {project: {"issues": [...], "prs": [...]} | {"error": "..."}}
  sessions  … ~/.claude/sessions/*.json の形 + "alive"(生きているか)+ "pane"(tmux の窓の表示)
  usage     … statusline_tee.py が書き出したファイルの中身の一覧
"""
from __future__ import annotations

import time

import detail
import hub
import records
import rows
import sessions
import stages
import usage
from rows import Topic

OTHER = ""  # プロジェクトの分からない質問票の置き場(タブ「その他」)
OTHER_LABEL = "その他"


def _gather(data: dict) -> dict[tuple[str, str], Topic]:
    topics: dict[tuple[str, str], Topic] = {}

    def get(project: str, key: str, issue: int | None) -> Topic:
        t = topics.get((project, key))
        if t is None:
            t = topics[(project, key)] = Topic(project=project, key=key, issue=issue)
        return t

    for (project, key), lines in sorted(data.get("records", {}).items()):
        if key == hub.HUB_KEY:  # 中心の記録は行にしない(中心の 1 行に出す)
            continue
        issue = rows.record_issue(key, lines)
        t = get(project, str(issue) if issue else key, issue)
        t.records.extend(lines)
    for project, doc in sorted(data.get("gh", {}).items()):
        for it in doc.get("issues", []) if isinstance(doc, dict) else []:
            n = it.get("number")
            if isinstance(n, int):
                get(project, str(n), n).gh_issue = it
        for p in doc.get("prs", []) if isinstance(doc, dict) else []:
            n = rows.pr_issue(p)
            if n is not None:
                get(project, str(n), n).prs.append(p)
            elif branch_topic(project, p, topics):
                topics[(project, branch_topic(project, p, topics))].prs.append(p)
            elif str(p.get("state", "")).upper() == "OPEN" and isinstance(p.get("number"), int):
                get(project, f"pr-{p['number']}", None).prs.append(p)
    grill = data.get("grill") or {}
    for sheet in grill.get("topics", []) if isinstance(grill, dict) else []:
        project, n = sheet.get("project") or OTHER, sheet.get("issue")
        if project == OTHER and sheet.get("archived"):
            continue
        if project != OTHER and isinstance(n, int) and n > 0:
            get(project, str(n), n).sheets.append(sheet)
        elif (project, sheet.get("topic")) in topics or not sheet.get("archived"):
            get(project, str(sheet.get("topic")), None).sheets.append(sheet)
    now = data["now"]
    for s in alive_sessions(data):
        where = sessions.locate(s.get("cwd", ""), data.get("projects", {}))
        if where and where[1]:
            project, key, n = where
            get(project, key, n).sessions.append(sessions.session_view(s, now))
    return topics


def branch_topic(project: str, pr: dict, topics: dict[tuple[str, str], Topic]) -> str | None:
    """番号のない PR を、ブランチ名と同じキーの記録に寄せる(chore/fix-readme → fix-readme)。"""
    head = str(pr.get("headRefName") or "")
    for candidate in (records.sanitize_key(head), records.sanitize_key(head.split("/", 1)[-1])):
        if candidate and (project, candidate) in topics:
            return candidate
    return None


def alive_sessions(data: dict) -> list[dict]:
    """生きている対話のセッション。新しい順。"""
    live = [s for s in data.get("sessions", []) if s.get("alive") and s.get("kind", "interactive") == "interactive"]
    return sorted(live, key=lambda s: -(s.get("statusUpdatedAt") or s.get("updatedAt") or 0))


def status_of(stage: str) -> str:
    """絞り込みの札の分類: 完了 / 未着手 / 進行中。"""
    if stage == stages.DONE:
        return "done"
    return "todo" if stage == stages.TODO else "active"


def build_row(t: Topic, usage_by_sid: dict[str, dict], now: float, grill_base: str = "/grill/") -> dict:
    stage = rows.record_stage(t) or rows.fallback_stage(t)
    title = rows.title_of(t)
    return {
        "id": f"{t.project or '_other'}/{t.key}",
        "project": t.project or None,
        "topic": t.key,
        "issue": t.issue,
        "title": title,
        "stage": stage,
        "stage_label": stages.LABELS[stage],
        "stage_index": stages.ORDER[stage],
        "status": status_of(stage),
        "mismatch": rows.mismatch(t),
        "my_turn": rows.my_turn(t),
        "session": t.sessions[0] if t.sessions else None,
        "context": usage.context_of(usage_by_sid.get(t.sessions[0]["session_id"]), now) if t.sessions else None,
        "started": rows.started_at(t),
        "latest": detail.latest_report(t.records),
        "links": detail.links(t, grill_base),
        "history": detail.history(t.records),
        "artifacts": detail.artifacts(t, grill_base),
        "focus": detail.focus(t, grill_base),
        "drafts": [{"draft_id": d["draft_id"], "kind": d["kind"], "label": rows.DRAFT_KINDS[d["kind"]],
                    "title": str(d.get("title", ""))} for d in rows.pending_drafts(t.records)],
    }


def sort_key(row: dict) -> tuple:
    """R3: 完了 → 番号のない進行中 → 番号のある行(番号順)。終わった番号のない行は完了の側。"""
    numbered = row["issue"] is not None
    if row["status"] == "done":
        return (0, 0 if numbered else 1, row["issue"] or 0, row["started"], row["topic"])
    if not numbered:
        return (1, 0, 0, row["started"], row["topic"])
    return (2, 0, row["issue"], "", row["topic"])


def tab_notes(project: str, data: dict) -> list[str]:
    doc = data.get("gh", {}).get(project)
    if isinstance(doc, dict) and doc.get("error"):
        return [f"GitHub の一覧を取れない: {doc['error']}"]
    if isinstance(doc, dict) and doc.get("loading"):
        return ["GitHub の一覧を読み込んでいる"]
    return []


def build_tab(project: str, rs: list[dict], notes: list[str] | None = None) -> dict:
    ordered = sorted(rs, key=sort_key)
    first_active = next((i for i, r in enumerate(ordered) if r["status"] != "done"), None)
    counts = {k: sum(1 for r in ordered if r["status"] == k) for k in ("active", "todo", "done")}
    return {
        "project": project or None,
        "label": project or OTHER_LABEL,
        "rows": ordered,
        "first_active": first_active,
        "my_turn": sum(1 for r in ordered if r["my_turn"]),
        "counts": counts,
        "notes": notes or [],
        "hub": None,  # 設定のあるプロジェクトだけ、compose が中心の 1 行を入れる
    }


OTHERS_TOP = 3  # 上の帯に名前を出す数


def other_sessions(data: dict, shown: set[str], usage_by_sid: dict[str, dict]) -> dict | None:
    """表に出ていない、生きているセッションのうち、使用量の値があるもの。

    上の帯には件数と、使用率の高い順に 3 件までを出し、残りは「ほか n 件」にまとめる。
    値が 1 件も無ければ None(帯にこの欄を出さない)。
    """
    now = data["now"]
    out = []
    for s in alive_sessions(data):
        view = sessions.session_view(s, now)
        if view["session_id"] in shown:
            continue
        context = usage.context_of(usage_by_sid.get(view["session_id"]), now)
        if context is None:
            continue
        where = sessions.locate(s.get("cwd", ""), data.get("projects", {}))
        out.append({
            "name": view["name"] or view["session_id"][:8],
            "project": where[0] if where else None,
            "state": view["state"],
            "label": view["label"],
            "context": context,
        })
    if not out:
        return None
    ordered = sorted(out, key=lambda x: (-x["context"]["pct"], x["name"]))
    rest = ordered[OTHERS_TOP:]
    return {
        "count": len(ordered),
        "top": ordered[:OTHERS_TOP],
        "rest": rest,
        "rest_label": f"ほか {len(rest)} 件" if rest else None,
    }


def compose(data: dict) -> dict:
    topics = _gather(data)
    now = data["now"]
    usage_docs = data.get("usage", [])
    usage_by_sid = usage.latest_by_session(usage_docs)
    by_project: dict[str, list[dict]] = {p: [] for p in data.get("projects", {})}
    shown: set[str] = set()
    configured = data.get("projects", {})
    for (project, _), t in topics.items():
        row = build_row(t, usage_by_sid, now, data.get("grill_base", "/grill/"))
        row["child_start"] = hub.child_button(row, configured.get(project), data.get("worktrees", {}).get(project, []),
                                              hub.is_starting(data, project, now, row["issue"]))
        by_project.setdefault(project, []).append(row)
        shown.update(s["session_id"] for s in t.sessions[:1])
    names = sorted(p for p, rs in by_project.items()
                   if p != OTHER and (p in configured or any(r["status"] != "done" for r in rs)))
    tabs = [build_tab(p, by_project[p], tab_notes(p, data)) for p in names]
    alive = alive_sessions(data)
    grill_base = data.get("grill_base", "/grill/")
    for tab in tabs:
        conf = configured.get(tab["project"])
        tab["hub"] = hub.hub_view(tab["project"], conf, data, alive,
                                  lambda t: build_row(t, usage_by_sid, now, grill_base)) if conf is not None else None
        if tab["hub"] and tab["hub"]["row"]["session"]:
            shown.add(tab["hub"]["row"]["session"]["session_id"])
    if by_project.get(OTHER):
        tabs.append(build_tab(OTHER, by_project[OTHER]))
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "limits": usage.limits(usage_docs, now),
        "other_sessions": other_sessions(data, shown, usage_by_sid),
        "my_turn": sum(t["my_turn"] for t in tabs),
        "tabs": tabs,
    }
