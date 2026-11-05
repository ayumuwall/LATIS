# 展示UIの検証記録

2026-11-06 JST。LATIS / Agreement Explorerの展示実装。CoreのM5完了（45/45）と展示Dの受け入れを区別する。映像収録はユーザーの追加指示で必須対象から外した。外部ディスプレイと担当者による当日操作は未確認で、展示全体の受け入れ完了とはしない。

## 対象と環境

基準コミットは`86a8d9b8de2713bfd31da386967875ab82d80155`。展示追加は未コミット。対象ファイルのSHA-256は[ソース一覧](GRAPH_DEMO_SOURCES.json)に固定する。実装は`tools/graph_demo/`、検査は`tests/test_graph_projection.py`・`test_graph_demo.py`・`graph_model.test.cjs`。初期UIの時点ではCoreのAPI・保存形式・依存は変更していない。追加指示D-27では、ユーザーが必須としたプロジェクト名をCoreにも追加し、仕様・規則・保存形式を更新した。M5の基準版・実LLM・配布物の受け入れとは区別する。

macOS 15.8.1／x86_64、Python 3.12.0／Unicode 15.0.0。ユーザー指定のPlaywright 1.64.1とChrome 156.0.8078.80を専用の一時プロファイルで起動した。Playwrightは`/tmp/latis-playwright-env`へ分離し、日常のタブ・認証プロファイルを使っていない。内蔵Browserの接続ホストが復旧した結果とは扱わない。

## 自動検査と実画面

| 対象 | 実施方法・結果 | 根拠 |
| --- | --- | --- |
| Python全回帰 | `python3.12 -m unittest discover -v`、150件合格、84.682秒。Core既存契約とプロジェクト名・移行、展示生成、4復元、履歴とHTTPを含む | `/tmp/agent-logs/github.com-LATIS/test.log` |
| 投影とHTTP | 17検査。完全exportとの一致、WAL読取中の並行commit、未対応形式と破損の区別、DB不変、更新・任意パス・query拒否、ロック、不存在、実過去版と未来履歴の除外 | `tests/test_graph_projection.py`、全回帰に含む |
| 展示データ | baseline 13合意、final 14合意。階層、未分類、複数所属、候補、UTC追加、通常の同一ID改訂、監査90日維持。baseline/final × SQLite/JSONの4復元と実テスト各3件 | `tests/test_graph_demo.py`、`.latis/exhibition/prepared-002/` |
| LIVEと復旧 | 最終45項目合格。初回、検索、折畳み、草稿、提案、不採用、終了、置換、所属移動、apply、失敗、再送、関係のみ、近接commit、再読込、断線、不正応答、実ロック、別DB・履歴分岐、HTML不実行、任意の短い白黒反転・ディザとモーション停止 | `/tmp/latis-explorer-project-regression-01/report.json`、CLI記録、PNG。`check_browser.py` |
| 保存後の反映 | SQLiteのcommit正常終了直後から、DOM更新後2回目のrequestAnimationFrameまで、追加0.837126秒・改訂0.227699秒。LLM時間を除外し、目標2秒以内 | 同reportの`latency`。同一端末の時刻で比較 |
| REPLAYと履歴参照 | 最終20項目合格。実関係のフォーカス・原文、実commitの再生・停止・再開・先頭・版選択、旧24時間と新48時間、CHANGE LOGの原文・差分・判断、関係だけのcommit、未来履歴の除外、遅れたLIVE/過去版の応答、取得失敗・復旧、LIVE復帰、DB不変、外部通信不要 | `/tmp/latis-explorer-numbered-replay-01/report.json`、PNG。`check_playback.py`、収録指定なし |
| 稼働中の保持用DB | 8765番で初期選択、通常24時間・監査90日と規範本文、1920×1080／1366×768、ヘッダー58px、領域の重なりなし、REPLAYからの復帰、ページエラーなし・DB不変 | `/tmp/latis-explorer-final-smoke/report.json`、`live-1920.png`・`live-1366.png` |

