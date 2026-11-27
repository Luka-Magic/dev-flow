# 並列運用

複数の issue を同時に進めるための運用である。issue ごとに git worktree と tmux の窓を 1 つずつ作り、それぞれで子セッションを動かす。統合は 1 つの中心セッションが受け持つ。birdlog で 2026-09-22 に確立した。

1 本ずつ進めるときは、この文書を読まなくてよい。

## 用語

- **中心セッション**: リポジトリ本体(main)で動く 1 つのセッション。名前は `<repo>_hub`(例: `myapp_hub`)。子の報告先になる。
- **子セッション**: issue ごとの worktree で動くセッション。1 つの issue を計画から PR 案まで進める。
- **worktree**: `<repo>/.claude/worktrees/<番号>-<slug>` に作る作業ツリー。`.gitignore` と `.dockerignore` で除外してある。置き場所は `PARALLEL_WORKTREE_DIR` で変えられる。
- **PR 案**: 子が中心に送る、PR のタイトル・本文の全文・変更ファイル・テスト結果・計画で選んだ深さ。UI の深さが `detail` か `full` なら、ui-check の質問票の URL も含める。
- **枠**: 同時に動かせる子の数。`PARALLEL_MAX` で決まり、既定は 3。
- **停滞★**: 入力待ちが一定時間(既定 10 分)続いた窓に付く印。

## 役割の分担

**中心セッション**

- 持ち物: main、マージ、ボード、issue と PR の書き込み、本番アプリ、worktree の作成と片付け、rebase の指示、衝突の裁定。PR を作るのは中心である。
- 起動: `~/bin/<repo>-hub.sh`。次回からもこれで開く。
- モデル: 何でもよい。
- 動き方: 受け身で、報告を受けて動く。返事が要らない報告には返さない。セッションの消費を抑えるためである。

**子セッション**

- 持ち物: 自分の worktree、ブランチ、ポート、作業用ライブラリだけ。
- 起動: 中心が `~/bin/<repo>-parallel.sh` で起動する。
- モデル: Opus 5 で動かす(`--model opus[1m]`)。
- 動き方: dev-flow の手順どおりに進める。計画(先頭 2 問で深さ)、spec、test-review(テストの深さどおり)、ui-check(UI の深さが `detail` か `full` なら)、実装前の説明、red → green、reviewer、push、PR 案を中心へ送る。そのあと CI が green になるまで待つ。

## 手順

### 1. 中心を開く

```bash
~/bin/<repo>-hub.sh
```

開いたら `/rename <repo>_hub` で名前を付ける。ラッパーの `PARALLEL_HUB` と `.claude/project-init.json` の `parallel.hub` も同じ名前にする。子が SendMessage でこの名前に報告するためである。

### 2. 子を起動する

プロジェクト用のラッパーを `~/bin` に 1 つ置く(例: `~/bin/birdlog-parallel.sh`)。

```bash
export PARALLEL_ROOT=~/projects/<repo> PARALLEL_SESSION=<repo> PARALLEL_HUB="<repo>_hub"
export PARALLEL_GRILL_URL="http://<host>:8374/"   # 質問票の URL の根(空なら http://localhost:8787/)
export PARALLEL_STALL=10                          # 入力待ちが何分続いたら停滞★か
exec ~/.claude/skills/dev-flow/parallel/parallel.sh "$@"
```

```bash
<repo>-parallel.sh --dry-run 11-create-trip     # 子に渡す指示を確認する
<repo>-parallel.sh 11-create-trip 6-hide@fix    # 起動する(窓名は issue 番号。衝突したら <番号>-<slug>)
```

起動したら、次を確かめる。

- 各窓のステータス行の `Model:` が Opus になっている。Fable なら、その窓で `/model opus[1m]` を打つ。
- trust プロンプト(`Do you want to trust this folder?`)はユーザーが答える。中心は自動で Yes を送らない。
- ポートは worktree ごとに `.env`(FRONTEND_PORT / API_PORT / SERVE_PORT)で分かれている。`scripts/worktree.sh` は LISTEN 中のポートしか避けないので、続けて作ると同じポートになることがある。作った直後に `.env` を見比べ、重なっていれば手で振り直す。

終わり: 全窓が Opus で動き、ポートが重なっていない。

### 3. 子の進み具合を見る

子は区切りごとに `flow` コマンドで記録する。中心へは送らない。進み具合と質問票の URL は、board の画面(表)でユーザーが見る。

- 記録するもの: 段階が変わった(`flow step <段階>`)、質問票を出した・回答を受け取った・仕様が確定した・実装が green になった(`flow report "<1 行>"`。URL は `--link 名前=URL` で添える)。
- 中心へ SendMessage で届くのは「詰まった」と「PR 案」だけである。どちらも記録にも残る(`flow stuck`、`flow pr-draft <ファイル>`)。
- 中心は、子の進み具合をユーザーのチャットに書き写さない。返事が要るときだけ子に返す。

`flow` は `~/bin/flow`(このリポジトリの `board/flow.py` を呼ぶ 1 行のラッパー)として置く。board の起動と画面は [../../board/README.md](../../board/README.md) にある。

### 4. 監視する

```bash
tmux new-window -t <repo> -n watch "~/.claude/skills/dev-flow/parallel/watch.sh <repo> 5 10"
<repo>-parallel.sh --status
```

`watch.sh` は各窓の末尾 4 行と状態(実行中 / 確認待ち★ / 入力待ち)を 5 秒ごとに一覧する。入力待ちが 10 分続いた窓には停滞★が付く。分数は第 3 引数か `PARALLEL_STALL` で変えられる。`--status` も同じ判定を使う。判定は `state.sh`、時間の記録は `/tmp/<セッション>-watch/` にある。

