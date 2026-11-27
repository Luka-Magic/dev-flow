#!/usr/bin/env bash
# 子から来た PR 案を、中心セッションが機械的に検証する。
#
#   check-pr.sh <リポジトリ本体のパス> <ブランチ名> [issue番号]
#
# 見るもの（1 行ずつ OK / NG で出す。NG が 1 つでもあれば終了コード 1）:
#   1 統合ブランチ   … origin/main を含んでいるか（rebase 済みか）
#   2 テストの diff  … .skip / .only / xfail / mark.skip が足されていないか
#   3 テストケース   … docs/test-cases/*.md が固定後に変わっていないか
#                      （変わっているなら answers/tr-*.json の再承認がその変更より新しいか）
#   4 attribution    … コミット本文に Co-Authored-By / Claude-Session / Generated with [Claude Code] が無いか
#   5 UI 確認        … 計画の grill の回答で depth-ui が detail / full なら answers/ui-*<番号>* があるか
#                      （深さの回答が無い古い issue は frontend ラベルで判定）
#
# 環境変数: CHECK_PR_BASE（既定 origin/main）、ANSWERS_DIR（既定 ~/.agent/diagrams/answers）
set -uo pipefail

ROOT="${1:-}"; BRANCH="${2:-}"; ISSUE="${3:-}"
if [[ -z "$ROOT" || -z "$BRANCH" ]]; then
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
BASE="${CHECK_PR_BASE:-origin/main}"
ANSWERS="${ANSWERS_DIR:-$HOME/.agent/diagrams/answers}"
ng=0

say()  { printf '%-14s %s\n' "$1" "$2"; }
okay() { say "$1" "OK${2:+ — $2}"; }
bad()  { say "$1" "NG — $2"; ng=1; }

git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || { echo "git リポジトリではない: $ROOT" >&2; exit 2; }
git -C "$ROOT" fetch --quiet origin >/dev/null 2>&1

REF="$BRANCH"
git -C "$ROOT" rev-parse --verify --quiet "$REF^{commit}" >/dev/null || REF="origin/$BRANCH"
if ! git -C "$ROOT" rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
  echo "ブランチが見つからない: $BRANCH（$ROOT）" >&2; exit 2
fi
if ! git -C "$ROOT" rev-parse --verify --quiet "$BASE^{commit}" >/dev/null; then
  echo "基準ブランチが見つからない: $BASE" >&2; exit 2
fi
MB="$(git -C "$ROOT" merge-base "$BASE" "$REF")"

# --- 1 統合ブランチを含むか
if git -C "$ROOT" merge-base --is-ancestor "$BASE" "$REF"; then
  okay "1 統合ブランチ" "$BASE を含む"
else
  behind="$(git -C "$ROOT" rev-list --count "$REF..$BASE" 2>/dev/null || echo '?')"
  bad "1 統合ブランチ" "$BASE より $behind コミット遅れ。子へ「git fetch origin && git rebase origin/main」を指示する"
fi

# --- 2 テストの diff に skip / only が足されていないか
test_files="$(git -C "$ROOT" diff --name-only "$MB" "$REF" \
  | grep -Ei '(^|/)(tests?|spec|__tests__)/|\.(test|spec)\.[jt]sx?$|(^|/)test_[^/]+\.py$|_test\.py$' || true)"
if [[ -z "$test_files" ]]; then
  okay "2 テスト diff" "テストファイルの変更なし"
else
  weakened="$(git -C "$ROOT" diff "$MB" "$REF" -- $test_files \
    | grep -E '^\+[^+].*(\.skip|\.only|xfail|mark\.skip|@unittest\.skip)' || true)"
  if [[ -z "$weakened" ]]; then
    okay "2 テスト diff" "skip / only / xfail の追加なし"
  else
    bad "2 テスト diff" "テストを弱めた行がある: $(head -3 <<<"$weakened" | tr '\n' ' ' | cut -c1-160)"
  fi
fi

# --- 3 承認済みテストケースが固定後に変わっていないか
changed_cases="$(git -C "$ROOT" diff --name-only "$MB" "$REF" -- 'docs/test-cases/*.md' || true)"
if [[ -z "$changed_cases" ]]; then
  okay "3 テストケース" "変更なし"
