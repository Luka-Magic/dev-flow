#!/usr/bin/env python3
"""flow: dev-flow の記録に 1 件足す。

  flow step <段階>             段階が変わった(計画 / 仕様 / … / レビュー / 完了)
  flow report "<1 行>"         報告(--link 名前=URL で成果物やプレビューを添えられる)
  flow stuck "<理由>"          詰まった
  flow pr-draft <ファイル>     PR 案(1 行目がタイトル、残りが本文)
  flow issue-draft <ファイル>  issue 案(同じ形)

プロジェクトと題材は --project / --topic で渡すか、作業フォルダから決める:
  プロジェクト … BOARD_PROJECT → git の共通ディレクトリ(worktree でも本体)の親フォルダ名
  題材         … BOARD_TOPIC → ブランチ名の #N → worktree のフォルダ名の先頭の番号 → ブランチ名
置き場所は BOARD_ROOT(既定 ~/.agent/devflow)。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import records
import stages
from records import LEADING_NUMBER_RE, sanitize_key

MAX_TEXT = 500
MAX_DRAFT_BYTES = 200_000
ISSUE_IN_BRANCH_RE = re.compile(r"#(\d{1,6})(?!\d)")


def _git(cwd: Path, *args: str) -> str:
    try:
        res = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.strip() if res.returncode == 0 else ""


def detect_project(cwd: Path, env: dict[str, str]) -> str:
    if env.get("BOARD_PROJECT"):
        return env["BOARD_PROJECT"]
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        return sanitize_key(Path(common).parent.name)
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return sanitize_key(Path(top).name) if top else ""


def topic_from(branch: str, worktree_name: str) -> tuple[str, int | None]:
    """ブランチ名・worktree のフォルダ名から (題材のキー, issue 番号)。"""
    m = ISSUE_IN_BRANCH_RE.search(branch)
    if m:
        return m.group(1), int(m.group(1))
    m = LEADING_NUMBER_RE.match(worktree_name)
    if m:
        return m.group(1), int(m.group(1))
    return sanitize_key(branch.replace("/", "-")), None


def detect_topic(cwd: Path, env: dict[str, str]) -> tuple[str, int | None]:
    if env.get("BOARD_TOPIC"):
        topic = env["BOARD_TOPIC"]
        m = LEADING_NUMBER_RE.match(topic)
        return topic, (int(m.group(1)) if m and topic.isdigit() else None)
    branch = _git(cwd, "branch", "--show-current")
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return topic_from(branch, Path(top).name if top else "")


def read_draft(path: str) -> dict:
    """PR 案・issue 案のファイル。1 行目がタイトル(先頭の # は取る)、残りが本文。"""
    data = Path(path).read_bytes()
    if len(data) > MAX_DRAFT_BYTES:
        raise ValueError(f"案のファイルが大きすぎる({len(data)} バイト)")
    text = data.decode("utf-8")
    first, _, rest = text.lstrip().partition("\n")
    title = first.lstrip("#").strip()
    if not title:
        raise ValueError("案の 1 行目(タイトル)が空")
    draft_id = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return {"draft_id": draft_id, "title": title, "body": rest.strip("\n")}


def one_line(text: str) -> str:
    line = " ".join(text.split())
    if not line:
        raise ValueError("文が空")
    return line[:MAX_TEXT]


def parse_links(values: list[str] | None) -> dict[str, str]:
    links: dict[str, str] = {}
    for v in values or []:
        name, sep, url = v.partition("=")
        if not sep or not name.strip() or not url.strip():
            raise ValueError(f"--link は 名前=URL の形: {v!r}")
        links[name.strip()] = url.strip()
    return links


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flow", description="dev-flow の記録に 1 件足す")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--project", help="プロジェクト名(既定: 作業フォルダから)")
        sp.add_argument("--topic", help="題材のキー(既定: ブランチ名の #N など)")
        sp.add_argument("--issue", type=int, help="issue 番号(既定: 題材のキーから)")

    sp = sub.add_parser("step", help="段階が変わった")
    sp.add_argument("stage")
    sp.add_argument("--title", help="題(issue の無い題材で表に出す名前)")
    common(sp)
    sp = sub.add_parser("report", help="報告(1 行)")
    sp.add_argument("text")
    sp.add_argument("--link", action="append", metavar="名前=URL", help="成果物・プレビューの URL")
    common(sp)
    sp = sub.add_parser("stuck", help="詰まった")
    sp.add_argument("text")
    common(sp)
    for name in ("pr-draft", "issue-draft"):
        sp = sub.add_parser(name, help=f"{name.split('-')[0].upper()} 案(1 行目がタイトル)")
        sp.add_argument("file")
        common(sp)
    return p


def build_entry(args: argparse.Namespace) -> dict:
    if args.cmd == "step":
        entry = {"kind": "step", "stage": stages.normalize(args.stage)}
        return {**entry, "title": one_line(args.title)} if args.title else entry
    if args.cmd == "report":
        entry = {"kind": "report", "text": one_line(args.text)}
        links = parse_links(args.link)
        return {**entry, "links": links} if links else entry
    if args.cmd == "stuck":
        return {"kind": "stuck", "text": one_line(args.text)}
    kind = "pr_draft" if args.cmd == "pr-draft" else "issue_draft"
    return {"kind": kind, **read_draft(args.file)}


def main(argv: list[str] | None = None, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    args = build_parser().parse_args(argv)
    try:
        project = args.project or detect_project(cwd, env)
        topic, issue = (args.topic, None) if args.topic else detect_topic(cwd, env)
        if args.topic and args.topic.isdigit():
            issue = int(args.topic)
        if args.issue is not None:
            issue = args.issue
        if not project or not topic:
            raise ValueError("プロジェクトか題材が決まらない。--project と --topic で渡してください")
        entry = build_entry(args)
        if issue is not None:
            entry = {**entry, "issue": issue}
        if env.get("BOARD_BY"):
            entry = {**entry, "by": env["BOARD_BY"]}
        root = Path(env.get("BOARD_ROOT") or records.DEFAULT_ROOT).expanduser()
        records.append(root, project, topic, entry)
    except (ValueError, OSError) as exc:
        print(f"flow: {exc}", file=sys.stderr)
        return 2
    print(f"flow: {project}/{topic} に {entry['kind']} を記録した")
    return 0


if __name__ == "__main__":
    sys.exit(main())
