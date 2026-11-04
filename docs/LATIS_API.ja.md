# LATIS API

**Prototype API Specification**  
**For a headless Agreement Engine**

## 1. この文書の目的

この文書は、プロトタイプ段階の LATIS に対して、実装可能で境界の明確な API を定義する。

LATIS は headless な **Agreement Engine** であり、主な責務は次の二つである。

- 現在の合意状態に関する、意味つきの view を返す
- proposal の打診に対して、影響範囲・競合・依存を返す

描画や長文編集は外部に委ねる。Graph UI は LATIS 本体に内蔵されなくてもよいが、LATIS の query-specific view を描く first-party client として強く最適化されるべきである。

---

## 2. 設計原則

### 2.1 Headless First

LATIS は UI を持たない前提で設計する。UI、CLI、IDE integration、agent はすべて外部クライアントである。

### 2.2 Query-Specific View

LATIS が返すのは raw graph dump ではなく、問い合わせに応じた **意味つきの部分グラフ** である。

### 2.3 Consultation is Ephemeral

proposal の打診は原則として永続化しない。

- 打診中は `consult_proposal` により診断結果のみを返す
- 採択された場合のみ `apply_proposal` により変更を永続化する

### 2.4 Accepted Change is Durable

永続化されるのは proposal セッションそのものではなく、採択された変更の結果である。

- node / relation の追加・更新
- provenance
- revisions
- 必要に応じて source artifact 参照

### 2.5 Human-in-the-Loop

LATIS は診断と構造化された回答を返すが、`Proceed / Revise / Abort` を決めるのは人間または上位運用である。

---

## 3. API レイヤ

プロトタイプでは、API を次の 4 系統に分ける。

1. **Views** — 現在状態の意味つき view を返す
2. **Consultations** — proposal 打診に対する影響診断を返す
3. **Actions** — 採択された変更を永続化する
4. **History / Context** — 履歴およびエージェント向け compact context を返す

---

## 4. 共通ルール

### 4.1 Versioning

すべての API は `/v1/` をプレフィックスに持つ。

### 4.2 Content Type

- Request: `application/json`
- Response: `application/json`

### 4.3 Time Format

日時は ISO 8601 を使う。

### 4.4 IDs

主要 ID は文字列とし、プロトタイプでは UUID または stable ID 互換文字列を許容する。

例:

- `ag_search_003`
- `scope_public_search`
- `q_sorting_002`
- `rev_2026_03_27_001`

### 4.5 Response Envelope

