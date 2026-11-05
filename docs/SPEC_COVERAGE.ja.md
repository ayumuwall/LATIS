# LATIS 仕様と実装の対応

現行の [Spec](v0.3.0/LATIS_Spec.md) と [API](v0.3.0/LATIS_API.md) を基準に、P0とP1の構造的な契約と、LLMの行動に関する受け入れを分けて追跡する。作業の進捗は [タスク管理票](TASKS.ja.md) で管理する。

## 判定の単位

M1では入力・出力・保存・変更検知のP0コア契約を、M2ではP1の子孫Scope検索・Markdown投影を、自動テストと実CLIで確認した。M3では `claude -p --safe-mode --model claude-opus-5-5 --effort high` で16ケースを実行し、操作・DB・現物と自然文を確認した。ケースごとの実施範囲と結果は [M3検証記録](M3_VERIFICATION.ja.md) にまとめる。Pythonによる既定シナリオとLLMの利用結果は別に記録する。

## 規範条項との対応

以下はM1で照合するコア契約。検証欄のC01〜C33は後段の検証索引、Eは [既存の受け入れテスト](../tests/test_engine.py)、Rは [実CLIの再現テスト](../tests/test_rehearsal.py) を指す。EのA/E番号はテスト名と旧実装計画のケースに対応する。

実装の略記は [model](../latis/model.py)、[engine](../latis/engine.py)、[storage](../latis/storage.py)、[cli](../latis/cli.py)。P0のコア欄は照合と回帰検証を終えた状態として管理する。意味判断を必要とする項目の利用確認は、下表と別にM3で行う。

### 共通契約と保存モデル

| 条項 | 確認した契約 | 主な実装 | 検証 |
| --- | --- | --- | --- |
| Spec §1〜3、API §1〜2 | LLMとコアの責務、9操作とCLI、外部URI・コマンド・LLMをコアが実行しない境界 | engine.execute、cli.main | C04、C23、R。LLMの自発的利用はM3 |
| API §3.1・3.4 | UTF-8 JSON、未知キー、型、nullと省略、Unicodeスカラー数・UTF-8バイト数、title/body/操作数/要求サイズの上限 | modelの入力検査、decode_json、canonical、cli.main | C01〜C04、C06、C22、C30 |
| API §3.2・§14 | 成否envelope、codeによるエラー、仕様・規則・DB・snapshot、capabilitiesと全limits | envelope、engine._read | C01、C02、C32 |
| Spec §4.1、API §4.1・6.2〜6.3 | Node全フィールド、8 kind、IDとkindの不変性、自然文の保持、nullable情報のartifact限定 | node_values、change_set、engine._simulate | C03〜C06、C22 |
| Spec §4.2、API §4.1 | locatorの形式・長さ、SHA-256の形式、独立したnull、通常artifactの再観測 | node_values、engine._simulate | C04、E:E01/E05、R |
| Spec §4.3、API §4.1.1 | subjectの実在する過去版、型・件数・重複・版矛盾、方法・結果・観測時刻・実行者・出所、作成後の固定値 | evidence、timestamp、existing_revision、engine._simulate | C22、C28、C30、E:E07/E09 |
| Spec §4.4、API §4.2 | 12 relation kind、向き・端点・状態・origin・qualifier・priority・basis、変更禁止フィールド | change_set、validate_graph、engine._simulate | C07〜C09、C11、Eの循環・例外テスト |
| Spec §4.4・5.1、API §4.4 | Revision、変更後target_refs、判断前consulted_basis、decisionと来歴の対応、主体・実行情報を自己申告として保存 | record、write_commit、history | C24、C29、E:E12 |
| Spec §5.2、API §3.1 | 不透明ID、個別版、commit連番、初期snapshot、同じ連番に達した別履歴の区別 | uid、state_at、_simulate、_write | C16、C32、C33、E:A25 |
| Spec §5.3 | scoped_toから所属を導出し、Scope階層をcontainsで表す。所属と権威を区別 | memberships、validate_graph | C07、C10、C12、E:A17 |
| Spec §6.1〜6.2、API §4.1〜4.2 | 許可された状態遷移、終端からの復活禁止、candidate/confirmed/originの分離 | transition、engine._simulate | C05、C08、C09、E:A12/A13 |
| Spec §6.3、API §4.3 | 事実・保存した判断・推定・未確認を区別する診断。根拠変更による自動失効を行わない | diagnostic、basis_status、relation_diagnostics | C15、C27、E:A12/E05 |

