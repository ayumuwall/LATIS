# LATIS API

**版:** v0.3-demo-draft  
**作成日:** 2026-11-04（日本時間）  
**状態:** 初期実装の規範的な操作契約。HTTP表記はCLI等へ写像でき、HTTPサーバーの起動自体を必須としない。

## 1. 対象と読み方

本版は、反復探索、途中状態の保存、照合、原子的な反映を実装するための契約である。従来の実験APIから変更を含む。DBスキーマの名前とHTTPの形を同一にする必要はないが、操作の効果・検査・返却情報は維持する。

日本語の本文、Scope未設定の記録、候補関係を初期実装から扱う。必須の意味判定器、ベクトル検索、全体の文脈生成は設けない。自然文の検討は呼出元LLMが担う。

以下の必須・禁止は実装要件であり、数値上限などは本仕様案で置くプロトタイプの既定値である。JSON例のID・版・内容は架空の例である。

本版は2026年11月7日の展示に向けた契約であり、別文書の「v0.3改訂提案」を全面採択したものではない。本書が操作・フィールドの正本となる。§2の9操作、artifactの観測情報、12種類の関係、§16のJSONによる退避・復元は必須とする。子孫Scope検索とMarkdown投影は、名前付きcapabilityがある場合だけ使える任意機能である。

本書にないparty、rule、拡張kind、時間条件、hybrid検索、署名、verify、redact、Markdown import、分散マージの操作・フィールドは受理しない。存在しない機能を無視して成功扱いにしない。

2026-11-04の検索拡張に関する追記は、Spec §8.4の責務の境界を明確にするものである。新しい検索mode、Request/Responseフィールド、capability、保存形式を追加せず、spec_version=0.3-demo-draft、rules_version=core-0.3.0を維持する。

## 2. エンドポイント

| メソッド・パス | 操作名 | 用途 |
| --- | --- | --- |
| GET /v1/meta | meta | 版、DB識別子、利用可能な操作を確認 |
| POST /v1/search | search | 条件を変えながら候補を検索 |
| GET /v1/nodes/{node_id} | detail | 現在または特定版のノードを取得 |
| GET /v1/relations/{relation_id} | relation-detail | 現在または特定版の関係を取得 |
| GET /v1/nodes/{node_id}/relations | relations | 関係の近傍を小さく取得 |
| GET /v1/history/{target_type}/{target_id} | history | nodeまたはrelationの改訂と来歴を取得 |
| POST /v1/actions/save-draft | save-draft | 草稿、候補、原文、新規Scopeを保存 |
| POST /v1/consultations/proposal-impact | consult | 変更計画を既存の記録へ照合 |
| POST /v1/actions/apply-proposal | apply | 前提を再検査して変更を確定 |

CLIは同じ操作名とJSON入出力を提供する。たとえばlatis searchはsearchのrequestを標準入力から読み、同じresponse envelopeを標準出力へ返す。診断ログは標準エラーへ分ける。CLIの引数ショートカットは後から追加できる。

## 3. 共通契約

### 3.1 データ形式

- UTF-8のJSON。時刻はUTCのRFC 3339文字列とする。
- IDとrevision_idは不透明な文字列。クライアントが接頭辞や時刻を解釈しない。
- database_idはDB作成時に生成し、バックアップ・復元で保持する。
- graph_revisionは0以上の整数。JSONで正確に表せる整数の範囲を使う。
- snapshot_idは各commitに付ける不変の一意ID。初期版0にも生成する。復元後に同じ連番が再び使われても、別の履歴なら異なるIDになる。
- リクエストの未知フィールドは400で拒否する。更新用の自由なJSON Patchは公開しない。
- レスポンスの未知フィールドはクライアントが無視できるようにする。
- nullと省略を同じ意味にしない。patchの省略は変更なし、nullは許されたnullableフィールドの解除を意味する。

### 3.2 Envelope

成功例:

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "api_version": "v1",
    "spec_version": "0.3-demo-draft",
    "rules_version": "core-0.3.0",
    "database_id": "db_example",
    "graph_revision": 41,
    "snapshot_id": "commit_example_41"
  },
  "errors": []
}
```

失敗時はok=false、data=nullを基本とし、errorsにcode、message、detailsを返す。機械処理はcodeで分岐する。messageの表現が同じであることは決定論性の保証に含めない。

構造的な結果の順序、対象ID、診断code、対象版は同じ入力・DB版・rules_versionで再現する。生成時刻やリクエスト追跡IDを追加しても、その差を構造的な結果の差として扱わない。

### 3.3 一度の読み取りとページング

一つのレスポンスは同じDBスナップショットから作る。独立した検索を繰り返す際に、最初のgraph_revisionへ固定し続ける必要はない。

ページを持つ操作はlimit（1〜100、既定20）、cursor、has_more、next_cursorを使う。cursorは検索条件・順序・database_id・graph_revision・snapshot_id・rules_versionと結び付く。続きの取得中にDBが変わった場合は409 CURSOR_STALEを返す。クライアントは先頭から検索し直すか、新しい問いへ進める。

has_more=falseは、その明示条件の結果を最後まで取得したことだけを表す。プロジェクト全体の意味的な網羅を表さない。total_countは必須にしない。

### 3.4 文字列と上限

titleは1〜240 Unicode文字、bodyは空文字を許し最大1 MiBとする。change_setは1〜100操作、JSONリクエスト全体は最大4 MiBとする。上限超過は413 LIMIT_EXCEEDEDを返し、途中まで反映しない。長い原文は複数のartifactへ分割し、元のsource_refと順序を残せる。

文字数はUnicodeスカラー値の数、バイト数はUTF-8で数える。不正なUnicodeは拒否する。特記のないID・actor・reason・authority_ref・source_refsの各要素は空でない文字列とし、これらの文字列から外部の命令を実行しない。自由記述の空白・改行は保存し、整形によって原文を変更しない。

これらの上限は負荷を予測可能にするための初期値であり、合意内容の形式化条件ではない。metaに実際の上限を返す。

## 4. データ形状

### 4.1 Node

```json
{
  "id": "ag_log_retention",
  "revision_id": "rev_ag_3",
  "commit_revision": 37,
  "kind": "agreement",
  "title": "ログの保持期間",
  "body": "サービスの通常ログは24時間保持する。",
  "lifecycle": "accepted",
  "locator": null,
  "content_hash": null,
  "evidence": null,
  "created_at": "2026-11-01T00:00:00Z",
  "updated_at": "2026-11-03T12:00:00Z"
}
```

kindはagreement、proposal、intent、rationale、question、scope、artifact、taskのいずれか。kindは作成後に変更しない。

lifecycleはdraft、proposed、accepted、rejected、superseded、retired。supersededはagreementに限定する。acceptedからdraft/proposedへ戻さず、採択済みの改訂・撤回として履歴を残す。rejectedはdraft/proposedから、supersededはaccepted agreementから、retiredはdraft/proposed/acceptedから遷移できる。rejected/superseded/retiredは終端状態とし、復活する場合は新しい記録を作りoriginates_from等で元へ結ぶ。

draftからproposedまたはaccepted、proposedからdraftまたはacceptedへの遷移を許す。acceptedへの遷移はapplyを通す。ただし新規Scopeの登録は§7の例外に従う。acceptedの本文・titleをacceptedのまま改訂することもapplyで扱う。

scope_idsはNodeの独立した保存フィールドではない。現在のviewにはactive/confirmedのscoped_toから導出した配列を添える。

Nodeの保存フィールドは上の例の全フィールドに限定する。id、revision_id、commit_revision、created_at、updated_atはサーバーが設定する。完全なNodeスナップショットではlocator、content_hash、evidenceを常に返し、未設定はnullとする。検索のsummaryは§5.1で列挙したフィールドだけを返す。

| フィールド | 型・既定値 | 契約 |
| --- | --- | --- |
| locator | stringまたはnull、既定null | artifactだけが非nullを持てる。1〜2048文字の不透明なURI。先頭は`^[A-Za-z][A-Za-z0-9+.-]*:`に一致し、空白・制御文字を含めない。URIの到達性や解決方法は検査しない |
| content_hash | stringまたはnull、既定null | artifactだけが非nullを持てる。`^sha256:[0-9a-f]{64}$`。呼出元が外部データの正確なバイト列から計算する。Unicode・改行等の正規化をしない |
| evidence | Evidenceまたはnull、既定null | artifactだけが非nullを持てる。作成時だけ指定でき、一回の観測を記録する |

locatorとcontent_hashは独立してnullを許す。locator例は、呼出元が作業場所を明示した上での`file:retention.py`、またはリポジトリ識別子と版を含む`git+https://example.invalid/demo.git/retention.py?commit=0123456789abcdef0123456789abcdef01234567`である。コアはURIへアクセスせず、resolverや実行環境を要求しない。ハッシュの形式一致は、ファイルの取得・内容一致・署名検証を済ませたという意味ではない。

#### 4.1.1 Evidence

| フィールド | 必須・型 | 契約 |
| --- | --- | --- |
| subject_refs | 必須、Node RevisionRefの配列、1〜100件 | 観測した既存ノードの版。typeはnodeのみ。同じnode IDに異なる版を混在させず、完全な重複は正規化で除く。$local_refと自分自身の参照は禁止 |
| method | 必須、空でないstring | 実行したテスト、検査、またはレビュー方法。文字列をコアが実行しない |
| outcome | 必須、string | passed / failed / inconclusive |
| observed_at | 必須、UTCのRFC 3339文字列 | 呼出元が申告する観測時刻。サーバーのcreated_atとは区別する |
| actor | 必須、空でないstring | 観測を実行した主体の申告 |
| source_refs | 任意、string配列、既定[] | 実行ログ等の出所。各要素は空でない文字列 |

既存の過去版を指すことを許し、subject_refsのID・版の対応と存在を検査する。観測後に対象が進んでいても、古い観測を履歴として保存できる。観測が現在版を検証しているかは、verified_byを確定する段階で別に確認する。

