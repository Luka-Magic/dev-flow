"""集め役: 合成(compose.py)に渡す材料を外から集める。テストでは使わず、見本の dict を直接渡す。

  記録       … <BOARD_ROOT>/records/
  質問票     … grill-visual の GET /api/state(HTTP)
  GitHub     … gh issue list / gh pr list(短時間キャッシュし、裏で取り直す)
  セッション … ~/.claude/sessions/*.json(生きているかは /proc で確かめる)と、tmux の窓の表示
  使用量     … <BOARD_ROOT>/usage/*.json(statusline_tee.py が書き出す)
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import config
import records
import sessions

GH_TTL = 60.0
GH_TIMEOUT = 20
GRILL_TIMEOUT = 2.0
ISSUE_FIELDS = "number,title,state,url"
PR_FIELDS = "number,title,state,url,headRefName,body,isDraft"
DEFAULT_SESSIONS_DIR = Path.home() / ".claude" / "sessions"


def read_json_files(folder: Path) -> list[dict]:
    out = []
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


def proc_alive(pid: object, proc_start: object) -> bool:
    """pid が生きていて、起動時刻(/proc/<pid>/stat の 22 番目)も一致するか。"""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    if not proc_start:
        return True
    fields = stat.rsplit(")", 1)[-1].split()
    return len(fields) > 19 and fields[19] == str(proc_start)


def fetch_grill_state(base: str) -> dict | None:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/state", timeout=GRILL_TIMEOUT) as res:
            doc = json.loads(res.read())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def run_gh(args: list[str], cwd: str | None) -> list[dict]:
    """gh を 1 回動かして JSON の配列を返す。失敗は RuntimeError(理由つき)。"""
    try:
        res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=cwd, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("gh が見つからない") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gh を動かせない: {type(exc).__name__}") from exc
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "gh が失敗した").strip().splitlines()[-1][:200])
    doc = json.loads(res.stdout or "[]")
    if not isinstance(doc, list):
        raise RuntimeError("gh の出力が配列でない")
    return doc


def gh_lists(conf: dict, runner: Callable[[list[str], str | None], list[dict]] = run_gh) -> dict:
    repo = ["-R", conf["repo"]] if conf.get("repo") else []
    cwd = None if repo else conf.get("path")
    if not repo and not (cwd and Path(cwd).is_dir()):
        return {"error": "リポジトリの場所が分からない"}
    try:
        issues = runner(["issue", "list", *repo, "--state", "all", "--limit", "200", "--json", ISSUE_FIELDS], cwd)
        prs = runner(["pr", "list", *repo, "--state", "all", "--limit", "100", "--json", PR_FIELDS], cwd)
    except (RuntimeError, ValueError) as exc:
        return {"error": str(exc)}
    return {"issues": issues, "prs": prs}


class GhCache:
    """gh の結果を短時間持つ。古くなったら裏で取り直し、その間は古い値を返す(画面を待たせない)。"""

    def __init__(self, ttl: float = GH_TTL, fetch: Callable[[dict], dict] = gh_lists):
        self.ttl, self.fetch = ttl, fetch
        self._data: dict[str, tuple[float, dict]] = {}
        self._busy: set[str] = set()
        self._lock = threading.Lock()

    def _refresh(self, name: str, conf: dict) -> None:
        try:
            doc = self.fetch(conf)
        except Exception as exc:  # 取り直しの失敗は表の注記にする(画面は止めない)
            doc = {"error": f"{type(exc).__name__}"}
        with self._lock:
            self._data[name] = (time.time(), doc)
            self._busy.discard(name)

    def get(self, projects: dict[str, dict]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        now = time.time()
        for name, conf in projects.items():
            if conf.get("github") is False or not (conf.get("repo") or conf.get("path")):
                continue
            with self._lock:
                stamp, doc = self._data.get(name, (0.0, {"issues": [], "prs": [], "loading": True}))
                stale = now - stamp > self.ttl and name not in self._busy
                if stale:
                    self._busy.add(name)
            if stale:
                threading.Thread(target=self._refresh, args=(name, conf), daemon=True).start()
            out[name] = doc
        return out


class Collector:
    """実物の材料を集める。設定・置き場所は起動時の環境変数と設定ファイルから決める。"""

    def __init__(self, root: Path, grill_url: str, sessions_dir: Path | None = None,
                 pane_reader: Callable[[str], str] | None = None, gh: GhCache | None = None):
        self.root, self.grill_url = root, grill_url
        self.sessions_dir = sessions_dir or Path(os.environ.get("BOARD_SESSIONS_DIR") or DEFAULT_SESSIONS_DIR)
        self.pane_reader = pane_reader
        self.gh = gh or GhCache()

    def projects(self) -> tuple[dict[str, dict], dict]:
        conf = config.load_config()
        return config.discover_projects(conf), conf

    def sessions(self) -> list[dict]:
        out = []
        for s in read_json_files(self.sessions_dir):
            alive = proc_alive(s.get("pid"), s.get("procStart"))
            pane = None
            target = sessions.tmux_target(s.get("tmux"))
            if alive and self.pane_reader and target:
                pane = self.pane_reader(target)
            out.append({**s, "alive": alive, "pane": pane})
        return out

    def github(self, projects: dict[str, dict]) -> dict[str, dict]:
        """GitHub の一覧。BOARD_GH_FIXTURE(見本の JSON)があれば gh を動かさずにそれを使う(demo.sh 用)。"""
        fixture = os.environ.get("BOARD_GH_FIXTURE")
        if fixture:
            try:
                doc = json.loads(Path(fixture).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {name: {"error": "見本の GitHub の一覧を読めない"} for name in projects}
            return doc if isinstance(doc, dict) else {}
        return self.gh.get(projects)

    def worktrees(self, projects: dict[str, dict]) -> dict[str, list[str]]:
        """プロジェクトごとの作業ツリーのフォルダ名(子を始めるときの slug の初期値に使う)。"""
        out: dict[str, list[str]] = {}
        for name, conf in projects.items():
            root = conf.get("path")
            if not isinstance(root, str) or not root:
                continue
            base = Path(root)
            folders: list[str] = []
            for wt in (conf.get("worktree_dir"), str(base / ".claude" / "worktrees")):
                if isinstance(wt, str) and Path(wt).is_dir():
                    folders.extend(p.name for p in Path(wt).iterdir() if p.is_dir())
            if base.parent.is_dir():  # 旧来の置き場所: リポジトリの隣の <名前>-<番号>-<slug>
                prefix = base.name + "-"
                folders.extend(p.name[len(prefix):] for p in base.parent.glob(prefix + "*") if p.is_dir())
            out[name] = sorted(set(folders))
        return out

    def inputs(self) -> dict:
        projects, conf = self.projects()
        return {
            "now": time.time(),
            "projects": projects,
            "records": records.read_all(self.root),
            "grill": fetch_grill_state(self.grill_url),
            "gh": self.github(projects),
            "sessions": self.sessions(),
            "usage": read_json_files(self.root / "usage"),
            "worktrees": self.worktrees(projects),
            "config_error": conf.get("error"),
        }