### 探索と読み取り

| 条項 | 確認した契約 | 主な実装 | 検証 |
| --- | --- | --- | --- |
| Spec §8.1、API §5.1 | 既定のaccepted agreement、kind/lifecycle、ScopeのOR、未分類、Scope自身のフィルター、子孫検索の任意capability | engine._read | C01、C10、E:A02/A20/A21、P01〜P05 |
| Spec §8.1、API §5.1 | NFKC＋casefold、リテラル部分一致AND、日本語2文字、title一致の順位、ID順、先頭240文字の抜粋、summaryの形 | engine._read、summary | C03、C10、E:A20 |
| API §5.2〜5.5 | 現在・特定版の詳細、直接関係の方向とフィルター、相手のlifecycle、履歴順・ページ・来歴の重複排除 | engine._read、existing_revision | C11、C32、E:E12 |
| Spec §7.2、API §5.3 | 内容依存関係のcurrent/changed/untracked、構造関係のnot_applicable、過去版へ現在の状態を混ぜない | basis_status、relation_diagnostics、engine._read | C08、C11、C27、E:A12/E05/E12 |
| Spec §8.2、API §3.2〜3.3 | 1応答の同一snapshot、決定論的な順序、条件・DB・規則・snapshotに結び付くcursor、DB変更時の失効 | engine.execute、page | C11、C15、C33、E:A16/A19 |
| Spec §8.3〜8.4、API §5.1・8.3 | 構造的な取得理由、候補と正本の区別、推論modeを標準検索へ混在させない境界 | _basis、_consult、入力の未知キー拒否 | C01、C13〜C15、E:A16/A21。推論検索の追加はM6 |

### 保存と照合と反映

| 条項 | 確認した契約 | 主な実装 | 検証 |
| --- | --- | --- | --- |
| API §6.1 | 4種類の操作、1〜100操作、refの形式と一意性、前方参照、同じ対象へのupdateの重複禁止 | change_set、engine._simulate | C03、C06、C16、正規化fixture |
| API §6.2〜6.3 | 作成状態と既定null、setの省略と解除、expected_revision、同値だけの変更の拒否、evidenceの後付け禁止 | change_set、engine._simulate | C04〜C06、C22、EのNO_CHANGESテスト |
| Spec §7.1〜7.2、API §6.4〜6.5 | 内容依存の確認時に最終版を記録し、追加根拠を維持・置換・解除する。候補や構造関係への不正な再確認を拒否 | change_set、engine._simulate | C07、C08、C13、C14、C28、E:A26 |
| Spec §7.3、API §6.6・§12 | 例外の条件とaccepted端点、原子的な全体置換、既存acceptedからの置換、置換訂正、新しい出所、撤回・分割 | engine._simulate、validate_graph | C09、Eの例外・置換・終端状態テスト。利用判断はM3 |
| Spec §7.4、API §4.2.1 | passedの証拠、固定subjectの自動包含、反映後最終版との一致、旧証拠の付け替え禁止 | engine._simulate、_basis | C07、C13、C22、C28、E:E03〜E09 |
| Spec §9.1、API §7 | save-draftでの草稿・候補・新規Scope・草稿の所属作成/終了、採択済み情報への迂回禁止 | engine._simulateのdraft検査 | C12、C22、E:A01/A14、草稿と所属の同時終了テスト |
| Spec §9.2、API §8.1〜8.2 | 正規化した変更の構造検査、参照版の存在、書き込まないconsult | _normalize、_simulate、_consult | C15、C32、E:A16 |
| API §8.3 | seedとbasis.refs、直接所属、明示関係の追加根拠、新規・既存evidenceの一段だけの展開、watchの再構築 | engine._basis | C13、C14、C28、E:A11/A26 |
| API §8.4 | 既定値、集合の重複排除・順序、原文とsource_refsの順序、JSONとSHA-256、execution_contextの省略と空オブジェクト | canonical、digest、change_set、record | C20、C29、正規化fixtureとEのCLI照合 |
| API §8.5 | 取得順と全inclusion_reasons、打ち切り、次の取得候補、保存された競合・古い判断の診断 | engine._consult | C15、C27、E:A16 |
| Spec §9.3〜9.4、API §9.1〜9.2・9.4 | authority_ref、理由、resolutions、readyの申告、未解決時の拒否、判断前と反映後の版の保存 | record、_write、write_commit | C29、E:E12、UNRESOLVED_DECISIONテスト。授権・意味の判断はM3 |
| API §9.3・§10.2 | 冪等性→basisの対応→expected版→basis refs→変更範囲→最終構造の検査順 | engine._write、_check_changes | C17、C32、E:A09、履歴不足・古い証拠のテスト |
| Spec §10、API §10.1〜10.3 | before/after、所属移動・撤回、Scope内のacceptedに接続する確定関係、priorityのみ・候補・別Scopeの扱い、未分類変更の通知 | engine._check_changes、membership_changes | C18、C19、E:A10/A11/A17/A22 |
| API §10.4・§13 | 再照合先・現在版・差分、履歴不足、固定subjectの差分、エラー時に部分反映しないこと | _write、_check_changes、_simulate | C17、C32、E:A14/E08、BASIS_UNAVAILABLEテスト |
| API §11.1 | DB全体で一意のキー、入力全体の正規化、同一再送の成功応答保存、異入力の拒否、失敗時のキー保持 | engine._write、write_commit | C20、C21、E:A15、基準履歴喪失後の再送テスト |
| API §11.2 | 最終検査・変更・履歴・来歴・成功応答を同じトランザクションで確定。BUSYと同時更新 | engine.execute、write_commit | C21、Eの同時更新・障害注入・BUSYテスト |