evidenceは自己申告の観測記録であり、独立した認証・実行証明ではない。実際に観測したコードや入力の版をsubject_refsへ入れる。未記録の依存まで調べたと保証しない。

evidenceが非nullのartifactでは、evidence、locator、content_hashを作成後に変更できない。再実行または観測内容の訂正は、新しいartifactを作って来歴を残す。title、body、lifecycleは通常の版管理に従って更新できるが、固定された観測値を置き換えない。evidenceがnullの通常artifactへ、update_nodeで後付けすることも禁止する。

### 4.2 Relation

```json
{
  "id": "rel_log_scope",
  "revision_id": "rev_rel_1",
  "commit_revision": 37,
  "from_node_id": "ag_log_retention",
  "to_node_id": "scope_logs",
  "relation_kind": "scoped_to",
  "lifecycle": "active",
  "confirmation": "confirmed",
  "origin": "agent",
  "priority": null,
  "qualifier": null,
  "basis_refs": [],
  "created_at": "2026-11-03T12:00:00Z",
  "updated_at": "2026-11-03T12:00:00Z"
}
```

| フィールド | 契約 |
| --- | --- |
| relation_kind | contains / scoped_to / depends_on / supports / conflicts_with / governs / specializes / exception_to / supersedes / originates_from / implemented_by / verified_by の12種類 |
| lifecycle | active / retired。retiredから復活させず新しい関係を作る |
| confirmation | candidate / confirmed。確定済み判断の取り消しはretireし、必要なら新しいcandidateを作る |
| origin | agent / human / import / system / unknown。作成時の由来であり変更しない |
| priority | integerまたはnull。保存のみ。効力や勝者の計算には使わない |
| qualifier | stringまたはnull。exception_toをconfirmedにするときは空でない文字列が必須 |
| basis_refs | 内容依存の判断が対象にしたノードのIDと版。読取専用 |

id、端点、relation_kindは変更しない。端点の訂正は、旧関係をretireして新関係を作る。実行済みの置換の事実を表すsupersedesだけは§6.6の修復手順に従う。contentに依存するconfirmed関係は両端ノードの版をbasis_refsに含める。basis_refsと現在版が違っても、自動的にcandidateへ降格させない。

contentに依存する関係はdepends_on、supports、conflicts_with、governs、specializes、exception_to、implemented_by、verified_by。それ以外は同一性に基づく構造として扱う。

型制約は次のとおり。

- containsの両端はscope。active/confirmedのcontainsに循環を作らない。
- scoped_toの終点はscope。scope自身の階層はcontainsで表す。
- exception_to、supersedes、specializes、conflicts_withの両端はagreement。
- implemented_by、verified_byはagreementからartifactへ向ける。端点がdraft/proposedであることも許し、採択済み合意だけに限定しない。
- 自己関係は禁止する。既存のactive/confirmed関係と、種類・端点・qualifierが同一の重複confirmed関係は作らない。
- exception_toとsupersedesの循環は禁止する。意味上の推移・継承は計算しない。

implemented_byは「この合意をこのartifactで実装している」という記録された判断である。verified_byは「この合意についてこの観測結果を検証の根拠とした」という判断である。関係の存在だけで、実装の正しさや検査の十分性を証明しない。

#### 4.2.1 verified_byの確定と観測対象版

verified_byを新しくconfirmedにする、candidateからconfirmedへ進める、またはreconfirm=trueにする場合、次を検査する。

1. 終点artifactにevidenceがあり、outcomeがpassedであること。満たさない場合は400 INVALID_CHANGEとする。failed/inconclusiveの観測とcandidate関係は保存できるが、検証済みの関係へ進めない。
2. 両端ノードの最終版と、実効basis_targetsの最終版に加え、終点evidenceの固定subject_refsをbasis_refsへ必ず含める。basis_targets=[]でも、この固定根拠を外せない。
3. 固定subject_refsの各版が、そのchange_set反映後の対応ノードの最終版と一致すること。同じchange_setで観測対象を実際に変更する場合も一致しないので、409 EVIDENCE_SUBJECT_CHANGEDとする。新しいevidence artifactは$local_refで指定できるが、そのsubject_refsには既存の版だけを使う。
4. 統合したbasis_refsはノードIDごとに一つの版とする。異なる版を選んで上書きしたり、古い固定subjectを現在版へ自動で書き換えたりしない。

通常のreadや、後日のsubjectノード更新に対して、この一致を永久的な整合性制約にはしない。版が変われば既存の関係はbasis_status=changedとなり、過去の確認と観測は保持する。古いテスト結果を新しいコード版へ貼り直すには、新しい観測が必要である。

### 4.3 RevisionRefと診断

RevisionRef:

```json
{
  "type": "node",
  "id": "ag_log_retention",
  "revision_id": "rev_ag_3"
}
```

typeはnodeまたはrelation。relationのbasis_refsはnodeだけを含め、採択時のbasis.refsは両方を含められる。本版のrelation.basis_status=currentは、保存したノードの参照版が一致することだけを示す。未記録の依存や、別の関係の版まで確認済みという意味ではない。関係の版を判断の前提にする場合は、採択時のcontext.basis_refsへ明示する。

診断例:

```json
{
  "code": "basis_changed",
  "evidence_kind": "structural_fact",
  "target_refs": [
    {"type": "relation", "id": "rel_conflict_1", "revision_id": "rev_conflict_2"}
  ],
  "message": "この判断が参照したノードの版が更新されている。",
  "details": {
    "node_id": "ag_log_retention",
    "recorded_revision_id": "rev_ag_3",
    "current_revision_id": "rev_ag_4"
  }
}
```

evidence_kindはstructural_fact、recorded_judgment、agent_inference、unverified。診断とAPIエラーを混同しない。unscopedやpartial_resultだけでapplyを拒否しない。

active/confirmedのimplemented_byまたはverified_byのbasis_statusがchangedの場合は、非blockingの診断verification_basis_changedを返す。evidence_kindはstructural_fact、target_refsは当該関係の現在版、details.changed_refsはnode_id、recorded_revision_id、current_revision_idを持つ配列で、node_id昇順とする。この診断は「記録された根拠の版が違う」ことを示し、実装の違反やテスト失敗を断定しない。

### 4.4 ProvenanceとRevision

Provenanceはid、commit_revision、target_refs、actor、principal_refs、source_refs、reason、created_atを持つ。任意のexecution_contextを保存できる。applyの記録にはproposal、change_set、decision、consulted_basis、validated_at_revisionも含める。関連ノード・関係から同じ採択記録へ戻れるようにする。

actorは書き込みの実行主体である。principal_refsは判断や依頼に関係した人・組織等を示す不透明な文字列の集合で、既定[]。例はhuman:demo-owner。存在確認、本人認証、委任、同意者数、アクセス制御を意味しない。save-draftではrecord、applyではdecisionからactor、principal_refs、reason、execution_contextを保存する。applyのsource_refsはproposal.source_refsとし、追加の判断出所はdecision内にも保持する。target_refsはこの書き込みで作成・変更した全対象の反映後のRevisionRefを持つ。

execution_contextは省略可能なオブジェクトで、model、model_version、provider、session_refという省略可能な空でないstringだけを受け付ける。nullと未知キーは拒否する。空オブジェクトは許す。省略時は保存内容にも含めず、モデル名を推測で補わない。これらは実行環境の自己申告であり、独立したレビューや承認の証明ではない。

Revisionはrevision_id、target_type、target_id、commit_revision、change_type、snapshot、provenance_idsを持つ。snapshotはその版の保存内容であり、現在のScope所属や現在の診断で書き換えない。

採択記録のconsulted_basisは、その判断をした時点の履歴である。採択操作自身が対象を更新しても、その過去記録を直ちに「無効な採択」と診断しない。現在の再確認に使うrelation.basis_refsや、再利用しようとする提案の前提とは区別する。

## 5. 探索と履歴

### 5.1 POST /v1/search

Request:

```json
{
  "query": "ログ 保持",
  "kinds": ["agreement"],
  "lifecycles": ["accepted"],
  "scope_ids": ["scope_logs"],
  "include_unscoped": true,
  "include_descendants": false,
  "limit": 20,
  "cursor": null
}
```

| パラメーター | 既定値・意味 |
| --- | --- |
| query | 空文字。空なら列挙検索 |
| kinds | ["agreement"] |
| lifecycles | ["accepted"]。未整理情報を探すときはdraft/proposedも明示する |
| scope_ids | []。空なら全Scopeおよび未分類を含む |
| include_unscoped | false。Scopeを指定した場合、そのScope所属ノードに未分類ノードを加える |
| include_descendants | false。trueはcapability search_descendantsがある場合だけ受理する |
| limit / cursor | 共通ページング |

queryはstring、kinds/lifecyclesは既知の値だけを含む空でない配列、scope_idsは既存Scope IDの配列、include_unscoped/include_descendantsはbooleanとする。配列の完全な重複は除く。存在しないScopeは404 TARGET_NOT_FOUND、Scope以外のIDは400 INVALID_REQUEST。limitは整数、cursorはnullまたは空でない文字列とし、これら以外にnullを既定値の代わりとして渡せない。

複数scope_idsはOR条件とする。子孫Scopeを暗黙には含めない。Scope自体を検索するときはkinds=["scope"]を指定し、scope_idsはそのScopeノード自身への所属フィルターであることに注意する。

include_descendants=trueを未対応の実装へ送った場合は、scope_idsが空でも400 UNSUPPORTED_FEATUREを返す。対応済みでscope_idsが非空なら、active/confirmedのcontainsを親から子へ全深さ辿り、指定Scope自身と子孫の集合へ所属フィルターを広げる。循環は禁止済みであり、複数経路は重複除去する。展開は同じ読み取りスナップショットで行い、順序はUTF-8のID昇順とする。scope_ids=[]なら従来どおり全体検索とし、展開集合は[]。include_unscopedは展開後に適用する。