else
  detail=""
  while read -r f; do
    [[ -n "$f" ]] || continue
    stem="$(basename "$f" .md)"
    log="$(git -C "$ROOT" log --format='%at' "$MB..$REF" -- "$f" || true)"
    count="$(grep -c . <<<"$log" || true)"
    if git -C "$ROOT" cat-file -e "$MB:$f" 2>/dev/null; then
      modified=true                      # 元からあったファイルを触った
    else
      [[ "$count" -gt 1 ]] && modified=true || modified=false   # 固定コミット 1 本だけなら新規作成
    fi
    if ! $modified; then
      detail+="${detail:+, }$stem: 新規に固定しただけ"
      continue
    fi
    # 書き換えのコミットごとに「直前のコミットより後・このコミットより前」に回答があるかを見る
    # （フックは編集時に「回答 > 最終コミット」を見る。コミット後は必ず回答の方が古くなるので、区間で照合する）
    mapfile -t times < <(tac <<<"$log")          # 古い順
    ok=true
    for ((i=1; i<${#times[@]}; i++)); do
      prev="${times[i-1]}"; cur="${times[i]}"
      [[ "$prev" =~ ^[0-9]+$ && "$cur" =~ ^[0-9]+$ ]] || { ok=false; break; }
      found=false
      for a in "$ANSWERS"/tr-"$stem"-round-*.json; do
        [[ -e "$a" ]] || continue
        m="$(stat -c %Y "$a" 2>/dev/null || echo 0)"
        if (( m > prev && m <= cur )); then found=true; break; fi
      done
      $found || { ok=false; break; }
    done
    if $ok; then
      detail+="${detail:+, }$stem: 変更あり・再承認あり"
    else
      bad "3 テストケース" "$stem を固定後に書き換えているが、直前のコミットからその書き換えまでの間に answers/tr-$stem-round-*.json の回答が無い。別 issue の質問票で承認した場合は中心が手で確かめる"
      detail=""
      break
    fi
  done <<<"$changed_cases"
  [[ -n "$detail" ]] && okay "3 テストケース" "$detail"
fi

# --- 4 コミット本文の attribution
attr="$(git -C "$ROOT" log "$MB..$REF" --format='%B' \
  | grep -E '^[ \t>]*(Co-Authored-By:|Claude-Session:)|Generated with \[Claude Code\]' || true)"
if [[ -z "$attr" ]]; then
  okay "4 attribution" "なし"
else
  bad "4 attribution" "コミット本文に $(head -1 <<<"$attr" | cut -c1-60) がある。rebase で落としてもらう"
fi

# --- 5 UI 確認: 計画の grill で選んだ UI の深さ（depth-ui）で要否を決める
# 計画の grill の回答のうち、topic に issue 番号を含み（<project>-<番号>-… / <番号>-…）、
# depth-ui を答えた最新のものを読む。tr-* / ui-* の回答は対象外。値は none / detail / full。
depth_ui() {
  python3 - "$ANSWERS" "$1" <<'PY'
import glob, json, os, re, sys
answers_dir, issue = sys.argv[1], sys.argv[2]
pat = re.compile(r'(^|-)' + re.escape(issue) + r'-')
best = None
for path in glob.glob(os.path.join(answers_dir, '*-round-*.json')):
    name = os.path.basename(path)
    if name.startswith(('tr-', 'ui-')):
        continue
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        continue
    topic = data.get('topic') or name.rsplit('-round-', 1)[0]
    value = (data.get('answers') or {}).get('depth-ui')
    if not pat.search(topic) or not isinstance(value, list) or not value:
        continue
    mtime = os.path.getmtime(path)
    if best is None or mtime > best[0]:
        best = (mtime, str(value[0]), name)
if best:
    print(best[1] + ' ' + best[2])
PY
}

ui_answer_for() {
  local a
  for a in "$ANSWERS"/ui-*"$1"*; do [[ -e "$a" ]] && { basename "$a"; return; }; done
}

if [[ -z "$ISSUE" ]]; then
  okay "5 UI 確認" "issue 番号の指定なし（省略）"
else
  read -r depth depth_file <<<"$(depth_ui "$ISSUE")"
  if [[ -n "${depth:-}" ]]; then
    case "$depth" in
      none)
        okay "5 UI 確認" "grill で UI の深さ「なし」（$depth_file）。不要" ;;
      detail|full)
        hit="$(ui_answer_for "$ISSUE")"
        if [[ -n "$hit" ]]; then
          okay "5 UI 確認" "UI の深さ「$depth」。$hit がある"
        else
          bad "5 UI 確認" "grill で UI の深さ「$depth」（$depth_file）なのに $ANSWERS/ui-*$ISSUE* が無い。ui-check を飛ばしている。子へ差し戻す"
        fi ;;
      *)
        bad "5 UI 確認" "depth-ui の値「$depth」が想定外（none / detail / full）。$depth_file を手で確かめる" ;;
    esac
  else
    # 深さを決める前に始めた issue: 従来どおり frontend ラベルで判定する
    labels="$( (cd "$ROOT" && gh issue view "$ISSUE" --json labels --jq '.labels[].name') 2>/dev/null || true)"
    if [[ -z "$labels" ]]; then
      say "5 UI 確認" "不明 — 深さの回答が無く、gh issue view #$ISSUE も読めなかった（手で確かめる）"
    elif ! grep -qx 'frontend' <<<"$labels"; then
      okay "5 UI 確認" "深さの回答なし・frontend ラベルなし（不要）"
    else
      hit="$(ui_answer_for "$ISSUE")"
      if [[ -n "$hit" ]]; then
        okay "5 UI 確認" "深さの回答なし・frontend ラベル。$hit がある"
      else
        bad "5 UI 確認" "深さの回答が無く frontend ラベルなのに $ANSWERS/ui-*$ISSUE* が無い。ui-check を飛ばしている。子へ差し戻す"
      fi
    fi
  fi
fi

echo
if [[ $ng -eq 0 ]]; then
  echo "全部 OK。PR 案をユーザーに提示してよい。"
else
  echo "NG があるので、まず子へ差し戻す。"
  exit 1
fi
