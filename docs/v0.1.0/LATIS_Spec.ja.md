# LATIS Spec

**Layered Agreement, Traceability & Intent System**  
**An Agreement Engine.**

## 1. この文書の目的

この文書は、LATIS を何として定義するか、その境界と中核機能を明確にするための仕様である。

LATIS は、ソフトウェア開発における合意事項・意図・根拠・未解決事項・スコープを構造化して保持し、問い合わせに応じて関連する合意の束を返す **合意エンジン** である。

LATIS は、文書エディタそのものではない。プロジェクト管理スイートでもない。AI の出力を正本化する装置でもない。

LATIS の責務は、**問い合わせを受け取り、既存の合意構造に照らして、構造化された回答を返すこと** にある。

---

## 2. LATIS の位置付け

### 2.1 LATIS は何をするか

LATIS は次を行う。

- 合意・意図・根拠・未解決事項・スコープを構造化して保持する
- proposal を既存の合意構造に照らして評価する
- conflict、dependency、impact、scope 近傍を返す
- 人間またはエージェントに対して compact context bundle を返す
- 履歴・来歴・状態遷移を追跡可能にする

### 2.2 LATIS は何をしないか

LATIS は次を本体責務としない。

- 長文仕様書の編集体験そのもの
- 万能なタスク管理
- バージョン管理システムの代替
- 単なるグラフ可視化ツール
- 特定エージェント専用の暗黙知を本体に埋め込むこと

### 2.3 LATIS と文書の関係

LATIS は文書を否定しないが、文書を意味の唯一の保存場所とは見なさない。

- `spec.md` などの Markdown 文書は、人間可読な表現である
- 文書は import / export / review / diff の媒体である
- 実効的な合意状態は LATIS 上の構造化モデルによって保持される

したがって、文書に何かが書かれていることと、それが LATIS 上で有効な合意であることは同一ではない。

---

## 3. 基本概念

### 3.1 Proposal Seed

人間のざっくりした要求、会話、外部仕様、メモなど、まだ仕様として正規化されていない入力。

例:

- 「検索結果はもっと新しい順にしたい」
- 外部から取り込んだ OpenSpec 文書
- 会議メモから抽出された変更要求

Proposal Seed は、LATIS に対する打診の入力である。

### 3.2 Proposal

Proposal Seed を、LATIS 上で評価可能な形に正規化したもの。

Proposal はまだ確定仕様ではない。LATIS による照合と、人間の判断を経て状態を持つ。

### 3.3 Agreement

現在有効な決定事項。実装、レビュー、影響分析の基点となる。

### 3.4 Intent

その合意や変更が何を達成しようとしているかを示す目的情報。

### 3.5 Rationale

なぜその決定が必要か、なぜその形が選ばれたかを説明する根拠情報。

### 3.6 Question

未解決の論点、判断待ちの問い、合意を阻害している保留事項。

### 3.7 Scope

機能、関心、領域、設計境界などを表す構造ノード。単なるタグではない。探索、集約、影響分析、局所表示の基盤となる。

### 3.8 Artifact

Markdown 文書、設計メモ、議論ログ、外部仕様など、構造の出所または表現先となる成果物。

---

## 4. 中核原則

### 4.1 合意優先

LATIS が第一に扱うのは、文章そのものではなく、合意の状態である。

### 4.2 先に照会、あとで確定

変更要求はまず LATIS に打診される。文書化や有効化はその後に行われる。

### 4.3 文書は proposal または rendering である

`spec.md` は人間にとって重要な成果物だが、LATIS の構造化モデルを経ずに単独で正本性を主張しない。

### 4.4 トレーサビリティ優先

影響・依存・競合は、推測ではなく明示的な関係として保持されるべきである。

### 4.5 AI 互換だが AI 依存ではない

エージェントは LATIS を活用できるべきだが、LATIS の中核データモデルはエージェント固有の暗黙知やブラックボックス生成に依存してはならない。

---

## 5. 状態モデル

LATIS は少なくとも次の状態を扱えるべきである。

- `draft` — まだ十分に正規化されていない
- `proposed` — 提案として登録された
- `accepted` — 有効な合意として採択された
- `conflicted` — 既存合意と衝突している
- `incomplete` — 必要情報が不足している
- `rejected` — 却下された
- `superseded` — 別の合意に置き換えられた
- `stale` — 現状と乖離している可能性がある

状態は二値ではなく、proposal の扱いを豊かにするための運用面でもある。

---

## 6. データモデル

### 6.1 Nodes

第一級の意味単位を保持する。

代表フィールド:

- `id`
- `kind`
- `title`
- `body`
- `state`
- `created_at`
- `updated_at`

代表 kind:

- `agreement`
- `proposal`
- `intent`
- `rationale`
- `question`
- `scope`
- `artifact`
- `task`

### 6.2 Relations