applied_filtersにはinclude_descendantsとexpanded_scope_idsを常に返す。falseならexpanded_scope_idsは重複除去・昇順化した元のscope_idsである。cursorはフラグと展開集合にも結び付く。この機能は取得範囲を広げるもので、効力・優先順位・継承を変えず、consultのwatchへも自動適用しない。

検索文字列は、原文を変更せず、索引用にUnicode NFKCとcasefoldで正規化する。空白で区切った各語がtitleまたはbodyに部分一致するAND検索とする。各語はtitle/bodyのどちらに一致してもよい。記号をFTS構文として解釈しない。語形展開・同義語・意味検索は本版の必須契約に含めない。

非空queryの順序は、正規化titleがquery全体と一致、全語がtitle内に一致、その他の順とし、同順位はidのバイト列昇順とする。空queryはid昇順。正規化規則・Unicodeデータ版・索引実装の変更はrules_versionに反映する。FTS等の索引を使う場合も、特に日本語の部分一致でこの契約を満たすことを検証する。

展示用の小規模データでは正規化文字列の走査で実装してよい。FTSの有無を仕様上の要件にせず、2文字の日本語を含む部分一致の結果を維持する。20万件での性能を、この契約を満たすだけで達成済みとは扱わない。

Responseのdata:

```json
{
  "items": [
    {
      "id": "ag_log_retention",
      "revision_id": "rev_ag_3",
      "kind": "agreement",
      "lifecycle": "accepted",
      "title": "ログの保持期間",
      "excerpt": "サービスの通常ログは24時間保持する。",
      "scope_ids": ["scope_logs"],
      "matched_fields": ["title", "body"]
    }
  ],
  "page": {"limit": 20, "returned_count": 1, "has_more": false, "next_cursor": null},
  "applied_filters": {
    "query": "ログ 保持",
    "kinds": ["agreement"],
    "lifecycles": ["accepted"],
    "scope_ids": ["scope_logs"],
    "include_unscoped": true,
    "include_descendants": false,
    "expanded_scope_ids": ["scope_logs"]
  },
  "diagnostics": []
}
```

excerptは本文の先頭240文字までの機械的抜粋とする。要約として書き換えない。0件、抜粋、件数制限の結果から「関連する合意は存在しない」と保証しない。

DecisionRAG等の任意の推論検索は、本操作の部分一致条件・順序・cursorへ黙って混在させない。将来の別操作または明示したcapabilityの契約で扱い、本版では未定義のmodeや索引メタデータをRequestへ追加しない。呼出元が外部検索で候補を得た場合は、IDから現在のdetailと必要なrelationsを取得し、根拠に使う版をcontext.basis_refs等へ渡せる。過去の結果を調べる場合は特定版と履歴を利用し、現在の合意とは区別する。外部検索が返した順位・スコア・要約をbasisの代わりに使わず、§8〜11の照合と変更検査を維持する。

### 5.2 GET /v1/nodes/{node_id}

任意query parameterはrevision_idのみ。省略時は現在版を返す。

現在版のdataはnode、scope_ids、diagnostics、provenance_idsを持つ。関係全体や長い履歴は同梱せず、別の取得へ進める。存在しないIDは404 TARGET_NOT_FOUND、別対象のrevision_idは404 REVISION_NOT_FOUND。

現在版のdiagnosticsでは、対象に直接接続するactive/confirmedのimplemented_by・verified_byを調べ、該当時にverification_basis_changedを返す。関係の詳細はrelationsで取得する。観測対象の物理ファイルへはアクセスしない。

revision_id指定時はその版のnodeスナップショットを返す。scope_idsはnullとし、scope_resolution="not_included_for_historical_revision"を付ける。過去版の本文に、現在の所属を混ぜない。関係の過去版は関係履歴から取得する。

### 5.3 GET /v1/relations/{relation_id}

任意query parameterはrevision_idのみ。現在版ではrelation、basis_status、diagnostics、provenance_idsを返す。basis_statusはnot_applicable、current、changed、untrackedのいずれか。

- 同一性に基づく関係はnot_applicable。
- contentに依存するcandidateで確認対象版がない場合はuntracked。
- confirmedのbasis_refsが現在版と一致すればcurrent、違えばchanged。
- 過去版指定時はrelationスナップショットだけを返し、basis_statusはnullとする。現在版に関する診断を過去の事実へ混ぜない。

verified_byのbasis_refsには固定されたevidence.subject_refsも含まれるため、対象コードのartifact版が変わればchangedになる。currentでも、呼出元がまだLATISへ記録していないファイル変更は検出できない。過去版以外では該当時に§4.3のverification_basis_changedを返す。

### 5.4 GET /v1/nodes/{node_id}/relations

query parameterはdirection（in / out / both、既定both）、relation_kinds（カンマ区切り、既定全種類）、confirmations（既定candidate,confirmed）、lifecycles（既定active）、limit、cursor。

CLIではrelation_kinds、confirmations、lifecyclesを文字列配列として渡す。明示する場合は空でない既知の値の配列とし、重複は除く。HTTPへ写像する場合だけカンマ区切りへ変換する。node_idは必須で、存在しなければ404 TARGET_NOT_FOUND。

端点がnode_idと一致する関係だけを返す。深さは1固定とし、必要なら隣接ノードに対して再度呼ぶ。directionは保存された向きに従う。conflicts_withもbothなら両方向で発見できる。

dataはitems、page、diagnostics。itemsはrelation、basis_status、other_node_summary（id、revision_id、kind、lifecycle、title）を持つ。順序はrelation.id昇順とする。候補を確定済みとして返さない。

diagnosticsはこのページに含む関係について返し、該当する検証関係にverification_basis_changedを含める。verified_byが0件という結果は、成功した検証があることを意味しない。missingという永続状態を作らず、明示条件で取得できた関係の集合を返す。

### 5.5 GET /v1/history/{target_type}/{target_id}

target_typeはnodeまたはrelation。query parameterはlimit、cursor。commit_revision降順、同順位revision_id昇順で返す。

dataはtarget、revisions、provenance、pageを持つ。revisionsにはスナップショットを含め、provenanceはそのページの版に対応する記録を重複排除して返す。履歴取得による状態変化は発生しない。

## 6. 共通change_set

### 6.1 形と参照

change_setはoperations配列を持つ。操作数は1〜100。利用できるopはcreate_node、update_node、create_relation、update_relationの4種類。

新しい記録は、そのchange_set内だけで有効なrefを持つ。refは英小文字で始まる英数字とアンダースコア、最大64文字とする。他の操作からは$refの形で参照する。既存IDは$で始まらない。ノードと関係を通してrefを重複させない。

新規ノードへの前方参照を許す。すべての参照を解決し、変更後の状態全体を検証してから、原子的に反映する。既存の同じ対象へのupdateは一つにまとめる。新規作成した記録に同じchange_set内でupdateを重ねない。

### 6.2 create_node

```json
{
  "op": "create_node",
  "ref": "new_agreement",
  "kind": "agreement",
  "title": "ログの保持期間",
  "body": "サービスの通常ログは48時間保持する。",
  "lifecycle": "accepted"
}
```

上の例のop、ref、kind、title、body、lifecycleを必須とする。追加できるフィールドはlocator、content_hash、evidenceだけで、それぞれ既定nullとする。artifact以外への非null指定は400 INVALID_CHANGE。id、revision_id、時刻はサーバーが生成する。新規状態はdraft/proposed/acceptedのみ。Evidenceの内部ではsource_refsだけが省略可能であり、§4.1.1の参照検査を行う。

### 6.3 update_node

```json
{
  "op": "update_node",
  "id": "ag_log_retention",
  "expected_revision_id": "rev_ag_3",
  "set": {"lifecycle": "superseded"}
}
```

setで変更できるのはtitle、body、lifecycle、およびevidenceがnullのartifactのlocator、content_hash。少なくとも一つ必要。locator/content_hashにnullを指定すると解除する。artifact以外、またはevidenceが非nullのartifactのsetへlocator/content_hashを指定した場合は、同じ値でも400 INVALID_CHANGEとする。evidenceはsetの許可フィールドに含めず、後付け・訂正・解除を拒否する。

idとkindは変更できない。expected_revision_idを必須とし、自分が読んだ対象版を指定する。全変更が現在値と同じであるだけのchange_setは400 NO_CHANGESを返す。通常artifactのlocator/content_hash変更もノード版を更新するため、その版を参照する関係ではbasis_statusが変わる。

### 6.4 create_relation

```json
{
  "op": "create_relation",
  "ref": "new_scope_membership",
  "from": "$new_agreement",
  "to": "scope_logs",
  "relation_kind": "scoped_to",
  "confirmation": "confirmed",
  "origin": "agent",
  "priority": null,
  "qualifier": null
}
```

op、ref、from、to、relation_kind、confirmation、originを必須とする。priorityとqualifierの既定はnull。lifecycleはactiveで作成する。

contentに依存する関係をconfirmedにする場合、basis_targetsで追加の根拠ノードを指定できる（既定[]）。両端ノードは自動的に含める。basis_targetsの各値は既存ノードIDまたは$local_refとし、confirmedとして反映するcommitの最終ノード版へ結び付ける。候補段階で確認済みの版があると偽装しないため、candidateにはbasis_targetsを指定しない。

verified_byの場合は§4.2.1に従い、終点のevidence.subject_refsを追加で固定根拠にする。これらをbasis_targetsとしてユーザーへ入力し直させない。同一性に基づく関係にもbasis_targetsを指定できない。

### 6.5 update_relation

```json
{
  "op": "update_relation",
  "id": "rel_exception_1",
  "expected_revision_id": "rev_exception_2",
  "set": {"qualifier": "公開APIの試験環境に限る。"},
  "reconfirm": true,
  "basis_targets": ["ag_base_policy"]
}
```

