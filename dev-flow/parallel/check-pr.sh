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
#   5 UI 確認        … issue 番号があり frontend ラベルが付いていれば answers/ui-*<番号>* があるか
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

# --- 5 frontend ラベルなら ui-check の回答があるか
if [[ -z "$ISSUE" ]]; then
  okay "5 UI 確認" "issue 番号の指定なし（省略）"
else
  labels="$( (cd "$ROOT" && gh issue view "$ISSUE" --json labels --jq '.labels[].name') 2>/dev/null || true)"
  if [[ -z "$labels" ]]; then
    say "5 UI 確認" "不明 — gh issue view #$ISSUE が読めなかった（ラベルを手で確かめる）"
  elif ! grep -qx 'frontend' <<<"$labels"; then
    okay "5 UI 確認" "frontend ラベルなし（不要）"
  else
    hit=""
    for a in "$ANSWERS"/ui-*"$ISSUE"*; do [[ -e "$a" ]] && hit="$a" && break; done
    if [[ -n "$hit" ]]; then
      okay "5 UI 確認" "$(basename "$hit") がある"
    else
      bad "5 UI 確認" "frontend ラベルなのに $ANSWERS/ui-*$ISSUE* が無い。ui-check を飛ばしている。子へ差し戻す"
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
