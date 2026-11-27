#!/usr/bin/env python3
"""見本データ: 架空のプロジェクトの記録・質問票・GitHub の一覧・セッション・使用量を一時フォルダに作る。

  python3 demo_data.py <フォルダ>

作るもの(demo.sh がこの置き場所を環境変数で board に渡す):
  devflow/records/ devflow/usage/   記録と使用量(BOARD_ROOT)
  sessions/                         セッション一覧(BOARD_SESSIONS_DIR)
  grill/                            質問票(demo_grill.py が配信する)
  gh.json                           GitHub の一覧の見本(BOARD_GH_FIXTURE)
  config.json                       設定(BOARD_CONFIG)
セッションの pid には 1 番(いつも生きている)を使い、生きているセッションに見せる。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

NOW = time.time()
WORK = "/srv/demo-work"   # 架空の作業フォルダ(実在しなくてよい)


def ts(minutes_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(NOW - minutes_ago * 60))


def write_json(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def write_records(root: Path, project: str, topic: str, lines: list[dict]) -> None:
    path = root / "devflow" / "records" / project / f"{topic}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")


def step(stage: str, ago: float, **kw) -> dict:
    return {"ts": ts(ago), "kind": "step", "stage": stage, **kw}


def report(text: str, ago: float, **kw) -> dict:
    return {"ts": ts(ago), "kind": "report", "text": text, **kw}


PR_BODY = """## 変更
- 表をまとめて 1 冊のブックに書き出す
- 書き出しの設定を保存する

## テスト
- 書き出しのテスト 12 件が通る

Closes #49"""


def records(root: Path) -> None:
    write_records(root, "sample_app", "35", [
        step("plan", 300, issue=35), report("計画の質問票を出した", 299, issue=35),
        step("spec", 200, issue=35), step("ticket", 150, issue=35),
        step("test_review", 40, issue=35), report("ルール 9 件の質問票を出した", 25, issue=35)])
    write_records(root, "sample_app", "49", [
        step("plan", 900, issue=49), step("spec", 700, issue=49), step("test_review", 600, issue=49),
        step("briefing", 400, issue=49), step("implement", 300, issue=49), step("review", 20, issue=49),
        report("PR 案を送った。CI 待ち", 4, issue=49, links={"プレビュー": "http://127.0.0.1:5173/"}),
        {"ts": ts(4), "kind": "pr_draft", "draft_id": "a1b2c3d4e5f6", "title": "feat: 表を 1 冊のブックにまとめて書き出す",
         "body": PR_BODY, "issue": 49}])
    write_records(root, "sample_app", "52", [
        step("plan", 15, issue=52), report("計画の質問票を作っている", 2, issue=52)])
    write_records(root, "sample_app", "fix-readme", [
        step("review", 30, title="README の誤字を直す"), report("PR 案を送った", 8),
        {"ts": ts(8), "kind": "pr_draft", "draft_id": "0f9e8d7c6b5a", "title": "docs: README の誤字を直す",
         "body": "## 変更\n- 手順の誤字を 3 か所直す"}])
    write_records(root, "sample_app", "30", [step("done", 3000, issue=30)])
    write_records(root, "notes_site", "8", [
        step("plan", 500, issue=8, title="タグで絞り込む"), step("spec", 300, issue=8),
        step("briefing", 50, issue=8),
        report("実装前の説明を出した", 45, issue=8, links={"実装前の説明": "http://127.0.0.1:8787/demo-brief-tags.html"})])
    write_records(root, "notes_site", "dark-theme", [
        step("implement", 90, title="暗い配色を足す"), {"ts": ts(12), "kind": "stuck", "text": "配色のトークンが 2 か所にある"}])


def github(root: Path) -> None:
    def issue(n: int, title: str, state: str = "OPEN") -> dict:
        return {"number": n, "title": title, "state": state, "url": f"https://github.com/example/sample_app/issues/{n}"}

    write_json(root / "gh.json", {"sample_app": {
        "issues": [issue(30, "用語の一覧を見る", "CLOSED"), issue(31, "差分の表示", "CLOSED"), issue(35, "セルの編集"),
                   issue(49, "1 冊のブックにまとめる"), issue(52, "印刷の余白"), issue(53, "列幅をそろえる"),
                   issue(54, "書き出しの形式を増やす")],
        "prs": [{"number": 60, "title": "feat: 差分の表示", "state": "MERGED", "headRefName": "feat/#31-diff", "body": "",
                 "url": "https://github.com/example/sample_app/pull/60"},
                {"number": 61, "title": "docs: README の誤字", "state": "OPEN", "headRefName": "chore/fix-readme",
                 "body": "", "url": "https://github.com/example/sample_app/pull/61"}],
    }})