setで変更できるのはlifecycle、confirmation、priority、qualifier。setの省略時は{}とする。少なくともsetに変更があるか、reconfirm=trueが必要。

reconfirmの既定はfalse。contentに依存する関係を再確認したときだけtrueとし、両端およびbasis_targetsを、反映後の版へ結び直す。contentに依存するconfirmed関係のqualifierを変更する場合はreconfirm=trueを必須とする。priorityだけの変更で以前の判断を自動的に再確認済みにしない。

reconfirm=trueでbasis_targetsを省略した場合は、既存basis_refsの両端以外の根拠IDを維持する。配列を明示した場合はその集合へ置き換え、明示[]は追加根拠を外す。consultのnormalized_requestでは、この実効的な追加根拠をbasis_targetsへ展開する。

verified_byでは、両端に加えて固定evidence.subject_refsのIDも除いて「追加根拠」を復元する。固定根拠は省略・空配列に関係なく再び含め、最終版との一致を確認する。reconfirm=trueは新たな観測を実行したことを意味せず、古い観測のsubject版を変更しない。

candidateからconfirmedへ移すときは新規確認としてbasis_refsを生成する。この新規確認ではbasis_targets省略を[]とする。basis_targetsを指定できるのは、この新規確認、またはreconfirm=trueの場合だけである。candidateに対するreconfirm=true、同一性に基づく関係のreconfirm=trueは400 INVALID_CHANGEを返す。

### 6.6 変更の組み合わせによる不変条件

- 新規作成または候補の確定によりsupersedesが新たにactive/confirmedになる場合、fromは変更後accepted agreement、toは同じchange_setでacceptedからsupersededへ移すagreementとする。
- agreementをsupersededへ変える場合、そのcommitで対応するsupersedesを新たにactive/confirmedにする。
- supersedesは実際に行った置換の事実として保持し、消去・retireしない。誤った置換を修復する場合は、必要な元の内容を新しいagreementとして再採択し、originates_fromで元へ結ぶ。誤って有効化した合意は必要に応じてretiredまたは新たな置換にし、訂正理由を同じapplyへ残す。終端状態を無履歴で復活させない。
- supersedesの端点の状態条件は新たな確定時の条件である。後続の置換でfromもsupersededになることは許す。
- 新規作成または候補の確定によりexception_toが新たにactive/confirmedになる場合、両端は変更後accepted agreement、qualifierは空でない。元の合意を自動的にsupersededへしない。
- retiredになったノードへ関係が残ることは、履歴として許す。現在有効な参照先とは表示せず、参照先のlifecycleも返す。
- 引用・根拠を改訂しただけで、関連するagreementのlifecycleを自動変更しない。
- implemented_byは§4.2の型制約、verified_byの新規確認・再確認は§4.2.1の観測対象版制約を満たす。既存関係が後日changedになったことだけを理由に、通常artifactの更新を拒否しない。

## 7. POST /v1/actions/save-draft

### 7.1 用途と制限

未整理の原文、提案、問い、候補関係を保存する。新規Scopeの作成も可能にする。意味を整理する前に記録できる入口である。

Requestはchange_set、record、idempotency_keyを必須とする。recordはactor、reasonを必須とし、source_refsは文字列配列で既定[]、principal_refsは空でない文字列の集合で既定[]。任意のexecution_contextは§4.4に従う。recordのそれ以外のキーは拒否する。principal_refsはノードID参照ではなく、許可や同意を機械検証するものでもない。

```json
{
  "change_set": {
    "operations": [
      {
        "op": "create_node",
        "ref": "note",
        "kind": "artifact",
        "title": "保持期間についての元メモ",
        "body": "保持期間を延ばしたい。どのログに適用するかは要確認。",
        "lifecycle": "draft"
      }
    ]
  },
  "record": {
    "actor": "agent:example",
    "principal_refs": ["human:demo-owner"],
    "source_refs": ["会話内で提示された保持期間に関するメモ"],
    "reason": "原文を保存し、対象範囲は後で整理する。"
  },
  "idempotency_key": "save-note-001"
}
```

許可する操作:

1. 新規ノードをdraft/proposedとして作る。
2. 新規scopeをacceptedとして作る。これは探索用の構造登録であり、合意の採択ではない。
3. 変更前がdraft/proposedであるノードを修正し、draft/proposed/rejected/retiredへ移す。
4. candidate関係を作成・修正・retireする。confirmedへ進めることはできない。
5. draft/proposedノードからscopeへのscoped_toだけをconfirmedで作成・retireできる。始点がacceptedのノードへの例外拡張はしない。

禁止する操作は409 CONSULTATION_REQUIRED。既存accepted scopeの内容変更、accepted agreementの所属変更もconsult/applyへ回す。kindの変更によって制限を迂回できてはならない。

### 7.2 応答

成功は200。dataにcreated_refs（refからID/版への写像）、updated_refs、commit_revision、provenance_idを返す。§11の共通書き込み契約に従う。

原文の保存を有効な合意の保存と誤認しない。後で採用する場合はconsult/applyでagreementを作るか、draft agreementをacceptedへ移す。

### 7.3 観測結果を保存する完全なRequest例

次は、既存のartifact_codeのrev_code_2を対象に検査を実行したという架空の例である。先に呼出元が作業場所を確認し、実際のコードを観測して通常artifactを更新する。以下の入力だけでコアがテストを実行することはない。保存時にartifact_codeが既に別の版へ進んでいても、過去の観測の記録として受理する。

```json
{
  "change_set": {
    "operations": [
      {
        "op": "create_node",
        "ref": "check_result",
        "kind": "artifact",
        "title": "保持期間の検査結果 002",
        "body": "指定したコード版に対して保持期間の境界値テストを実行した記録。",
        "lifecycle": "draft",
        "locator": "file:artifacts/check-002.txt",
        "content_hash": null,
        "evidence": {
          "subject_refs": [
            {"type": "node", "id": "artifact_code", "revision_id": "rev_code_2"}
          ],
          "method": "demo_projectを作業場所として python -m unittest -v を実行",
          "outcome": "passed",
          "observed_at": "2026-11-06T07:00:00Z",
          "actor": "agent:demo",
          "source_refs": ["run:retention-check-002"]
        }
      }
    ]
  },
  "record": {
    "actor": "agent:demo",
    "principal_refs": ["human:demo-owner"],
    "reason": "実行結果を一回の観測として残し、合意との対応は別途照合する。",
    "source_refs": ["run:retention-check-002"],
    "execution_context": {"session_ref": "demo-session-002"}
  },
  "idempotency_key": "save-check-result-002"
}
```

成功のcreated_refs.check_resultで返されたID・版を次のconsultへ使う。以下の例では、そのIDがartifact_check_002だったとする。new evidenceとconfirmed verified_byを同じapplyで作ることも可能だが、subject_refsに新規$local_refや未発行の版を使うことはできない。

## 8. POST /v1/consultations/proposal-impact

### 8.1 Request

Requestはproposal、change_set、context、optionsを持つ。proposalとchange_setは必須。context、optionsは省略可能。

| フィールド | 内容 |
| --- | --- |
| proposal | titleとbodyが必須。source_refsは文字列配列、既定[] |
| change_set | 意図する実際の変更。§6の4種類の操作 |
| context.scope_ids | 探索で扱った既存Scope ID。既定[] |
| context.anchor_node_ids | 起点にした既存ノードID。既定[] |
| context.basis_refs | 判断の前提として明示する現在のRevisionRef。既定[] |
| context.exploration_note | 調べた範囲・残る不明点の短い説明。既定空文字。思考過程の逐語記録は要求しない |
| options.max_related_items | 1〜100、既定20。返す候補数の上限 |

context.basis_refsは、全検索結果を転記する欄ではない。提案の意味や採択方法に関係した重要な本文・根拠・関係の版を含める。未指定でも対象そのものの版確認は自動で行う。

context.basis_refsでは同じtype/idに一つの現在版を指定する。完全な重複は除き、同じ対象へ異なる版を指定した場合は400 INVALID_REQUESTとする。観測した過去版はevidence.subject_refsへ記録し、この欄の現在版指定とは区別する。

例は、既存の24時間の合意を、48時間の新しい合意へ全体置換する計画である。この要求が既存のユーザー指示で明確に認可され、新しい食い違いがない場合は、追加の人間確認を挟まず進められる。

```json
{
  "proposal": {
    "title": "通常ログの保持を48時間へ変更",
    "body": "現行の24時間という合意全体を48時間へ置き換える。",
    "source_refs": ["現在の会話にある保持期間変更の指示"]
  },
  "change_set": {
    "operations": [
      {
        "op": "create_node",
        "ref": "new_agreement",
        "kind": "agreement",
        "title": "ログの保持期間",
        "body": "サービスの通常ログは48時間保持する。",
        "lifecycle": "accepted"
      },
      {
        "op": "update_node",
        "id": "ag_log_retention",
        "expected_revision_id": "rev_ag_3",
        "set": {"lifecycle": "superseded"}
      },
      {
        "op": "create_relation",
        "ref": "new_scope_membership",
        "from": "$new_agreement",
        "to": "scope_logs",
        "relation_kind": "scoped_to",
        "confirmation": "confirmed",
        "origin": "agent"
      },
      {
        "op": "create_relation",
        "ref": "replacement",
        "from": "$new_agreement",
        "to": "ag_log_retention",
        "relation_kind": "supersedes",
        "confirmation": "confirmed",
        "origin": "agent"
      }
    ]
  },
  "context": {
    "scope_ids": ["scope_logs"],
    "anchor_node_ids": ["ag_log_retention"],
    "basis_refs": [
      {"type": "node", "id": "ag_log_retention", "revision_id": "rev_ag_3"}
    ],
    "exploration_note": "通常ログの合意とその直接Scopeを確認した。"
  },
  "options": {"max_related_items": 20}
}
```

