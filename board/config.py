"""個人の設定(リポジトリの外)と、並列運用のラッパーからのプロジェクトの見つけ方。

設定ファイル: BOARD_CONFIG、無ければ ~/.config/devflow-board/config.json。無くても動く。
  {
    "projects": {"<名前>": {"path": "~/work/<名前>", "hub": "<中心のセッション名>", "repo": "owner/name",
                           "github": true, "worktree_dir": "..."}},
    "wrapper_glob": "~/bin/*-parallel.sh",     並列運用のラッパー(PARALLEL_ROOT などを読む)
    "allowed_hosts": ["<Tailscale の名前>"],    127.0.0.1 / localhost 以外で開くときの名前
    "grill_url": "http://127.0.0.1:8787"
  }
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

from records import KEY_RE

DEFAULT_CONFIG = Path.home() / ".config" / "devflow-board" / "config.json"
DEFAULT_WRAPPER_GLOB = "~/bin/*-parallel.sh"
DEFAULT_HUB_SCRIPT_GLOB = "~/bin/*-hub.sh"
EXPORT_RE = re.compile(r"^\s*export\s+(PARALLEL_[A-Z_]+)=(.*)$", re.MULTILINE)
DEFAULT_IN_VAR_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:-(.*)\}$")
FIELDS = {"PARALLEL_ROOT": "path", "PARALLEL_HUB": "hub", "PARALLEL_SESSION": "tmux_session",
          "PARALLEL_WORKTREE_DIR": "worktree_dir"}


def config_path() -> Path:
    return Path(os.environ.get("BOARD_CONFIG") or DEFAULT_CONFIG).expanduser()


def load_config(path: Path | None = None) -> dict:
    """設定ファイル。無い・壊れているときは空(壊れているときは error に理由)。"""
    path = path or config_path()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        return {"error": f"設定ファイルを読めない: {type(exc).__name__}"}
    return doc if isinstance(doc, dict) else {"error": "設定ファイルの最上位がオブジェクトでない"}


def _unquote(raw: str, home: str) -> str:
    value = raw.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    m = DEFAULT_IN_VAR_RE.match(value)
    if m:  # ${VAR:-既定} は既定の値を使う
        value = m.group(1)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
    return value.replace("${HOME}", home).replace("$HOME", home)


def parse_wrapper(text: str, home: str) -> dict:
    """ラッパーの export 行から {path, hub, tmux_session, worktree_dir}。"""
    out: dict[str, str] = {}
    for var, raw in EXPORT_RE.findall(text):
        if var in FIELDS:
            value = _unquote(raw, home)
            if value and "$" not in value:
                out[FIELDS[var]] = value
    return out


def discover_projects(config: dict, home: str | None = None) -> dict[str, dict]:
    """並列運用のラッパーと設定ファイルからプロジェクトの一覧。設定ファイルの値が優先。"""
    home = home or str(Path.home())
    found: dict[str, dict] = {}
    pattern = str(config.get("wrapper_glob") or DEFAULT_WRAPPER_GLOB).replace("~", home, 1)
    for wrapper in sorted(glob.glob(pattern)):
        try:
            conf = parse_wrapper(Path(wrapper).read_text(encoding="utf-8", errors="replace"), home)
        except OSError:
            continue
        name = Path(conf.get("path", "")).name
        if name and KEY_RE.fullmatch(name):
            found[name] = {**conf, "wrapper": wrapper}
    hub_scripts = _hub_scripts(config, home)
    for name, conf in found.items():
        prefix = Path(conf["wrapper"]).name.removesuffix("-parallel.sh")
        script = hub_scripts.get(name) or hub_scripts.get(prefix)
        if script:
            found[name] = {**conf, "hub_script": script}
    projects = config.get("projects")
    for name, conf in (projects.items() if isinstance(projects, dict) else []):
        if KEY_RE.fullmatch(str(name)) and isinstance(conf, dict):
            merged = {**found.get(name, {}), **conf}
            if "hub_script" not in merged and hub_scripts.get(str(name)):
                merged["hub_script"] = hub_scripts[str(name)]
            for key in ("path", "wrapper", "worktree_dir"):
                if isinstance(merged.get(key), str):
                    merged[key] = _home(merged[key], home)
            cmd = merged.get("hub_command")
            if isinstance(cmd, list) and cmd and isinstance(cmd[0], str):  # 先頭(実行するファイル)だけ ~ を展開する
                merged["hub_command"] = [_home(cmd[0], home), *cmd[1:]]
            found[name] = merged
    return found


def _hub_scripts(config: dict, home: str) -> dict[str, str]:
    """中心の起動スクリプト(既定 ~/bin/*-hub.sh)。{名前の部分: パス}。"""
    pattern = str(config.get("hub_script_glob") or DEFAULT_HUB_SCRIPT_GLOB).replace("~", home, 1)
    return {Path(p).name.removesuffix("-hub.sh"): p for p in sorted(glob.glob(pattern))
            if Path(p).is_file() and os.access(p, os.X_OK)}  # 動かせないものは「無い」とみなす


def _home(value: str, home: str) -> str:
    """先頭の ~/ だけをホームに置き換える。"""
    return home + value[1:] if value == "~" or value.startswith("~/") else value
