"""R8 指示の配達。"""
from __future__ import annotations

from pathlib import Path

from fakes import FakeCourier, FakeTmux

import actions
import records

TARGET = {"name": "demo-5", "tmux": "%7"}
CONFIRM_PANE = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n"


def test_r8_courier_failure_falls_back_to_tmux_and_send_is_recorded(board_root: Path):
    courier, tmux = FakeCourier(ok=False), FakeTmux()

    result = actions.send_instruction(board_root, "demo", "5", TARGET, "テストを先に直して", courier, tmux)

    assert result == {"delivered": True, "via": "tmux", "error": None}
    assert tmux.sent == [("%7", "テストを先に直して")]
    [entry] = records.read(board_root, "demo", "5")
    assert (entry["kind"], entry["text"], entry["via"]) == ("sent", "テストを先に直して", "tmux")


def test_r8_window_with_confirmation_choices_is_not_typed_into(board_root: Path):
    courier, tmux = FakeCourier(ok=False, error="配達係: 宛先が見つからない"), FakeTmux(pane=CONFIRM_PANE)

    result = actions.send_instruction(board_root, "demo", "5", TARGET, "続けて", courier, tmux)

    assert result["delivered"] is False
    assert result["via"] is None
    assert "確認の選択肢が出ているので tmux では送らない" in result["error"]
    assert tmux.sent == []
    [entry] = records.read(board_root, "demo", "5")
    assert entry["kind"] == "sent" and entry["delivered"] is False


def test_r8_courier_success_is_used_first(board_root: Path):
    courier, tmux = FakeCourier(ok=True), FakeTmux()

    result = actions.send_instruction(board_root, "demo", "5", TARGET, "README も直して", courier, tmux)

    assert result == {"delivered": True, "via": "courier", "error": None}
    assert courier.sent == [("demo-5", "README も直して")]
    assert tmux.sent == []


def test_courier_reads_delivered_line_from_claude_output():
    import subprocess

    import deliver

    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="探しました\nDELIVERED\n", stderr="")

    def failing(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="FAILED: 宛先が無い\n", stderr="")

    assert deliver.Courier(runner=runner, claude="claude-fake").send("demo-5", "a\nb") == deliver.Result(True, "courier", None)
    assert calls[0][:2] == ["claude-fake", "-p"] and "a b" in calls[0][2] and "「demo-5」" in calls[0][2]
    assert deliver.Courier(runner=failing).send("x", "y").error == "配達係: 宛先が無い"


def test_tmux_text_starting_with_dash_is_not_an_option():
    import subprocess

    import deliver

    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    deliver.TmuxSender(runner=runner).send("%7", "-X cancel")

    assert calls[0] == ["tmux", "send-keys", "-t", "%7", "-l", "--", "-X cancel"]
    assert deliver.TmuxSender(runner=runner).send("%7:evil", "a").delivered is False


def test_courier_uses_smallest_model_by_default_and_can_be_changed(monkeypatch):
    import deliver

    monkeypatch.delenv("BOARD_COURIER_MODEL", raising=False)
    default = deliver.Courier(claude="claude-fake").command("demo-5", "a")
    chosen = deliver.Courier(claude="claude-fake", model="sonnet").command("demo-5", "a")
    monkeypatch.setenv("BOARD_COURIER_MODEL", "opus")
    by_env = deliver.Courier(claude="claude-fake").command("demo-5", "a")

    assert default[default.index("--model") + 1] == "haiku"
    assert chosen[chosen.index("--model") + 1] == "sonnet"
    assert by_env[by_env.index("--model") + 1] == "opus"
    assert default[:2] == ["claude-fake", "-p"] and "--allowedTools" in default
