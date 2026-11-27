#!/usr/bin/env bash
# board を http://127.0.0.1:8792/ で動かす(冪等)。ループバック限定で、外へは公開しない。
#   board/serve.sh             # 動いていなければ起動する
#   board/serve.sh --restart   # 止めて起動し直す(server.py などを直したあと。board.html は再起動不要)
#   board/serve.sh --stop      # 止める
# ポートは BOARD_PORT(既定 8792)、記録の置き場所は BOARD_ROOT(既定 ~/.agent/devflow)。
# BOARD_UI_COMMENTS=1 なら、画面に ui-comments を差し込み、専用サーバー(ui_comments.sh、既定 4321)も起こす。
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${BOARD_PORT:-8792}"
ROOT="${BOARD_ROOT:-$HOME/.agent/devflow}"
LOG="$ROOT/.server.log"
URL="http://127.0.0.1:$PORT/"
mkdir -p "$ROOT"

is_board() { timeout 3 curl -fsS "$URL" 2>/dev/null | grep -q '<title>dev-flow board</title>'; }
port_pid() { ss -ltnp "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

stop() {
  local pid
  pid="$(port_pid)"
  if [ -z "$pid" ]; then echo "not running: $URL"; return 0; fi
  if ! is_board; then echo "ERROR: port $PORT は board 以外が使っている(pid $pid)。止めない" >&2; return 1; fi
  kill "$pid" && echo "stopped: board(pid $pid)"
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -z "$(port_pid)" ] && return 0; sleep 0.3; done
}

case "${1:-}" in
  --stop) stop; exit $? ;;
  --restart) stop || exit 1 ;;
  "") ;;
  *) echo "使い方: $0 [--restart|--stop]" >&2; exit 2 ;;
esac

if [ "${BOARD_UI_COMMENTS:-}" = "1" ]; then "$HERE/ui_comments.sh" || exit 1; fi

if is_board; then echo "already running: $URL"; exit 0; fi
if [ -n "$(port_pid)" ]; then
  echo "ERROR: port $PORT は別のアプリが使っている。BOARD_PORT で変える" >&2
  exit 1
fi

BOARD_PORT="$PORT" BOARD_ROOT="$ROOT" setsid nohup python3 "$HERE/server.py" >>"$LOG" 2>&1 </dev/null &
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if is_board; then echo "started: $URL"; exit 0; fi
  sleep 0.3
done
echo "ERROR: 起動できなかった。$LOG を見る" >&2
exit 1
