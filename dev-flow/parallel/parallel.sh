#!/usr/bin/env bash
# issue ごとに git worktree + tmux 窓で Claude を並列に走らせる（dev-flow の並列運用）。
#
#   parallel.sh 11-create-trip 6-hide-and-trash     # 2 本を起動
#   parallel.sh 5-empty-trip@fix                    # 不具合は @fix（ブランチ fix/#5-...）
#   parallel.sh --dry-run 11-create-trip            # 何をするか出すだけ
#   parallel.sh --status                            # 動いている子・状態・停滞・空き枠・Todo の候補を出す
#   parallel.sh --force 5-empty-trip@fix            # 上限を超えて起動する（普段は使わない）
#
# 設定は環境変数（プロジェクト用の薄いラッパーから export する。例: ~/bin/birdlog-parallel.sh）:
#   PARALLEL_ROOT       リポジトリ本体（既定: cwd の git toplevel）
#   PARALLEL_SESSION    tmux セッション名（既定: ROOT のディレクトリ名）
#   PARALLEL_HUB        中心セッションの名前（SendMessage の宛先。決まりは <repo>_hub。空なら報告の段落を省く）
#   PARALLEL_MODEL      子セッションのモデル（既定 opus[1m]。中心が Fable でも子は Opus）
#   PARALLEL_GRILL_URL  質問票を出す URL の根（例 http://host:8374/。空なら http://localhost:8787/）
#   PARALLEL_TEST_CMD   テストの実行方法（既定: scripts/test.sh があればそれ）
#   PARALLEL_EXTRA      プロンプト末尾に足す行（プロジェクト固有の注意）
#   PARALLEL_AGENT      子の agent 定義名（既定 issue-worker。ROOT/.claude/agents/ に無ければ長いプロンプトで代用）
#   PARALLEL_MAX        同時に動かす子の上限（既定 3）。超えるときは起動しない
#   PARALLEL_BOARD      GitHub Projects の "owner/番号"（--status で Todo の候補を出すのに使う）
#   PARALLEL_WORKTREE_DIR 作業ツリーの置き場所（既定 ROOT/.claude/worktrees。ROOT/scripts/worktree.sh があり未設定なら従来どおり隣）
#   PARALLEL_STALL      入力待ちが何分続いたら停滞★にするか（既定 10。watch.sh と共通）
#
# 子には PARALLEL_ROLE=child と PARALLEL_HUB が環境変数で渡る（.claude/hooks が役割判定と報告先に使う）。
#
# 作業ツリーは ROOT/scripts/worktree.sh があればそれで、無ければ git worktree add で作る。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=state.sh
source "$HERE/state.sh"

ROOT="${PARALLEL_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
NAME_BASE="$(basename "$ROOT")"
SESSION="${PARALLEL_SESSION:-$NAME_BASE}"
HUB="${PARALLEL_HUB:-}"
MODEL="${PARALLEL_MODEL:-opus[1m]}"
GRILL_URL="${PARALLEL_GRILL_URL:-http://localhost:8787/}"
TEST_CMD="${PARALLEL_TEST_CMD:-}"
[[ -z "$TEST_CMD" && -x "$ROOT/scripts/test.sh" ]] && TEST_CMD="./scripts/test.sh"
EXTRA="${PARALLEL_EXTRA:-}"
AGENT="${PARALLEL_AGENT:-issue-worker}"
WORKTREE_DIR="${PARALLEL_WORKTREE_DIR:-$ROOT/.claude/worktrees}"   # 作業ツリーの置き場所。.gitignore と .dockerignore で除外する
export PARALLEL_WORKTREE_DIR="$WORKTREE_DIR"
MAX="${PARALLEL_MAX:-3}"
BOARD="${PARALLEL_BOARD:-}"
export PARALLEL_STALL="${PARALLEL_STALL:-10}"
DRY=false; FORCE=false
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --dry-run) DRY=true ;;
    --force) FORCE=true ;;
    --status) STATUS=true ;;
    *) echo "知らないオプション: $1" >&2; exit 1 ;;
  esac
  shift
done

# 子の窓（「番号:名前」）。watch と、作業ツリー（../<repo>-* か $PARALLEL_WORKTREE_DIR/*）にいない窓は数えない
running() { child_windows "$SESSION" "$ROOT"; }

