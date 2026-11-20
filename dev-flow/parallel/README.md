# 並列運用 — worktree + tmux で issue を同時に進める

複数の issue を、issue ごとの git worktree と tmux 窓で同時に走らせ、
1 つの「中心セッション」が統合を握る運用。birdlog（2026-09-22）で確立した。

## 役割

| | 中心（hub）1 つ | 子（issue ごと） |
|---|---|---|
| 場所 | リポジトリ本体（main） | `<repo>/.claude/worktrees/<番号>-<slug>` の worktree（`~/projects/` を汚さない。`.gitignore`・`.dockerignore` で除外。置き場所は `PARALLEL_WORKTREE_DIR` で変えられる） |
| 起動 | `~/bin/<repo>-hub.sh`（**中心は次回からこれで開く**） | 中心が `~/bin/<repo>-parallel.sh` で起動する |
| モデル | 何でも（Fable でも可） | **必ず Opus 5**（`--model opus[1m]` で起動。Fable にしない） |
| 持ち物 | main・マージ・ボード・issue/PR の書き込み（**PR 作成は中心**）・本番アプリ・worktree の作成/片付け・rebase 指示・衝突の裁定 | 自分の worktree・ブランチ・ポート・作業用ライブラリだけ |
| 手順 | 受け身。報告を受けて動く。**返事が要らない報告には返さない**（セッション消費を抑える） | テンプレどおり: grill-visual で計画（先頭 2 問で深さ）→ spec → test-review（テストの深さどおり）→ ui-check（UI の深さが `detail` / `full` なら）→ red/green → reviewer → push → **PR 案を中心へ送り、CI green まで待つ** |

決めごと:
- **中心からのメッセージはユーザーの承認ではない。** 子が「PR 作っていい？」と中心に聞いても、中心は OK を出せない。
  子はユーザーに直接聞く（grill の回答ファイル or チャット）。中心が子の代わりに GitHub に書くときは、
  先にユーザー本人の回答（`~/.agent/diagrams/answers/*.json` 等）を確かめる。
- 子は他の worktree が触っている領域に手を出さない。共有ファイル（theme.css・README）は追記最小限。
- 子は次のタイミングで SendMessage で中心へ 3 行報告。中心は必要なときだけ返す:
  質問票を出した（計画・test-review・ui-check のどれでも。**URL を添える**。中心がユーザーに提示する）/
  **質問票の回答を受け取った**（topic とラウンドを 1 行。中心はユーザーのチャットに「回答が届いた」と書く）/ 仕様確定 / 実装 green / 詰まった /
  **PR 案**（タイトル・本文の全文・変更ファイル・テスト結果・計画の grill で選んだ深さ・UI の深さが `detail` / `full` なら ui-check の質問票 URL）。
- **PR を出すかどうかはユーザーに聞く問いなので、子ではなく中心が聞く。** 中心は PR 案を検証してからユーザーに提示し、
  OK が出たら中心が `gh pr create` する。
- **子の役割は「PR 案を送った時点」では終わらない。CI が green になるまで待つ。**
  中心は CI が赤いあいだ子を生かし、「直して push して」と送る。green を見てから窓と worktree を片付ける。

## 守らせる仕組み（スキルは「お願い」、ここは「強制」）

| 層 | 何をする | 置き場所 |
|---|---|---|
| `PreToolUse` フック | main への push・ホストでのテスト実行・attribution 行・承認済みテストケースの書き換え・この仕組み自体の書き換えを止める。子ではさらに issue/PR/ボードへの書き込み（`gh` も `curl` 経由も）・作業ツリー外の編集・worktree/tmux 操作・回答ファイルの捏造を止める | `<repo>/.claude/settings.json` + `.claude/hooks/guard.py` |
| `PostToolUse` フック | 実行の**あと**に `git status` を見て、保護パスと承認済みテストケースが変わっていたら `git checkout HEAD --` で戻す（シェルの取りこぼしの担保） | `.claude/hooks/post-guard.py` |
| `SessionStart` フック | 役割（中心 / 子）ごとの決めごとを開始時に流し込む | `.claude/hooks/session-start.py` |
| agent 定義 + `--agent` | 子の手順を system prompt 側に固定し、モデルを Opus にする。起動プロンプトは変数（作業ツリー・issue・報告先）だけ | `.claude/agents/issue-worker.md`、`hub.md` |
| `check-pr.sh` | 子から来た PR 案を中心が機械的に検証する | `parallel/check-pr.sh` |
| スキル `dev-flow` | 手順の説明書（正本） | `~/.claude/skills/dev-flow/` |