### 保守と互換性

| 条項 | 確認した契約 | 主な実装 | 検証 |
| --- | --- | --- | --- |
| Spec §11、API §16.1 | DB指定の優先順、親を探索しない、通常操作で自動初期化しない、initの再実行と未対応DBの拒否 | cli.main、engine._maintenance、storage.connect | C23、C32、Eの不明DB・旧形式テスト |
| API §16.2 | 一貫したSQLite backup、format_version=2の完全JSON、6種類の記録、元のID・版・snapshot、出力順 | engine._backup、storage.read、order_snapshot | C24〜C26、E:A23、R |
| API §16.2 | 最新レコードと履歴、参照・所属差分・来歴・成功応答、過去の証拠・changed関係の保持、未知情報の拒否 | validate_snapshot、validate_target、parse_record | C24、C25、C31、Eの不正復元・旧証拠復元テスト |
| API §16.2 | 既存先の拒否、一時出力を完成品にしない公開、復元失敗時の出力削除、sourceの保持 | storage.publish、engine._maintenance | C26、E:A23、既存ファイル・symlinkのテスト |
| Spec §12〜13、API §1・15 | 固定語彙、未対応のcapability・保存形式の明示的拒否、旧形式や自己申告の推測変換をしない | 入力検査、meta、restore | C01、C20、C29、E:A21 |

## コア検証の索引

C番号は [test_contracts.py](../tests/test_contracts.py) の以下のメソッドに対応する。複数の入力・状態・破損例をsubTestやループで検証するメソッドを含む。

| ID | メソッド |
| --- | --- |
| C01 | `test_common_null_unknown_types_and_envelope` |
| C02 | `test_wire_utf8_size_limits_and_json_errors` |
| C03 | `test_scalar_and_byte_limits_preserve_original_text` |
| C04 | `test_uri_hash_and_untrusted_strings_are_data` |
| C05 | `test_node_kinds_and_lifecycle_matrix` |
| C06 | `test_immutable_node_fields_and_local_reference_validation` |
| C07 | `test_relation_kind_matrix_and_final_endpoint_versions` |
| C08 | `test_relation_confirmation_reconfirmation_and_additional_roots` |
| C09 | `test_supersedes_repair_and_existing_accepted_replacement` |
| C10 | `test_search_order_scope_or_and_summary_contract` |
| C11 | `test_relations_filters_pages_history_and_retired_endpoint` |
| C12 | `test_save_draft_permission_boundary_and_terminal_membership` |
| C13 | `test_consult_new_evidence_additional_root_is_watched` |
| C14 | `test_consult_evidence_expansion_is_one_level` |
| C15 | `test_consult_scope_conflicts_and_inclusion_reasons` |
| C16 | `test_opaque_ids_do_not_collide_with_planning_placeholders` |
| C17 | `test_precondition_and_basis_error_precede_context_or_missing_delta` |
| C18 | `test_candidate_and_unrelated_scope_updates_do_not_block` |
| C19 | `test_explicit_relation_priority_change_is_basis_changed` |
| C20 | `test_idempotency_normalization_global_keys_and_execution_context` |
| C21 | `test_same_key_in_separate_cli_processes_commits_once` |
| C22 | `test_evidence_reference_shape_limits_and_explicit_immutability` |
| C23 | `test_cli_db_precedence_and_missing_database_not_created` |
| C24 | `test_snapshot_rejects_types_provenance_and_success_response_mismatch` |
| C25 | `test_sqlite_duplicate_json_keys_and_invalid_scalar_are_not_discarded` |
| C26 | `test_backup_wal_snapshot_and_publish_failure` |
| C27 | `test_explicit_retired_judgment_reports_old_basis` |
| C28 | `test_maximum_evidence_subjects_are_not_limited_by_display_count` |
| C29 | `test_execution_metadata_resolutions_and_source_order` |
| C30 | `test_rfc3339_utc_forms_preserve_observation_time` |
| C31 | `test_snapshot_record_times_need_not_be_identical` |
| C32 | `test_basis_metadata_digest_and_read_revision_errors` |
| C33 | `test_cursor_detects_restored_fork_with_equal_revision` |