### 8.2 コアで行う照合

一つの読み取りスナップショットに対して、以下を行う。

1. 形式、ID、型、状態遷移、expected_revision_id、変更後の不変条件を検査する。
2. 変更対象、関係の端点、明示された起点・根拠から確認範囲を組み立てる。
3. その範囲の既存記録と直接の関係を取得する。
4. 保存済みの競合、候補関係、判断対象版の変化、未分類・表示上限を診断として返す。
5. そのchange_setに対応するbasisを返す。

verified_byの新規確認・再確認では、同じスナップショットと変更計画から§4.2.1を検査する。対象subjectが既に進んでいる、または同じ計画で実際に改訂される場合はEVIDENCE_SUBJECT_CHANGEDとする。consultは予定の最終revision_idを発行しないため、計画内の内容変更の有無で一致不能を判定する。confirmedの検証関係を読むだけの場合には、その古い根拠を拒否せずverification_basis_changedとして報告する。

コアが返すrecorded_conflictは、保存された関係の事実である。本文を意味比較して新しい競合が存在しないと判定した結果ではない。関連する本文を読み、意味上の食い違いを検討するのは呼出元の責務である。

### 8.3 自動的に含める対象とwatch

まず、次をexisting seed nodesとする。

- update_nodeの対象。
- create_relationの既存端点、update_relationの両端。
- context.anchor_node_ids。
- context.basis_refsに含むnode、およびrelationの両端。そのrelation.basis_refsが指す追加根拠ノードも、現在版で含める。既に古くなった過去の確認は診断として併記する。
- 新しく確認する内容依存関係の実効basis_targetsにある既存node。省略から引き継いだ根拠も含む。
- 新しく確認・再確認するverified_byの終点evidence.subject_refsにある既存node。終点が$local_refでも、subject_refsのノードは既存でなければならない。

context.basis_refsが指すconfirmed verified_byの終点、および実効basis_targetsに含まれるevidence artifactについても、そのevidence.subject_refsのノードをseedへ加える。固定された観測版は保存したまま、seedとbasis.refsでは照合時の現在版を使う。この追加取得は明示された観測のsubjectを一段展開するものであり、subject自身のevidenceを再帰的に辿る全依存解析ではない。

watch.node_idsは、この集合とする。watch.scope_idsは、context.scope_ids、seed nodesの直接Scope所属、change_setにある新しいscoped_toの既存Scope終点を合わせた集合とする。新しい$local_refのScopeは、まだ過去の変更がないためwatchに含めない。

basis.refsには、seed nodesの現在版、update_relationの現在版、context.basis_refs、seed nodesの直接所属を示すactive/confirmed scoped_toの版を、重複なく含める。意味判断に使う追加の根拠はcontext.basis_refsで補う。

候補の取得範囲は、seed nodes、その直接のactive関係と相手、watch.scope_idsへ直接所属するノード、Scopeノード自体とする。confirmedとcandidateを区別し、terminal状態の相手も履歴の手掛かりとして識別する。Scope階層の自動展開は行わない。

related_itemsはseed nodes、直接近傍、Scope所属ノードの順で返し、区分内はid昇順とする。重複を除きmax_related_itemsで打ち切る。basis.refsに入るのは定義された参照と明示した根拠であり、全候補を既読とみなした巨大なread setではない。

各related_itemに空でないinclusion_reasons配列を返す。値はseed、explicit_relation_neighbor、same_scopeだけで、該当する全理由をこの固定順で並べる。seedは上記集合、explicit_relation_neighborはseedの直接active関係で結ばれた相手、same_scopeはwatch Scope自身またはそこへ直接所属するノードを意味する。複数理由を持つ項目の返却区分は最初の理由で決める。これは構造的な取得理由であり、意味上の関連性や文脈の十分性の認定ではない。

seedに直接接続するactive/confirmedのimplemented_by・verified_byについて、該当時にverification_basis_changedを返す。全体の検証関係を網羅したと解釈しない。

### 8.4 Basis

```json
{
  "schema_version": "basis-1",
  "database_id": "db_example",
  "graph_revision": 41,
  "snapshot_id": "commit_example_41",
  "rules_version": "core-0.3.0",
  "change_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "refs": [
    {"type": "node", "id": "ag_log_retention", "revision_id": "rev_ag_3"},
    {"type": "node", "id": "scope_logs", "revision_id": "rev_scope_1"},
    {"type": "relation", "id": "rel_log_scope", "revision_id": "rev_rel_1"}
  ],
  "watch": {
    "node_ids": ["ag_log_retention", "scope_logs"],
    "scope_ids": ["scope_logs"]
  },
  "exploration_note": "通常ログの合意とその直接Scopeを確認した。"
}
```

上のダイジェストは形を示す例である。実際には返されたbasisをそのまま使用する。

change_digestは、normalized_requestのproposal、change_set、contextを対象とする。optionsは表示上限なので含めない。正規化は、既定値の補完、集合として扱うID配列とRevisionRef配列の重複除去・昇順化（IDはUTF-8バイト列順、RevisionRefはtype・id・revision_idの順で比較）、JSONオブジェクトキーの昇順化とする。operations配列の順序、本文の空白・改行、source_refsの順序は保存する。

集合はcontext.scope_ids、context.anchor_node_ids、context.basis_refs、basis_targets、evidence.subject_refs、basis.refs、basis.watch.node_ids、basis.watch.scope_ids、および書き込みのprincipal_refsとする。重複版の矛盾は除去前に拒否する。create_nodeのlocator/content_hash/evidenceはnullへ、evidence.source_refsは[]へ補完する。create_relationのpriority/qualifierはnullへ、confirmedの内容依存関係のbasis_targetsは[]へ補完する。candidateや同一性に基づく関係に、許可されないbasis_targetsを補完しない。update_relationはset={}、reconfirm=falseを既定とし、再確認で引き継ぐ実効basis_targetsは§6.5に従って基準版から展開する。update_node.setの未指定フィールドは補完せず、変更なしとして扱う。execution_contextの省略と{}は同一視しない。

正規化後のJSONを空白なし、非ASCII文字はそのままのUTF-8でシリアライズし、SHA-256を計算する。文字列では二重引用符とバックスラッシュをバックスラッシュでエスケープする。U+0008/U+0009/U+000A/U+000C/U+000Dはそれぞれ\b/\t/\n/\f/\r、その他のU+0000〜U+001Fは小文字16進の\u00xxで表し、スラッシュはエスケープしない。不正なUnicodeは拒否する。JSON数値は整数のみで、10進の最短表記（負のゼロは0）とする。実装時には正規化の共通fixtureを用意し、APIとCLIで同じ値になることを確認する。クライアントによるダイジェストの再生成は通常不要。

basisは対象と照合範囲の記述であり、認証や承認の証明ではない。初期実装は信頼されたローカルクライアントを対象とし、署名receiptや相談セッション用サーバー保存を要求しない。それでもapplyでのサーバー側再検査は省略しない。

### 8.5 Response

dataは次を持つ。

| フィールド | 内容 |
| --- | --- |
| normalized_request | 正規化したproposal、change_set、context。applyへ渡す実体 |
| basis | §8.4の前提記録 |
| related_items | id、revision_id、kind、lifecycle、title、excerpt、scope_ids、inclusion_reasonsを持つ候補。excerptは§5.1と同じ機械的抜粋 |
| related_page | returned_count、has_more。has_moreならsearch/relationsで追加取得する |
| diagnostics | 構造的事実、保存済みの判断、候補、未確認を区別した情報 |
| structural_validation | 文字列"valid"。構造検査で不正なら成功レスポンスを返さない |
| next_queries | 省略可能な追加取得候補の配列。省略時は[]と同じ。各要素はoperation（search / relations）と、その操作のCLI JSON入力であるrequestを持つ |

required_user_approvalという一律のフラグは返さない。コアが前提の変化を検知することと、意味上の選択のために人間へ打診することを分ける。related_pageが完了していても、意味的に完全な文脈を得たとは主張しない。

consultはドメインデータを書き込まず、graph_revisionを進めない。通常はconsultation_idの永続保存を行わない。basisを失った、提案内容を変更した、前提が変わった場合は再度consultできる。

## 9. POST /v1/actions/apply-proposal

### 9.1 Request

| フィールド | 必須・内容 |
| --- | --- |
| proposal / change_set / context | 必須。consultのnormalized_requestからそのまま渡す |
| basis | 必須。対応する照合結果 |
| decision.actor | 必須。実行者の識別子または説明 |
| decision.principal_refs | 任意、既定[]。空でない不透明な文字列の集合。判断・依頼に関係した人・組織等の参照で、権限検査ではない |
| decision.execution_context | 任意。§4.4のオブジェクト。省略時は保存しない。nullは不可 |
| decision.authority_ref | 必須。この変更を実行できるユーザー指示・過去判断の参照。短い説明も許す |
| decision.reason | 必須。採用・変更・整理する理由 |
| decision.semantic_review | 必須。ready / needs_user_decision。apply可能なのはreadyのみ |
| decision.resolutions | 既定[]。発見した食い違いの扱いを記録する配列 |
| idempotency_key | 必須。§11に従う |

resolutionsの各要素ではissue（空でない論点の説明）、source_refs（関係するID・版または会話参照の文字列配列）、resolution（空でない決定内容）、authority_ref（空でない判断の根拠）を必須とする。source_refsは空配列を許す。機械的な版検査が必要なものはcontext.basis_refsにも加える。decisionで受理するキーは表に列挙したものだけとする。

判断部分の例:

```json
{
  "actor": "agent:example",
  "principal_refs": ["human:demo-owner"],
  "authority_ref": "現在の会話にある、通常ログを48時間へ変更する明示指示",
  "reason": "既存の保持期間の合意を、指定された期間へ全体置換する。",
  "semantic_review": "ready",
  "resolutions": []
}
```

