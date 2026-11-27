# board: dev-flow の進み具合を 1 画面で見る

並列運用では、子セッションが 1 つ進むたびに長い報告が中心セッションのチャットに届く。
board は、進み具合・URL・指示を 1 枚の表に移し、チャットを遡らずに「次にやること」へ行けるようにする 1 人用のローカル Web アプリである。
仕様は [`docs/specs/2026-11-28-board.md`](../docs/specs/2026-11-28-board.md)。

- 全プロジェクトの題材(issue 1 つ、または issue のない作業 1 つ)を、プロジェクトのタブごとの表で出す。
- 質問票への回答、PR 案と issue 案の承認、子への短い指示が、この画面で済む。
- Claude Code の利用枠(5 時間・週)と、セッションごとのコンテキスト使用率を出す。

127.0.0.1 だけで待ち受ける。ログインは無い。Python の標準ライブラリだけで動く。

## 起動

```bash
board/serve.sh             # http://127.0.0.1:8792/ (動いていれば何もしない)
board/serve.sh --restart   # server.py などを直したあと(board.html は再読み込みだけでよい)
board/serve.sh --stop
```

ポートは `BOARD_PORT`、記録の置き場所は `BOARD_ROOT`(既定 `~/.agent/devflow`)で変えられる。
ログは `<BOARD_ROOT>/.server.log`。

質問票は grill-visual(既定 `http://127.0.0.1:8787`)のものを、board が `/grill/<パス>` の下で中継して表の枠に埋め込む。
質問票の JS が叩く `/submit` と `/api/chat` も同じ入口で中継する。grill-visual が止まっていると、質問票の枠は開けない(表は出る)。

### 見本データで開く

```bash
board/demo.sh              # http://127.0.0.1:8793/ (Ctrl-C で止めて、見本を消す)
```

架空のプロジェクトの記録・質問票・GitHub の一覧・セッション・使用量を一時フォルダに作り、別のポートで起動する。
見本の質問票サーバー(`demo_grill.py`)も一緒に動く。実物の記録・セッション・GitHub・grill-visual には触らず、配達(指示の送信)も切ってある。

### Tailscale から開く

board は 127.0.0.1 だけで待ち受ける。外から開くときは Tailscale の中継(`tailscale serve` など)を使い、
その名前を設定ファイルの `allowed_hosts` に足す。足していない名前からの要求は 403 で断る(DNS の付け替えで読まれないため)。

## 記録: `flow` コマンド

題材ごとの追記専用の記録(1 行 1 件の JSON)に 1 件足す。置き場所は `<BOARD_ROOT>/records/<プロジェクト>/<題材>.jsonl`。

```bash
flow step 仕様                                  # 段階が変わった(計画 / 仕様 / チケット / テストレビュー / UI確認 / 実装前の説明 / 実装 / レビュー / 完了)
flow report "計画の質問票を出した" --link 質問票=http://127.0.0.1:8787/grill-12-export.html
flow report "実装前の説明を出した" --link 実装前の説明=http://127.0.0.1:8787/20261128-plan-export.html
flow stuck "テスト用の DB が立ち上がらない"
flow pr-draft pr.md                             # PR 案。1 行目がタイトル、残りが本文の全文
flow issue-draft issue.md                       # issue 案。同じ形
flow step 計画 --title "README の誤字を直す"      # issue の無い題材に、表に出す題を付ける
```

`flow` は `python3 board/flow.py` のこと。使いやすくするなら `~/bin/flow` に
`exec python3 <このリポジトリ>/board/flow.py "$@"` の 1 行を置く。

プロジェクトと題材は `--project` / `--topic` で渡すか、作業フォルダから決まる。

| 決めるもの | 順番 |
|---|---|
| プロジェクト | `BOARD_PROJECT` → git の共通ディレクトリ(worktree でも本体)の親フォルダ名 |
| 題材 | `BOARD_TOPIC` → ブランチ名の `#N` → worktree のフォルダ名の先頭の番号 → ブランチ名 |

プロジェクト名と題材のキーは英数字と `-` `_` だけ。壊れた行があっても、ほかの行は読む。

## 表の決まり

- 段階は記録の最後の `step` を正とする。記録が無く issue が開いていれば「未着手」、閉じていれば「完了」。
- 自分の番: 回答待ちの質問票 / 承認待ちの PR 案・issue 案 / 実装前の説明が未回答 / セッションが確認の選択肢で止まっている。
- 並びは上から、完了 → 番号のない進行中 → 番号のある行(番号順)。開いたときは最初の進行中の行が一番上に来る。
- 記録の段階が、質問票や PR の有無から導ける段階より手前なら、段階の横に印を出す。
- プロジェクトの分からない質問票は「その他」のタブに入る。
- `gh` が無い・失敗する・GitHub を使わないプロジェクトでも、記録と質問票だけで表は出る。

