"""見本(demo.sh)用の起動の偽物。tmux もラッパーも動かさず、見本のセッション一覧にファイルを足すだけ。

  中心 … 見本のセッション一覧に、その名前の生きているセッション(pid 1)を足す。表は「動いている」になる
  子   … そのプロジェクトで動いている子が上限(3)以上なら、並列運用のラッパーと同じ文で断る。
          そうでなければ、作業ツリーの場所にセッションを足す
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from start import ChildPlan, HubPlan, Result

LIMIT = 3


class DemoLauncher:
    def __init__(self, sessions_dir: Path, projects: dict[str, dict]):
        self.sessions_dir, self.projects = sessions_dir, projects

    def _proc_start(self) -> str:
        return Path("/proc/1/stat").read_text().rsplit(")", 1)[-1].split()[19]

    def _add_session(self, name: str, cwd: str) -> None:
        ms = int(time.time() * 1000)
        doc = {"pid": 1, "procStart": self._proc_start(), "sessionId": f"demo-started-{name}", "cwd": cwd,
               "name": name, "kind": "interactive", "status": "busy", "updatedAt": ms, "statusUpdatedAt": ms}
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        (self.sessions_dir / f"demo-started-{abs(hash(name))}.json").write_text(json.dumps(doc, ensure_ascii=False))

    def start_hub(self, plan: HubPlan) -> Result:
        name = plan.argv[plan.argv.index("--name") + 1]
        self._add_session(name, plan.cwd)
        return Result(True, 0, f"見本: tmux の {plan.session} に窓 {plan.window} を作ったことにした")

    def start_child(self, plan: ChildPlan) -> Result:
        wt = Path(plan.cwd) / ".claude" / "worktrees"
        running = 0
        for f in self.sessions_dir.glob("*.json"):
            try:
                cwd = json.loads(f.read_text()).get("cwd", "")
            except (OSError, ValueError):
                continue
            running += cwd.startswith(str(wt) + "/")
        if running >= LIMIT:
            return Result(False, 1, f"子の上限 {LIMIT} を超えます（動いている: {running}、起動しようとした: 1）。\n"
                                    "PR が出て CI が green になった子を片付けてから起動するか、--force を付けてください。")
        self._add_session(f"child-{plan.arg}", str(wt / plan.arg.removesuffix("@fix")))
        return Result(True, 0, f"見本: 作ります: {wt / plan.arg.removesuffix('@fix')}\ntmux に窓を用意しました")