これはdecision部分だけの例であり、完全なapplyリクエストには上表の全必須フィールドを含める。consultの応答を受けたクライアントはnormalized_requestを展開し、basis、decision、idempotency_keyを加えるだけで送信できる。

既存の指示で解決している内容は、その指示をauthority_refに使える。新たな承認イベントを作るためだけの人間への確認は要求しない。authority_refの文字列だけで外部サービスの認証・権限が保証されるわけではない。

### 9.2 意味判断の責務

呼出元LLMは、今回の変更に関係する本文と保存済み判断を調べる。既存合意との食い違いが見つかり、既存の指示・例外等では扱いが決まらない場合は、semantic_review=needs_user_decisionのまま人間に打診する。この状態でのapplyは409 UNRESOLVED_DECISIONで拒否する。

readyは、現在の変更について未解決の判断が残っていないという呼出元の宣言である。全DBの意味を検査したという宣言ではない。コアは理由や既知の対象の構造を検証できるが、宣言の意味的な真偽を証明する機能を持たない。LLM向け使用文書と受け入れシナリオでもこの契約を検証する。

既存の不整合が今回の変更に関係しない場合は、その箇所を必要に応じてquestion等へ残して進められる。全体整理の完了を採択の前提にしない。

### 9.3 反映前の検査順序

1. リクエスト形式を検証し、成功済みidempotency_keyがあれば§11に従って以前の結果を返す。現在のbasisを先に検査して再送を失敗にしない。
2. database_id、basis schema、rules_version、change_digestの対応を検査する。basis.graph_revisionに保存されたsnapshot_idがbasis.snapshot_idと一致することも確認する。
3. 各expected_revision_idとbasis.refsを確認する。
4. §10の規則で照合後の変更を検査し、対象・関連範囲の変化を検知する。
5. 変更後の型・状態・参照・関係の不変条件、decisionの必須項目を検証する。新規確認・再確認のverified_byでは、固定evidence.subject_refsと変更後最終版の一致も検査する。
6. 最後の版・変更範囲検査と反映を同じ短い書き込みトランザクションで行う。
7. ノード、関係、版、来歴、commit、成功応答、idempotency記録をまとめて確定する。

事前検査後に別更新が入った場合も、最後の検査で見落とさない。LLMや人間の応答待ち、外部ネットワーク呼び出しをトランザクション内に置かない。

basisのrefs/watchをクライアントが減らすことで、必須検査を縮小できてはならない。コアはchange_setとcontextから対象を再構築し、basisの基準版で必要だった対象・直接所属情報も保持した履歴から確認する。存在しない基準版・参照版を、現在版で置き換えて通さない。

### 9.4 成功応答

Responseのdata例:

```json
{
  "created_refs": {
    "new_agreement": {"type": "node", "id": "ag_log_retention_48h", "revision_id": "rev_ag_new_1"},
    "new_scope_membership": {"type": "relation", "id": "rel_log_scope_new", "revision_id": "rev_rel_new_1"},
    "replacement": {"type": "relation", "id": "rel_replacement", "revision_id": "rev_replacement_1"}
  },
  "updated_refs": [
    {"type": "node", "id": "ag_log_retention", "revision_id": "rev_ag_4"}
  ],
  "commit_revision": 42,
  "provenance_id": "prov_retention_change",
  "consulted_at_revision": 41,
  "validated_at_revision": 41,
  "diagnostics": []
}
```

validated_at_revisionは、書き込み直前に検査したDB版。commit_revisionは新しい変更後の版である。照合後に無関係な更新があれば、consulted_at_revisionとvalidated_at_revisionは異なってよい。

content依存の関係のbasis_refsは、このcommitで作成・更新された$local_refを含め、最終的なノード版へ解決する。来歴には、以前の参照版を含むconsulted_basisを別に保存する。

verified_byの固定subject_refsはその観測版を保持したまま統合する。新しいコードに追随させるため、古い観測のsubject_refsを最新revision_idへ書き換える処理は行わない。

### 9.5 検証関係を確定する完全なRequest例

§7.3で保存した結果を使う例である。この架空のDBではag_retention、artifact_check_002、artifact_codeが未分類であり、各版が下記basisの値と一致している。対応するconsultのproposal/change_set/contextから返されたnormalized_requestとbasisを、そのまま使用する。実際には利用中のDBが返した値へ置き換える。

```json
{
  "proposal": {
    "title": "保持期間の検査結果を合意へ結び付ける",
    "body": "記録済みコード版について成功した境界値テストを、保持期間の合意の検証根拠として記録する。",
    "source_refs": ["run:retention-check-002"]
  },
  "change_set": {
    "operations": [
      {
        "op": "create_relation",
        "ref": "verification",
        "from": "ag_retention",
        "to": "artifact_check_002",
        "relation_kind": "verified_by",
        "confirmation": "confirmed",
        "origin": "agent",
        "priority": null,
        "qualifier": "記録された保持期間の境界値テストの範囲で確認した。",
        "basis_targets": []
      }
    ]
  },
  "context": {
    "scope_ids": [],
    "anchor_node_ids": [],
    "basis_refs": [],
    "exploration_note": "合意、検査結果、検査対象コードの各版を確認した。"
  },
  "basis": {
    "schema_version": "basis-1",
    "database_id": "db_demo",
    "graph_revision": 17,
    "snapshot_id": "commit_demo_17",
    "rules_version": "core-0.3.0",
    "change_digest": "sha256:3b833b2404de088bc06f809a5a0e1aad08e6912d25025df2e58039aa3021463a",
    "refs": [
      {"type": "node", "id": "ag_retention", "revision_id": "rev_retention_2"},
      {"type": "node", "id": "artifact_check_002", "revision_id": "rev_check_002_1"},
      {"type": "node", "id": "artifact_code", "revision_id": "rev_code_2"}
    ],
    "watch": {
      "node_ids": ["ag_retention", "artifact_check_002", "artifact_code"],
      "scope_ids": []
    },
    "exploration_note": "合意、検査結果、検査対象コードの各版を確認した。"
  },
  "decision": {
    "actor": "agent:demo",
    "principal_refs": ["human:demo-owner"],
    "execution_context": {"session_ref": "demo-session-002"},
    "authority_ref": "既存の実装・検証依頼に基づく結果記録",
    "reason": "記録されたテストの観点と合意を照合し、この版について検証関係を確定する。",
    "semantic_review": "ready",
    "resolutions": []
  },
  "idempotency_key": "confirm-verification-002"
}
```

この例のchange_digestはproposal/change_set/contextの正規化結果から計算した値である。artifact_codeがconsult後にrev_code_3へ変われば、applyはまずBASIS_CHANGEDで再照合を求める。再照合で同じ古い結果を確定しようとした場合はEVIDENCE_SUBJECT_CHANGEDとなる。結果だけを読み直して合格扱いにせず、必要な検査を実行し、新しいevidence artifactを記録する。

## 10. 変更検知と再照合

### 10.1 変更ログに必要な情報

commitごとに対象の変更前後のスナップショットを辿れるようにする。最低限、ノードのkind/lifecycle/直接Scope所属、関係の端点/種類/lifecycle/confirmation、変更前後のrevision_idを比較できることが必要である。

scoped_toを追加・retireした場合、始点ノードの本文版が変わらなくても、所属変化をログから検知する。同じcommitで複数の所属や状態を変えた場合は、commit開始前とcommit終了後を比較する。

graph_revisionが進んだという理由だけでapplyを拒否しない。basisから現在までの変更を、以下の優先順で分類する。

### 10.2 要再照合となる変化

| 条件 | エラー |
| --- | --- |
| update対象のexpected_revision_idが現在版と違う | PRECONDITION_CHANGED |
| basis.refsで明示された版が現在版と違う | BASIS_CHANGED |
| 確認したScopeでaccepted agreementが追加・改訂・撤回・置換・移動された | CONTEXT_CHANGED |
| watch.node_idsへ接続する関係が新たにconfirmedになった、qualifier・basis_refs・confirmation・lifecycleが変わった、またはretireされた | CONTEXT_CHANGED |
| 内容依存の根拠として参照した版が変わった | BASIS_CHANGED |

判定はbefore/after両側を見る。acceptedからretiredへ、confirmedからretiredへ、監視Scopeから別Scopeへ移ったものを「現在は対象外」として除外しない。

この関係差分は、列挙したフィールドの値を比較して検知する。自然文の意味比較ではない。priorityだけの変更はこの判定に含めないが、その関係をbasis.refsに明示していた場合は個別版の不一致を検知する。

watch Scopeのaccepted agreementに接続する確定関係についても、同じフィールド差分をCONTEXT_CHANGEDの対象に含める。これにより、合意本体の版が同じでも根拠や例外の構造の変化を検知できる。

単なる新しいdraft/proposedの追加、その草稿だけのscoped_to整理、candidate関係の追加は、それ自体をCONTEXT_CHANGEDにしない。ただしその記録をbasis.refsに明示していた場合、その版の変化はBASIS_CHANGEDとする。候補の追加は非blockingの診断として通知できる。

### 10.3 監視外・未分類の変更

監視対象との構造上の接点がない更新は、今回の前提を自動的に失効させない。既知の別Scopeの更新はそのまま進められる。

照合後に、直接Scopeを持たないaccepted agreementが追加・改訂された場合はunclassified_changesを返し、追加探索の手掛かりとする。この通知自体はapplyの一律拒否理由にしない。最大20件のIDとrevision_id、has_more、after_revisionを返せる。続きを調べる場合はScope未指定のsearchやhistoryを使う。

監視外の関係に、自然文では関連するものが存在する可能性は残る。その検出を保証するために全DBの意味照合を強制しない。参照範囲と監視対象はbasisに残す。

### 10.4 再照合エラー

PRECONDITION_CHANGED、BASIS_CHANGED、CONTEXT_CHANGEDは409で、対象差分、現在のgraph_revision、次に再取得するIDを返す。書き込みは行わない。

