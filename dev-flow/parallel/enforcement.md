# 決めごとを強制する仕組み

スキルに書いた決めごとは、エージェントへのお願いにとどまる。並列運用では、破られると困る決めごとをフックで強制する。
この文書は、フックを直すとき、またはフックに止められた理由を知りたいときに読む。

## 層

| 層 | 何をする | 置き場所 |
|---|---|---|
| `PreToolUse` フック | 実行の前に止める。全員: main への push、ホストでのテスト実行、attribution 行、承認済みテストケースの書き換え、この仕組み自体の書き換え。子だけ: issue・PR・ボードへの書き込み(`gh` も `curl` 経由も)、作業ツリーの外の編集、worktree と tmux の操作、回答ファイルの捏造 | `<repo>/.claude/settings.json` と `.claude/hooks/guard.py` |
| `PostToolUse` フック | 実行のあとに `git status` を見る。保護パスと承認済みテストケースが変わっていたら `git checkout HEAD --` で戻す。シェル経由で `PreToolUse` をすり抜けた変更の担保である | `.claude/hooks/post-guard.py` |
| `SessionStart` フック | 役割(中心 / 子)ごとの決めごとを、セッションの開始時に流し込む | `.claude/hooks/session-start.py` |
| agent 定義と `--agent` | 子の手順を system prompt の側に固定し、モデルを Opus にする。起動プロンプトには変数(作業ツリー、issue、報告先)だけを渡す | `.claude/agents/issue-worker.md`、`hub.md` |
| `check-pr.sh` | 子から来た PR 案を、中心が機械的に検証する | `parallel/check-pr.sh` |
| スキル `dev-flow` | 手順の説明書(正本) | `~/.claude/skills/dev-flow/` |

## 判定の決まり

- 役割は、作業ツリーの `.git` がファイルなら子と判定する。`PARALLEL_ROLE` で上書きできる。
- 仕組み自体を直すときは、`WORKFLOW_MAINTENANCE=1 claude` で起動する。
- Bash の判定は単語の一致ではなく、コマンドの構造を解析して行う。だから `grep pytest` は通り、`bash -c 'pytest ...'` は止まる。
- 雛形は birdlog の `.claude/hooks/` と `.claude/agents/` にある。共通部品は `_common.py`、自己テストは `test_guard.sh`。

## 承認済みテストケースの凍結と、その鍵

`docs/test-cases/<stem>.md` は、git に入った時点で凍る。書き換えが通るのは、次の条件を満たすときだけである。

**条件**: `~/.agent/diagrams/answers/tr-<stem>-round-*.json` のうち一番新しいものの更新時刻が、そのファイルの最終コミットの時刻より新しい。

つまり「凍結 → 人が質問票で再承認 → 書き換え」の順でしか動かせない。

- 回答ファイルは人の承認そのものなので、子は `~/.agent/diagrams/answers/` に書けない。`~/.agent/diagrams/` のそれ以外(grill-data、assets)には書ける。
- `PreToolUse` と `PostToolUse` の両方が同じ条件を見るので、シェル経由で書いても戻される。

**時刻の扱いの食い違い(既知)**: `check-pr.sh` は作者時刻(`%at`)で比べる。rebase でコミット時刻(`%ct`)が更新されても、再承認が古く見えないようにするためである。一方、フック側(`_common.py`)はまだコミット時刻で比べている。そのため rebase の直後は、子が凍結ファイルを触れなくなる。安全側の誤検知なので実害は小さい。直すなら chore の PR で揃える。
