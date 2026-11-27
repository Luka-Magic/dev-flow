"""配達: 画面からの指示を、宛先のセッションへ届ける部品(差し替え可能)。

本命 … 配達係: `claude -p` の使い捨てセッションが ListAgents で宛先を探し、SendMessage で 1 回送る
予備 … tmux: 宛先の窓に文字を打ち込んで Enter を送る。確認の選択肢が出ている窓には送らない

どちらも外のプロセスを動かすので、テストでは偽物(同じ send を持つもの)を渡す。
"""
from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from sessions import pane_state, valid_pane

MAX_TEXT = 2000
COURIER_TIMEOUT = 180
COURIER_TOOLS = "ListAgents,SendMessage"
DEFAULT_COURIER_MODEL = "sonnet"  # 既定のモデル(利用者の指定)。設定・環境変数で変えられる
COURIER_PARALLEL = 2  # 同時に起動する配達係の上限(連打で claude -p が増えないように)
COURIER_PROMPT = """あなたは配達係です。次の 1 件を届けたら終わります。
1. ListAgents で、名前が「{name}」のセッションを探す。
2. 見つかったら、SendMessage でそのセッションに、下の本文をそのまま 1 回だけ送る。
3. ほかの操作(ファイルの読み書き、コマンドの実行、返事を待つこと)はしない。
本文:
-----
{text}
-----
最後の行に、送れたら DELIVERED、送れなければ FAILED: <理由> とだけ書く。"""

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Result:
    delivered: bool
    via: str | None      # "courier" / "tmux" / None(届かなかった)
    error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


class Sender(Protocol):
    def send(self, target: str, text: str) -> Result: ...


class PaneSender(Sender, Protocol):
    def pane_text(self, target: str) -> str: ...


def clean_text(text: str) -> str:
    """1 行にして長さを抑える(改行は tmux では送信の Enter になってしまうため)。"""
    line = " ".join(str(text).split())
    if not line:
        raise ValueError("送る文が空")
    return line[:MAX_TEXT]


class Courier:
    """配達係。`claude -p` を 1 回起動して、宛先へ SendMessage させる。"""

    def __init__(self, runner: Runner = subprocess.run, claude: str | None = None, timeout: int = COURIER_TIMEOUT,
                 model: str | None = None):
        self.runner = runner
        self.claude = claude or os.environ.get("BOARD_CLAUDE", "claude")
        # モデル: 引数 → BOARD_COURIER_MODEL → sonnet(server.py は環境変数 → 設定の courier_model の順で渡す)
        self.model = model or os.environ.get("BOARD_COURIER_MODEL") or DEFAULT_COURIER_MODEL
        self.timeout = timeout
        self._slots = threading.BoundedSemaphore(COURIER_PARALLEL)

    def command(self, name: str, text: str) -> list[str]:
        prompt = COURIER_PROMPT.format(name=name, text=clean_text(text))
        return [self.claude, "-p", prompt, "--model", self.model, "--allowedTools", COURIER_TOOLS]

    def send(self, target: str, text: str) -> Result:
        if not self._slots.acquire(blocking=False):
            return Result(False, None, "配達係: ほかの配達の途中")
        try:
            res = self.runner(self.command(target, text), capture_output=True, text=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Result(False, None, f"配達係を動かせない: {type(exc).__name__}")
        finally:
            self._slots.release()
        lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
        last = lines[-1] if lines else ""
        if res.returncode == 0 and last == "DELIVERED":
            return Result(True, "courier", None)
        reason = last.removeprefix("FAILED:").strip() if last.startswith("FAILED") else f"終了コード {res.returncode}"
        return Result(False, None, f"配達係: {reason[:200]}")


class TmuxSender:
    """tmux の窓へ文字を打ち込む。宛先は %ペイン。"""

    def __init__(self, runner: Runner = subprocess.run):
        self.runner = runner

    def pane_text(self, target: str) -> str:
        if not valid_pane(target):
            return ""
        try:
            res = self.runner(["tmux", "capture-pane", "-p", "-t", target], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return res.stdout if res.returncode == 0 else ""

    def send(self, target: str, text: str) -> Result:
        if not valid_pane(target):
            return Result(False, None, f"tmux の宛先が正しくない: {target!r}")
        try:  # -- のあとに置き、- で始まる文を tmux のオプションとして読ませない
            typed = self.runner(["tmux", "send-keys", "-t", target, "-l", "--", clean_text(text)],
                                capture_output=True, text=True, timeout=5)
            if typed.returncode != 0:
                return Result(False, None, f"tmux: {(typed.stderr or '').strip()[:200]}")
            entered = self.runner(["tmux", "send-keys", "-t", target, "Enter"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Result(False, None, f"tmux を動かせない: {type(exc).__name__}")
        if entered.returncode != 0:
            return Result(False, None, f"tmux: {(entered.stderr or '').strip()[:200]}")
        return Result(True, "tmux", None)


def deliver(target: dict, text: str, courier: Sender | None, tmux: PaneSender | None) -> Result:
    """R8: 配達係で送り、失敗したら tmux に切り替える。確認の選択肢が出ている窓には tmux で送らない。"""
    name, pane = target.get("name"), target.get("tmux")
    reasons: list[str] = []
    if courier is not None and name:
        first = courier.send(name, text)
        if first.delivered:
            return first
        reasons.append(first.error or "配達係: 届かなかった")
    elif not name:
        reasons.append("宛先のセッション名が無い")
    if tmux is None or not pane:
        reasons.append("tmux の宛先が無い")
        return Result(False, None, " / ".join(reasons))
    if pane_state(tmux.pane_text(pane)) == "confirm":
        reasons.append("確認の選択肢が出ているので tmux では送らない")
        return Result(False, None, " / ".join(reasons))
    return tmux.send(pane, text)