def sheet_html(topic: str, title: str) -> str:
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>{title}</title>
<style>body{{background:#1c1a17;color:#ebe6dc;font-family:"IBM Plex Sans JP",sans-serif;padding:24px;line-height:1.6}}
.q{{border:1px solid #3a3730;border-radius:8px;padding:16px;margin:12px 0}}label{{display:block;margin:6px 0}}
button{{background:#e27a52;color:#1c1a17;border:0;border-radius:6px;padding:8px 16px;font-weight:600;cursor:pointer}}
button:focus-visible{{outline:2px solid #e27a52;outline-offset:2px}}img{{max-width:240px;border-radius:6px}}</style></head>
<body><h1 style="font-size:18px">{title}</h1><p>見本の質問票(demo)。board の中継ごしに開いている。</p>
<div class="q"><b>Q1 書き出しの形式はどれにするか</b>
<label><input type="radio" name="q1" value="a" checked> 1 冊のブック</label>
<label><input type="radio" name="q1" value="b"> シートごとのファイル</label>
<img src="assets/{topic}/fig.svg" alt="見本の図"></div>
<button id="go" type="button">送信</button> <span id="st"></span>
<script>document.getElementById("go").onclick=function(){{fetch("/submit",{{method:"POST",headers:{{"Content-Type":"application/json"}},
body:JSON.stringify({{topic:"{topic}",round:1,answers:{{q1:document.querySelector("input:checked").value}}}})}})
.then(function(r){{document.getElementById("st").textContent=r.ok?"送信した":"送れなかった";
window.parent.postMessage({{type:"grill-submitted",topic:"{topic}",round:1}},location.origin);}});}};</script></body></html>"""


def grill(root: Path) -> None:
    g = root / "grill"
    topics = [
        ("35-cell-edit-rules", "#35 セルの編集 — テストレビュー", "test-review", "sample_app", 35, "waiting"),
        ("49-export-plan", "#49 1 冊のブックにまとめる — 計画", "計画", "sample_app", 49, "done"),
        ("52-print-margin-plan", "#52 印刷の余白 — 計画", "計画", "sample_app", 52, "answered"),
        ("sample-next-version", "次の版で何を作るかの相談", "計画", "sample_app", None, "waiting"),
        ("naming-ideas", "名前の候補", None, None, None, "waiting"),
    ]
    state = []
    for topic, title, kind, project, issue, st in topics:
        (g / f"grill-{topic}.html").parent.mkdir(parents=True, exist_ok=True)
        (g / f"grill-{topic}.html").write_text(sheet_html(topic, title), encoding="utf-8")
        fig = g / "assets" / topic / "fig.svg"
        fig.parent.mkdir(parents=True, exist_ok=True)
        fig.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="60"><rect width="240" height="60" '
                       'rx="6" fill="#24221e" stroke="#e27a52"/><text x="16" y="36" fill="#ebe6dc" font-size="14">'
                       'fig</text></svg>', encoding="utf-8")
        state.append({"topic": topic, "title": title, "kind": kind, "project": project, "issue": issue, "state": st,
                      "open_round": None if st == "done" else 1, "updated_at": ts(30), "version": "1",
                      "html_exists": True, "archived": False, "error": None})
    write_json(g / "state.json", {"generated_at": ts(0), "topics": state})
    brief = sheet_html("plan-tags", "実装前の説明: タグで絞り込む").replace(
        '<img src="assets/plan-tags/fig.svg" alt="見本の図">', "")
    (g / "demo-brief-tags.html").write_text(brief, encoding="utf-8")


def sessions_and_usage(root: Path) -> None:
    stat = Path("/proc/1/stat").read_text()
    start = stat.rsplit(")", 1)[-1].split()[19]

    def sess(name: str, cwd: str, status: str, ago: float, **kw) -> dict:
        ms = int((NOW - ago * 60) * 1000)
        return {"pid": 1, "procStart": start, "sessionId": f"demo-{name}", "cwd": cwd, "name": name,
                "kind": "interactive", "status": status, "updatedAt": ms, "statusUpdatedAt": ms, **kw}

    wt = f"{WORK}/sample_app/.claude/worktrees"
    docs = [
        sess("sample-35", f"{wt}/35-cell-edit", "idle", 25),
        sess("sample-49", f"{wt}/49-export-book", "idle", 3),
        sess("sample-52", f"{wt}/52-print-margin", "busy", 0),
        sess("sample-fix-readme", f"{wt}/fix-readme", "waiting", 8, waitingFor="permission prompt: Bash(git push)"),
        sess("sample_app_hub", f"{WORK}/sample_app", "idle", 2),
        sess("notes-8", f"{WORK}/notes_site/.claude/worktrees/8-tags", "idle", 44),
        sess("scratch", f"{WORK}/scratch", "busy", 0),
    ]
    for d in docs:
        write_json(root / "sessions" / f"{d['sessionId']}.json", d)
    pcts = {"sample-35": 44, "sample-49": 72, "sample-52": 12, "sample-fix-readme": 21, "sample_app_hub": 35,
            "notes-8": 58, "scratch": 71}
    for i, (name, pct) in enumerate(pcts.items()):
        write_json(root / "devflow" / "usage" / f"demo-{name}.json", {
            "written_at": NOW - (i + 1) * 60, "session_id": f"demo-{name}",
            "context_window": {"used_percentage": pct, "context_window_size": 1000000},
            "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": NOW + 3 * 3600},
                            "seven_day": {"used_percentage": 61, "resets_at": NOW + 3 * 86400}},
            "model": {"display_name": "Opus"}, "cwd": WORK})


def config(root: Path) -> None:
    write_json(root / "config.json", {
        "wrapper_glob": str(root / "no-wrappers" / "*-parallel.sh"),
        "projects": {
            "sample_app": {"path": f"{WORK}/sample_app", "hub": "sample_app_hub", "repo": "example/sample_app"},
            "notes_site": {"path": f"{WORK}/notes_site", "github": False},
        },
    })


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    root = Path(argv[0])
    for build in (records, github, grill, sessions_and_usage, config):
        build(root)
    print(f"demo data: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