## 設定ファイル

`~/.config/devflow-board/config.json`(`BOARD_CONFIG` で変えられる)。無くても動く。

```json
{
  "projects": {
    "sample_app": {"path": "~/work/sample_app", "hub": "sample_app_hub", "repo": "someone/sample_app"},
    "notes_site": {"path": "~/work/notes_site", "github": false}
  },
  "wrapper_glob": "~/bin/*-parallel.sh",
  "allowed_hosts": ["<Tailscale の名前>"],
  "grill_url": "http://127.0.0.1:8787"
}
```

- プロジェクトは自動で見つける。並列運用のラッパー(`wrapper_glob`、既定 `~/bin/*-parallel.sh`)の
  `PARALLEL_ROOT` `PARALLEL_HUB` `PARALLEL_SESSION` `PARALLEL_WORKTREE_DIR` を読み、設定ファイルの値で上書きする。
  記録や質問票にしか出てこないプロジェクトも、進行中の題材があればタブになる。
- `path` はセッションの作業フォルダからプロジェクトと題材を見分けるのと、`gh` を動かす場所に使う。
- `hub` は承認を知らせる中心のセッションの名前。`repo` があれば `gh -R <repo>` で読む。
- `github: false` なら `gh` を動かさない。

環境変数: `BOARD_PORT` `BOARD_ROOT` `BOARD_CONFIG` `BOARD_GRILL_URL` `BOARD_SESSIONS_DIR`(既定 `~/.claude/sessions`)
`BOARD_ALLOWED_HOSTS`(カンマ区切り)。

## 使用量の組み込み

コンテキスト使用率と利用枠は、ステータス行のスクリプトが受け取る JSON から書き出す。
`statusline_tee.py` は、その JSON から必要な値だけを `<BOARD_ROOT>/usage/<session_id>.json` に原子的に書き出し、
受け取った JSON をそのまま元のステータス行のコマンドへ渡す。書き出しに失敗しても、元のコマンドは動く。

この作業では設定に組み込んでいない。組み込むときは `~/.claude/settings.json` の `statusLine` を次のように変える。

変更前:

```json
"statusLine": {"type": "command", "command": "<元のコマンド>"}
```

変更後:

```json
"statusLine": {"type": "command", "command": "python3 <このリポジトリ>/board/statusline_tee.py -- <元のコマンド>"}
```

元のコマンドに引数やシェルの記法があるときは `-- sh -c '<元のコマンド>'` の形にする。
新しく開いたセッションから書き出される。終了したセッションの値は表に出さない。利用枠は最も新しい書き出しの値を使う。

## 指示の送信と配達係の試験

画面の枠の下の欄から、その題材のセッションへ 1 行送れる。送った文と結果は題材の記録に残る。

1. 配達係: `claude -p` の使い捨てセッションが `ListAgents` で宛先を探し、`SendMessage` で 1 回送る。
2. 配達係が失敗したら、tmux の窓へ文字を打ち込む。確認の選択肢が出ている窓には送らない。

配達係が実物で届くかは、まだ試していない。人が次の手順で試す。

```bash
board/courier_check.sh <宛先のセッション名>
```

確かめること:

- 宛先の窓に、試験の 1 行が届くか。止まっている(入力待ちの)相手が起きるか。
- 相手の権限の設定で、メッセージが保留されないか。
- 届かないなら tmux を本線にする(仕様「進め方」)。

## 承認

PR 案・issue 案の「承認」を押すと、記録に承認を足し、中心のセッション(設定の `hub`)へ「承認された」と配達する。
同じ案を 2 回押しても 1 回分。「直して」は、欄に書いた文を「PR 案を直して: …」としてその題材のセッションへ送る。

## テスト

```bash
uvx pytest -q board/tests
```

テストは一時フォルダと見本だけを相手にする。実物の `~/.claude`、tmux、`gh`、grill-visual には依存しない(配達は偽物)。

## ファイル

| ファイル | 役目 |
|---|---|
| `server.py` | HTTP の入口と質問票の中継 |
| `compose.py` `rows.py` `detail.py` `sessions.py` `usage.py` | 表の合成(純粋関数) |
| `collect.py` `config.py` | 集め役(記録・質問票・`gh`・セッション・使用量)と設定 |
| `records.py` `stages.py` `flow.py` | 記録と `flow` コマンド |
| `deliver.py` `actions.py` | 配達(配達係・tmux)と承認 |
| `statusline_tee.py` | 使用量の書き出し |
| `board.html` | 画面(1 ファイル) |
| `serve.sh` `demo.sh` `demo_data.py` `demo_grill.py` `courier_check.sh` | 起動・見本・配達の試験 |
| `docs/skill-changes.md` | スキルの文面の変更案(子の報告を記録に移す) |
