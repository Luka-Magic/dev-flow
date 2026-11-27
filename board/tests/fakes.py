"""配達の偽物(実物のセッションや tmux には触らない)。"""
from __future__ import annotations

from deliver import Result


class FakeCourier:
    def __init__(self, ok: bool, error: str = "宛先が見つからない"):
        self.ok, self.error, self.sent = ok, error, []

    def send(self, name: str, text: str) -> Result:
        self.sent.append((name, text))
        return Result(True, "courier", None) if self.ok else Result(False, None, self.error)


class FakeTmux:
    def __init__(self, pane: str = "> \n"):
        self.pane, self.sent = pane, []

    def pane_text(self, target: str) -> str:
        return self.pane

    def send(self, target: str, text: str) -> Result:
        self.sent.append((target, text))
        return Result(True, "tmux", None)
