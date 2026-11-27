"""設定ファイルと並列運用のラッパーからのプロジェクトの見つけ方。"""
from __future__ import annotations

import json
from pathlib import Path

import config

WRAPPER = '''#!/usr/bin/env bash
export PARALLEL_ROOT="$HOME/work/sample_app"
export PARALLEL_SESSION="sample_app"
export PARALLEL_HUB="${PARALLEL_HUB:-sample_app_hub}"
export PARALLEL_GRILL_URL="http://example.invalid:8374/"
exec ~/.claude/skills/dev-flow/parallel/parallel.sh "$@"
'''


def test_projects_come_from_wrappers_and_config_overrides(tmp_path: Path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "sample_app-parallel.sh").write_text(WRAPPER, encoding="utf-8")
    conf = {"wrapper_glob": str(tmp_path / "bin" / "*-parallel.sh"), "hub_script_glob": str(tmp_path / "none-*.sh"),
            "projects": {"sample_app": {"repo": "someone/sample_app"}, "notes": {"path": "~/notes", "github": False}}}

    projects = config.discover_projects(conf, home=str(tmp_path))

    assert projects["sample_app"] == {"path": f"{tmp_path}/work/sample_app", "tmux_session": "sample_app",
                                      "hub": "sample_app_hub", "repo": "someone/sample_app",
                                      "wrapper": str(tmp_path / "bin" / "sample_app-parallel.sh")}
    assert projects["notes"] == {"path": f"{tmp_path}/notes", "github": False}


def test_missing_or_broken_config_still_works(tmp_path: Path):
    assert config.load_config(tmp_path / "nothing.json") == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert "error" in config.load_config(broken)
    assert json.dumps(config.discover_projects({"wrapper_glob": str(tmp_path / "none-*.sh")}, home=str(tmp_path))) == "{}"


def test_wrapper_and_hub_script_are_found_and_hub_command_comes_from_config(tmp_path: Path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "sample_app-parallel.sh").write_text(WRAPPER, encoding="utf-8")
    (tmp_path / "bin" / "sample_app-hub.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    conf = {"wrapper_glob": str(tmp_path / "bin" / "*-parallel.sh"), "hub_script_glob": str(tmp_path / "bin" / "*-hub.sh"),
            "projects": {"notes": {"path": "~/notes", "hub_command": ["/opt/notes-hub", "--fast"]}}}

    projects = config.discover_projects(conf, home=str(tmp_path))

    assert projects["sample_app"]["wrapper"] == str(tmp_path / "bin" / "sample_app-parallel.sh")
    assert projects["sample_app"]["hub_script"] == str(tmp_path / "bin" / "sample_app-hub.sh")
    assert projects["notes"]["hub_command"] == ["/opt/notes-hub", "--fast"]
    assert "hub_script" not in projects["notes"]


def test_tilde_in_wrapper_and_hub_command_is_expanded(tmp_path: Path):
    conf = {"wrapper_glob": str(tmp_path / "none-*.sh"), "hub_script_glob": str(tmp_path / "none-*.sh"),
            "projects": {"notes": {"wrapper": "~/bin/notes-parallel.sh", "hub_command": ["~/bin/notes-hub.sh", "~x"]}}}

    notes = config.discover_projects(conf, home=str(tmp_path))["notes"]

    assert notes["wrapper"] == f"{tmp_path}/bin/notes-parallel.sh"
    assert notes["hub_command"] == [f"{tmp_path}/bin/notes-hub.sh", "~x"]