プロトタイプでは次の envelope を使う。

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "api_version": "v1"
  },
  "errors": []
}
```

エラー時:

```json
{
  "ok": false,
  "data": null,
  "meta": {
    "api_version": "v1"
  },
  "errors": [
    {
      "code": "SCOPE_NOT_FOUND",
      "message": "scope_public_search was not found"
    }
  ]
}
```

---

## 5. 共通データ shape

### 5.1 Node

```json
{
  "id": "ag_search_003",
  "kind": "agreement",
  "title": "検索結果は関連度順で表示する",
  "body": "Public search result ordering defaults to relevance.",
  "state": "accepted",
  "scope_ids": ["scope_public_search"],
  "created_at": "2026-03-27T10:00:00+09:00",
  "updated_at": "2026-03-27T10:00:00+09:00"
}
```

### 5.2 Relation

```json
{
  "id": "rel_001",
  "from_node_id": "ag_search_014",
  "to_node_id": "ag_search_003",
  "relation_kind": "supersedes",
  "state": "accepted",
  "is_inferred": false
}
```

### 5.3 Provenance

```json
{
  "id": "prov_001",
  "target_type": "node",
  "target_id": "ag_search_014",
  "actor": "user:ayumu",
  "source_ref": "artifact:spec_md#AG-SEARCH-014",
  "reason": "User accepted proposal after consultation.",
  "created_at": "2026-03-27T11:30:00+09:00"
}
```

### 5.4 Revision

```json
{
  "id": "rev_2026_03_27_001",
  "target_type": "node",
  "target_id": "ag_search_014",
  "change_type": "create",
  "snapshot": {
    "state": "accepted"
  },
  "created_at": "2026-03-27T11:30:00+09:00"
}
```

---

## 6. Views API

## 6.1 GET `/v1/views/state`

現在の内部状態から、条件に応じた意味つき部分グラフを返す。

### 用途

- Graph UI が現在状態を描画する
- scope 単位の局所地形を見る
- node 近傍の relation を確認する

### Query Parameters

- `scope_id?`
- `node_id?`
- `depth?` — 既定値 `1`
- `include_kinds?` — カンマ区切り
- `include_relation_kinds?` — カンマ区切り
- `states?` — 既定値 `accepted`

`scope_id` または `node_id` の少なくとも一方を要求する。

### Response Example

```json
{
  "ok": true,
  "data": {
    "view_kind": "state",
    "focus": {
      "scope_id": "scope_public_search"
    },
    "nodes": [
      {
        "id": "scope_public_search",
        "kind": "scope",
        "title": "Public Search",
        "state": "accepted"
      },
      {
        "id": "ag_search_003",
        "kind": "agreement",
        "title": "検索結果は関連度順で表示する",
        "state": "accepted"
      },
      {
        "id": "q_search_002",
        "kind": "question",
        "title": "ピン留め項目との優先順位",
        "state": "proposed"
      }
    ],
    "relations": [
      {
        "id": "rel_101",
        "from_node_id": "ag_search_003",
        "to_node_id": "scope_public_search",
        "relation_kind": "scoped_to",
        "state": "accepted"
      }
    ],
    "summary": {
      "accepted_agreements": 1,
      "open_questions": 1
    }
  },
  "meta": {
    "api_version": "v1"
  },
  "errors": []
}
```

---

## 6.2 GET `/v1/views/scope-brief/{scope_id}`

指定した scope の短い構造的要約を返す。

### 用途

- 人間向け要約
- エージェントが scope の全体像を掴む
- Graph UI のサイドパネル表示

### Response Fields

- `scope`
- `summary`
- `key_agreements`
- `unresolved_questions`
- `relevant_intents`
- `nearby_scopes`

### Response Example

```json
{
  "ok": true,
  "data": {
    "scope": {
      "id": "scope_public_search",
      "title": "Public Search"
    },
    "summary": "公開検索の結果表示と検索体験を扱う scope。既定の並び順は関連度順。",
    "key_agreements": [
      {
        "id": "ag_search_003",
        "title": "検索結果は関連度順で表示する",
        "state": "accepted"
      }
    ],
    "unresolved_questions": [
      {
        "id": "q_search_002",
        "title": "ピン留め項目との優先順位",
        "state": "proposed"
      }
    ],
    "relevant_intents": [],
    "nearby_scopes": []
  },
  "meta": {
    "api_version": "v1"
  },
  "errors": []
}
```

---

## 6.3 GET `/v1/views/node/{node_id}`

単一 node とその近傍関係を返す。

### 用途

- node 詳細表示
- related rationale / dependency / exception の確認
- Graph UI のフォーカス切替

### Query Parameters

- `depth?` — 既定値 `1`
- `include_relation_kinds?`

### Response Fields

- `node`
- `neighbors`
- `relations`
- `summary`

---

## 7. Consultations API

## 7.1 POST `/v1/consultations/proposal-impact`

proposal seed または proposal draft を受け取り、既存合意との関係を診断して返す。

### 重要な性質

- **永続化しない**
- 診断結果だけを返す
- Graph UI はこのレスポンスをそのまま overlay として描画できる

### Request Body

```json
{
  "proposal": {
    "title": "検索結果は更新日順で表示する",
    "body": "Public search results should default to updated_at desc.",
    "scope_hint_ids": ["scope_public_search"],
    "intent": "ユーザーが最新情報を見つけやすくする",
    "rationale": "最新項目の参照頻度が高い"
  },
  "options": {
    "max_related_nodes": 20,
    "include_overlay": true,
    "include_context_bundle": true
  }
}
```

### Response Fields

- `normalized_proposal`
- `related_agreements`
- `conflicts`
- `dependencies`
- `exception_candidates`
- `supersede_candidates`
- `related_rationales`
- `open_questions`
- `affected_scopes`
- `recommended_action`
- `overlay`
- `context_bundle`

### Response Example

```json
{
  "ok": true,
  "data": {
    "normalized_proposal": {
      "kind": "proposal",
      "title": "検索結果は更新日順で表示する",
      "scope_ids": ["scope_public_search"]
    },
    "related_agreements": [
      {
        "id": "ag_search_003",
        "title": "検索結果は関連度順で表示する",
        "state": "accepted"
      }
    ],
    "conflicts": [
      {
        "against_node_id": "ag_search_003",
        "reason": "same scope, opposite default ordering"
      }
    ],
    "dependencies": [],
    "exception_candidates": [],
    "supersede_candidates": [
      {
        "target_node_id": "ag_search_003",
        "reason": "proposal appears to replace the existing default ordering"
      }
    ],
    "related_rationales": [],
    "open_questions": [
      {
        "id": "q_search_002",
        "title": "ピン留め項目との優先順位"
      }
    ],
    "affected_scopes": [
      {
        "id": "scope_public_search",
        "title": "Public Search"
      }
    ],
    "recommended_action": {
      "type": "needs_human_decision",
      "message": "Accepted only if ag_search_003 is superseded or narrowed by scope."
    },
    "overlay": {
      "nodes_to_add": [
        {
          "temp_id": "proposal_1",
          "kind": "proposal",
          "title": "検索結果は更新日順で表示する"
        }
      ],
      "relations_to_add": [
        {
          "from_node_id": "proposal_1",
          "to_node_id": "ag_search_003",
          "relation_kind": "conflicts_with"
        }
      ],
      "nodes_to_highlight": ["ag_search_003", "q_search_002", "scope_public_search"]
    },
    "context_bundle": {
      "agreements": ["ag_search_003"],
      "questions": ["q_search_002"],
      "scope_ids": ["scope_public_search"]
    }
  },
  "meta": {
    "api_version": "v1"
  },
  "errors": []
}
```

---

## 8. Actions API

## 8.1 POST `/v1/actions/apply-proposal`

人間または上位運用で `Proceed` と判断された proposal を、LATIS の現在状態へ反映する。

### 重要な性質

- 永続化を行う
- node / relation / provenance / revision を生成または更新する
- **打診セッション自体は原則保存しない**
- そのため、`apply-proposal` は **参照IDだけでなく、反映対象の proposal 本文または正規化済み proposal** を必ず受け取る
- 必要なら `consultation_fingerprint` や `base_revision_id` を添えて、直前に見た打診結果と同一内容かを検証する

### Request Body

```json
{
  "proposal": {
    "title": "検索結果は更新日順で表示する",
    "body": "Public search results should default to updated_at desc.",
    "scope_ids": ["scope_public_search"],
    "intent": "ユーザーが最新情報を見つけやすくする",
    "rationale": "最新項目の参照頻度が高い"
  },
  "consultation": {
    "consultation_fingerprint": "sha256:9c4d...",
    "base_revision_id": "rev_2026_03_27_001"
  },
  "decision": {
    "action": "accept_as_supersede",
    "target_node_ids": ["ag_search_003"],
    "actor": "user:ayumu",
    "reason": "Changed product direction after consultation"
  },
  "source_refs": [
    "artifact:spec_md#draft_2026_03_27_01"
  ]
}
```

### Supported `decision.action`

- `accept_new_agreement`
- `accept_as_exception`
- `accept_as_supersede`
- `accept_question`
- `reject`

### 運用上の注意

`apply-proposal` は、直前の `consultations/proposal-impact` を参照した**外部クライアント**が、
そのとき提示された `normalized_proposal` を保持して再送することを前提とする。
LATIS Core は consultation を永続化しなくてもよい。
必要に応じて `consultation_fingerprint` と `base_revision_id` を照合し、
「別の proposal を誤って反映していないか」「相談後に内部状態が変わっていないか」を検査する。

### Response Fields

- `created_nodes`
- `updated_nodes`
- `created_relations`
- `updated_relations`
- `provenance`
- `revisions`
- `result_summary`

### Response Example

```json
{
  "ok": true,
  "data": {
    "created_nodes": [
      {
        "id": "ag_search_014",
        "kind": "agreement",
        "title": "検索結果は更新日順で表示する",
        "state": "accepted"
      }
    ],
    "updated_nodes": [
      {
        "id": "ag_search_003",
        "kind": "agreement",
        "state": "superseded"
      }
    ],
    "created_relations": [
      {
        "id": "rel_220",
        "from_node_id": "ag_search_014",
        "to_node_id": "ag_search_003",
        "relation_kind": "supersedes",
        "state": "accepted"
      }
    ],
    "updated_relations": [],
    "provenance": [
      {
        "id": "prov_220",
        "target_type": "node",
        "target_id": "ag_search_014",
        "actor": "user:ayumu",
        "source_ref": "artifact:spec_md#draft_2026_03_27_01",
        "reason": "Changed product direction after consultation"
      }
    ],
    "revisions": [
      {
        "id": "rev_2026_03_27_001",
        "target_type": "node",
        "target_id": "ag_search_014",
        "change_type": "create"
      },
      {
        "id": "rev_2026_03_27_002",
        "target_type": "node",
        "target_id": "ag_search_003",
        "change_type": "state_change"
      }
    ],
    "result_summary": {
      "message": "Proposal applied as a superseding agreement."
    }
  },
  "meta": {
    "api_version": "v1"
  },
  "errors": []
}
```

---

## 9. History API

## 9.1 GET `/v1/history/node/{node_id}`

特定 node に関する revision と provenance を返す。

### 用途

- なぜこの agreement があるのかを追う
- Graph UI の history view
- proposal 採択後の変更説明

### Response Fields

- `node`
- `revisions`
- `provenance`

---

## 10. Context API

## 10.1 POST `/v1/context/task-context`

実装タスクや質問文を受け取り、compact context bundle を返す。

### 用途

- コーディングエージェント向けの最小文脈
- QA エージェント向けの検索前 bundle
- 人間向けの要点整理

### Request Body

```json
{
  "task": {
    "title": "公開検索のデフォルト並び順を変更したい",
    "body": "What should I know before implementing this change?"
  },
  "options": {
    "max_items": 12
  }
}
```

### Response Fields

- `summary`
- `agreements`
- `questions`
- `rationales`
- `scope_ids`
- `implementation_notes`

---

## 11. Optional Meta API

## 11.1 GET `/v1/meta`

このエンジンが受けられる問い合わせ面を返す。

### 注意

これはプロトタイプでは **必須ではない**。ただし、将来的に複数クライアントや Skillpack を整理する際に有用である。

### Response Example

```json
{
  "ok": true,
  "data": {
    "engine": "LATIS",
    "version": "0.1",
    "supported_queries": [
      "views.state",
      "views.scope_brief",
      "views.node",
      "consultations.proposal_impact",
      "actions.apply_proposal",
      "history.node",
      "context.task_context"
    ]
  },
  "meta": {
    "api_version": "v1"
  },
  "errors": []
}
```

---

## 12. Graph UI との責務分担

### LATIS が担うこと

- 現在状態の意味つき view を返す
- proposal の影響範囲を返す
- 反映後の state / provenance / revision を保持する
- compact context bundle を返す

### 外部 Graph UI が担うこと

- state view の描画
- proposal overlay の描画
- diff / highlight の表現
- 人間の `Proceed / Revise / Abort` 操作

### 重要

Graph UI は raw graph database viewer ではなく、**LATIS が返す view を描くクライアント** として設計する。

---

## 13. 最小実装セット

プロトタイプで最初に実装すべき API は次の 5 本で十分である。

1. `GET /v1/views/state`
2. `GET /v1/views/scope-brief/{scope_id}`
3. `POST /v1/consultations/proposal-impact`
4. `POST /v1/actions/apply-proposal`
5. `POST /v1/context/task-context`

余力があれば次を追加する。

6. `GET /v1/views/node/{node_id}`
7. `GET /v1/history/node/{node_id}`
8. `GET /v1/meta`

---

## 14. 一文で言うと

LATIS API の原則は次の一文に要約できる。

**LATIS は、現在状態の view と proposal の影響診断を返し、採択された変更だけを永続化する headless Agreement Engine である。**
