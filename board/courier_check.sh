#!/usr/bin/env bash
# 配達係の試験: 宛先のセッションへ、試験の 1 行を配達係(claude -p + ListAgents + SendMessage)で送る。
#   board/courier_check.sh <宛先のセッション名>
# 確かめること(仕様の「最初に確かめること」):
#   - 届くか(止まっている相手が起きるか)
#   - 相手の権限の設定で保留されないか
# 人が手で動かす。board のテストはこれを動かさない。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "使い方: $0 <宛先のセッション名>" >&2
  exit 2
fi
TARGET="$1" TEXT="board の配達係の試験です($(date +%H:%M:%S))。返事は要りません。" \
python3 - "$HERE" <<'PY'
import os
import sys

sys.path.insert(0, sys.argv[1])
from deliver import Courier  # noqa: E402

result = Courier().send(os.environ["TARGET"], os.environ["TEXT"])
if result.delivered:
    print(f"届いた(配達係)。宛先の窓で、試験の 1 行が届いたか・保留されていないかを見る: {os.environ['TARGET']}")
else:
    print(f"届かなかった: {result.error}")
    sys.exit(1)
PY