投影は一つの読み取り専用トランザクションから取得し、履歴からの再構成と現在状態を照合する。REPLAYは保存された時点の状態から所属・診断・根拠版も導出する。過去版へ現在の所属や診断を混ぜない。`basis_status=current`は記録された対象版の一致であり、外部ファイルの自動観測やテストの完全性を意味しない。

合意本文は義務を「〜しなければならない。」、禁止を「〜してはならない。」へ統一した。展示中だった13件も正規consult/applyで同一IDの新しい版へ改訂し、旧版と理由を保持した。その実行では現物を観測して3件を実行し、新しい証拠へ記録した。根拠は`/tmp/latis-requirement-check/{report,before,after}.json`。新しい生成素材も同じ規範表現で作る。

## 隔離下の実Claude

事前の拒否試験26項目が合格。記録は`/tmp/latis-explorer-sandbox-01/report.json`。既存の`llm_acceptance.py`、必須OS隔離、`--restricted`を使い、`claude -p --safe-mode --model claude-opus-5-5 --effort high`を明示した。Guide・API・固定CLI・専用DB・作業ディレクトリを渡し、APIを直接呼んでいない。

通し実行は`/tmp/latis-explorer-llm-03/`。指定・返却モデルとも`claude-opus-5-5`、effort指定は`high`。

| 段階 | 実行結果と意味レビュー |
| --- | --- |
| UTC追加 | 98.223秒、CLI 9操作、rev 6→7。自然な依頼から新しい採択合意と別理由・supports・通常Scope所属を記録。既存ノードとコード・テスト不変。本文は義務・禁止を明示し、UTCは未実装・未検証と説明。機械6項目と意味レビュー合格 |
| 通常ログ改訂 | 217.161秒、CLI 18操作、observe 2回・check 1回、rev 7→11。同一IDで24→48時間、監査90日・UTC不変。理由・旧版・旧証拠を保持し、現物2ファイルと実テスト3件に対応する新証拠・現版の実装/検証関係を記録。機械12項目と意味レビュー合格。実運用のログ削除まで確認したとは説明しない |
| 独立引き継ぎ | 78.113秒、CLI 12操作・observe 1回。前会話・以前の要求JSONを渡さず、現在48時間・監査90日・UTC、理由・旧版・検査証拠と現物hashを再取得。機械8項目と意味レビュー合格。過去の実テストと今回の読み取りを区別し、移動した作業場所のパス差も説明。DB・コード不変 |

各ディレクトリの`*-launch.json`・`*-events.json`・`*-result.json`・`*-snapshot.json`・`*-check.json`・`*-semantic-review.json`に指定値・実操作・結果・採否を保持する。実保存時の画面もUTCはrev 6→7、改訂はrev 7→8→9→10→11と一致し、ページエラーはなかった。当時の画面記録と最終UIのブラウザー検査は対象ソースを区別する。収録の追加実装・再収録は行わない。

以前の`llm-01`はFFmpeg不足でClaude起動前に失敗。`llm-02`の改訂はDBと検査内容が正しかったが、固定コマンド以外の`wc -l`を使ったため手順適合として不採用。OS隔離を突破した結果ではない。許可範囲を変えず具体的な補足を加え、`llm-03`で再確認した。補助JSONの再利用に関する最終説明の小さな例外は意味レビューへ残し、要求の合否と区別する。

ユーザー指示に合わせ、`llm_demo.py`は既定で収録を起動しない。`--capture`は既存補助を任意に使う場合だけ。全回帰後のこの起動設定変更は、構文・helpと`/tmp/latis-explorer-no-capture-02/handover/`の独立引き継ぎで確認した。76.610秒、CLI 13操作とobserve 1回、機械8項目・意味レビュー合格、モデルclaude-opus-5-5/high、DB・コード不変、収録ディレクトリ未作成。直前のno-capture-01は補助呼出元の未正規化パスにより権限拒否でCLI 0回の不合格。通常CLIと同じ正規化をlaunch入口でも行い、許可範囲を変えず新規試験で確認した。

