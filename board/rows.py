"""題材(表の 1 行)を集めて、1 行分の値を導く(純粋関数)。

題材の見分け方:
  番号のある題材 … issue 番号。記録(issue 欄か数字だけのキー)、issue、PR、質問票の issue をまとめる
  番号のない題材 … 記録のキー、または質問票の topic
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import stages

PR_BRANCH_ISSUE_RE = re.compile(r"(?:^|/)#?(\d{1,6})(?:-|$)")
PR_BODY_ISSUE_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d{1,6})\b", re.IGNORECASE)


def pr_issue(pr: dict) -> int | None:
    """PR がどの issue のものか(ブランチ名の #N か N-、本文の Closes #N)。"""
    m = PR_BRANCH_ISSUE_RE.search(str(pr.get("headRefName") or ""))
    if not m:
        m = PR_BODY_ISSUE_RE.search(str(pr.get("body") or ""))
    return int(m.group(1)) if m else None


@dataclass
class Topic:
    """1 行の材料。合成の途中だけで使う(外には dict で返す)。"""
    project: str
    key: str
    issue: int | None = None
    records: list[dict] = field(default_factory=list)
    gh_issue: dict | None = None
    prs: list[dict] = field(default_factory=list)
    sheets: list[dict] = field(default_factory=list)
    sessions: list[dict] = field(default_factory=list)  # sessions.session_view の値。新しい順


def record_issue(key: str, lines: list[dict]) -> int | None:
    for line in reversed(lines):
        n = line.get("issue")
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return n
    return int(key) if key.isdigit() else None


def last_step(lines: list[dict]) -> str | None:
    for line in reversed(lines):
        if line.get("kind") == "step" and line.get("stage") in stages.ORDER:
            return line["stage"]
    return None


def record_stage(t: Topic) -> str | None:
    """R1: 記録の最後の step が正。記録が無ければ issue の開閉で未着手か完了。"""
    stage = last_step(t.records)
    if stage:
        return stage
    if t.gh_issue is not None:
        return stages.DONE if str(t.gh_issue.get("state", "")).upper() == "CLOSED" else stages.TODO
    return None


def waiting_sheets(t: Topic) -> list[dict]:
    return [s for s in t.sheets if s.get("state") == "waiting"]


DRAFT_KINDS = {"pr_draft": "PR 案", "issue_draft": "issue 案"}


def pending_drafts(lines: list[dict]) -> list[dict]:
    """承認待ちの案。種類ごとに最後の 1 件だけを見る(新しい案が古い案を置き換える)。"""
    approved = {line.get("draft_id") for line in lines if line.get("kind") == "approve"}
    latest: dict[str, dict] = {}
    for line in lines:
        if line.get("kind") in DRAFT_KINDS and isinstance(line.get("draft_id"), str):
            latest[line["kind"]] = line
    return [d for kind, d in sorted(latest.items(), reverse=True) if d["draft_id"] not in approved]


BRIEF_LINK_WORDS = ("実装前の説明", "brief")


def record_links(lines: list[dict]) -> list[tuple[str, str, str | None]]:
    """記録の report に添えた (名前, URL, そのときの段階)。古い順。"""
    out: list[tuple[str, str, str | None]] = []
    stage: str | None = None
    for line in lines:
        if line.get("kind") == "step":
            stage = line.get("stage")
        links = line.get("links")
        if line.get("kind") == "report" and isinstance(links, dict):
            out.extend((str(k), str(v), stage) for k, v in links.items() if isinstance(v, str))
    return out


def briefing_link(t: Topic) -> str | None:
    """段階が「実装前の説明」で、説明文書の URL が記録にあれば、その URL(回答待ちとみなす)。"""
    if last_step(t.records) != "briefing":
        return None
    found = [url for name, url, _ in record_links(t.records) if any(w in name for w in BRIEF_LINK_WORDS)]
    return found[-1] if found else None


def my_turn(t: Topic) -> str | None:
    """R2: 人の操作を待っているなら、その理由を 1 つの短い文で返す。"""
    if any(s["state"] == "confirm" for s in t.sessions[:1]):
        return "確認の選択肢で止まっている"
    sheets = waiting_sheets(t)
    if any(stages.from_grill_kind(s.get("kind")) == "briefing" for s in sheets) or (not sheets and briefing_link(t)):
        return "実装前の説明に答える"
    if sheets:
        return "質問票に答える"
    drafts = pending_drafts(t.records)
    if drafts:
        return f"{DRAFT_KINDS[drafts[0]['kind']]}を承認する"
    return None


def started_at(t: Topic) -> str:
    """題材を始めた時刻(番号のない行の並びに使う)。記録の最初の行、無ければ質問票の更新時刻。"""
    stamps = [str(line.get("ts", "")) for line in t.records[:1]] + [str(s.get("updated_at", "")) for s in t.sheets]
    stamps = [x for x in stamps if x]
    return min(stamps) if stamps else ""


def title_of(t: Topic) -> str:
    """題: issue の題 → 記録の title → 質問票の題 → キー。"""
    if t.gh_issue and t.gh_issue.get("title"):
        return str(t.gh_issue["title"])
    for line in reversed(t.records):
        if line.get("kind") in ("step", "report") and isinstance(line.get("title"), str) and line["title"].strip():
            return line["title"].strip()
    for sheet in t.sheets:
        if sheet.get("title"):
            return str(sheet["title"])
    return t.key


def evidence_stage(t: Topic) -> tuple[str, str] | None:
    """質問票・PR・issue の有無から導ける段階と、その出所。導けなければ None。"""
    if any(str(p.get("state", "")).upper() == "MERGED" for p in t.prs) or (
            t.gh_issue and str(t.gh_issue.get("state", "")).upper() == "CLOSED"):
        return stages.DONE, "issue と PR"
    if any(str(p.get("state", "")).upper() == "OPEN" for p in t.prs):
        return "review", "PR"
    if briefing_link(t) or any(name for name, _, _ in record_links(t.records) if any(w in name for w in BRIEF_LINK_WORDS)):
        return "briefing", "実装前の説明"
    found = [st for st in (stages.from_grill_kind(s.get("kind")) for s in t.sheets) if st]
    if found:
        return max(found, key=lambda k: stages.ORDER[k]), "質問票"
    return None


def mismatch(t: Topic) -> str | None:
    """R6: 記録の段階が、質問票や PR の有無から導ける段階より手前なら、その説明。"""
    recorded = last_step(t.records)
    derived = evidence_stage(t)
    if not recorded or not derived or stages.ORDER[recorded] >= stages.ORDER[derived[0]]:
        return None
    stage, source = derived
    gap = " " if source[-1].isascii() else ""  # 英字の後ろだけ空ける(PR から / 質問票から)
    return f"記録は「{stages.LABELS[recorded]}」だが、{source}{gap}からは「{stages.LABELS[stage]}」まで進んでいる"


def fallback_stage(t: Topic) -> str:
    """記録も issue も無い行(質問票だけ、PR だけ)の段階。質問票が全部終わっていれば完了。"""
    open_pr = any(str(p.get("state", "")).upper() == "OPEN" for p in t.prs)
    if t.sheets and not open_pr and all(s.get("state") == "done" for s in t.sheets):
        return stages.DONE
    derived = evidence_stage(t)
    if derived:
        return derived[0]
    return "plan" if t.sheets else stages.TODO  # 種類の分からない質問票でも、出ていれば計画の段階とみなす
