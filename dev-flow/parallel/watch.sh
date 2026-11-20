#!/usr/bin/env bash
# tmux の各窓で動いている Claude の様子を 1 画面にまとめる。
#
#   watch.sh <セッション名> [秒] [停滞とみなす分]   # 例: watch.sh birdlog 5 10
#   tmux の窓 "watch" で動かしておくと、Ctrl-b w で一覧を見に行ける
#
# 状態の見分け方と、入力待ちが続いた時間の数え方は state.sh に置いてある
# （parallel.sh --status と同じ判定）。入力待ちが <停滞とみなす分> を超えた窓には
# 「停滞★」が付く。中心セッションはこれをユーザーに報告する。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=state.sh
source "$HERE/state.sh"

SESSION="${1:?tmux セッション名を指定してください}"
INTERVAL="${2:-5}"
export PARALLEL_STALL="${3:-${PARALLEL_STALL:-10}}"
SELF="$(tmux display-message -p '#{window_name}' 2>/dev/null || echo watch)"

while true; do
  clear
  printf '%s  セッション %s（%s 秒ごと・入力待ち %s 分で停滞★・Ctrl-c で終了）\n' \
    "$(date '+%H:%M:%S')" "$SESSION" "$INTERVAL" "$PARALLEL_STALL"
  while IFS=: read -r idx name; do
    [[ "$name" == "$SELF" ]] && continue
    text="$(pane_text "$SESSION" "$idx")"
    st="$(state_of "$text")"
    mins="$(idle_minutes "$SESSION" "$name" "$st")"
    label="$st"
    [[ "$st" == "入力待ち" && "$mins" -gt 0 ]] && label="$st ${mins} 分"
    label="$label$(stall_mark "$mins")"
    body="$(grep -vE '^\s*$' <<<"$text" | tail -4)"
    printf '\n\033[1m── %s: %s  [%s]\033[0m\n' "$idx" "$name" "$label"
    sed 's/^/  /' <<<"$body" | cut -c1-110
  done < <(tmux list-windows -t "$SESSION" -F '#{window_index}:#{window_name}' 2>/dev/null)
  sleep "$INTERVAL"
done