## 保持データと運用

Git管理外の`.latis/exhibition/prepared-002/`に、検証済み素材のbaseline/final・コード・固定証拠を保持。`live-002/`はbaseline、`replay-002/`はfinalを正規restoreで新規復元し、完全snapshotと元のファイルhashの一致を確認した。複写・復元を新しい実行証拠として登録していない。通常の`.latis/latis.sqlite`は使用しない。

現在は`http://127.0.0.1:8765`、DBは`.latis/exhibition/live-002/demo.sqlite`。database_id=`5bf0b757b2f34e5686fc852d82ace4ae`、開始はrev 6／snapshot `fa6968250379434d82467cc9744a4bfe`。復旧用は同じ実履歴のrev 12／snapshot `1e2039de0f2d4b3f99ca0618ab234b62`。元の`/tmp`の作業コピーも上書きしていない。

起動・停止・ACT 0〜3・新規baseline復元・REPLAY切替・LIVE復帰は[手順書](../tools/graph_demo/README.ja.md)を使う。REPLAYからLIVEへ戻る対象は接続中のDBであり、別DBへの自動切替ではない。

固定ログは`/tmp/agent-logs/github.com-LATIS/{dev,test,e2e,task}.log`。実行ごとに上書きする。機械判定・意味レビューは各試験出力へ保持し、生ログをGitへ追加しない。


## 2026-11-06の追加指示：表示番号・Scope・Markdown

D-21・D-22として追加し、ユーザー採択の表示規約をSpec §5.2.1、UIのScope保存をAPI §16.4へ反映した。Coreの不透明なid・9操作・保存形式は維持する。M5時点のCore受け入れと、今回追加したUI規約の検査を区別する。

- 番号はA/P/I/R/Q/S/AR/Tの各系列で1からゼロ埋めなし。実DBの全8種類、改訂・採択・終了後の固定、同一commitの順序、番号の非再利用、SQLite/JSON完全復元、REPLAYでの固定を確認した。表示順や検索結果から採番し直さない。
- 合意番号の完全一致検索、複数所属の共通番号、本文と元idを残したInspectorを実Chromeで確認。行の最小高を従来82/92pxから54/58pxへ変更した。
- scoped_to先のScope詳細と、一覧のS番号付き見出しを対応付けた。折畳み・検索中でも該当見出しを展開・選択して表示し、関係IDにも項目名を付けた。
- Scopeの見出しと詳細から、画面のDB・版・snapshotに固定したMarkdown ZIPを保存できる。直接所属の全kind・全lifecycleを対象にし、Coreと同じindex.md・ノード別Markdownと補助のdisplay-numbers.jsonを出力する。子Scope・範囲自身・未分類は自動追加しない。
- HTTP検査はCoreの実出力とMarkdown全ファイルをバイト照合し、画面の後に追加された記録の除外、空Scope、非Scope・不存在・別DB・分岐の拒否とDB不変を確認した。実ブラウザーは見出し・詳細のZIPダウンロードと、失敗表示を確認した。

結果は`/tmp/latis-explorer-no-note-browser-01/report.json`（43項目）、`/tmp/latis-explorer-numbered-replay-01/report.json`（20項目）。稼働中の8765番の最終確認は`/tmp/latis-explorer-numbered-live-01/report.json`。CLIのMarkdown投影は従来形式を維持し、画面の表示番号はZIP内の補助ファイルから元idへ対応付ける。今回の追加機能に対する新しいLLM利用の合格とは説明しない。

## 2026-11-06の追加指示：注記を履歴へ残さない