```json
{
  "ok": false,
  "data": null,
  "meta": {
    "api_version": "v1",
    "spec_version": "0.3-demo-draft",
    "rules_version": "core-0.3.0",
    "database_id": "db_example",
    "graph_revision": 43,
    "snapshot_id": "commit_example_43"
  },
  "errors": [
    {
      "code": "CONTEXT_CHANGED",
      "message": "照合したScopeに新しい合意が追加された。必要箇所を再確認してください。",
      "details": {
        "consulted_at_revision": 41,
        "current_revision": 43,
        "changed_refs": [
          {"type": "node", "id": "ag_new_constraint", "revision_id": "rev_constraint_1"}
        ],
        "next_action": "reconsult"
      }
    }
  ]
}
```

これはLLMへの再確認要求であり、人間の再承認要求ではない。LLMが差分を調べ、意味の選択が変わらなければ同じユーザー指示を根拠に再照合・反映できる。

履歴不足などで基準版以後の差分が確認できない場合は409 BASIS_UNAVAILABLEとし、新しいconsultへ戻る。現在のデータだけで「その間に変化なし」と推測しない。

EVIDENCE_SUBJECT_CHANGEDは409で、detailsにevidence_target（既存IDまたは$local_ref）とsubject_changesを返す。各要素はnode_id、observed_revision_id、current_revision_id、changed_in_change_set（boolean）を持ち、node_id昇順とする。同じ計画内で変わる場合はchanged_in_change_set=trueで示し、consult時に未発行の最終版を捏造しない。観測した過去版が存在しない場合は、このエラーではなくREVISION_NOT_FOUNDである。

通常の版・watch検査が先に不一致を見つけた場合は、そのPRECONDITION_CHANGED／BASIS_CHANGED／CONTEXT_CHANGEDを先に返す。どのエラーでも書き込みは部分実行せず、人間への再承認を自動要求しない。

## 11. 書き込みの共通要件

### 11.1 冪等性

save-draftとapplyのidempotency_keyは、1〜128文字の英数字・ピリオド・コロン・ハイフン・アンダースコアとする。DB内で一意とする。

- 同じキーと同じ正規化済みリクエストの再送は、保存された成功結果を返す。
- 同じキーで入力が違う場合は409 IDEMPOTENCY_CONFLICT。
- 成功した操作の後に他の変更があっても、元の結果を返す。基準版エラーへ変えない。
- 失敗はキーを消費しない。入力を修正して再試行できる。
- 同じキーの並行実行が二重反映にならないよう、最終検査と成功記録の保存を同じトランザクションで行う。

冪等性の入力ダイジェストは操作名とリクエスト全体からidempotency_keyだけを除いて計算する。decisionとbasisも含める。正規化方式は§8.4を用い、意味の同一性をLLMで推定しない。

record/decisionのprincipal_refs省略は[]へ、record.source_refsとdecision.resolutionsの省略は[]へ補完する。evidenceやexecution_contextを含め、実際の記録内容が違う再送は同じ操作とみなさない。書き込みはURI取得、テスト実行、モデル呼び出しを内部で行わない。

再送の成功応答は元のcommitを示すものであり、現在のDBの最新状態を保証しない。最新状態はdetail等で読み直す。初期実装では成功記録を期限削除しない。バックアップ復元で破棄された後続の操作まで、復元先に成功記録が残るとは保証しない。

### 11.2 整合性と同時実行

ノード・関係・版・来歴・変更ログ・成功結果の保存は、全成功または全失敗とする。読み取り中の各responseが、途中まで反映された状態を混在させてはならない。

並行更新を見つけたら、相手の変更を失わない。BUSY等の一時的失敗では、キーを維持した再試行を可能にする。自動再試行でユーザーの判断やexpected_revision_idを勝手に最新値へ書き換えない。

初期SQLite実装では、短い書き込みトランザクション内で最終検査とcommitを行う。検索や照合の間に長い書き込みロックを持たない。

## 12. 代表的な操作の組み立て

| 用途 | change_set |
| --- | --- |
| 新規採択 | accepted agreementを作り、必要なscoped_toや根拠を結ぶ |
| 草稿の採択 | draft/proposed agreementをacceptedへ移す |
| 同一合意の改訂 | expected_revision_id付きでacceptedの本文・titleを更新する |
| 全体置換 | 新しいaccepted agreement＋旧agreementをsuperseded＋confirmed supersedes |
| 例外 | accepted agreement＋qualifier付きconfirmed exception_to。元の合意はacceptedのまま |
| 撤回 | accepted agreementをretiredにする。置換先は不要 |
| 合意の分割 | 旧合意をretiredにし、複数の新合意とoriginates_fromで出所を残す |
| 確定したScope所属の変更 | 旧scoped_toをretireし、新しいscoped_toを作る |
| 候補関係の確定 | candidateをconfirmedへ移し、必要なbasis_refsを生成する |
| 誤った確定関係の訂正 | 旧関係をretireし、新しい関係を作る。実行済みsupersedesの修復は§6.6に従う |
| 根拠変更後の再確認 | 本文の意味を確認し、必要なら関係をreconfirm=trueで更新する |
| コード・入力の観測更新 | evidenceがnullのdraft artifactのlocator/content_hash/bodyをsave-draftで更新する。採択済みの合意は変更しない |
| 検査結果の記録 | 既存の対象版をsubject_refsに持つ新しいevidence artifactをsave-draftで作る。失敗結果も保存できる |
| 実装・検証の対応付け | implemented_by、またはpassedの観測へのverified_byをconsult/applyで確定する |
| 再検証後の対応付け | 新しいevidence artifactへのverified_byを作り、必要なら旧関係を同じapplyでretireする。過去の観測は残す |
| 未解決事項の終了 | questionをretiredへ移し、理由と必要な解決先を来歴・関係で残す |

acceptedの意味・適用を変える操作はconsult/applyを通す。save-draftで許された途中状態の整理は、毎回人間との折衝を要しない。

## 13. エラー一覧

| HTTP相当 | code | 次の行動 |
| --- | --- | --- |
| 400 | INVALID_REQUEST / INVALID_CHANGE | フィールド・型・状態遷移等を直す |
| 400 | INVALID_BASIS / NO_CHANGES | basisの取り違えを確認、または不要な更新を省く |
| 400 | UNSUPPORTED_FEATURE | meta.capabilitiesを確認し、未対応の任意機能を使わない |
| 400 | UNSUPPORTED_FORMAT | 対応するjson format_version=2または本版のSQLite退避を使う。黙って変換しない |
| 400 | INVALID_DATABASE | DB形式・参照整合性を確認する。不正部分を切り捨てて復元しない |
| 404 | TARGET_NOT_FOUND / REVISION_NOT_FOUND | IDまたは版を再確認する |
| 409 | CONSULTATION_REQUIRED | accepted変更をconsult/applyへ回す |
| 409 | UNRESOLVED_DECISION | 残る意味判断を解決する。必要なら人間へ打診 |
| 409 | PRECONDITION_CHANGED / BASIS_CHANGED / CONTEXT_CHANGED | 差分を読み、必要箇所を再照合する |
| 409 | EVIDENCE_SUBJECT_CHANGED | 観測対象の版を確認し、必要な検査と新しい結果記録を行う。古い結果の固定版を書き換えない |
| 409 | CURSOR_STALE | 検索を新しい版でやり直す |
| 409 | IDEMPOTENCY_CONFLICT | 入力の取り違えを確認する。別操作なら新しいキーを使う |
| 409 | BASIS_UNAVAILABLE / RULES_CHANGED | 現在のデータと処理規則でconsultし直す |
| 409 | DESTINATION_EXISTS | 新しい退避先・復元先を指定する。既存ファイルやディレクトリを上書きしない |
| 413 | LIMIT_EXCEEDED | 入力を分割・縮小する。部分反映はない |
| 503 | BUSY | 同じキーで再試行できる。前提を自動上書きしない |

異なるdatabase_idは400 INVALID_BASIS。basisより現在のgraph_revisionが小さい、基準履歴が利用不能、同じ基準連番のsnapshot_idが一致しない場合は409 BASIS_UNAVAILABLEとする。これにより、バックアップへ巻き戻してから同じ連番まで進んだ別履歴へ、古いbasisを流用しない。

## 14. GET /v1/meta

dataにはapi_version、spec_version、rules_version、database_id、graph_revision、snapshot_id、capabilities、limitsを返す。capabilitiesは§2の9操作名を含み、実装済みの場合だけsearch_descendants、markdown_exportを追加する。artifactのevidenceと12種類の関係は本版の必須契約であり、任意機能へ格下げしない。

limitsはmax_page_size=100、max_title_chars=240、max_body_bytes=1048576、max_request_bytes=4194304、max_change_operations=100、max_locator_chars=2048、max_evidence_subject_refs=100を返す。本版はこの既定値で実装する。値を将来変更する場合は契約版へ反映する。

任意機能が未対応でも既定の操作は使える。searchでinclude_descendantsを省略またはfalseにする場合、search_descendantsは不要。exportのformat=jsonにはmarkdown_exportは不要である。未対応機能の使用は400 UNSUPPORTED_FEATUREとし、details.capabilityへ必要なcapability名を入れる。

同じAPI v1の試作中でも、破壊的な契約変更にはspec_versionとrules_versionの更新を伴わせ、旧クライアントが互換性を判断できるようにする。公開安定版のバージョニング方針は試作結果を受けて定める。

## 15. 旧APIとの対応