## 受け入れケースとの対応

以下のコア欄はPythonの検証に対応する。M3欄は利用確認の対応先であり、すべての個別分岐を実行したという意味ではない。実施した16ケースは後段とM3検証記録を参照する。

| ケース | コアで確認したことと検証 | M3の利用確認との対応 |
| --- | --- | --- |
| A01 | 未分類・候補・草稿の保存。E:A01、C12 | M3-03：推測で確定せず利用を始める |
| A02 | search/detail/relations/historyの追加取得経路。C10、C11、E:A02 | M3-03：得た手掛かりから問いを作る |
| A03 | page/related_pageの打ち切りと継続先。C11、C15、E:A03 | M3-03：取得部分を全体と説明しない |
| A04 | 重複する草稿を保持して他の作業を進める。E:A04 | M3-03・05：同一性の検討と必要範囲の整理 |
| A05 | readyとauthority_refを受ける採択経路。C29、E:A05 | M3-04：同じ許可を取り直さない |
| A06 | 通常・監査の別合意、通常の同一ID改訂。E:A06、R | M3-04：曖昧な対象だけ打診する |
| A07 | 無関係のquestionが今回のapplyを止めない。E:A07 | M3-04：残る不整合の影響範囲を判断する |
| A08 | 「90日」を含む原文をそのまま保持する。C03、E:A08 | M3-03・05：意味を「以上」等へ変えない |
| A09 | expected_revisionの変化を拒否。C17、E:A09 | M3-06：再取得して再照合する |
| A10 | Scope内の追加・撤回・所属移動をbefore/afterで検知。E:A10 | M3-06：構造変化と意味競合を区別する |
| A11 | 関係・所属・追加根拠の変化を検知。C13、C14、E:A11 | M3-06：必要な構造を取り直す |
| A12 | 参照版の変化を診断し、acceptedを維持。C08、C27、E:A12 | M3-06・07：効力と再検討を区別する |
| A13 | candidate/confirmed/originを分離。C07、C08、E:A13 | M3-05：推定を確定済みと扱わない |
| A14 | 不正変更・途中障害の部分反映を防ぐ。C06、C24、E:A14、障害注入テスト | M3-05・06：失敗を確定済みと説明しない |
| A15 | 同一入力の再送、異入力の拒否、失敗キーの再利用。C20、C21、E:A15 | M3-06：結果不明時に同じキーを使う |
| A16 | 同じ版・条件で順序・basis・診断が再現。C15、E:A16、正規化fixture | LLMの文言一致は判定対象にしない |
| A17 | priorityのみの変更と明示参照の扱いを分離。C19、E:A17 | M3-05：局所性・数値で勝者を作らない |
| A18 | 毎編集に事前照会を要求する操作を追加しない。9操作とGuideの責務を照合 | M3-04：不要な照会・承認を増やさない |
| A19 | 途中のDB更新でCURSOR_STALE。C11、C33、E:A19 | M3-03：新しい条件・版で再検索する |
| A20 | 日本語2文字、NFKC/casefold、記号の部分一致。C10、E:A20 | M3-03：言い換えが必要な場合の再検索 |
| A21 | 旧形式・旧版を拒否し、元データを保持。E:A21、不正SQLite復元テスト | 自動移行はM6-04 |
| A22 | 草稿の所属・候補・別Scopeの変更で一律停止しない。C18、E:A22 | M3-06：必要な変更だけ再検討する |
| A23 | SQLite/JSONでID・履歴・証拠・成功応答を保持。C24〜C26、C31、E:A23 | M3-08：復元したDBから再利用する |
| A24 | 9操作のJSON stdin/stdout、終了コード、ログの分離。C02、C23、R | M3-01〜08：ClaudeがCLIを実際に使う |
| A25 | 同じgraph_revisionの別履歴をsnapshotで拒否。C33、E:A25 | M3-06：古いbasisを流用しない |
| A26 | 明示関係・再確認で維持する追加根拠をbasisへ含める。C08、C13、C14、E:A26 | M3-06：根拠の差分を読む |
| E01 | 現物のコード・テストを別artifactとして観測。C04、R | M3-07：Claude自身が現物を読む |
| E02 | 対象版・方法・実結果・観測時刻・実行者を保存。C22、C29、C30、R | M3-07：実行とレビューを区別する |
| E03 | passedへのverified_byと固定subjectの自動包含。C07、C28、R | M3-07：合意との対応を判断する |
| E04 | failed/inconclusive/証拠なしをconfirmedにしない。C07、E:E04 | M3-07：失敗や未検証を成功と説明しない |
| E05 | コード・テスト版の変化でchangedと診断。E:E05、R | M3-07：合意違反や失効と即断しない |
| E06 | 旧証拠のreconfirmとbasis_targetsによる付け替えを拒否。E:E06、R | M3-07：必要な検査と新しい証拠へ進む |
| E07 | 実在する過去版の証拠を保存・復元。C22、E:E07、旧証拠復元テスト | M3-07：現在版の成功と区別する |
| E08 | 照合後と同じbatch内の対象変更を拒否。E:E08、C28 | M3-06・07：対象版を確認し直す |
| E09 | evidence/locator/content_hashを固定。C22、E:E09 | M3-07：訂正は新しい証拠へ残す |
| E10 | 実ファイルだけの変更をコアが検知したとしない。E:E10、Rの現物照合 | M3-07・08：説明前に現物を再観測する |
| E11 | 結果は実行ごとの新規artifact。検証関係0件を成功へ変換しない。R、E:E11 | M3-07：記録と実行の範囲を説明する |
| E12 | 前提版・変更後版・主体・実行情報・証拠を履歴から再取得。C29、E:E12、R | M3-08：独立したClaudeセッションで再利用する |

