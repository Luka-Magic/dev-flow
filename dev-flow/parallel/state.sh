#!/usr/bin/env bash
# 窓の状態の見分け方を watch.sh と parallel.sh --status で共有するための小さな関数群。
# 単体では動かない。`source` して使う。
#
#   pane_text <セッション> <窓の番号>            … 窓の見えている文字
#   state_of <文字>                              … 実行中 / 確認待ち★ / 入力待ち
#   idle_minutes <セッション> <窓> <状態>        … 入力待ちが続いている分数（それ以外は 0）
#   stall_mark <分>                              … しきい値を超えていたら " 停滞★"
#   child_windows <セッション> <ルート>          … 「番号:名前」。watch と、兄弟作業ツリー以外の窓は除く
#
# 状態の見分け方:
#   実行中     … 画面に "esc to interrupt" がある（Claude が動いている）
#   確認待ち   … 選択肢（❯ Yes / No など）が出ている ← 人の操作が要る
#   入力待ち   … どちらでもない ← 返事待ちか、終わっている
#
# 入力待ちの続いた時間は /tmp/<セッション>-watch/<窓> に始まった時刻を置いて数える
# （PARALLEL_STATE_DIR で場所を変えられる）。しきい値は PARALLEL_STALL 分（既定 10）。

state_dir() { echo "${PARALLEL_STATE_DIR:-/tmp/$1-watch}"; }

pane_text() { tmux capture-pane -p -t "$1:$2" 2>/dev/null; }

state_of() {
  local text="$1"
  if grep -qE 'esc to interrupt|Esc to interrupt' <<<"$text"; then echo "実行中"
  elif grep -qE '^\s*[❯>]\s*(Yes|No|[0-9]\.)' <<<"$text"; then echo "確認待ち★"
  elif grep -qE 'Do you want|trust this folder|approve' <<<"$text"; then echo "確認待ち★"
  else echo "入力待ち"
  fi
}

idle_minutes() {   # idle_minutes <セッション> <窓> <状態>
  local session="$1" win="$2" st="$3" dir f since now
  dir="$(state_dir "$session")"
  mkdir -p "$dir" 2>/dev/null || { echo 0; return; }
  f="$dir/$(printf "%s" "$win" | tr -c "A-Za-z0-9_.-" "_")"
  now="$(date +%s)"
  if [[ "$st" == "入力待ち" ]]; then
    [[ -f "$f" ]] || printf '%s' "$now" > "$f"
    since="$(cat "$f" 2>/dev/null)"
    [[ "$since" =~ ^[0-9]+$ ]] || since="$now"
    echo $(( (now - since) / 60 ))
  else
    rm -f "$f" 2>/dev/null
    echo 0
  fi
}

stall_mark() {     # stall_mark <分> [しきい値]
  local mins="$1" limit="${2:-${PARALLEL_STALL:-10}}"
  [[ "$mins" =~ ^[0-9]+$ ]] || return 0
  (( mins >= limit )) && printf ' 停滞★'
  return 0
}

child_windows() {  # child_windows <セッション> <リポジトリ本体のパス>
  local session="$1" root="$2" parent base
  parent="$(dirname "$root")"; base="$(basename "$root")"
  tmux list-windows -t "$session" -F '#{window_index}:#{window_name}:#{pane_current_path}' 2>/dev/null \
  | while IFS=: read -r idx name path; do
      [[ "$name" == watch ]] && continue
      case "$path" in
        "$parent/$base-"*) echo "$idx:$name" ;;
        "${PARALLEL_WORKTREE_DIR:-/nonexistent}/"*) echo "$idx:$name" ;;
      esac
    done
}