| 旧案 | 本版 |
| --- | --- |
| views/state、scope-brief | search＋detail＋relationsで基本機能を先に実装。便宜viewは追加候補 |
| views/node | nodes/{node_id}とrelations |
| history/node/{node_id} | history/node/{node_id}を維持し、relationも対応 |
| context/task-context | 初期必須から外し、必要なら探索の入口として追加 |
| proposal-impact | 維持。具体的change_set、版、watch、basisを定義 |
| apply-proposalのdecision.action | change_setで操作内容を明示。採択・例外・置換・撤回・整理を共通に扱う |
| 任意のconsultation_fingerprint、base_revision_id | 必須のbasisへ置換。個別版とDB全体の変更連番を区別 |
| state、is_inferred | lifecycle、およびconfirmationとoriginへ分ける |

v0.2からの自動移行は展示版の対象外とする。旧DB・旧論理スナップショットを保持し、本版の試作は新しいDBから始める。rules_version=core-0.3.0により旧basisを無効化し、旧形式を推測変換して開かない。将来の移行でも、未確認の記録を確定済みへ推測変換しない。

## 16. CLIの初期化と保守

この節は、日常の9操作を動かすための初期設定とデータの持ち運びを定める。実装時の契約であり、現時点でCLIが配布済みという意味ではない。

### 16.1 DBの指定と初期化

DBパスは共通オプションのlatis --db PATH、次に環境変数LATIS_DB、どちらもない場合は作業ディレクトリの.latis/latis.sqliteを使う。相対パスは作業ディレクトリから解決し、親ディレクトリに別DBを探して切り替えない。

latis initは、標準入力の{}を受け取り、指定パスに空のDBを作る。database_idと初期snapshot_idを生成し、graph_revision=0とする。spec_version=0.3-demo-draft、rules_version=core-0.3.0を保存する。既に本版の有効なLATIS DBがあれば初期化し直さず、現在のmetaを返す。別形式のファイルなら400 INVALID_DATABASE、旧版等の対応外のLATIS DBなら400 UNSUPPORTED_FORMATを返し、上書きしない。通常の検索・書き込み操作では、存在しないDBを黙って新規作成しない。

通常操作のCLI入力は、HTTPのpath parameterとquery/bodyを一つのJSONオブジェクトへまとめる。たとえばdetailはnode_idと任意revision_id、historyはtarget_type、target_id、limit、cursorを受け取る。POST系は本文をそのまま使い、metaは{}とする。

CLI終了コードは成功0、契約上のエラー1、予期しない実行障害2とする。可能な限り失敗時も同じJSON envelopeを返す。ログと進捗表示をstdoutへ混ぜない。

### 16.2 退避と移送

保守操作はbackup、export、restoreの3種類とする。これらは既に存在するDBと履歴を一貫した形で退避・移送する操作である。Markdown exportだけは現在状態の閲覧用投影であり、復元形式ではない。外部の仕様文書の取り込みにはsave-draftを使う。

| 操作 | stdinのJSON | 効果 |
| --- | --- | --- |
| backup | destinationのみ必須（新しいファイルパス） | 一貫したSQLite DBスナップショットを保存 |
| export | destination必須。formatはjson / markdown、既定json | jsonはformat_version=2の完全な論理スナップショット。markdownは§16.3の任意機能 |
| restore | source（ファイルパス）、format（sqlite / json）を必須 | --dbで指定した、まだ存在しないDBへ検証して復元 |

パス文字列は空でないstringとし、相対パスはCLIの作業ディレクトリから解決する。保守操作にidempotency_keyは付けず、DBのgraph_revisionを進めない。backup/exportの既存出力先、restoreの既存DBは409 DESTINATION_EXISTSで拒否する。失敗した一時出力を完成した退避として扱わず、書き込み途中のDBファイルを単純コピーした結果を一貫したbackupとみなさない。完成物を新しい出力先へ公開してから成功を返す。

export/restoreのformatが上表以外の文字列の場合は400 UNSUPPORTED_FORMATとする。exportのjsonでnode_idsやscope_idsを指定することは400 INVALID_REQUESTとし、完全スナップショットを部分輸出へ変えない。format=markdownが既知でもcapabilityがない場合は400 UNSUPPORTED_FEATUREとなる。

完全な入力例:

```json
{"destination":"demo-backup.sqlite"}
```

上はbackup用である。JSON移送のexportとrestoreは次の入力を使う。

```json
{"format":"json","destination":"demo-snapshot.json"}
```

```json
{"format":"json","source":"demo-snapshot.json"}
```

backup/exportの成功dataはformat（sqlite / json / markdown）、destination（絶対パス）、database_id、graph_revision、snapshot_idを持つ。restoreの成功dataは§14と同じmeta内容とする。sourceは読み取りだけを行い、復元成功・失敗のどちらでも変更しない。

論理スナップショットの最上位はformat="latis-snapshot"、format_version=2、meta、nodes、relations、revisions、provenance、commits、idempotency_recordsとする。6種類の記録は配列。検索索引や生成要約は含めず、復元時に再構成する。exportは一つの読み取りスナップショットを使う。

- metaはdatabase_id、graph_revision、snapshot_id、rules_version、spec_versionを含む。
- nodes/relationsは現在の保存内容。Nodeのlocator/content_hash/evidence、およびRelationのbasis_refsを含む。導出されたscope_ids、basis_status、診断は含めない。
- revisions/provenanceは過去の完全な内容を含む。
- commitsの要素はgraph_revision、snapshot_id、created_at、change_refs、membership_changes、provenance_idを持つ。初期commitは変更配列が空でprovenance_id=null。
- change_refsの要素はtype、id、before_revision_id、after_revision_id。新規作成のbefore_revision_idはnullとする。
- membership_changesの要素はnode_id、before_scope_ids、after_scope_ids。本文版が変わらない所属変更も記録する。
- idempotency_recordsの要素はidempotency_key、operation、request_digest、response。成功応答を同じ内容で再返却できるようにする。

配列はnodes/relations/provenanceをid昇順、revisionsをcommit_revision・target_type・target_id・revision_idの順、commitsをgraph_revision昇順、idempotency_recordsをidempotency_key昇順で出力する。各IDの比較はUTF-8バイト列順とする。referencesの集合も同じ正規化順序を用いるが、原文やsource_refsの順序は変えない。

復元はID、版、来歴、commitの同一性を保持する。参照整合性、最新レコードと履歴の対応、metaとcommitの対応、evidence.subject_refsの対象IDと過去版の対応を検証し、不正な部分だけを取り除いて成功扱いにしない。現在の対象版と古い観測版が異なることは正当な履歴であり、復元時に現在版へ書き換えたり、古い観測を捨てたりしない。過去のconfirmed関係が現在changedであることも許す。

JSONはformat="latis-snapshot"かつformat_version=2、本版のspec_version/rules_versionだけを受理する。format_version=1を含む未対応形式・版は400 UNSUPPORTED_FORMATとし、自動移行しない。同じくSQLite restoreは本版と整合する既知のDB形式だけを受理する。対応形式の内部に不正なフィールドや参照がある場合は400 INVALID_DATABASEとする。新しいDBファイルが完成してから利用可能にし、失敗した復元先を通常操作で開かない。

復元による履歴の巻き戻し後は、§3・§10のsnapshot_id確認で古いbasis/cursorを検出する。複数のコピーを別々に更新してマージする操作は本版に含めない。

### 16.3 Markdown投影（任意capability: markdown_export）

exportでformat="markdown"を指定した場合に使う。対応済みの実装だけがmeta.capabilitiesへmarkdown_exportを掲示する。未対応では400 UNSUPPORTED_FEATUREを返す。

| フィールド | 契約 |
| --- | --- |
| format | 必須、"markdown" |
| destination | 必須、空でないstring。まだ存在しない出力ディレクトリ |
| node_ids | 任意、空でない既存ノードID配列。重複除去・昇順化する |
| scope_ids | 任意、空でない既存Scope ID配列。重複除去・昇順化する |

node_idsとscope_idsは同時指定できない。両方省略した場合は全ノードの現在版を選ぶ。node_idsは指定ノードを、scope_idsはactive/confirmed scoped_toでそのいずれかへ直接所属するノードを選ぶ。Scope自身を暗黙に追加せず、子孫や未分類も自動追加しない。状態やkindによる暗黙の除外はなく、rejected/superseded/retiredも選択対象に含める。0件の選択結果は有効であり、index.mdだけを作成する。存在しないIDは404 TARGET_NOT_FOUND、scope_ids内の非Scopeは400 INVALID_REQUESTとする。

```json
{
  "format": "markdown",
  "destination": "demo-view",
  "scope_ids": ["scope_retention"]
}
```

同じDBスナップショットから、次の規則で出力する。

1. 各選択ノードのファイル名は`<kind>/node-<encoded_id>.md`とする。encoded_idはIDのUTF-8バイト列をbase64url化し、末尾の=を除いた文字列。不透明なIDをそのままファイルパスへ使わない。
2. ファイル先頭の`---`で囲んだfront matterには、完全なNodeのフィールド、scope_ids、provenance_ids、relationsを持つJSONオブジェクトを置く。JSONはYAML 1.2としても読めるため、独立したYAML変換器を必須にしない。bodyはfront matterから除き、その直後へUTF-8の原文を改変せず置く。titleはfront matterへ必ず含める。
3. relationsは選択ノードへ直接接続する現在の関係の配列で、各要素はdirection（in / out）と完全なRelationであるrelationを持つ。candidate/confirmed、active/retiredのいずれも含め、relation.id昇順にする。端点が出力対象外でも、そのIDとbasis_refsを省略しない。evidence.subject_refsも固定版を含めて出力する。範囲外ノードの本文・外部ファイルは取得しない。
4. index.mdにdatabase_id、graph_revision、snapshot_id、spec_version、選択条件と、ID昇順のノード一覧（ID・title・kind・lifecycle・相対ファイルリンク）を記す。参照先が選択範囲外なら、生成されていないファイルへのリンクを作らずIDで示す。

投影は読み取り専用であり、編集してもDBは更新されない。Markdownをrestoreへ入力すること、Markdown import、項目同期は本版に含めない。DBを復元するには§16.2の完全なJSONかSQLiteバックアップを使う。