## P1と保留事項

P番号は [test_p1.py](../tests/test_p1.py) の同番号で始まるメソッドに対応する。実装は [projection](../latis/projection.py)、engine._read/_backup、storage.publish_directory/rename_directory。

| 条項 | 確認した契約 | 検証 |
| --- | --- | --- |
| Spec §5.3・8.1、API §5.1 | active/confirmed containsの全深さ・複数経路・複数起点を展開し、元Scopeを含めて重複除去・ID昇順。直接検索とinclude_unscopedを維持 | P01、P02 |
| API §3.3・5.1 | フラグとexpanded_scope_idsを常に返す。空Scopeは全体検索。cursorはフラグ・展開集合・snapshotに結合し、階層更新時はCURSOR_STALE | P02、P03、C33 |
| Spec §5.3、API §5.1・8.3 | 子孫をconsultのwatchや効力へ継承せず、子孫だけの更新で親の計画を一律停止しない | P04 |
| API §14・16.3 | 両capabilityの掲示、未対応時のUNSUPPORTED_FEATUREとdetails.capability、init/restore応答の整合 | P05、P18、E:A21 |
| API §16.3 | 全体/明示ノード/直接Scopeの選択、同時指定・空配列・未知ID・非Scopeの拒否、0件と全kind/全lifecycle、候補・終了所属の除外 | P06〜P08 |
| API §16.3 | IDのUTF-8をbase64url化したパス、body以外の完全NodeとScope/来歴/全直接関係、原文bodyのバイト保持 | P09〜P11 |
| Spec §4.3、API §16.3 | candidate/confirmed・active/retired関係と方向、範囲外端点/basis_refs、古いevidence.subject_refsを保持。範囲外本文や外部ファイルを取得しない | P09、P10 |
| API §16.3 | indexのDB/graph/snapshot/仕様/選択条件、ID順の一覧と存在するファイルへの相対リンク、Markdown文字のエスケープ | P06、P08、P11、P12 |
| API §3.2・16.3 | 並行WAL更新時も同じsnapshotから全ファイルを生成。完成後だけ公開し、既存先・空ディレクトリ・symlink・公開競合で上書きしない | P13〜P15 |
| API §16.3 | 書込/fsync/公開失敗時の一時出力削除とDB保持、投影編集の非反映、Markdown restoreの拒否、CLI終了コード | P16、P17、P19 |
| API §16.2〜16.3 | 実CLIによるP1利用、完全JSON形式2と復元後の検索を維持。配布wheelの同梱Guide・例 | P18、M2のパッケージ検証 |

