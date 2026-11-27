"""中心と子を始める部品(差し替え可能)。画面からの要求の文字列をコマンドとして実行しない。

  中心 … 設定の hub_command か、自動で見つけた起動スクリプト(~/bin/<名前>-hub.sh)を、
          そのプロジェクトの tmux セッションの「hub」窓で動かす。名前は --name <PARALLEL_HUB> で付ける
  子   … 並列運用のラッパー(~/bin/<名前>-parallel.sh)に <番号>-<slug>[@fix] を 1 つ渡す

どちらも引数の配列で渡し、シェルを介さない(tmux 3 以降の new-window は複数の引数をそのまま実行する)。
テストと見本(demo)では偽物の launcher を使い、実物を起動しない。
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import hub

SLUG_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?")
SESSION_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_ISSUE = 999_999
CHILD_TIMEOUT = 180
OUTPUT_TAIL_LINES = 20
OUTPUT_TAIL_CHARS = 2000

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class HubPlan:
    session: str
    window: str
    cwd: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class ChildPlan:
    wrapper: str
    arg: str
    cwd: str


@dataclass(frozen=True)
class Result:
    ok: bool
    code: int | None
    output: str

    def to_dict(self) -> dict:
        return asdict(self)


def tail(text: str) -> str:
    """長い出力は末尾だけ(行数と文字数の両方で切る)。"""
    lines = (text or "").rstrip().splitlines()[-OUTPUT_TAIL_LINES:]
    return "\n".join(lines)[-OUTPUT_TAIL_CHARS:]


def hub_plan(project: str, conf: dict) -> HubPlan:
    """中心の起動の段取り。名前・コマンド・tmux セッションの検査に落ちたら ValueError。"""
    name = conf.get("hub")
    if not isinstance(name, str) or not name.strip() or "\n" in name:
        raise ValueError("中心の名前(PARALLEL_HUB)が分からない")
    argv = hub.hub_command(conf)
    if not argv:
        raise ValueError("起動スクリプトが無い")
    if argv[0].startswith("-"):
        raise ValueError("起動コマンドの先頭が - で始まっている")
    session = hub.tmux_session(project, conf)
    if not SESSION_RE.fullmatch(session):
        raise ValueError(f"tmux のセッション名に使えない文字がある: {session!r}")
    cwd = str(conf.get("path") or Path.home())
    return HubPlan(session=session, window=hub.HUB_WINDOW, cwd=cwd, argv=(*argv, "--name", name))


def child_arg(issue: object, slug: object, fix: object) -> str:
    """ラッパーに渡す 1 つの引数 <番号>-<slug>[@fix]。値は検査してから組み立てる。"""
    if isinstance(issue, bool) or not isinstance(issue, int) or not 1 <= issue <= MAX_ISSUE:
        raise ValueError("issue 番号が正しくない")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError("slug は英数字とハイフンだけ(40 文字まで、先頭と末尾は英数字)")
    if not isinstance(fix, bool):
        raise ValueError("種類(fix)は true か false")
    return f"{issue}-{slug}" + ("@fix" if fix else "")


def child_plan(conf: dict, issue: object, slug: object, fix: object) -> ChildPlan:
    wrapper = conf.get("wrapper")
    if not isinstance(wrapper, str) or not wrapper:
        raise ValueError("並列運用のラッパーが無い")
    return ChildPlan(wrapper=wrapper, arg=child_arg(issue, slug, fix), cwd=str(conf.get("path") or Path.home()))


class TmuxLauncher:
    """実物を起動する部品。runner を差し替えればテストで偽物にできる。"""

    def __init__(self, runner: Runner = subprocess.run):
        self.runner = runner

    def _run(self, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        return self.runner(cmd, capture_output=True, text=True, timeout=timeout, check=False)

    def start_hub(self, plan: HubPlan) -> Result:
        target = f"={plan.session}"
        try:
            has = self._run(["tmux", "has-session", "-t", target], 5)
            if has.returncode == 0:
                cmd = ["tmux", "new-window", "-d", "-t", f"{target}:", "-n", plan.window, "-c", plan.cwd, *plan.argv]
            else:
                cmd = ["tmux", "new-session", "-d", "-s", plan.session, "-n", plan.window, "-c", plan.cwd, *plan.argv]
            res = self._run(cmd, 10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Result(False, None, f"tmux を動かせない: {type(exc).__name__}")
        return Result(res.returncode == 0, res.returncode, tail((res.stdout or "") + (res.stderr or "")))

    def start_child(self, plan: ChildPlan) -> Result:
        try:
            res = self.runner([plan.wrapper, plan.arg], capture_output=True, text=True, timeout=CHILD_TIMEOUT,
                              cwd=plan.cwd if Path(plan.cwd).is_dir() else None, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Result(False, None, f"ラッパーを動かせない: {type(exc).__name__}")
        return Result(res.returncode == 0, res.returncode, tail((res.stdout or "") + (res.stderr or "")))
