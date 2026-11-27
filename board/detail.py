"""1 行の詳しい中身: 最新の報告・報告の履歴・リンク・成果物・今見るもの(純粋関数)。"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import stages
from rows import (
    DRAFT_KINDS,
    Topic,
    briefing_link,
    pending_drafts,
    record_links,
    waiting_sheets,
)

HISTORY_MAX = 200
PREVIEW_WORDS = ("プレビュー", "preview")
PAGE_PATH_RE = re.compile(r"^/([A-Za-z0-9][A-Za-z0-9._-]*\.html)$")


def sheet_url(sheet: dict, grill_base: str) -> str:
    return f"{grill_base}grill-{sheet.get('topic')}.html"


def embed_url(url: str, grill_base: str) -> str:
    """質問票と同じ置き場所のページ(/<名前>.html)は、board の中継(grill_base)ごしの URL にする。"""
    path = urlsplit(url).path
    m = PAGE_PATH_RE.match(path)
    return f"{grill_base}{m.group(1)}" if m else url


def latest_report(lines: list[dict]) -> str | None:
    for line in reversed(lines):
        if line.get("kind") in ("report", "stuck") and line.get("text"):
            prefix = "詰まった: " if line["kind"] == "stuck" else ""
            return prefix + str(line["text"])
    return None


def history_text(line: dict) -> str | None:
    kind = line.get("kind")
    if kind == "step":
        return f"段階: {stages.LABELS.get(str(line.get('stage')), line.get('stage'))}"
    if kind == "report":
        return str(line.get("text", ""))
    if kind == "stuck":
        return f"詰まった: {line.get('text', '')}"
    if kind in DRAFT_KINDS:
        return f"{DRAFT_KINDS[kind]}: {line.get('title', '')}"
    if kind == "approve":
        return f"承認した: {line.get('title') or line.get('draft_id', '')}"
    if kind == "sent":
        how = {"courier": "配達係で届いた", "tmux": "tmux で届いた"}.get(str(line.get("via")))
        tail = how or f"届かなかった: {line.get('error', '')}"
        return f"送った: {line.get('text', '')}({tail})"
    return None


def history(lines: list[dict]) -> list[dict]:
    """報告の履歴。新しい順、1 行ずつ。"""
    out = []
    for line in reversed(lines[-HISTORY_MAX:]):
        text = history_text(line)
        if text:
            out.append({"ts": str(line.get("ts", "")), "kind": str(line.get("kind")), "text": " ".join(text.split())})
    return out


def _main_pr(t: Topic) -> dict | None:
    open_prs = [p for p in t.prs if str(p.get("state", "")).upper() == "OPEN"]
    pool = open_prs or t.prs
    return max(pool, key=lambda p: p.get("number") or 0) if pool else None


def links(t: Topic, grill_base: str) -> list[dict]:
    """リンクの欄: 質問票(回答待ちを優先し、無ければ最新)・issue・PR・プレビュー のうち、あるもの。"""
    out = []
    sheets = waiting_sheets(t) or sorted(t.sheets, key=lambda s: str(s.get("updated_at", "")))[-1:]
    if sheets and sheets[0].get("html_exists", True):
        out.append({"label": "質問票", "url": sheet_url(sheets[0], grill_base)})
    if t.gh_issue and t.gh_issue.get("url"):
        out.append({"label": "issue", "url": str(t.gh_issue["url"])})
    pr = _main_pr(t)
    if pr and pr.get("url"):
        out.append({"label": "PR", "url": str(pr["url"])})
    previews = [url for name, url, _ in record_links(t.records) if any(w in name.lower() for w in PREVIEW_WORDS)]
    if previews:
        out.append({"label": "プレビュー", "url": previews[-1]})
    return out


def artifacts(t: Topic, grill_base: str) -> list[dict]:
    """成果物の一覧(段階ごと): 質問票・記録に添えた URL・PR。"""
    by_stage: dict[str, list[dict]] = {}
    for sheet in sorted(t.sheets, key=lambda s: str(s.get("updated_at", ""))):
        stage = stages.from_grill_kind(sheet.get("kind")) or "plan"
        by_stage.setdefault(stage, []).append({"label": str(sheet.get("title") or sheet.get("topic")),
                                               "url": sheet_url(sheet, grill_base)})
    for name, url, stage in record_links(t.records):
        if any(w in name.lower() for w in PREVIEW_WORDS):
            continue
        by_stage.setdefault(stage if stage in stages.ORDER else "plan", []).append({"label": name, "url": url})
    for pr in sorted(t.prs, key=lambda p: p.get("number") or 0):
        if pr.get("url"):
            by_stage.setdefault("review", []).append({"label": f"PR #{pr.get('number')}", "url": str(pr["url"])})
    return [{"stage": k, "stage_label": stages.LABELS[k], "items": by_stage[k]}
            for k in stages.ORDER if k in by_stage]


def focus(t: Topic, grill_base: str) -> dict | None:
    """今見るもの: 確認の選択肢 → 回答待ちの質問票 → 実装前の説明 → 承認待ちの案。"""
    if t.sessions and t.sessions[0]["state"] == "confirm":
        return {"type": "confirm", "text": t.sessions[0].get("asking") or "確認の選択肢で止まっている"}
    sheets = waiting_sheets(t)
    if sheets:
        return {"type": "page", "title": str(sheets[0].get("title") or ""), "url": sheet_url(sheets[0], grill_base)}
    brief = briefing_link(t)
    if brief:
        return {"type": "page", "title": "実装前の説明", "url": embed_url(brief, grill_base)}
    drafts = pending_drafts(t.records)
    if drafts:
        d = drafts[0]
        return {"type": "draft", "draft_kind": d["kind"], "label": DRAFT_KINDS[d["kind"]], "draft_id": d["draft_id"],
                "title": str(d.get("title", "")), "body": str(d.get("body", ""))}
    return None