| 保留対象 | 現在のコア契約 | 残るタスク |
| --- | --- | --- |
| API §15の旧形式移行 | 旧形式・旧basisを推測変換せず拒否 | 自動移行はM6-04 |
| Spec §8.4・§12〜13の拡張 | 正本と派生索引、主体とモデル、分類と権威等の境界を維持し、未定義のフィールドを拒否 | M6で採否・仕様化 |

P1のコア契約はM2で実装・検証した。M3のprojectionではClaudeがcapabilities確認後に子孫検索を使い、見つかった合意だけをnode_idsでMarkdownへ投影した。実展示環境・ホストされたCI・最終受け入れはM4〜M5で確認する。

## 検証結果

M2時点の実行対象はM1完了コミット `7c95c67` にM2の変更を加えた作業ツリー。全94件（P0の75件とP1の19件）の結果と対象ソースの識別情報は [M2検証記録](M2_VERIFICATION.ja.md) に保持する。P0初版 `3b52beb` に対するM1の結果は [M1検証記録](M1_VERIFICATION.ja.md) を参照する。現在の運用・復旧・配布と対象版は [受け入れ記録](ACCEPTANCE.ja.md) に分け、過去のハッシュを現在の実装に付け替えない。

M1で修正した主な差分は次のとおり。

- 新しいevidence artifactを追加根拠にした場合も、既存のsubjectノードをwatchとbasisへ含める。
- 個別の前提版の不一致を、差分履歴・watchの検査より先に返し、再照合先と現在版を応答する。
- Scopeだけを起点にしても範囲内の保存済み競合を診断し、明示参照した終了済み判断の古い根拠も報告する。
- 計画内の仮IDが既存の不透明IDと衝突しないようにする。
- 草稿を終了するbatchで新しいconfirmed所属を作る迂回を拒否し、固定された観測値への不正な更新を先に検査する。
- CLI・JSON復元・SQLite内のJSONで重複キーを拒否し、深すぎる入力を契約エラーにする。UTC時刻の有効な表記と原文を保持する。
- 復元時に版の型、正規化された集合、判断と来歴、変更計画、照合時の参照版、成功応答の作成/更新分類を検査する。記録時刻同士の一致など、仕様にない条件は追加しない。

M2では子孫展開、読み取り専用投影、排他的ディレクトリ公開、P1の入力例と配布物の検査を追加した。階層更新で展開集合が変わった場合も、cursorはDB版の失効を先に判定する。

Claude CLIによる利用テストはM1・M2では実施せず、M3で16ケース・17呼出し・CLI操作182件を確認した。入力条件と判定は [M3ケース](M3_CASES.ja.md)、実結果と対象の識別情報は [M3検証記録](M3_VERIFICATION.ja.md) を参照する。

M3では未整理の探索と全件取得、質問と明示済み対象、同一IDの改訂と明示された置換・分割等、4種類の前提変更と無関係更新、結果不明、成功・失敗・未観測変更、P1、独立セッションを確認した。LLMへCURSOR_STALEを実際に返す分岐や、JSON復元後のLLM再利用はこの16ケースに含めていない。Coreの該当契約は既存の自動テストで確認し、運用と同一構成での最終受け入れをM4〜M5へ引き継ぐ。

M4では [実プロセスの検査](../tests/test_processes.py) でcommit前の強制終了・BUSY後の同一キー再試行・異なるキーの競合・公開直前の競合と停止を確認した。[復元の検査](../tests/test_reset_demo.py) ではDB・現物・証拠の一組の復元、両形式の全記録の保持、復元後の別履歴に対するbasis・cursorの拒否を実CLIで確認した。配布物は [再現スクリプト](../scripts/verify_release.py) と [導入後の実CLI検査](../scripts/check_distribution.py) を使う。LLM自動試験の隔離範囲は [別記録](LLM_SANDBOX.ja.md) を参照する。