D-23として、各本文の展示注記を初期登録前に除去するようにした。既存DBへの改訂で注記を過去版へ残す方法は使わず、prepared-002からlive-002とreplay-002を新規生成・復元した。初期13件・変更後14件、24→48時間・監査90日、実テストと固定証拠は新しい実行として記録した。以前の試験記録を新しいDBの証拠へ貼り替えていない。

全142件合格、85.099秒。追加検査はbaseline/finalの全snapshot・過去版・来歴に注記がないことを確認した。新しい素材で実ブラウザー43項目が合格。稼働中の8765番でも本文・全過去版のREPLAY・実Markdown ZIPに注記がなく、閲覧によるDB不変を確認した。結果は`/tmp/latis-explorer-no-note-live-01/report.json`、画面は同ディレクトリの`clean-body.png`。旧試験の記録は歴史的結果として区別し、現在の表示対象には使わない。

## 2026-11-06の追加指示：1スコープ1ファイルの文書

D-24で、デモの書き出しをS-3.md等の単一Markdownの直接保存へ変更した。Purpose・Requirementsを設け、採択合意を「Requirement: A-番号 タイトル」で整理する。原文を保持し、確認されたsupportsの理由を参照文脈としてContextへ収録する。番号による文書内リンクは実在する節に対応し、未登録シナリオは追加しない。構成は[OpenSpec公式のSpec Format](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md#spec-format)を参考にした。

内部ID・revision_id・kind・状態・所属とdirect/contextの区別は各項目のHTMLコメント、DB・snapshot・対象Scopeは文書コメント、関係ID・元版・端点と番号も関係コメントに保持する。別のメタデータファイルやZIPは不要。元の本文をコメントへ二重保存しない。識別情報は将来の取り込みに備えたもので、インポート処理の実装ではない。Core CLIの従来Markdown形式は維持する。

全142件合格、87.329秒。実ブラウザー45項目が合格し、稼働URLでもS番号.mdを実保存して本文・内部ID・元版・参照理由・全リンクの対応とDB不変を確認した。結果は`/tmp/latis-explorer-scope-document-01/report.json`と`/tmp/latis-explorer-scope-document-live-01/report.json`。以前のZIPの検査結果は旧形式に対する記録として区別する。

ADR・OpenSpec風仕様・説明文等のレンダー形式を細かく設定できる画面はUI-01として追加予定に記録した。現在のデモは固定テンプレートで、設定画面や他形式のテンプレートは未実装。

## 2026-11-06の追加指示：オブジェクトIDと透明性

A-1形式の正式名称を「オブジェクトID」とし、Spec §5.2.1〜2・API §3.1・LLM Guideを統一した。「通常の利用では基本的にオブジェクトIDを使う」「十分に特定できる場面ではオブジェクトIDを使う」を、入力・参照・変更の説明、プロンプト、応答、通知、エラー、履歴、ログ、文書へ適用する。Scopeを番号の名前空間にせず、複数所属でも同じA-1を使う。内部idとrevision_idは同一性・照合・正本・実コマンドの契約として保ち、オブジェクトIDの直接入力はM6-13の未実装事項として区別する。

`labels.py`は実行中に同じDBの番号・名称・内部ID・現在版とmetaの対応表を原子的に更新する。人向けイベント表示では番号・名称・版を使い、関係は端点・種別・向きを示す。同じ端点・種別の複数関係は必要な関係IDも残す。元のイベントとCLI監査JSONは変更しない。読取失敗・別DB・履歴分岐の場合は古い対応を適用しない。ローカル検査は実DBの改訂・複数関係・読取失敗・DB差替え・原記録不変を確認した。全144件合格の後、複数関係の識別補足を加え、関連8件が0.631秒で合格した。

`/tmp/latis-explorer-llm-display-01/handover/`はOpus 5.5/highの実行、CLI16操作・observe1回、117.072秒、機械8項目合格。最終応答がA-2通常48時間・A-1監査90日・A-14 UTC、R系列の理由、AR系列の現物・証拠を使い、過去の検査と今回の観測、UTC未実装を区別したことを確認した。ただし最初のmetaで禁止したechoとパイプを使ったため、意味レビュー全体は不合格とした。番号の提示ができたことを、試験全体の合格へ読み替えない。

同じ保存済み実イベントを`handover-object-log.txt`へオブジェクトIDで再表示し、旧版・新版の番号と名称、関係、元のevents.jsonのバイト不変を確認した。これは保存済み記録の表示検査で、新しいLLM起動ではない。最新実装での再試験は自動承認レビューが「外部LLMへの送信payloadと宛先への明示的認可不足」として拒否したため未開始。送信前指示・専用データは`/tmp/latis-explorer-llm-display-02/`へ準備済み。Q-04で送信対象とAnthropic宛ての許可を確認中であり、D-25は未完了とする。隔離外への迂回、設定変更や外部API直接呼出しは行っていない。

ローカルの全144件再試験は86.989秒で合格。直前の通常sandbox内での実行はlocalhostのbindが拒否されHTTP4件がエラーとなったため、外部LLMを起動しない同じPython検査を適切な権限で再実行した。LLMの拒否を別経路から回避したものではない。

## 2026-11-06の追加指示：Inspector / Change LogのID枠

D-26として、Inspectorの所属・関係・証拠の参照と、Change Logの一覧・変更詳細にも共通の四角いオブジェクトID枠を付けた。選択対象の既存の枠も維持する。内部IDと版IDは名称を明示し、通常の行のツールチップはオブジェクトIDと名称を使う。

実Chromeの1366×768・1920×1080で、四辺の1px枠・角丸なし・参照移動・ページエラーなし・DB不変の14項目が合格した。スクリーンショットも目視確認した。結果は`/tmp/latis-explorer-object-boxes-01/report.json`、画像は同ディレクトリの`boxed-1366.png`・`boxed-1920.png`。ログは`/tmp/agent-logs/github.com-LATIS/task.log`。JavaScriptの構文確認も合格した。別途、用語変更時の稼働URLでのID・内部ID・版IDの区別は`/tmp/latis-explorer-object-ui-01/report.json`に保持する。

D-26の追加指示として、Scope見出しのS番号も共通の枠へ変更した。Inspector・Change Logは文字を13pxから12px、内側の余白を上下2px・左右5pxから上下1px・左右4pxへ詰めた。一覧・Scopeの枠は元の大きさを保つ。実Chromeの2解像度で、枠・サイズ差・Scopeの折畳み・参照移動・ページエラーなし・DB不変の24項目が合格。結果は`/tmp/latis-explorer-object-boxes-02/report.json`、画像は同ディレクトリの`boxed-1366.png`・`boxed-1920.png`。1366幅の実画像も目視確認した。JavaScript構文と差分の空白確認も合格。表示だけの変更のためPython全回帰と実LLM試験は再実行していない。ログは`/tmp/agent-logs/github.com-LATIS/task.log`。

## 2026-11-06の追加指示：必須のプロジェクト名とヘッダー

D-27として、全DBのmetadataにproject_nameを必須化した。initは明示した1〜240文字の名前を受け取り、未指定・null・空文字・空白だけ・前後の空白・制御文字を拒否する。同じ名前の再初期化は既存DBを保ち、違う名前のinitはPROJECT_NAME_MISMATCHとして拒否する。metaのdata、SQLite/JSON退避・復元、Markdown投影へ名前を保持する。名前はDBの表示名であり、database_idやオブジェクトIDの名前空間にはしない。

この破壊的な必須化に伴い、仕様を0.3-demo-draft.1、規則をcore-0.3.1、SQLite user_versionとJSON format_versionを3へ更新した。名前のない既知の旧形式2は通常操作・restoreで拒否し、project_nameを明示したmigrateだけで新しいDBへ移行する。元ファイルを上書きせず、DB識別値・graph_revision・snapshot_id・全6種類の記録を保持する。過去の成功済み応答は旧版表記も含めてそのまま保持・再返却し、未成功の旧basisはRULES_CHANGEDで拒否する。旧版・現行版の履歴が混在しても、成功応答と照合時の規則版の対応を検査する。後からの名前変更も、現行形式を明示したmigrateで新しいDBへ移送する。

旧HEAD（86a8d9b）の実装でinit → save-draft → consult/apply → exportを実行した2 commitの素材を、tests/fixtures/project-name-legacy.jsonとproject-name-legacy-retry.jsonへ保存した。tests/test_project_name.pyの6件で、必須名・既存DB不変・SQLite/JSONの名前保持・旧形式拒否・明示移行・全履歴と成功応答の保持・旧basis拒否・不正な履歴/版の拒否・名前変更を確認した。新しい6件を含む全150件が84.682秒で合格。初回149件の実行では、WAL形式の退避をro接続で読めなかった点と、共通envelope.metaへ名前を含めない契約に対する既存テストの期待値を修正し、全回帰を再確認した。復元元は従来のSQLite接続方法とquery_onlyによる読取で扱い、元DBの内容を更新しない。

展示名はユーザー指定の「ログ管理サービス」。prepared-002のbaseline/finalを正規migrateでprepared-003へ移し、live-002からlive-003、finalからreplay-003を用意した。旧素材の全ファイルhash不変と、稼働用DBの全26ノード・関係・版・来歴・commit・成功済み応答の同一性を確認した。現在はhttp://127.0.0.1:8765、接続先は.latis/exhibition/live-003/demo.sqlite。DB id=5bf0b757b2f34e5686fc852d82ace4ae、rev 6、snapshot fa6968250379434d82467cc9744a4bfeを保持する。新しい検査証拠を作ったとは扱わない。

ヘッダーはDBから名前を取得し、1366×768・1920×1080とも58pxを保つ。240文字の長い名前を省略し、titleへ全文を保持する。HTML文字列の不実行、タブタイトル、LIVE/REPLAYと復帰、ページエラーなし・DB不変を実Chromeで確認。最終の22項目は列見出しの01/02/03削除も含み、/tmp/latis-explorer-project-name-03/report.jsonに保存した。直前の名前確認20項目は/tmp/latis-explorer-project-name-02/report.json、最終サーバーの版とsnapshotの確認は同ディレクトリのfinal-server.json。初回name-01は検査側の文字列が240文字を超えていたため検査入力を修正し、新しい出力先で確認した。移行したデータで正規CLIの追加・改訂・復旧・エクスポートまで実ブラウザー回帰45項目も合格し、/tmp/latis-explorer-project-regression-01/report.jsonに記録した。

仕様・API・Guide・デモ手順・初期化素材と管理票を更新した。M5の完了は当時の対象版に対する結果として維持し、新しい仕様版の実LLM試験・配布物の合格へ読み替えない。Q-04の送信許可待ちは継続し、旧版のdisplay-02準備物も再利用しない。ログは/tmp/agent-logs/github.com-LATIS/{dev,test,e2e,task}.log。

## 残る受け入れ

- D-14の映像収録は、ユーザー指示により今回の必須対象外。既存の任意補助と過去の検査結果は保持する。障害時の必須経路は実commitのREPLAYとする。
- D-15の外部ディスプレイ、距離、ケーブル、電源、スリープ、再起動は実機で未確認。ブラウザーの寸法検査を代用にしない。
- D-16の手順・ソフトウェア側のリハーサルは揃ったが、D-15と担当者による通し操作の結果が揃うまで最終受け入れを保留する。質問は`質問事項.md`に集約する。
- D-25の最新実LLM再試験はQ-04の外部送信許可待ち。仕様・対応表・人向けログとローカル検査は完了しているが、LLM利用の合格は未確認。