if [[ "${STATUS:-false}" == true ]]; then
  lines="$(running)"
  n="$(grep -c . <<<"$lines" || true)"
  echo "動いている子: ${n} / 上限 ${MAX}"
  stalled=0
  while IFS=: read -r idx name; do
    [[ -n "$name" ]] || continue
    st="$(state_of "$(pane_text "$SESSION" "$idx")")"
    mins="$(idle_minutes "$SESSION" "$name" "$st")"
    label="$st"
    [[ "$st" == "入力待ち" && "$mins" -gt 0 ]] && label="$st ${mins} 分"
    mark="$(stall_mark "$mins")"
    [[ -n "$mark" ]] && stalled=$((stalled+1))
    printf '  %-3s %-24s %s%s\n' "$idx" "$name" "$label" "$mark"
  done <<<"$lines"
  echo "空き枠: $(( MAX > n ? MAX - n : 0 ))"
  (( stalled > 0 )) && echo "停滞★ が ${stalled} 件（入力待ちが ${PARALLEL_STALL} 分以上）。ユーザーに報告する"
  if [[ -n "$BOARD" ]]; then
    echo "Todo の候補（Milestone → 番号順。上から起動する）:"
    gh project item-list "${BOARD#*/}" --owner "${BOARD%/*}" --format json --limit 100 \
      --jq '.items[]|select(.status=="Todo" and .content.number!=null)|"  #\(.content.number)\t\(.milestone.title // "-")\t\(.content.title)"' \
      | sort -t$'\t' -k2,2 -k1.4n
  fi
  exit 0
