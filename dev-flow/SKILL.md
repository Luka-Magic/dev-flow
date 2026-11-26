---
name: dev-flow
description: 新機能や大きめの変更を、計画 → 仕様 → チケット → テストレビュー → UI 確認 → 実装前の説明 → 自律実装 → レビューの順で進める開発フロー。「フローで進めて」「dev-flow で」で使う。計画の最初に UI モックとテストレビューの深さを選ぶので、小さな変更も同じ入口から軽く通せる。
---

# dev-flow

新機能や大きめの変更を、「何をもって完成とするか」を人が決めてから実装に入る開発フローである。
AI の自律実装(/goal)では、テストが事実上の完了条件になる。だから完了条件(ルールと例)だけは人がレビューし、コードは全部読まなくてよい。この考え方で全体を組んである。

## 用語

- **grill**: 計画を問い詰める質問票。grill-visual スキルでブラウザに出し、回答を自動で回収する。
- **深さ**: この題材で UI モックとテストレビューをどこまでやるか。計画の最初の 2 問で選ぶ([references/depth.md](references/depth.md))。
- **seam**: テストが叩く公開境界。HTTP の入口、CLI、公開関数など。
- **ルールと例**: 受け入れ基準の形。ルールは 1 行の業務ルール、例はそれを示す具体的なテストケース。test-review スキルが作る。
- **凍結**: 承認済みのルールと例を `docs/test-cases/<slug>.md` に保存し、実装中は編集しないこと。

## 手順

各ステップは「終わり」の条件を満たしてから次へ進む。

1. **計画**。grill-visual で問い詰める。質問票の JSON に `"kind": "計画"` を書く。ラウンド 1 の先頭 2 問で深さを選び、深さに関係なく聞ける問いを同じラウンドに続けて並べる(往復を減らすため)。画面の構造が論点になり、UI の深さが `full` なら、議論を続けずに粗いモックを質問票に埋め込む([references/mock-in-plan.md](references/mock-in-plan.md))。CONTEXT.md や ADR が要る題材は domain-modeling スキルの規律に従う。
   終わり: 深さが決まり、決めることが尽きた。
2. **仕様化**。会話を spec に合成する(mattpocock の to-spec 準拠)。seam を人と合意する。seam は既存のものを優先し、できるだけ高い位置に置き、数は最少(理想は 1)にする。モックで決まった画面一覧・遷移・必須項目は言葉で spec に書き、モックはリンクで添える。
   終わり: spec と seam に人の OK がある。
3. **チケット分割**。tracer bullet の縦切りで分ける(to-tickets 準拠)。git リポジトリなら issue にする。複数の issue を同時に走らせるなら [parallel/README.md](parallel/README.md) の運用に従う。git でない playground などは `<app>/docs/tickets/NN-<slug>.md` に 1 チケット 1 ファイルで置く。
   終わり: チケットが縦切りで並び、順番が決まった。
4. **テストレビュー**。チケットごとに、実装の前に test-review スキルを実行する。テストの深さが `full` のときのステップで、`light` と `none` の扱いは references/depth.md にある。
   終わり: 全ルールが採用になり、凍結ファイルがある。
5. **UI 確認**。UI の深さが `detail` か `full` のとき、ui-check スキルを実行する。計画で構造を見た画面は、テストレビューで仕様が変わったものだけ再提示する。「直す」が出たら、仕様 → 影響するルールと例の再承認 → モックの再提示、を両方が採用になるまで繰り返す。
   終わり: 全画面が「このまま」になった。
6. **実装前の説明**。どの深さでも行う。決めたことを html スキルで 1 枚の文書にし、末尾で「これで良いか」を聞く([references/pre-implementation-brief.md](references/pre-implementation-brief.md))。
   終わり: 「このまま進める」の回答が届いた。
7. **自律実装**。test-review が出す /goal テンプレで実行する。1 例ずつ red → green で進める(tdd スキル準拠)。承認済みの一覧があっても、テストコードは 1 例ずつ書く。テストを一括で先に生成する横切り(horizontal slicing)は、Pocock と t-wada の両系譜がアンチパターンとしている。
   終わり: 全ルールの全例が green。
8. **レビュー**。この順に見る。①テストファイルの diff(skip・削除・アサーションの弱体化がないか)。②凍結ファイルとの突合(全ルールの全例が実装されているか)。③code-review スキル。git なら PR を作り、人が承認してマージする。
   終わり: マージされた。

## 原則

- 凍結ファイル(`docs/test-cases/*.md`)は実装中に編集しない。変更が要るときは実装を止め、人に差し戻して再承認を取る。
- テストの skip・削除・アサーションの弱体化は「失敗」として扱う。/goal の完了条件文にもそう書く(test-review のテンプレに含まれる)。
- テストの実行はプロジェクトの規定に従う(playground 系は docker compose のコンテナ内)。
- 指示は許可リストで書く(「このファイルのみ編集可」)。禁止で書くより守られる。

## 参照

- [references/depth.md](references/depth.md): 深さの 2 問、選択肢ごとのフロー、推奨の目安、ラウンドの組み方
- [references/mock-in-plan.md](references/mock-in-plan.md): 計画の grill にモックを埋め込む段階と見せ方
- [references/pre-implementation-brief.md](references/pre-implementation-brief.md): 実装前の説明文書の中身と回答欄
- [parallel/README.md](parallel/README.md): worktree と tmux で複数 issue を同時に進める運用(強制の仕組みは parallel/enforcement.md)
- `docs/2026-10-17-research-test-review-and-mocks.md`(このリポジトリ): ルール単位のテストレビューと、早いモックの根拠
- `~/projects/playground/reports/2026-09-21-test-review-research.md`: テストレビューが要る理由(reward hacking の実証データ)
