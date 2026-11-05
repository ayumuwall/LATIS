# LATIS Concerns

## 1. 懸念事項

### 1.1 優先順位と例外規則の曖昧さ
`governs` と `exception_to` の優先順位、同一スコープ内の競合処理が明文化されていないため、AI/人間の判断が揺れやすい。

### 1.2 影響分析（Impact）の境界不明確さ
どの relation_kind をどの深さまで追うか、スコープ境界をどう扱うかが不明確なため、影響範囲が過大・過小になりやすい。

### 1.3 Proposal 正規化の責務の分散
Operation ではエージェントが proposal compiler になる一方、API は `normalized_proposal` を返す前提で、正規化ルールの所在が曖昧。

### 1.4 実運用での入力コスト
合意・意図・根拠・質問を十分に入力しないと制度が回らないが、初期運用では入力負荷が壁になる可能性がある。

### 1.5 例外と supersede の乱用
例外や置換が増えると、合意体系が肥大化し、検索や相談結果の一貫性が崩れるリスクがある。

---

## 2. 解決案

### 2.1 優先順位規則の明文化
`governs` と `exception_to` の優先順位、同一スコープ内の競合処理、`supersedes` の適用条件を 1 枚の運用規約として固定する。

### 2.2 影響分析の境界定義
Impact の走査対象 relation_kind、深さ上限、スコープ越境の可否を定義し、`proposal-impact` の応答に「判定根拠（ルール参照）」を含める。

### 2.3 Proposal 正規化ルールの整理
scope_hint の扱い、intent/rationale の必須性、最低限の入力要件を Spec に集約し、API/Operation で参照する。

### 2.4 入力コスト低減の導線
最初は必須フィールドを最小化し、consultation の結果から不足情報を返すことで段階的に補完する運用を採用する。

### 2.5 例外・置換の健全化
例外や置換は明示的な理由・期限・適用範囲を求め、一定期間で review する運用を用意する。

---

## 3. 補足提案

現状の懸念の多くは、モデル自体の破綻というより、`Spec` / `API` / `Operation` の規範がまだ十分に固定されていないことに起因している。したがって、大きなモデル変更よりも、責務分担と判定規則の明文化を先に進めるのが妥当である。

### 3.1 文書整理の優先順位

まず次の順に整理する。

1. `Spec` に規範的ルールを追加する
2. `API` に説明責任のための応答項目を追加する
3. `Operation` に初期運用の最低限ルールを追加する
4. 例外・置換に対する軽いガードレールを設ける

### 3.2 `Spec` に追加すべき規範

`Spec` には少なくとも次を一節として追加する。

- `governs` / `exception_to` / `supersedes` の判定順
- 同一 scope 内の競合解決規則
- Impact の探索対象 relation_kind、深さ上限、scope 越境条件
- Proposal Seed と Proposal の責務分担
- `scope_hint`、`intent`、`rationale` の扱い

### 3.3 `API` に追加すべき応答項目

`proposal-impact` の応答には、診断結果だけでなく判定理由も含める。

- `rule_refs` — 適用した規則への参照
- `impact_paths` — どの relation を辿って影響判定したか
- `missing_requirements` — 不足している入力情報
- `normalization_notes` — Proposal 正規化で補完・解釈した内容

### 3.4 `Operation` に追加すべき初期運用ルール

初期 consultation では、必須入力を最小限に抑える。

- 最低限は `title` / `body` と、あれば `scope_hint_ids`
- `intent` / `rationale` は consultation 時点では任意
- 不足情報は consultation の結果として返し、段階的に補完する
- `accept_as_exception` / `accept_as_supersede` では `rationale` を実質必須とする

### 3.5 例外・置換に対するガードレール

例外や置換の乱用を避けるため、最低限次を要求する。

- `reason`
- `applicable_scope_ids`
- `review_at`
- 必要なら `expires_at`

### 3.6 実装寄りの暫定ルール

プロトタイプ段階では、次の暫定ルールを置くと判断が安定しやすい。

- Proposal Seed の責務は人間またはエージェントが持つ
- `normalized_proposal` の責務は LATIS Core が持つ
- Impact は既定で `depends_on` / `governs` / `supports` / `scoped_to` を深さ 2 まで辿る
- scope 越境は明示 relation がある場合に限る
- `exception_to` は局所的な絞り込みや限定適用に使う
- `supersedes` は既存の有効な合意を置換する場合にのみ使う
- 部分変更や限定変更は、原則として `supersedes` より scope の絞り込みで扱う

### 3.7 まとめ

懸念の中心は、発想の誤りではなく、判定規約の未固定にある。したがって、先に必要なのは大規模な機能追加ではなく、判断ルールと責務境界の明文化である。
