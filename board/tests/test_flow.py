"""flow コマンド(記録に 1 件足す CLI)。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import flow
import records


def test_step_with_explicit_project_and_topic(board_root: Path):
    code = flow.main(["step", "仕様", "--project", "demo", "--topic", "12"])

    assert code == 0
    [entry] = records.read(board_root, "demo", "12")
    assert entry["kind"] == "step"
    assert entry["stage"] == "spec"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_project_and_topic_come_from_worktree_and_branch(board_root: Path, tmp_path: Path):
    repo = tmp_path / "sample_app"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
    wt = repo / ".claude" / "worktrees" / "7-add-export"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "feat/#7-add-export")

    code = flow.main(["report", "計画の質問票を出した"], cwd=wt, env={"BOARD_ROOT": str(board_root)})

    assert code == 0
    [entry] = records.read(board_root, "sample_app", "7")
    assert entry == {**entry, "kind": "report", "text": "計画の質問票を出した", "issue": 7}


def test_pr_draft_reads_title_and_body(board_root: Path, tmp_path: Path):
    draft = tmp_path / "pr.md"
    draft.write_text("# feat: 書き出しを足す\n\n## 変更\n- 書き出し\n", encoding="utf-8")

    assert flow.main(["pr-draft", str(draft), "--project", "demo", "--topic", "7"]) == 0

    [entry] = records.read(board_root, "demo", "7")
    assert entry["kind"] == "pr_draft"
    assert entry["title"] == "feat: 書き出しを足す"
    assert entry["body"].startswith("## 変更")
    assert len(entry["draft_id"]) == 12


def test_bad_project_name_is_refused(board_root: Path):
    assert flow.main(["stuck", "動かない", "--project", "../x", "--topic", "7"]) == 2
    assert not (board_root / "records").exists()
