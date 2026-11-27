#!/usr/bin/env bash
# 見本データで board を開く。架空のデータを一時フォルダに作り、別ポートで起動する(Ctrl-C で止めて片付ける)。
#   board/demo.sh                 # http://127.0.0.1:8793/
#   BOARD_DEMO_PORT=8795 board/demo.sh
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
python3 "$HERE/demo_grill.py" "$DIR/grill" "$GRILL_PORT" & pids+=($!)
BOARD_ROOT="$DIR/devflow" BOARD_SESSIONS_DIR="$DIR/sessions" BOARD_CONFIG="$DIR/config.json" \
BOARD_GH_FIXTURE="$DIR/gh.json" BOARD_GRILL_URL="http://127.0.0.1:$GRILL_PORT" BOARD_PORT="$PORT" \
BOARD_NO_TMUX=1 BOARD_NO_COURIER=1 \
  python3 "$HERE/server.py" & pids+=($!)
sleep 1
echo "demo: http://127.0.0.1:$PORT/ (見本データ: $DIR、Ctrl-C で止める)"
wait
