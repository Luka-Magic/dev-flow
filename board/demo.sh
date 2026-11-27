#!/usr/bin/env bash
# 見本データで board を開く。架空のデータを一時フォルダに作り、別ポートで起動する(Ctrl-C で止めて片付ける)。
#   board/demo.sh                 # http://127.0.0.1:8793/
#   BOARD_DEMO_PORT=8795 board/demo.sh
#   BOARD_UI_COMMENTS=1 board/demo.sh   # ui-comments を差し込む(専用サーバーは実物と共用。止めない)
# 実物の記録・セッション・GitHub・grill-visual には触らない。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${BOARD_DEMO_PORT:-8793}"
GRILL_PORT="${BOARD_DEMO_GRILL_PORT:-8794}"
DIR="$(mktemp -d "${TMPDIR:-/tmp}/board-demo.XXXXXX")"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$DIR"; }
trap cleanup EXIT INT TERM

python3 "$HERE/demo_data.py" "$DIR" >/dev/null
if [ "${BOARD_UI_COMMENTS:-}" = "1" ] && ! "$HERE/ui_comments.sh"; then
  echo "WARN: ui-comments を起こせないので、差し込まずに起動する" >&2
  export BOARD_UI_COMMENTS=0
fi
python3 "$HERE/demo_grill.py" "$DIR/grill" "$GRILL_PORT" & pids+=($!)
BOARD_ROOT="$DIR/devflow" BOARD_SESSIONS_DIR="$DIR/sessions" BOARD_CONFIG="$DIR/config.json" \
BOARD_GH_FIXTURE="$DIR/gh.json" BOARD_GRILL_URL="http://127.0.0.1:$GRILL_PORT" BOARD_PORT="$PORT" \
BOARD_NO_TMUX=1 BOARD_NO_COURIER=1 BOARD_UI_COMMENTS_PROJECT="${BOARD_UI_COMMENTS_PROJECT:-devflow-board-demo}" \
  python3 "$HERE/server.py" & pids+=($!)
sleep 1
echo "demo: http://127.0.0.1:$PORT/ (見本データ: $DIR、Ctrl-C で止める)"
wait
