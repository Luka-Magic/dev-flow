# 調査メモ: チケットの大きさと「その場で進める」基準(2026-11-28)

`dev-flow/references/ticket-size.md` の根拠。一次資料を 2026-11-28 に確かめた。確かめられなかった点は末尾に書く。

## 要点

1. **切りすぎは、縦切りの手順でいちばん多く報告される問題である。**
   Matt Pocock の to-tickets の文書は、3 行の変更に 12 チケットができた例を挙げ、「Over-decomposition is the most reported problem with this skill」と書く。対処は、公開前の確認でまとめるよう頼むことである。同じ文書は「変更全体が 1 つのコンテキストに収まるなら、このスキルは要らない。そのまま実装する」とも書く。
   https://www.aihero.dev/skills-to-tickets (2026-08-24 更新)
2. **細かく切ることは、モデルの弱さへの対処だった面がある。**
   Anthropic の 2025-11-26 の記事は、エージェントが一度にやりすぎるので 1 機能ずつ進めることを勧めた。2026-03-24 の記事は、新しいモデルでは作業の分割を外しても 2 時間以上まとまって動いたと報告し、「手順の部品は、モデルが単独でできないことについての仮定を表す」と書く。
   https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
   https://www.anthropic.com/engineering/harness-design-long-running-apps
3. **大きく渡すと、律速は人のレビューに移る。**
   DORA は「AI は大きなコードを速く作る。巨大な PR を作る誘惑を避ける」と書く。Faros AI の調査(1,255 チーム)では、AI をよく使うチームで PR の大きさが 154% 増え、レビュー時間が 91% 増えた(相関であり、因果ではない)。Google のレビューの手引きは、100 行は妥当、1000 行は大きすぎ、基準は「自己完結した 1 つの変更」とする。
   https://dora.dev/capabilities/working-in-small-batches/
   https://www.faros.ai/blog/ai-productivity-paradox-report-2025
   https://google.github.io/eng-practices/review/developer/small-cls.html
4. **切る基準は「独立に終えられ、確かめられること」である。**
   to-tickets は、各チケットが単独で見せられる・確かめられることを求める。判定の問いは「終わったら何を見せられるか」。Shape Up は、作業をタスクではなく「互いに独立に終えられるまとまり」に分ける。
   https://basecamp.com/shapeup/3.3-chapter-12
5. **小さな変更に重い手順をかけるのは害である。**
   Birgitta Böckeler は、小さなバグ修正が 4 つのストーリーと 16 個の受け入れ基準になった例を挙げ、変更の大きさと種類に応じた手順が要ると書く。Claude Code の公式の手引き(2026-07 時点の版)は「差分を 1 文で説明できるなら、計画を飛ばす」と書いていた。Cursor の手引きも、素早い変更は計画なしでよいとする。
   https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
   https://web.archive.org/web/20260715084717id_/https://code.claude.com/docs/en/best-practices.md
   https://cursor.com/blog/agent-best-practices
6. **その場でやる範囲が黙って広がるのを防ぐ。**
   Kent Beck は、AI との作業が脱線した兆候に「頼んでいない機能(妥当な次の一歩でも)」を挙げる。
   https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes

## この文書で決めたこと(資料にないもの)

- **始める前にユーザーに一言確認する。** これを定めた一次資料は見つからなかった。6 の歯止めとして、このフローで足した。
- **差分の目安を「数百行」とした。** レビューの研究は人が書いたコードが対象で、AI が書いた差分でも同じかは確かめられていない。数字は目安で、規則ではない。

## 確かめられなかったこと

Google のレビューの実態を調べた論文(2018)の本文、SmartBear の数字の元データ、Kent Beck『Tidy First?』の本文、受け入れ基準の数の上限を定めた資料。