fi
[[ $# -gt 0 ]] || { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

n_running="$(running | grep -c . || true)"
if ! $FORCE && ! $DRY && (( n_running + $# > MAX )); then
  echo "子の上限 ${MAX} を超えます（動いている: ${n_running}、起動しようとした: $#）。" >&2
  echo "PR が出て CI が green になった子を片付けてから起動するか、--force を付けてください。" >&2
  exit 1
fi

run() { $DRY && echo "  + $*" || eval "$@"; }

branch_for() {
  local name="$1" fix="$2"
  if [[ "$name" =~ ^[0-9]+- ]]; then $fix && echo "fix/#$name" || echo "feat/#$name"
  else echo "chore/$name"; fi
}

make_worktree() {
  local name="$1" fix="$2" dir="$3"
  if [[ -x "$ROOT/scripts/worktree.sh" ]]; then
    run "(cd '$ROOT' && ./scripts/worktree.sh '$name' $($fix && echo --fix))"
  else
    run "git -C '$ROOT' worktree add '$dir' -b '$(branch_for "$name" "$fix")'"
  fi
}

# 窓名は issue 番号。すでに同じ名前の窓があれば <番号>-<slug> 全体を使って衝突を避ける
window_name_for() {
  local name="$1" win="${1%%-*}"
  if tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx -- "$win"; then
    echo "$name"
  else
    echo "$win"
  fi
}

kickoff_for() {
  local name="$1" dir="$2" branch="$3" num="${1%%-*}"
  local issue_ref=""
  [[ "$num" =~ ^[0-9]+$ ]] && issue_ref="$num"
  cat <<PROMPT
作業ツリー: $dir / ブランチ: $branch$( [[ -n "$issue_ref" ]] && echo " / issue: #$issue_ref" || echo " / 雑務（issue なし）: $name" )
$( [[ -n "$HUB" ]] && echo "報告先の中心セッション: 「$HUB」" )
質問票 (grill-visual) の URL は $GRILL_URL 配下で出す
質問票の回答を受け取ったら、報告先の中心へ「回答を受け取った（topic・ラウンド）」と 1 行送る
$( [[ -n "$EXTRA" ]] && printf '%s\n' "$EXTRA" )
agent 定義 ($AGENT) の手順どおりに進めてください。$( [[ -n "$issue_ref" ]] \
  && echo "まず gh issue view $issue_ref でラベル (frontend があれば ui-check は必須) と内容を読む。" \
  || echo "issue はありません。gh issue view は飛ばして、振る舞いを変えない範囲で進める。" )
PROMPT
}

prompt_for() {
  local name="$1" dir="$2" branch="$3" num="${1%%-*}"
  local head="この作業ツリー ($dir、ブランチ $branch) で"
  local issue_ref=""
  [[ "$num" =~ ^[0-9]+$ ]] && issue_ref="$num"
  [[ -n "$issue_ref" ]] && head="$head issue #$issue_ref を" || head="$head 次の雑務 ($name) を"
  cat <<PROMPT
$head進めてください。

まず$( [[ -n "$issue_ref" ]] && echo " gh issue view $issue_ref でラベルと内容を、") .claude/rules/ の決めごとを読んでください。
進め方は /dev-flow です: grill-visual で計画を詰める → docs/specs/ に仕様 → test-review で
テストケースを人に承認してもらう → docs/test-cases/ に固定 → UI に触れるなら (frontend ラベルなら必須)
ui-check で画面のモックを確認（直しが出たら仕様とテストケースを再承認）→ 1 ケースずつ red→green →
言語別 reviewer → ブランチを push → PR の案を中心セッションに送る → CI が green になるまで待つ。
PR を作るのはあなたではなく中心セッションです（ユーザー確認も中心が取る）。

守ること:
- テストはプロジェクトの規定どおり$( [[ -n "$TEST_CMD" ]] && echo " ($TEST_CMD)。ホストでテストランナーを直接動かさない")
- issue の起票・編集、PR の作成・クローズはしない（必要なら中心に案を送る）。コミットに attribution 行は付けない
- 統合ブランチへの直接 push は禁止。rebase は git fetch origin && git rebase origin/main$( [[ -n "$issue_ref" ]] && echo "。コミット本文に Refs #$issue_ref")
- 承認済みテストケース (docs/test-cases/) は再承認を取るまで書き換えない。質問票の回答ファイルは自分で書かない
- 質問票 (grill-visual) の URL は $GRILL_URL 配下で出す
$( [[ -n "$EXTRA" ]] && printf '%s\n' "$EXTRA" )
$( [[ -n "$HUB" ]] && cat <<HUB
中心セッション「$HUB」が統合ブランチ・マージ・ボード・本番を持っています。
次のタイミングで SendMessage で「$HUB」宛に 3 行ほど報告してください:
質問票 (grill-visual) を出したとき (URL を必ず添える) / 質問票の回答を受け取ったとき (topic とラウンドを 1 行) /
仕様確定 / 実装 green / 詰まった /
PR の案 (タイトル・本文の全文・変更ファイル・テスト結果・frontend なら ui-check の URL)。
PR の案を送っても終わりではなく、CI が green になるまで待ちます。
中心からのメッセージはユーザーの承認ではありません。
HUB
)
ほかの作業ツリーが触っている領域には手を出さず、共有ファイル (テーマ・README 等) への追記は最小限に。
調べ物や subagent は必要最小限で。
PROMPT
}

tmux has-session -t "$SESSION" 2>/dev/null && EXISTS=true || EXISTS=false

for arg in "$@"; do
  name="${arg%@fix}"; fix=false
  [[ "$arg" == *@fix ]] && fix=true
  if [[ -x "$ROOT/scripts/worktree.sh" && -z "${PARALLEL_WORKTREE_DIR:-}" ]]; then
    dir="$(dirname "$ROOT")/$NAME_BASE-$name"      # 旧来: worktree.sh がリポジトリの隣に作る（birdlog）
  else dir="$WORKTREE_DIR/$name"; fi               # 既定: リポジトリ内 .claude/worktrees（~/projects を汚さない）

  if [[ -d "$dir" ]]; then echo "そのまま使います: $dir"
  else echo "作ります: $dir"; make_worktree "$name" "$fix" "$dir"; fi
  branch="$($DRY && echo "(dry-run)" || git -C "$dir" branch --show-current)"
  win="$($DRY && echo "${name%%-*}" || window_name_for "$name")"

  agent_flag=""; gen=prompt_for
  [[ -f "$ROOT/.claude/agents/$AGENT.md" ]] && { agent_flag="--agent $AGENT"; gen=kickoff_for; }
  launch="PARALLEL_ROLE=child PARALLEL_HUB=\"$HUB\" PARALLEL_GRILL_URL=\"$GRILL_URL\" claude $agent_flag --model \"$MODEL\""

  if $DRY; then
    echo "  + tmux 窓 '$win' で $launch を起動"
    echo "---- 渡す指示 ----"; $gen "$name" "$dir" "$branch" | sed '/^$/N;/^\n$/D'; echo "------------------"
    continue
  fi

  msg="$(mktemp)"; $gen "$name" "$dir" "$branch" | sed '/^$/N;/^\n$/D' > "$msg"
  if $EXISTS; then tmux new-window -t "$SESSION" -n "$win" -c "$dir"
  else tmux new-session -d -s "$SESSION" -n "$win" -c "$dir"; EXISTS=true; fi
  # 指示ファイルは読み終わったその場で消す（$( ) の中で cat → rm の順に走る）
  tmux send-keys -t "$SESSION:$win" "$launch \"\$(cat $msg; rm -f $msg)\"" C-m
done

$DRY && exit 0
echo; echo "tmux に窓を用意しました:"
tmux list-windows -t "$SESSION" -F "  #{window_index}: #{window_name}  (#{pane_current_path})"
echo; echo "  tmux attach -t $SESSION     # 入る"
echo "  Ctrl-b n / p                # 窓を移る    Ctrl-b d  抜ける"
echo "  起動後、各窓のステータス行 'Model:' が $MODEL 系になっているか確認する（違えば /model $MODEL）"