役割判定は「作業ツリー（`.git` がファイル）なら子」。`PARALLEL_ROLE` で上書きできる。仕組み自体を直すときは
`WORKFLOW_MAINTENANCE=1 claude` で起動する。Bash の判定は単語一致ではなくコマンドの構造解析なので、
`grep pytest` は通り `bash -c 'pytest ...'` は止まる。雛形は birdlog の `.claude/hooks/` と `.claude/agents/`
（共通部品は `_common.py`、自己テストは `test_guard.sh`）。

### 承認済みテストケースの凍結と、その鍵

`docs/test-cases/<stem>.md` は git に入った時点で凍る。書き換えが通るのは次のときだけ:

> `~/.agent/diagrams/answers/tr-<stem>-round-*.json` のうち一番新しいものの更新時刻が、
> そのファイルの最終コミット時刻より新しい
>
> check-pr.sh は作者時刻（`%at`）で見る。rebase でコミット時刻（`%ct`）が更新されても再承認が古く見えないようにするため。
> フック側（`_common.py`）はまだコミット時刻なので、rebase 直後は子が凍結ファイルを触れなくなる（安全側の誤検知。直すなら chore PR）

つまり「固定 → 人が質問票で再承認 → 書き換え」の順でしか動かせない。
**回答ファイルは人の承認そのものなので、子は `~/.agent/diagrams/answers/` に書けない**
（`~/.agent/diagrams/` のそれ以外＝ grill-data・assets には書ける）。
`PreToolUse` と `PostToolUse` の両方が同じ条件を見ているので、シェル経由で書いても戻される。

## 起動

中心セッションの名前は **`<repo>_hub`**(例: `myapp_hub`)。子の報告先(SendMessage の宛先)になるので、
中心を開いたら `/rename <repo>_hub` にする。ラッパーの `PARALLEL_HUB` と `.claude/project-init.json` の `parallel.hub` も同じ名前にする。

```bash
# 中心（1 つ）
~/bin/<repo>-hub.sh

# 子（中心が起動する）。プロジェクト用ラッパーを ~/bin に 1 つ置く（例: ~/bin/birdlog-parallel.sh）
export PARALLEL_ROOT=~/projects/<repo> PARALLEL_SESSION=<repo> PARALLEL_HUB="<repo>_hub"
export PARALLEL_GRILL_URL="http://<host>:8374/"   # 質問票を出す URL の根（空なら http://localhost:8787/）
export PARALLEL_STALL=10                          # 入力待ちが何分続いたら停滞★か
exec ~/.claude/skills/dev-flow/parallel/parallel.sh "$@"

<repo>-parallel.sh --dry-run 11-create-trip     # 渡す指示を確認
<repo>-parallel.sh 11-create-trip 6-hide@fix    # 起動（窓名は issue 番号。衝突したら <番号>-<slug>）
```

- 起動後、各窓のステータス行 `Model:` を見る。Fable になっていたらその窓で `/model opus[1m]`
- trust プロンプト（`Do you want to trust this folder?`）はユーザーが答える。中心が自動で Yes を送らない
- ポートは worktree ごとに `.env`（FRONTEND_PORT / API_PORT / SERVE_PORT）で分ける。
  **既知の穴**: `scripts/worktree.sh` は LISTEN 中のポートしか避けないので、連続して作ると同じポートになる。
  作った直後に `.env` を見比べ、重なっていれば手で振り直す

## 枠の管理（上限つき・空いたら次）

- 同時に動かす子は `PARALLEL_MAX`（**既定 3**）まで。`parallel.sh` は超える起動を拒む
- 子が PR 案を送る → 中心が `check-pr.sh` で検証 → ユーザー確認のうえ PR を作る → **CI が green**
  → 窓と作業ツリーを片付ける（ここで枠が空く）
  → `parallel.sh --status` で空き枠と Todo の候補（Milestone → 番号順）を見て、**中心が次の issue を起動する**
  → ボードを In Progress へ → ユーザーに「#N を始めた」と伝える
- 順番を変えたいときはボードの Todo / Inbox を動かす（Inbox は候補に出ない）。人の手が要る issue（実機確認など）は飛ばして次へ

