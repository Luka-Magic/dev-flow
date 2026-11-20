# dev-flow 最適化の調査レポート — テストレビューの軽量化と UI モックの前倒し

調査日: 2026-10-17
対象: `~/.claude/skills/dev-flow/`(計画 → 仕様 → チケット → テストレビュー → UI 確認 → /goal → レビュー → PR)
前回レポート: `~/projects/playground/reports/2026-09-21-test-review-research.md`(テストレビューが要る理由。本稿では重複部分を引用のみ)

凡例: **一次** = 公式ドキュメント・公式ブログ・仕様・ソースコード・論文。**二次** = まとめ記事・検索スニペット。二次だけの根拠は本文で明示する。

---

## 1. 要約

### 悩み 1: テストレビューの手間

- 承認の単位を「ケース 1 件」から「ルール(受け入れ基準)1 件 + その下の例」に上げると、問いの数が 1/3〜1/5 に減る。Example Mapping(Cucumber 公式ブログ)と Gherkin の `Rule` キーワードがこの 2 層構造の一次資料。
- 「AI が推奨を付け、人は既定を受け入れるか異議を出すだけ」は spec-kit の `/clarify`(推奨案に "yes" で採用)、Devin の計画(30 秒で自動続行)、Apache の lazy consensus(沈黙 = 同意)に同型の先例がある。
- 高リスクだけ人が見る、は ISTQB CTFL 4.0.1 §5.2.3(リスクレベル = 発生確率 × 影響でテスト範囲と優先度を決める)が根拠。
- 懸念は前回レポート §5-7 の automation complacency。既定「採用」を増やすほど、ルール単位の問いは「人が読んで決めた」形を保つ必要がある。

### 悩み 2: UI を早く見たい

- 「議論が長引く問いは、話すのをやめて使い捨てプロトタイプを作る」は mattpocock `prototype` スキルの明文(ローカル一次資料)。grill の途中で呼ぶ前提で設計されている。
- v0 公式は「静的ドキュメントではなく動くプロトタイプを土台に」「仕様を実際の操作に根ざす」と位置づけ。Figma Make・Claude Artifacts も「最初の出力は下書き、会話で直す」。
- 弊害は資料が揃っている: 作り込んだモックは判断を固定する(Shape Up「ワイヤーフレームは具体的すぎる」「具体的なモックは後工程の人を偏らせる」、NN/g「磨かれた見た目は『これで本番に』を誘う」、Dow 2010「1 案を磨き続ける fixation」)。
- 対策も同じ資料から出る: 段階を分ける(文字のブレッドボード → 粗いモック)、構造の違う 2〜3 案を並べる(Dow 2010 の並列プロトタイプ、Stitch・Pocock も複数案前提)、モックからテストを導くときは Cucumber の「UI を仮定しない」「実装が変わったら文言が変わるか」で UI 結合を除く。

---

## 2. A. テストレビューの手間を減らす方法

### 2.1 承認コストを下げる考え方(根拠つき)