ノード間の型付き有向関係を保持する。

代表フィールド:

- `id`
- `from_node_id`
- `to_node_id`
- `relation_kind`
- `state`
- `priority`
- `is_inferred`

代表 relation_kind:

- `contains`
- `depends_on`
- `conflicts_with`
- `supports`
- `scoped_to`
- `governs`
- `specializes`
- `exception_to`
- `supersedes`
- `originates_from`

### 6.3 Provenance

ノードや関係の出所、理由、導入者を保持する。

代表フィールド:

- `id`
- `target_type`
- `target_id`
- `actor`
- `source_ref`
- `reason`
- `created_at`

### 6.4 Revisions

変更履歴を保持する。

代表フィールド:

- `id`
- `target_type`
- `target_id`
- `change_type`
- `snapshot`
- `created_at`

---

## 7. 問い合わせモデル

LATIS の本体機能は問い合わせ受付と回答である。少なくとも次の問い合わせ種別を持てるべきである。

### 7.1 Change Consultation

入力された Proposal Seed または Proposal を既存合意に照らして評価する。

期待される返答:

- 関連する agreement
- conflict 候補
- dependency 候補
- exception / supersede 候補
- 関連 intent / rationale
- 同 scope の open question
- 影響を受けうる scope / artifact
- 推奨アクション

### 7.2 Scope Brief

指定 scope に関する短い構造的要約を返す。

期待される返答:

- scope summary
- key agreements
- unresolved questions
- relevant intents
- nearby scopes

### 7.3 Impact Report

ある node または proposal の変更がどこに波及するかを返す。

期待される返答:

- downstream agreements
- related artifacts
- blocking questions
- governance / dependency path

### 7.4 Schema Summary

ある scope や artifact に関係するスキーマ情報・制約情報を整理して返す。

期待される返答:

- entities
- fields
- constraints
- governing agreements
- examples or references

### 7.5 Context for Task

実装またはレビューのために必要最小限の context bundle を返す。

期待される返答:

- target agreement / proposal
- directly connected constraints
- nearby rationale
- open questions in same scope
- short scope summary

---

## 8. レスポンス原則

LATIS の応答は、長文をそのまま返すことより、問い合わせに必要な構造を返すことを優先する。

最低限、応答は次の性質を持つべきである。

- **局所性**: 問いに必要な範囲だけ返す
- **説明可能性**: なぜその node や relation が返ったかがわかる
- **トレーサビリティ**: 出所や関連根拠に辿れる
- **状態性**: accepted / conflicted などの状態を含む
- **人間可読性**: UI や Markdown に自然に落とし込める

---

## 9. Retrieval 原則

LATIS はデフォルトで文書全体をコンテキストとして返さない。

代わりに、対象に応じて compact context bundle を組み立てる。

最小 bundle には、たとえば次が含まれる。

- 対象 agreement または proposal
- 直接つながる決定・制約
- 関連 rationale
- 同 scope の open question
- 近傍の impact candidate
- 短い scope summary

LATIS の目的の一つは、**より少ないテキストで十分にすること** である。

---

## 10. 文書との同期

`spec.md` などの文書は、LATIS の外部表現である。

そのため、文書と LATIS の関係は次のように定義される。

- 文書は Proposal または Agreement を表現できる
- 文書上の status は、LATIS の判定結果を書き戻したものであるべきである
- 文書が単独で `accepted` を主張してはならない
- stable ID により、文書上の項目と LATIS 上の node は対応づけられるべきである

---

## 11. Skillpack と公共的問い合わせ面

LATIS 本体は、特定のエージェント専用のスキルを内蔵しなくてよい。

ただし初期段階では、LATIS をうまく使うための問い合わせ作法が必要になる可能性がある。この作法群を本仕様では **Skillpack** と呼ぶ。

Skillpack は本質ではない。LATIS の問い合わせ面が十分に公共的・明示的になれば、Skillpack は薄い標準クライアント実装へと縮退していくのが望ましい。

本仕様の立場は次の通りである。

- LATIS 本体は合意エンジンである
- Skillpack は過渡期の利用補助である
- 将来的には、汎用エージェントが自然に使える問い合わせ面を持つことが望ましい

---

## 12. 初期実装方針

現実的な初期実装としては、次を想定する。

- canonical storage としての SQLite
- lexical retrieval のための FTS
- optional な vector search
- Markdown の import / export
- scope-aware なローカルグラフ表示

この段階では inspectable で軽量であることを優先する。

---

## 13. 非目標

初期プロトタイプにおいて、LATIS は次を目標としない。

- 完全自動の真理判定
- 万能な自然言語理解
- すべての運用フローの自動化
- 巨大で抽象的な統合プラットフォーム化

LATIS はまず、**問い合わせに対して構造的に正しい答えを返せる合意エンジン** として成立すべきである。
