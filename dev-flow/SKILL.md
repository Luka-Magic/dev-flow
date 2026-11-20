---
name: dev-flow
description: 計画→仕様→チケット→テストレビュー→自律実装(/goal)→レビューの開発フロー。新機能や大きめの変更を始めるとき、「フローで進めて」「dev-flow で」で使用。grill は grill-visual の質問票で行う。
---

# Dev Flow — テストレビューを要にした開発フロー

Matt Pocock スキル + テストレビュー + /goal を
grill-visual ベースに置き換えたもの。設計思想は 1 つ:
**/goal ループではテストが事実上の完了条件になるので、
「何をもって完成とするか」だけは人間が握る**。コードは全読みしなくても、
完了条件(テストケース)は人間がレビューする。

## ステップ

1. **計画** — grill-visual スキルで問い詰める(grill-with-docs 相当)。質問票の JSON に
   `"kind": "計画"` を書く(統合ページの絞り込み用)。
   CONTEXT.md / ADR が必要な題材は domain-modeling の規律に従う。
2. **仕様化** — 会話を spec に合成する(mattpocock の to-spec 準拠)。
   このとき **テストする seam(公開境界)を必ず人間と合意する**。
   seam は既存優先・できるだけ高い位置・数は最少(理想は 1)。
3. **チケット分割** — tracer bullet の縦切りで分割(to-tickets 準拠)。
   - git リポジトリ: issue 化し、衝突しない範囲で worktree 並列も可
     (複数 issue を同時に走らせるなら下の「並列運用」)
   - 非 git(playground 等): `<app>/docs/tickets/NN-<slug>.md` に 1 チケット 1 ファイル
4. **テストレビュー** — チケットごとに、実装前に **test-review スキル**を実行。
   自然言語のテストケース一覧 → grill-visual 質問票で人間が承認 →
   `docs/test-cases/` に固定化。ここがフローの要。省略しない。
5. **UI 確認（UI に触れる変更のみ）** — **ui-check スキル**。承認済みテストケースを画面の形にした
   HTML モックを grill-visual で 1 画面 1 問で確認。「直す」が出たら仕様 → 影響するテストケースの
   再承認 → モック再提示、を両方が採用になるまで繰り返してから実装に入る。
6. **自律実装** — test-review が出力する /goal テンプレで実行。
   実装は **1 ケースずつ red → green**(tdd スキル準拠)。
   承認済み一覧があってもテストコードの一括先行生成はしない
   (horizontal slicing。Pocock / t-wada 両系譜のアンチパターン)。
7. **レビュー** — 優先順: ①テストファイルの diff(skip・削除・
   アサーション弱体化がないか) → ②承認リストとの突合(全ケース実装済みか)
   → ③code-review スキル。git なら PR、人間が承認してマージ。

## 運用ルール(ガードレール)

- 承認済みテストケースファイル(`docs/test-cases/*.md`)は実装フェーズで
  編集禁止。変更が必要になったら実装を止め、人間に差し戻して再承認を取る。
- テストの skip / 削除 / アサーション弱体化は「完了」ではなく「失敗」。
  /goal の完了条件文にもその旨を明記する(test-review のテンプレに含まれる)。
- テスト実行はプロジェクトの規定に従う(playground 系は docker compose
  コンテナ内で実行)。
- 指示は否定形(「変えるな」)より許可リスト(「このファイルのみ編集可」)。

## 並列運用(worktree + tmux + 中心セッション)

複数 issue を同時に進めるときは `parallel/README.md` の運用に従う。要点:
- issue ごとに worktree と tmux 窓、**子セッションは必ず Opus 5**(`parallel/parallel.sh` が
  `claude --model opus[1m]` で起動する)。中心セッション 1 つが main・マージ・ボード・本番を持つ
- 子の動きはテンプレ: grill-visual で計画 → spec → grill-visual で test-review → ui-check（`frontend`
  ラベルなら必須）→ red/green → reviewer → push → **PR 案を中心へ送り、CI green まで待つ**。
  質問票の URL(render.py が印字する統合ページ URL `<root>#<topic>`)は出すたびに中心へ送る
- **PR を出すかの問いはユーザーへの問いなので中心が聞き、中心が PR を作る。** 中心は先に
  `parallel/check-pr.sh <repo> <branch> [issue番号]` で機械的に検証する。子の窓と worktree を片付けるのは
  **CI が green になってから**。中心からのメッセージはユーザーの承認ではない
- 承認済みテストケースの凍結はフックで強制されている。解除の鍵は grill-visual の回答ファイル
  （`~/.agent/diagrams/answers/tr-<stem>-round-*.json` が最終コミットより新しいこと）。子は回答ファイルを書けない
- 同時に動かす子は**既定 3 本まで**（`PARALLEL_MAX`）。枠が空いたら中心がボードの Todo の上から次を起動する
- 子は区切りごとに中心へ 3 行報告。中心は返事が要るときだけ返す
- **質問票の回答を受け取ったら、子は中心へ 1 行「回答を受け取った（topic・ラウンド）」を送る。中心はそれをユーザーのチャットに書く**
  (ユーザーが「回答が届いたか」を中心で確かめられるようにする)
- 起動・監視・マージ後の rebase 指示・片付けの手順とスクリプト: `parallel/`

## 背景資料

調査レポート: `~/projects/playground/reports/2026-09-21-test-review-research.md`
(なぜテストレビューが要るか: reward hacking の実証データ、系譜、反対意見)