| 考え方 | 何をするか | 根拠(一次) | 注意 |
|---|---|---|---|
| 粒度をルールに上げる | 「ルール(受け入れ基準)」を承認単位にし、個々の例はルールの下に並べて一覧で見る | Example Mapping: 青カード = ルール、緑カード = そのルールを示す例。例はルールなしでは文脈を失い、ルールは例なしでは曖昧 ([cucumber.io/blog](https://cucumber.io/blog/bdd/example-mapping-introduction/))。Gherkin の `Rule` キーワードは「実装すべき 1 つの業務ルール」を表し、関連シナリオを束ねる ([Gherkin Reference](https://cucumber.io/docs/gherkin/reference/)) | ルールを承認しても例の漏れは別。Example Mapping は「赤カード(未解決の問い)が残れば着手しない」で補う |
| 例を表で圧縮する | 同じルールの入力違いは `Scenario Outline` + `Examples` 表で 1 シナリオにまとめる | Gherkin Reference: 「Scenario Outline はテンプレートで複数シナリオを簡潔に表す」「Examples の各行につき 1 回実行」 | 現 test-review の「1 ケース = 1 行の横長表」と相性がよい |
| シナリオを短く | 1 例 3〜5 ステップ、数を増やしすぎない、UI や技術を仮定しない | Gherkin Reference: "Keep your scenarios short, and don't have too many"、"examples that don't make any assumptions about technology or user interface" | モック由来のケースは UI を仮定しやすい(§4.4) |
| 宣言的に書く | 操作手順(クリック・入力)ではなく振る舞いを書く。判定基準は「実装が変わったらこの文言は変わるか」 | [Writing better Gherkin](https://cucumber.io/docs/bdd/better-gherkin/): "Will this wording need to change if the implementation does?" | 現 test-review の「HOW でなく WHAT」と同じ |
| 要件を定型文で短く | EARS 5 パターン(Ubiquitous / When / While / If-Then / Where)+複合 | [Mavin, EARS](https://alistairmavin.com/ears/): 句の順序を固定し「自然言語要件の一般的な問題を減らす、あるいは無くす」。Kiro は requirements.md を EARS で書く ([kiro.dev](https://kiro.dev/docs/specs/feature-specs/)) | EARS は「要件」の記法。期待値(具体的な値)は例の側に残す |
| 差分だけ承認 | 2 ラウンド目以降は変更・追加したケースだけ再提示 | 現 test-review が既に実施。spec-kit `/clarify` も「回答を spec の該当節に書き戻して保存」を 1 問ごとに行う ([clarify.md](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md)) | — |
| リスクの高いものだけ人が見る | 発生確率 × 影響でリスクレベルを付け、高いものだけ明示承認 | ISTQB CTFL v4.0.1 §5.2.3: 「定量的アプローチではリスクレベルは発生確率 × 影響の積」「製品リスク分析の結果は、テスト範囲・テストレベル・技法とカバレッジ・工数・優先順位の決定に使う」 ([PDF](https://www.istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf)) | リスク付けを AI がやると、その判定自体が盲点になる(前回レポート §6 の「検証者と構築者の同一性」) |
| 推奨を付け、受け入れを既定にする | 各問に推奨案を添え、「yes」で推奨を採用 | mattpocock `grilling`: "Word each question so 'yes' accepts your recommended answer"(ローカル)。spec-kit `/clarify`: 推奨案 + 選択肢 2〜5、"yes"/"recommended" で採用、最大 5 問 | 既に grill-visual が実施。test-review は「採用(推奨)」が既定 |
| 異議申し立て方式 | 期限までに異議がなければ通す | Apache lazy consensus: 明示的な承認なしに進めてよいが、異議(正当な理由つき)が出たら聞く。通常 72 時間待つ ([community.apache.org](https://community.apache.org/committers/decisionMaking.html))。Devin: 計画提示後 30 秒で自動続行、複雑な作業は「Wait for my approval」を選ぶ(二次: 検索スニペット。ページ直接取得は失敗) | 「待ち時間 = 承認」は、人が読まなくても通ってしまう。前回レポート §3 の reward hacking 対策としてのレビューが空洞化する |

### 2.2 2025〜2026 年の AI エージェント開発手法: 実装前の人間レビューの置き場所

| 手法 | 人が承認するもの | 自動で進むもの | 出典 |
|---|---|---|---|
| GitHub spec-kit | 憲法 Article III(Test-First, NON-NEGOTIABLE): 「テストが書かれ、**ユーザーが検証・承認し**、失敗を確認するまで実装コードを書かない」。spec の `[NEEDS CLARIFICATION]` マーカーを `/clarify`(最大 5 問・1 問ずつ・推奨案つき)で解消。checklist は「**要件文の単体テスト**」でレビュワー所有、`[x]` は要件が通った意味で実装完了ではない | plan の gate(簡潔さ・抽象化禁止・統合優先)は LLM が通過か例外記録、tasks.md は「Task agent が実行可能」 | [spec-driven.md](https://github.com/github/spec-kit/blob/main/spec-driven.md), [clarify.md](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md), [checklist.md](https://github.com/github/spec-kit/blob/main/templates/commands/checklist.md), [GitHub Blog 2025-09-02](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/): "your role isn't just to steer. It's to verify" |
| AWS Kiro (Feature Specs) | requirements.md(EARS)→ design.md → tasks.md の各フェーズ間に承認ゲート。「Quick Spec は 3 フェーズを承認ゲートなしで自動実行」「違いは、次が生成される前に各文書をレビューするかどうか」。Design-First 版は技術設計 → 要件 → タスクの順 | 任意の「Analyze Requirements」で矛盾・曖昧・欠落を AI が検出。Plan mode は文書を作らず会話で計画し「承認すると実行が自動で始まる」 | [feature-specs](https://kiro.dev/docs/specs/feature-specs/), [best-practices](https://kiro.dev/docs/specs/best-practices/), [plan](https://kiro.dev/docs/specs/plan/) |
| Anthropic Claude Code | plan mode で計画を提示し承認(`ExitPlanMode` は「ユーザーの操作が必須」なツール)。`Ctrl+G` で計画を直接編集。「大きめの機能は `AskUserQuestion` でインタビューさせて SPEC.md を書かせ、別セッションで実装」 | 検証は「テスト・ビルド・スクリーンショット比較」をエージェントに与えて閉ループ化。`/goal` は別の小型モデルが毎ターン条件判定。Stop hook は決定論的ゲート。敵対的レビューは別 subagent | [best-practices](https://code.claude.com/docs/en/best-practices), [permission-modes](https://code.claude.com/docs/en/permission-modes), [hooks](https://code.claude.com/docs/en/hooks), [goal](https://code.claude.com/docs/en/goal) |
| OpenAI Codex | `/plan`「多段階の計画のため plan mode を切り替える」、`/goal`「永続的な目標。先に `/plan` で形を作る」、`--ask-for-approval` でコマンド実行前の承認タイミングを制御 | `codex review` で非対話レビュー | [Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)(developers.openai.com からのリダイレクト先), [Slash commands](https://learn.chatgpt.com/docs/reference/slash-commands)。計画提示後の UI 文言(「Implement this plan?」)は公式ページで確認できず |
| Cursor (Plan Mode) | 「明確化の質問 → コードベース調査 → 実装計画」の順。計画は Markdown でチャットかファイルから編集し「Click to build」 | 計画の調査部分 | [cursor.com/docs/agent/plan-mode](https://cursor.com/docs/agent/plan-mode)。モック・プロトタイプの言及なし |
| Devin (Interactive Planning) | 初期評価 → コード引用つき詳細計画を提示。既定は 30 秒待って自動続行、「Wait for my approval」を選べば止まる(二次: 検索スニペット) | 計画の生成・実行 | [docs.devin.ai interactive-planning](https://docs.devin.ai/work-with-devin/interactive-planning)(直接取得はチュートリアル索引が返り本文未確認) |
| Lovable (Plan mode) | 「Lovable builds only what you approve」。計画を編集・一部指定で修正・スキップできる | 承認後の Build | [docs.lovable.dev/features/plan-mode](https://docs.lovable.dev/features/plan-mode)。モック先行の推奨なし |

共通点: どのツールも**承認の単位は「文書 1 枚」か「計画 1 本」**で、テストケース 1 件ずつの承認を求める公式手順は見つからなかった(spec-kit Article III も「テスト群をユーザーが承認」であり件数単位の UI はない)。

### 2.3 自然言語の受け入れ基準を短く書く記法(一次資料)

| 記法 | 形 | 一次資料 | dev-flow での使いどころ |
|---|---|---|---|
| Example Mapping | 1 ストーリー(黄)/ ルール(青)/ 例(緑)/ 問い(赤)。25 分で親指投票。**セッション中に Gherkin は書かない**(会話の邪魔になる)。成熟チームでは PO が例を出し、他の 2 人が Gherkin を起こして PO がレビュー=「会話がどれだけ伝わったかのテスト」 | [Wynne 2015](https://cucumber.io/blog/bdd/example-mapping-introduction/), [cucumber.io/docs](https://cucumber.io/docs/bdd/example-mapping/) | grill の出力をルール/例/問いの 3 列に分け、赤が残る間は test-review に進まない |
| Gherkin (`Rule` / `Scenario Outline`) | Given/When/Then。`Rule` で業務ルール単位に束ねる。`Examples` 表で入力違いをまとめる。3〜5 ステップ、UI 非依存 | [Gherkin Reference](https://cucumber.io/docs/gherkin/reference/), [Better Gherkin](https://cucumber.io/docs/bdd/better-gherkin/) | 凍結ファイルの形式を「ルール見出し + 例の表」にする |
| EARS | `When <trigger>, the <system> shall <response>` 等 5 パターン | [Mavin](https://alistairmavin.com/ears/), Kiro の requirements.md | 仕様(spec)の受け入れ基準の 1 行目 |
| Canon TDD の Test List | 「カバーしたいテストシナリオの一覧」を最初に書く。「これは分析、ただし**振る舞いの**分析」「実装設計の決定を混ぜない」。実装中に見つけた項目はリストに足す | [Beck 2023](https://newsletter.kentbeck.com/p/canon-tdd) | 一覧は固定物ではなく、追加は差分承認で扱う(現ルールと整合) |
| spec-kit checklist | 「要件文の単体テスト」。要件の明確さ・完全性・曖昧さを問う項目。実装の確認には使わない | [checklist.md](https://github.com/github/spec-kit/blob/main/templates/commands/checklist.md) | test-review の自己チェック(「バグを 1 つ入れたら落ちるか」)に「要件の曖昧さ」項目を足す |

### 2.4 「AI が案を出し、人は却下・修正だけする」軽量レビューの事例

| 事例 | 仕組み | 出典 |
|---|---|---|
| spec-kit `/clarify` | AI が 10 カテゴリで曖昧さを走査し、Partial/Missing のカテゴリだけ質問化。**推奨案を先頭に置き "yes" で採用**。最大 5 問、1 問ずつ、各回答を即 spec に書き戻す | [clarify.md](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md) |
| Devin Interactive Planning | 計画を提示し、既定 30 秒で自動続行(opt-out 承認)。複雑なら「Wait for my approval」 | 二次(検索スニペット)。[公式ページ](https://docs.devin.ai/work-with-devin/interactive-planning) |
| Apache lazy consensus | 「やります」と宣言 → 72 時間異議がなければ実行。異議には正当な理由が要る | [community.apache.org](https://community.apache.org/committers/decisionMaking.html) |
| Claude Code auto mode | 人の代わりに分類器モデルが各操作をレビューし、危険なものだけ止める。「auto mode は許可プロンプトを減らすが安全を保証しない」 | [permission-modes](https://code.claude.com/docs/en/permission-modes) |
| Claude Code 敵対的レビュー | 実装 subagent とは別の fresh context の subagent が diff を計画と突合し「ギャップだけ報告」。「ギャップを探せと言われたレビュワーは健全でも何か報告するので、正しさに関わるものだけ報告させる」 | [best-practices](https://code.claude.com/docs/en/best-practices) |
| Kiro Quick Spec | 3 フェーズを承認ゲートなしで生成、後から見る | [best-practices](https://kiro.dev/docs/specs/best-practices/) |

反対意見(一次): Böckeler(martinfowler.com, 2025-10-15)は Kiro / spec-kit / Tessl を試し「spec-kit は大量の Markdown を出し、互いにもコードとも重複していた」「正直コードをレビューする方がマシ」「チェックリストは AI が解釈するので 100% 守られる保証はない」 ([記事](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html))。→ 文書を増やして承認回数を減らすのは逆効果。**承認対象の文書そのものを短くする**方向が整合する。

---

## 3. B. UI モックを計画の初期に出す方法

### 3.1 design-first / prototype-first の一次資料

| 資料 | 主張 | 出典 |
|---|---|---|
| mattpocock `prototype` スキル(ローカル) | 「プロトタイプは**問いに答える使い捨てコード**。問いが形を決める」。UI 枝: 1 ルートに**構造が根本的に異なる 3 案**(上限 5)を `?variant=` で切替、色違いは案に数えない。「grill が長引く問いは、話すのをやめて使い捨てを作り、見て、1 行で答える」。grill-me / grill-with-docs の「grill できない問い」がここに来て、答えが to-spec に流れる。全アプリのプロトタイプは別物(本番に漂流する) | `~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.3.1/skills/engineering/prototype/{SKILL,UI,LOGIC}.md`, `docs/engineering/prototype.md` |
| mattpocock `wayfinder` / `to-spec` / `to-tickets` | wayfinder のチケット種別に `prototype`(HITL)があり「どう見えるか・どう振る舞うか」が鍵の問いで使う。to-spec / to-tickets は「プロトタイプが散文より正確に決定を符号化した断片(state machine, schema 等)は inline し、出所を注記」 | 同ディレクトリ `wayfinder/SKILL.md`, `to-spec/SKILL.md`, `to-tickets/SKILL.md` |
| Vercel v0 (Prototyping) | 「プロトタイプは仮説検証に効くが、時間と資源の制約で遅れがち」「v0 は動くプロトタイプで早期・継続的な検証を可能にする」「チームは静的ドキュメントではなく共有の動くプロトタイプから作業する」「仕様を実際のユーザー操作に根ざす」 | [v0.app/docs/prototyping](https://v0.app/docs/prototyping) |
| Vercel v0 (PRD) | 「高レベルの製品アイデアを詳細な技術仕様に」。PRD とプロトタイプの前後関係は書かれていない | [v0.app/docs/prd-design](https://v0.app/docs/prd-design) |
| Figma Make | 「複雑なアプリは最初のプロンプトの前に plan mode に切り替える」→「コードを書く前にレビュー・修正できる構造化された計画」→「functional prototype or web app」を生成 | [help.figma.com](https://help.figma.com/hc/en-us/articles/31304485164695-Create-a-Figma-Make-file) |
| Claude Artifacts | 「デザイナーやエンジニアでなくてもランディングページやアプリをモックアップできる」「最初から反復する前提で。最初の版は動く下書き」 | [academy.claude.com](https://academy.claude.com/tutorials/use-artifacts-to-visualize-and-create-ai-apps-without-ever-writing-a-line-of-code)(support.claude.com からのリダイレクト先) |
| Google Stitch | 「プロンプトや画像から UI デザインとフロントエンドコードを数分で」「**複数のバリアント**を生成して比較」「Figma に貼り付けて続きを」 | [developers.googleblog.com 2025-05-20](https://developers.googleblog.com/stitch-a-new-way-to-design-uis/) |
| Lovable / Cursor / Kiro | plan mode はあるがモック先行の推奨はない。Kiro Design-First は「技術設計 → 要件」で UI ではない | 各公式(§2.2) |
| Claude Code (Artifact 機能) | 「セッションの出力を private な対話型 Web ページとして公開。端末の文字より視覚的に見たい・共有したい出力向け」 | [features-overview](https://code.claude.com/docs/en/features-overview) |
| 「vibe prototyping」 | 公式ドキュメント・論文での用語定義は**確認できず**(検索結果は実践者ブログとスキル集のみ) | — |

### 3.2 モックを早く出すことの弊害(一次資料)

| 資料 | 内容 |
|---|---|
| Shape Up ch.2 "Principles of Shaping" | 「ワイヤーフレームや高忠実度モックに直行すると、詳細を早く決めすぎる。デザイナーに創造の余地がなくなる」「数語で定義すると誰にも意味が分からない(言葉は抽象的すぎる)」→ shaped work は rough / solved / bounded ([basecamp.com/shapeup](https://basecamp.com/shapeup/1.1-chapter-02)) |
| Shape Up ch.4 "Find the Elements" | ブレッドボード(場所・操作・接続を**言葉で**書く)と fat marker sketch。「ワイヤーフレームや具体的な視覚レイアウトから始めると不要な細部に捕まる」「**具体的なモックは、あとに続く人の仕事を偏らせる**」「細部を省くことで後工程のデザイナーに余地を残す」 ([basecamp.com/shapeup](https://basecamp.com/shapeup/1.3-chapter-04)) |
| NN/g, Pernice 2016 | 「磨かれた見た目だと役員が『これで本番に』と言いやすい」「粗いプロトタイプなら明日出荷とは思われない」「時間と汗を投じるほど手放しにくい」「低忠実度は参加者の圧を下げ、否定的な反応を出しやすい(正直な反応)」 ([nngroup.com](https://www.nngroup.com/articles/ux-prototype-hi-lo-fidelity/)) |
| Dow et al. 2010 (ACM TOCHI) | 「反復は fixation(1 案を他を考えずに磨き続ける)も生む」。並列に複数案を作ってから講評を受けた群は、1 案ずつ講評を受けた群より成果(クリック率・専門家評価)が高く、案の多様性も高く、自己効力感も上がった ([PDF](http://sing.stanford.edu/cs303-sp11/papers/ParallelPrototyping2010-final.pdf)) |
| Cucumber Gherkin Reference | 「技術や UI を仮定しない例を考えること」「実装が変わっても文言が変わらない」→ **モックから起こしたケースは UI 手順になりやすい**という逆方向の弊害 |
| Buxton, Sketching User Experiences | 「スケッチは速く・安く・使い捨てで発散的、プロトタイプは収束的」は二次資料の要約のみ確認。原典の引用は**確認できず** |

### 3.3 モック → 受け入れ基準 → テスト、の順序に根拠はあるか

- **順序を直接規定する一次資料は見つからなかった。** 近いのは v0 の「プロトタイプで仕様を実際の操作に根ざす」と、Pocock の「プロトタイプの答えを to-spec に inline する」(モックが spec の入力になる)。
- Example Mapping は「会話(ルール・例)→ 後で Gherkin」の順で、セッション中にテスト文を書かない。モックは例を具体化する補助と読める。
- Kiro の Design-First は「設計 → 要件」だが対象は技術設計(アーキテクチャ、擬似コード)で UI モックではない。
- 弊害側: モック先行だとケースが UI 手順(クリック・ボタン名)に結びつき、Cucumber の「UI を仮定しない」「宣言的」に反する。モックを「正」にすると Shape Up の言う「後工程を偏らせる」が起きる。
- 整理すると: **モックは「例」を見える化する道具、受け入れ基準の正は言葉(EARS / Rule)に置く**、が複数の一次資料と整合する線。

---

## 4. C. 両方に関わるもの

### 4.1 承認回数そのものを減らす設計の是非

| 立場 | 内容 | 出典 |
|---|---|---|
| 回数を減らす選択肢を公式に用意 | Kiro: Feature Specs(フェーズ毎に承認)と Quick Spec(承認なしで 3 文書生成)。「違いは次が生成される前に各文書をレビューするかどうか」「明示的な承認チェックポイントが有効なチーム向け」 | [kiro.dev best-practices](https://kiro.dev/docs/specs/best-practices/) |
| 1 枚に集約 | Claude Code: インタビュー → SPEC.md 1 枚 → 新セッションで実装。「最も役立つ spec は自己完結で、ファイルとインターフェースを挙げ、範囲外を述べ、end-to-end の検証手順で終わる」 | [best-practices](https://code.claude.com/docs/en/best-practices) |
| 1 回の問いの束 | Claude Code `AskUserQuestion` は「1〜4 問の選択式」を 1 回で出す。grilling スキルは「フロンティア(前提が揃った問い)を 1 ラウンドにまとめて聞く」 | [hooks](https://code.claude.com/docs/en/hooks), ローカル `grilling/SKILL.md` |
| 逆に 1 問ずつ | spec-kit `/clarify` は「EXACTLY ONE question at a time」最大 5 問 | [clarify.md](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md) |
| 文書の量が負荷 | Böckeler: 「大量の Markdown のレビューは冗長」「承認しても実装が従う保証はない」 | [martinfowler.com](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) |
| 承認は小さく頻繁に | Example Mapping: 1 ストーリー 25 分、ほぼ隔日。Claude Code: 「早めに頻繁に軌道修正」「2 回直して直らなければ /clear」 | [Wynne 2015](https://cucumber.io/blog/bdd/example-mapping-introduction/), [best-practices](https://code.claude.com/docs/en/best-practices) |

読み取り: 「1 枚にまとめる」ことを肯定する一次資料(Claude Code の SPEC.md、Kiro Quick Spec)と、「1 枚が重くなるとレビューが崩れる」一次資料(Böckeler)の両方がある。**回数より 1 回あたりの読む量**を制御するのが共通の含意。

### 4.2 Claude Code 公式機能のうち「人間の承認ポイント」に関係するもの

| 機能 | 承認ポイント設計との関係 | 出典 |
|---|---|---|
| plan mode / `ExitPlanMode` | 計画提示 → 承認で編集可に。`ExitPlanMode` と `AskUserQuestion` は「ユーザー操作が必須」で、hook が `allow` を返すだけでは通らない(`updatedInput` に回答を入れる必要)。`-p` 非対話では permission host がないと提示されない | [hooks](https://code.claude.com/docs/en/hooks), [permission-modes](https://code.claude.com/docs/en/permission-modes) |
| `AskUserQuestion` | 1〜4 問の選択式。端末で答える前提。`dontAsk` モードでは拒否される。→ スマホ・非同期の質問票(grill-visual)を置き換えるものではない | 同上 |
| Hooks | 「CLAUDE.md の指示は助言、hook は決定論的」「ガードレールは hook に置く」。`PreToolUse` の `permissionDecision: deny` で編集を止める(現行の凍結フックと同じ)。`Stop` hook は exit 2 でターン終了を止める。プロンプト型 hook は `/goal` の基盤 | [features-overview](https://code.claude.com/docs/en/features-overview), [hooks](https://code.claude.com/docs/en/hooks) |
| `/goal` | 別の小型モデルが毎ターン「未達 / 達成 / 不可能」を判定。良い条件は「測定可能な終了状態 1 つ + 証明方法 + 変えてはいけない制約」。4,000 字まで | [goal](https://code.claude.com/docs/en/goal) |
| Subagents | 「fresh context のレビュワーは diff と基準だけを見る」敵対的レビュー。実装者と採点者を分ける | [best-practices](https://code.claude.com/docs/en/best-practices) |
| Skills | 「ワークフローは skill、毎回必ずは hook」。副作用のある skill は `disable-model-invocation: true` | [features-overview](https://code.claude.com/docs/en/features-overview) |
| Artifact | セッション出力を対話型 Web ページとして公開。スマホ閲覧に向く | 同上 |

---

## 5. 現在の dev-flow への適用案

前提(コーディネータ補足): UI モックは**grill の質問票の各問に埋め込み、質問と一緒に見ながら答える**形。別ページでモックだけを先に出す形ではない。

### 案 1: テストレビューの単位を「ルール + 例」の 2 層にする(Step 4)

- **変更**: 質問票の 1 問 = 1 ルール(EARS 1 行 or Gherkin `Rule` 見出し)。本文に、そのルールを示す例を現行の横長表(振る舞い / 入力 / 期待結果 / 分類)で列挙。選択肢は「ルールを採用 / 例を直す(メモ) / ルールごと削除」。凍結ファイル `docs/test-cases/<slug>.md` も「ルール見出し + 例の表」構造に変える。
- **狙い**: 問いの数を例の数からルールの数へ(目安 1/3〜1/5)。人は「この業務ルールで完成と言えるか」を読み、例は網羅の確認に目を通すだけ。
- **根拠**: Example Mapping(ルール/例/問い)、Gherkin `Rule` と `Scenario Outline`、Beck の Test List は「振る舞いの分析」、Cucumber「例は少なく短く」。
- **懸念**: 例の 1 件ずつのミューテーション思考(「バグを 1 つ入れたら落ちるか」)は AI の自己チェックに寄る。凍結フックは「ファイル単位」なので変更不要だが、check-pr.sh の「全ケース実装済みか」の突合はルール/例の両方を数える必要がある。

### 案 2: 既定「採用」+ リスク別の明示承認 + 「残り全部採用」(Step 4)

- **変更**: AI が各ルールにリスク(影響 × 不確かさ、高/中/低)と理由を付ける。高だけ「採用 / 修正 / 削除」の明示選択を求め、中・低は既定を「採用」にして質問票に折りたたみ表示。画面下に「未回答をすべて推奨どおりにする」操作を置き、回答 JSON にはどれが明示選択でどれが既定採用かを残す。
- **狙い**: 「承認」から「異議申し立て」へ重心を移す。既定を受け入れるコストをゼロに近づけ、人の注意を高リスクに集める。
- **根拠**: ISTQB §5.2.3(リスクで範囲と優先度を決める)、spec-kit `/clarify`("yes" で推奨採用)、grilling スキル("yes" で推奨を受け入れる言い回し)、Apache lazy consensus、Devin の opt-out 承認。
- **懸念**: 前回レポート §5-7 の automation complacency(常に信頼できるシステムへの過信で検出率が落ちる)。対策として、既定採用の件数を質問票の冒頭に出す、ラウンドごとに「低リスクのうち 1 件だけ抜き打ちで明示承認を求める」など、人が読む契機を残す。リスク判定を AI がやる以上、その判定がテストと同じ盲点を持つ(前回 §6)。時間経過での自動承認(Devin/Apache 型)は**採らない**。回答ファイルが凍結解除の鍵なので、既定採用も必ず送信を経る。

### 案 3: 仕様の受け入れ基準とテストケースを同じ質問票で 1 回に(Step 2 + 4)

- **変更**: 仕様化(Step 2)の「seam の合意」と、ルール単位のテストケース(案 1)を同じ質問票の別タブに載せ、1 回の送信で spec と test-cases を同時に固定する。チケットが小さい(tracer bullet 1 本)ときだけ。大きいときは現行どおり分ける。
- **狙い**: ラウンド往復を 1 回減らす。seam の問いとルールの問いは前提が同じなので同じフロンティアに置ける(grilling の規律と整合)。
- **根拠**: Claude Code「SPEC.md 1 枚に検証手順まで含める」、Kiro「レビューを各文書の前に挟むかどうかは選択」、Example Mapping「1 ストーリー 25 分」。
- **懸念**: Böckeler の「Markdown が多いと読めない」。1 枚の問いの数が 10 を超えるならタブを分けるか案 1 で圧縮してから。seam の変更がテストケース全体を無効にするので、seam の問いは先頭に置き、seam を変えたら残りは次ラウンドに回す(フロンティアの規律)。

### 案 4: grill の質問票にモックを埋め込む(Step 1)— 段階・粒度・固定しすぎ対策

- **どの段階で何を作るか**(2 段階に分ける):

| ラウンド | 粒度 | 作り方 | 質問票での見せ方 |
|---|---|---|---|
| 1(問題と範囲が決まる前) | **文字のブレッドボード**: 画面名 / その画面でできる操作 / 遷移先、を箇条書き。見た目なし | Shape Up の breadboarding。AI が会話から起こす | 問いの本文に箇条書きで添える。問いは「この画面と操作で足りるか」「要らない画面は」 |
| 2 以降(画面の論点が出たとき) | **粗い HTML モック**を、論点のある画面だけ。**構造の異なる 2〜3 案**。色・余白・書体は既定(プロジェクトのテーマを流用するが、見た目を問わない) | Pocock `prototype` UI 枝(構造が違う案、色違いは案ではない)。`~/.agent/diagrams/assets/<topic>/index.html` に案ごとのタブ(ui-check と同じ 1 ページ・タブ式) | 各問の `image` に案のスクショ(スマホ幅 390px)、本文に案ごとの iframe/リンク。問いは「A / B / C のどれに近いか、または B のヘッダ + C の一覧のような組合せ」。選択肢は構造の違いを言葉で説明する |

- **「動く HTML」はいつ**: 論点が状態遷移(入力途中で戻ったら?、エラー時は?)のときだけ、Pocock の LOGIC 枝(状態パネルつき単一 HTML、ボタンで状態が変わる)を 1 ファイル作る。見た目の論点では静的でよい。全画面を動かすことはしない(Pocock「全アプリのプロトタイプは別物で本番に漂流する」)。
- **固定しすぎへの対策**(資料の根拠つき):
  1. **複数案を並べる**(Dow 2010: 並列 → 多様性と成果が上がり fixation を避ける。Stitch も「複数バリアントで比較」)。1 案だけ見せない。
  2. **粗さを保つ**(NN/g: 粗いと正直な否定が出やすく「本番に」と誤解されない。Shape Up: 細部を省いて後工程に余地)。質問票に「これは問いに答えるための使い捨て。実装に流用しない」と毎回明記(ui-check の既存ルールを grill にも適用)。
  3. **聞くことを絞る**(ui-check の既存ルール「色・余白は聞かない。配置・導線・情報の有無・操作の意味を聞く」を grill でも踏襲)。
  4. **正は言葉に置く**: モックで決まった点は Pocock to-spec の流儀で「決定を符号化した断片」(画面一覧・遷移・必須項目)だけを spec に書き、モック自体は `~/.agent/diagrams/assets/` に残して spec からリンク。
  5. **モック→テストケースの導出時に UI 結合を除く**: Cucumber の「実装が変わったらこの文言は変わるか」「技術や UI を仮定しない」をセルフチェックに追加。「ボタン X を押す」は「ユーザーは◯◯できる」に書き直す。
- **根拠**: Pocock `prototype`(grill が長引く問いは作って見せる。grill-me の「grill できない問い」の受け皿)、v0(静的文書より動くプロトタイプで早期検証)、Shape Up ch.2/ch.4、NN/g 2016、Dow 2010。
- **懸念**: モック生成のトークンと時間(Pocock: 問いを狭く、1 回の作業で答えが出る範囲に)。grill のラウンドが 1 つ増える可能性(ブレッドボードはラウンド 1 に同居できる)。スマホで 3 案を見比べる負荷(1 画面 1 問、案はタブで切替、スクショは縦長 1 枚ずつ)。grill-visual の `image` は「クリックで原寸」なので、画面名のタブ + スクショで足りるかを 1 度試す必要がある。

### 案 5: ui-check を「差分確認」に縮める(Step 5)

- **変更**: 案 4 で grill 中にモックを承認した画面は、テスト承認後の ui-check では**変更があった画面だけ**再提示。info タブの「承認済みテストケースとの対応表」は残す。変更がなければ ui-check は対応表の確認 1 問で終える。
- **狙い**: 往復を 1 回減らす。grill で見たモックと実装前モックの二重確認を避ける。
- **根拠**: Kiro「各文書の前にレビューを挟むかは選択」、v0「プロトタイプが仕様を根ざす」、Pocock「答えは spec に流れ、プロトタイプは primary source として残す」。
- **懸念**: テストレビューで仕様が動いた場合、grill 時のモックが古くなる。「テストレビューで変わったルールに紐づく画面」を機械的に特定する必要があり、案 1 の「ルール見出し」に画面名を持たせると対応表が引ける。`frontend` ラベルの check-pr.sh 条件(`answers/ui-*` の存在)は、grill 側の回答ファイルも鍵として認めるよう調整が要る。

---

## 6. 参考 URL 一覧

### 一次資料(公式・仕様・論文・ローカル)

- Cucumber, Matt Wynne "Introducing Example Mapping" (2015): https://cucumber.io/blog/bdd/example-mapping-introduction/
- Cucumber Docs "Example Mapping": https://cucumber.io/docs/bdd/example-mapping/
- Cucumber "Gherkin Reference": https://cucumber.io/docs/gherkin/reference/
- Cucumber "Writing better Gherkin": https://cucumber.io/docs/bdd/better-gherkin/
- Alistair Mavin "EARS": https://alistairmavin.com/ears/
- Kent Beck "Canon TDD" (2023): https://newsletter.kentbeck.com/p/canon-tdd
- ISTQB CTFL Syllabus v4.0.1 §5.2.3: https://www.istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf
- GitHub spec-kit "spec-driven.md": https://github.com/github/spec-kit/blob/main/spec-driven.md
- GitHub spec-kit "clarify.md": https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md
- GitHub spec-kit "checklist.md": https://github.com/github/spec-kit/blob/main/templates/commands/checklist.md
- GitHub Blog, Den Delimarsky "Spec-driven development with AI" (2025-09-02): https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
- AWS Kiro Docs "Feature Specs": https://kiro.dev/docs/specs/feature-specs/
- AWS Kiro Docs "Specs best practices": https://kiro.dev/docs/specs/best-practices/
- AWS Kiro Docs "Plan mode": https://kiro.dev/docs/specs/plan/
- Claude Code "Best practices": https://code.claude.com/docs/en/best-practices
- Claude Code "Permission modes"(plan mode): https://code.claude.com/docs/en/permission-modes
- Claude Code "Hooks reference": https://code.claude.com/docs/en/hooks
- Claude Code "/goal": https://code.claude.com/docs/en/goal
- Claude Code "Extend Claude Code"(機能比較表): https://code.claude.com/docs/en/features-overview
- OpenAI Codex "Developer commands": https://learn.chatgpt.com/docs/developer-commands?surface=cli
- OpenAI Codex "Slash commands": https://learn.chatgpt.com/docs/reference/slash-commands
- Cursor Docs "Plan Mode": https://cursor.com/docs/agent/plan-mode
- Devin Docs "Interactive Planning": https://docs.devin.ai/work-with-devin/interactive-planning(本文の直接取得は失敗。検索スニペットのみ)
- Lovable Docs "Plan mode": https://docs.lovable.dev/features/plan-mode
- Vercel v0 Docs "Prototyping": https://v0.app/docs/prototyping
- Vercel v0 Docs "PRD design": https://v0.app/docs/prd-design
- Figma Help "Create a Figma Make file": https://help.figma.com/hc/en-us/articles/31304485164695-Create-a-Figma-Make-file
- Claude Academy "Use artifacts to visualize and create AI apps": https://academy.claude.com/tutorials/use-artifacts-to-visualize-and-create-ai-apps-without-ever-writing-a-line-of-code
- Google Developers Blog "Introducing Stitch" (2025-05-20): https://developers.googleblog.com/stitch-a-new-way-to-design-uis/
- Basecamp "Shape Up" ch.2 Principles of Shaping: https://basecamp.com/shapeup/1.1-chapter-02
- Basecamp "Shape Up" ch.4 Find the Elements: https://basecamp.com/shapeup/1.3-chapter-04
- Nielsen Norman Group, Kara Pernice "UX Prototypes: Low Fidelity vs. High Fidelity" (2016): https://www.nngroup.com/articles/ux-prototype-hi-lo-fidelity/
- Dow et al. "Parallel Prototyping Leads to Better Design Results, More Divergence, and Increased Self-Efficacy", ACM TOCHI 17(4), 2010: http://sing.stanford.edu/cs303-sp11/papers/ParallelPrototyping2010-final.pdf (DOI 10.1145/1879831.1879836)
- Apache "Decision Making / Lazy Consensus": https://community.apache.org/committers/decisionMaking.html
- Birgitta Böckeler "Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl" (martinfowler.com, 2025-10-15): https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
- mattpocock-skills v1.3.1(ローカル): `~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.3.1/skills/engineering/prototype/`、`.../wayfinder/SKILL.md`、`.../to-spec/SKILL.md`、`.../to-tickets/SKILL.md`、`.../productivity/grilling/SKILL.md`、`.../docs/engineering/prototype.md`

### 二次資料(入口として使用、根拠にはしていない)

- Devin Interactive Planning の 30 秒自動続行・「Wait for my approval」: 検索スニペット(docs.devin.ai 各言語版)
- Buxton "Sketching User Experiences" の要約: uxmatters 書評、xplane 等
- Human Factors International newsletter(Dow 2010 の要約): https://www.humanfactors.com/newsletters/parallel_prototyping.html

### 確認できなかったこと

- 「vibe prototyping」「prototype-first」を定義した公式文書・論文
- Buxton 原典の該当箇所の文言
- Codex が計画提示後に出す確認 UI の正確な文言
- 「モック → 受け入れ基準 → テスト」の順序を直接規定する一次資料(近い記述は v0・Pocock to-spec のみ)
- Gojko Adzic "Specification by Example" の「Refining the specification」章の具体的な処方(章題の存在のみ確認)