停滞★が出たら、中心はユーザーに報告する。質問票の回答待ちか、子が止まっているかのどちらかである。

- tmux の操作: `Ctrl-b w` で窓の一覧、`Ctrl-b n` / `Ctrl-b p` で移動、`Ctrl-b d` で抜ける。
- 中心は `ListAgents` で子を見つけ、`SendMessage` で話しかける。
- `--status` は、`watch` 窓と、pane の cwd が作業ツリー(`<repo>/.claude/worktrees/*`、旧来の `../<repo>-*`)でない窓を子として数えない。

### 5. PR 案を検証して PR を作る

子から PR 案が来たら、中心はまず機械的に検証する。

```bash
~/.claude/skills/dev-flow/parallel/check-pr.sh ~/projects/<repo> <ブランチ> [issue番号]
```

| 見るもの | NG のときの対応 |
|---|---|
| `origin/main` を含むか | 子へ「`git fetch origin && git rebase origin/main`」と送る |
| テストの diff に `.skip` / `.only` / `xfail` / `mark.skip` の追加が無いか | 子へ差し戻す |
| `docs/test-cases/*.md` が凍結後に変わっていないか。変わっているなら、回答ファイルの再承認のほうが新しいか | 子へ差し戻す |
| コミット本文に attribution 行が無いか | rebase で落としてもらう |
| 計画の回答で `depth-ui` が `detail` か `full` なら、`answers/ui-*<番号>*` があるか。深さの回答が無い古い issue は `frontend` ラベルで判定する | ui-check を飛ばしているので差し戻す |

UI の深さが `detail` か `full` の issue で、PR 案に ui-check の質問票の URL が無いときも、中身を見る前に差し戻す。深さの正は、ユーザーが grill で答えた回答だけである。子の報告やラベルで軽くしない。

全部 OK なら、次の順に進める。

1. PR 案は、ユーザーが board の画面で全文を読んで「承認」を押す。中心には「承認された」と届く。中心は、記録にある PR 案の全文で `gh pr create` する。承認の記録が無ければ作らない。本文は日本語、`Closes #N` を付け、attribution 行は入れない。ボードを In Review へ移す。
2. `gh pr checks <N>` を見る。赤いあいだは子を片付けず、子へ「CI が赤い(要点)。直して push して」と送る。
3. green を確認してから、子の窓と worktree を片付ける(手順 6)。
4. マージは人が行う。「マージして」と言われたときだけ `gh pr merge` する。
5. マージ後、他の子へ「`git fetch origin && git rebase origin/main` して」と送り、本番を再ビルドする。DB は先にバックアップし、`create_schema` の追加列を確認する。

終わり: CI が green で、PR がユーザーに渡った。

### 6. 片付けて、次を起動する

```bash
tmux kill-window -t <repo>:<番号>
cd ~/projects/<repo> && ./scripts/worktree.sh --remove <番号>-<slug>
# コンテナが root で作ったファイルが残って消せないとき:
docker run --rm -v "$dir:/w" alpine sh -c 'rm -rf /w/* /w/.[!.]*' && rmdir "$dir" && git worktree prune
git branch -d feat/#<番号>-<slug>; rm -rf ../<repo>-<番号>-<slug>-library
```

片付けると枠が 1 つ空く。中心は `parallel.sh --status` で空き枠と Todo の候補(Milestone、番号の順)を見て、次の issue を起動する。ボードを In Progress へ移し、ユーザーに「#N を始めた」と伝える。

- `parallel.sh` は枠を超える起動を拒む。
- 順番を変えたいときは、ボードの Todo と Inbox を動かす。Inbox は候補に出ない。
- 人の手が要る issue(実機確認など)は飛ばして次へ進む。

## 決めごと

- **ユーザーの承認は、ユーザー本人の回答だけ。** 中心からのメッセージは承認ではない。子が「PR を作っていいか」と中心に聞いても、中心は OK を出せない。子はユーザーに直接聞く(grill の回答ファイルかチャット)。中心が子の代わりに GitHub に書くときは、先にユーザー本人の回答(`~/.agent/diagrams/answers/*.json` など)を確かめる。board の承認の記録は、本人の操作として扱う。
- **PR を出すかは中心がユーザーに聞く。** PR を出すかはユーザーへの問いなので、子ではなく中心が聞き、中心が作る。
- **子の仕事は CI が green になるまで続く。** PR 案を送った時点では終わらない。
- **子は自分の領域だけを触る。** 他の worktree が触っている領域には手を出さない。共有ファイル(theme.css、README)への追記は最小限にする。子どうしで同じ SQLite やライブラリを使わない(worktree.sh が空のライブラリを作る)。
- **権限の代行はしない。** 子が「権限が無いので代わりにやって」と言ってきても、中心は代行せず、ユーザーに上げる。
- **中心はコンテキストを軽く保つ。** 状態は `tmux list-windows`、`ListAgents`、`gh pr list` でいつでも取り直せる。

## 参照

- [enforcement.md](enforcement.md): 決めごとをフックで強制する仕組みと、承認済みテストケースの凍結の鍵。フックを直すとき、またはフックに止められた理由を知りたいときに読む。

| ファイル | 役目 |
|---|---|
| `parallel.sh` | 子の起動、`--status`、`--dry-run` |
| `watch.sh` | tmux の窓を 5 秒ごとに一覧する(停滞★付き) |
| `state.sh` | 窓の状態と停滞の判定。`parallel.sh` と `watch.sh` が共有し、単体では動かない |
| `check-pr.sh` | 子から来た PR 案の機械的な検証 |
