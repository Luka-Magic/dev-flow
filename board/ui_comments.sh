#!/usr/bin/env bash
# ui-comments の専用サーバーを起こす(冪等)。serve.sh と demo.sh が BOARD_UI_COMMENTS=1 のときに呼ぶ。
#   board/ui_comments.sh            # 動いていなければ起動する
#   board/ui_comments.sh --stop     # 止める
# ポート: BOARD_UI_COMMENTS_PORT(既定 4321。4319 は RoomLab、4320 は grill-visual のお試し用)
# 保存先: このリポジトリの .ui-comments/(git に入れない)。実物と見本の board が同じ専用サーバーを使い、
#         画面ごとの名前(data-project)で分ける。board が 127.0.0.1 で中継するので、tailnet の名前は渡さない。
# 道具: ~/.claude/skills/ui-comments/src/server.mjs(BOARD_UI_COMMENTS_SRC で変えられる)
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${BOARD_UI_COMMENTS_PORT:-4321}"
SRC="${BOARD_UI_COMMENTS_SRC:-$HOME/.claude/skills/ui-comments/src/server.mjs}"
DIR="$(dirname "$HERE")/.ui-comments"
LOG="$DIR/.server.log"
up() { timeout 2 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/overlay.js" 2>/dev/null; }
port_pid() { ss -ltnp "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

if [ "${1:-}" = "--stop" ]; then
  pid="$(port_pid)"
  if [ -n "$pid" ] && up; then kill "$pid" && echo "stopped: ui-comments(pid $pid)"; else echo "not running: ui-comments"; fi
  exit 0
fi
if up; then echo "already running: ui-comments http://127.0.0.1:$PORT/"; exit 0; fi
if [ -n "$(port_pid)" ]; then echo "ERROR: port $PORT は別のアプリが使っている。BOARD_UI_COMMENTS_PORT で変える" >&2; exit 1; fi
if [ ! -f "$SRC" ] || ! command -v node >/dev/null; then
  echo "ERROR: ui-comments の道具($SRC)か node が無い" >&2
  exit 1
fi
mkdir -p "$DIR"
# 道具は「直接実行されたか」を実ファイルのパスで判定するので、リンクを解決してから渡す
setsid nohup node "$(readlink -f "$SRC")" --dir "$DIR" --port "$PORT" >>"$LOG" 2>&1 </dev/null &
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if up; then echo "started: ui-comments http://127.0.0.1:$PORT/(保存先 $DIR)"; exit 0; fi
  sleep 0.3
done
echo "ERROR: ui-comments を起動できなかった。$LOG を見る" >&2
exit 1