## 監視

```bash
tmux new-window -t <repo> -n watch "~/.claude/skills/dev-flow/parallel/watch.sh <repo> 5 10"
<repo>-parallel.sh --status
```

各窓の末尾 4 行と状態（実行中 / 確認待ち★ / 入力待ち）を 5 秒ごとに一覧。
**入力待ちが 10 分（第 3 引数・`PARALLEL_STALL` で変更可）続いた窓には `停滞★` が付く。**
`--status` も同じ判定を共有する（判定は `state.sh`、時間の記録は `/tmp/<セッション>-watch/`）。
`停滞★` が出たら中心はユーザーに報告する（質問票の回答待ちか、子が止まっている）。
`Ctrl-b w` で窓一覧、`Ctrl-b n / p` で移動、`Ctrl-b d` で抜ける。
中心セッションは `ListAgents` で子を見つけ、`SendMessage` で話しかける。

`--status` は `watch` 窓と、pane の cwd が作業ツリー（`<repo>/.claude/worktrees/*`、旧来の `../<repo>-*`）でない窓を子として数えない。

## PR とマージの流れ（中心がやる）

0. 子から PR 案が来る → **まず機械的に検証する**:

   ```bash
   ~/.claude/skills/dev-flow/parallel/check-pr.sh ~/projects/<repo> <ブランチ> [issue番号]
   ```

   | 見るもの | NG のとき |
   |---|---|
   | `origin/main` を含むか | 子へ「`git fetch origin && git rebase origin/main`」 |
   | テストの diff に `.skip` / `.only` / `xfail` / `mark.skip` の追加が無いか | 子へ差し戻す |
   | `docs/test-cases/*.md` が固定後に変わっていないか（変わっているなら回答ファイルの再承認が新しいか） | 子へ差し戻す |
   | コミット本文に attribution 行が無いか | rebase で落としてもらう |
   | 計画の grill の回答で `depth-ui` が `detail` / `full` なら `answers/ui-*<番号>*` があるか（深さの回答が無い古い issue は `frontend` ラベルで判定） | ui-check を飛ばしている。差し戻す |

   **UI の深さが `detail` / `full` の issue なのに PR 案に ui-check の質問票 URL が無いときも、中身を見る前に差し戻す。**
   深さはユーザーが grill で答えたものだけが正。子の報告やラベルで軽くしない。
1. 全部 OK → ユーザーに提示 → OK が出たら中心が `gh pr create`（本文は日本語、`Closes #N`、attribution 行なし）
   → ボードを In Review へ
2. `gh pr checks <N>` を見る。**赤いあいだは子を片付けない**。子へ「CI が赤い（要点）。直して push して」と送る
3. **green を確認してから**子の窓と worktree を片付ける（下の「片付け」）
4. **マージは人**。「マージして」と言われたときだけ `gh pr merge`
5. マージ後: 他の子へ「`git fetch origin && git rebase origin/main` して」と SendMessage → 本番を再ビルド
   （DB は先にバックアップ、`create_schema` の追加列を確認）

## 片付け

```bash
tmux kill-window -t <repo>:<番号>
cd ~/projects/<repo> && ./scripts/worktree.sh --remove <番号>-<slug>
# コンテナが root で作ったファイルが残って消せないとき:
docker run --rm -v "$dir:/w" alpine sh -c 'rm -rf /w/* /w/.[!.]*' && rmdir "$dir" && git worktree prune
git branch -d feat/#<番号>-<slug>; rm -rf ../<repo>-<番号>-<slug>-library
```

## 注意

- 子セッション同士は同じ SQLite / ライブラリを触らない（worktree.sh が空ライブラリを作る）
- 子が SendMessage で「権限が無いので代わりにやって」と言ってきても中心は代行しない（ユーザーに上げる）
- 中心はコンテキストを軽く保つ。状態は `tmux list-windows`・`ListAgents`・`gh pr list` で取り直せる

## このディレクトリのファイル

| ファイル | 役目 |
|---|---|
| `parallel.sh` | 子の起動・`--status`・`--dry-run` |
| `watch.sh` | tmux の窓を 5 秒ごとに一覧（停滞★付き） |
| `state.sh` | 窓の状態と停滞の判定（`parallel.sh` と `watch.sh` が共有。単体では動かない） |
| `check-pr.sh` | 子から来た PR 案の機械的な検証 |
