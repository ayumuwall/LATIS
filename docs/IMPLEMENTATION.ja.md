# P0とP1の参照実装

規範は [v0.3.0のSpec](v0.3.0/LATIS_Spec.md) と [API](v0.3.0/LATIS_API.md)。本書は実装の起動・検査手順を説明する。安定版リリースや展示受け入れの完了を意味しない。

現行Spec/APIのP0＋P1はM5で受け入れを完了した。対象版・実施範囲・保証の限界は [M5検証記録](M5_VERIFICATION.ja.md)、完了した進捗と次期仕様の検討項目は [タスク管理票](TASKS.ja.md) で管理する。

条項ごとの確認先は [仕様と実装の対応表](SPEC_COVERAGE.ja.md)、現行P0＋P1の同一構成による受け入れと判定は [M5検証記録](M5_VERIFICATION.ja.md) を参照する。P0の初期照合は [M1](M1_VERIFICATION.ja.md)、P1は [M2](M2_VERIFICATION.ja.md)、以前のClaude利用は [M3](M3_VERIFICATION.ja.md)、M4までの運用・復旧・配布は [受け入れ記録](ACCEPTANCE.ja.md) に保持する。

## 実行環境

Python 3.12.xと標準ライブラリだけで動く。SQLite以外のサーバー、外部AI、HTTP、MCPは不要。
`core-0.3.0` の検索規則にはUnicode 15.0.0を使う。同じrules_versionで検索結果が変わらないよう実行環境を固定し、異なるUnicodeデータ版は `RULES_CHANGED` で拒否する。Python更新時には正規化fixtureの確認と規則版の判断を行う。

仮想環境は使用する機種ごとに作り、CLI・検査の前に有効化する。別の機種から共有した `.venv` は、インタープリタの絶対パスが一致せず起動できない場合がある。2026-11-05のApple Silicon機では既定の `python3` が3.14だったため、Homebrew Python 3.12.11を明示した。

```sh
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip --isolated install 'setuptools>=68' wheel
python --version
```

M5のIntel機では、pyenvのPython 3.12.0から `/tmp/latis-m5-intel/env` を新しく作って検証した。Python 3.12が `python3.12` で起動できる環境では、次のように専用の未存在パスを使える。

```sh
python3.12 -m venv /tmp/latis-env
source /tmp/latis-env/bin/activate
python --version
```

本体の実行依存は標準ライブラリだけで、setuptools・wheelはビルド用である。Intel機の結果は [M5検証記録](M5_VERIFICATION.ja.md)、Apple Silicon機の事前確認は [サンドボックス記録](LLM_SANDBOX.ja.md#2026-11-05-apple-silicon環境でのm5前確認) に分ける。Python 3.12とUnicode 15.0.0を確認してから既存のDBや検査を実行する。

リポジトリ直下から、インストールせず実行できる。

```sh
./bin/latis --db /tmp/latis-example.sqlite init <<'JSON'
{}
JSON
./bin/latis --db /tmp/latis-example.sqlite meta <<'JSON'
{}
JSON
```

`python3 -m latis` でも同じCLIになる。`bin`をPATHへ加えるか、Python 3.12の仮想環境で `python -m pip install --no-deps .` を実行すれば `latis` を使える。パッケージ構築にはsetuptoolsを使う。
wheelにもv0.3.0の仕様・LLM Guide・展示素材を同梱する。仮想環境へインストールした場合、ガイドは `<仮想環境>/share/latis/docs/v0.3.0/LATIS_LLM_Guide.md` にある。

配布物の再現検査は `scripts/verify_release.py --output <未存在の一時ディレクトリ>` を使う。必要なソースだけを複写し、ビルド用と実行用の仮想環境を分け、実行用にはローカルwheelだけを導入する。ビルドは `log-window build` のログへ出力する。9操作・P1・両形式の復元・同梱文書と素材の一致まで、ソースツリー外のCLIで検査し、wheelのSHA-256と全応答を残す。CIでも同じスクリプトを使う。

DBの指定は `--db` → `LATIS_DB` → 作業ディレクトリの `.latis/latis.sqlite` の順。親ディレクトリのDBは探索しない。エージェントには絶対パスを渡すと取り違えを減らせる。
入力はJSONオブジェクト1個、stdoutはJSON envelope1個。診断ログはstderr。終了コードは成功0、契約エラー1、予期しない障害2。

## 実装した範囲

- 日常の9操作：`meta/search/detail/relation-detail/relations/history/save-draft/consult/apply`。
- `init/backup/export/restore`。JSONは完全な `format_version=2` のスナップショット。
- 8種類のノード、12種類の関係、状態遷移、型・循環・重複の検査。
- 個別版、commit、snapshot、来歴、採択時の前提と判断理由。
- 構造的な照合、基準時点からの変更前後の検査、短いSQLiteトランザクションによる原子的な更新。
- 成功済みの同一入力の再送、異入力の拒否、失敗したキーの再利用。
- artifactの所在・実バイトのハッシュ、固定された検査証拠、実装・検証関係、版変化の診断。
- 日本語2文字を含むNFKC＋casefoldの部分一致AND検索、安定した順位、DB版に結び付いたcursor。
- P1の子孫Scope検索とMarkdown投影。`meta.capabilities` に `search_descendants` と `markdown_export` を返す。

仕様にないフィールド・旧保存形式・Markdown import等は拒否する。
コアは外部ファイルを取得せず、テストを実行しない。下記のリハーサルは呼出元スクリプトが現物を観測・実行して結果をCLIへ渡す。

## 子孫Scope検索とMarkdown投影

利用前に `meta` で対応するcapabilityを確認する。以下の `scope_id` は、`search` で `kinds=["scope"]` と必要な `lifecycles` を指定して得た実IDへ置き換える。

`search_descendants` がない接続先では、通常の `relations` でactive/confirmed containsの子孫を辿り、取得したScope IDを明示して検索する。`markdown_export` がなければ完全JSON exportまたは通常の取得操作を使う。未対応のP1要求は `UNSUPPORTED_FEATURE` であり、0件や成功した投影と説明しない。

```sh
./bin/latis --db /tmp/latis-example.sqlite search <<'JSON'
{"scope_ids":["scope_id"],"include_descendants":true,"include_unscoped":false}
JSON
```

指定Scopeと、active/confirmedのcontainsで辿れる全子孫を同じsnapshotから展開する。`applied_filters.expanded_scope_ids` で実際の範囲を確認できる。`scope_ids=[]` はフラグによらず全体検索。Scope間の効力・優先・継承やconsultのwatchは変わらない。DBが更新されたら古いcursorを使わず検索し直す。

Markdownはまだ存在しないディレクトリへ出力する。全体の投影は次の例で作れる。

```sh
./bin/latis --db /tmp/latis-example.sqlite export <<'JSON'
{"format":"markdown","destination":"/tmp/latis-example-view"}
JSON
```

`node_ids` または `scope_ids` に空でない実ID配列を指定すると範囲を選べる。同時指定はできない。Scope指定はactive/confirmed scoped_toによる直接所属だけを選び、Scope自身・子孫・未分類を暗黙に加えない。kindや終端状態による除外もない。0件ならindex.mdだけを作る。

`index.md` のfront matterにはDB・graph・snapshot・仕様版と正規化した選択条件を記し、ID順の表から本文へリンクする。各ノードは `<kind>/node-<base64url(IDのUTF-8、末尾の=なし)>.md`。JSONのfront matterはbody以外の保存フィールド、直接のScope、来歴参照、直接接続した全関係を持ち、その直後に原文bodyを置く。candidate/retired関係、範囲外ID、basis_refs、evidence.subject_refsも保持する。

同じsnapshotから一時ディレクトリに全ファイルを書き、完成後に公開する。既存のファイル・空ディレクトリ・symlinkを上書きせず、競合時は `DESTINATION_EXISTS`。排他的公開にはmacOSのrenamex_np、Linuxのrenameat2、Windowsのrenameを使い、未対応環境ではI/Oエラーとして終了する。ローカルの検証環境はM2検証記録に示す。

投影の編集はDBへ反映されない。復元には完全JSONかSQLiteバックアップを使う。入力例は [examples](v0.3.0/examples/README.md#p1の入力例) にも同梱する。

## 展示の再現

出力先にはまだ存在しないディレクトリを指定する。元の題材は変更せず、作業コピーを作る。

```sh
# 出たログパスへコマンド全体の出力を保存する。
~/.local/bin/log-window e2e
FORCE_COLOR=1 python3 scripts/rehearse.py --output /tmp/latis-demo-run > /tmp/agent-logs/github.com-LATIS/e2e.log 2>&1
```

ログのパスは環境ごとの `log-window` の出力に置き換える。
スクリプトは通常のCLIを別プロセスから呼び、次の順に確認する。

1. 空の専用DBへ通常のconsult/applyでseedを採択する。
2. 初期コード・テストのハッシュを確認し、実テスト3件を実行する。結果を新しい証拠にして通常・監査の両合意へ結ぶ。
3. SQLiteとJSONの初期退避を作る。
4. 通常ログの同じagreementを24時間から48時間へ改訂する。監査ログ90日は維持する。
5. コード・テストを更新し、両artifactを再観測する。旧証拠の再確認が拒否されることを確かめる。
6. 実テスト3件を再実行し、新しい証拠へ両合意を結び直す。旧証拠・旧版・変更理由は残す。
7. 最終状態を退避・JSON復元し、新しいCLIプロセスから合意・変更理由・現物との対応を読み直す。

出力には `demo.sqlite`、`baseline.sqlite/json`、`final.sqlite/json`、`restored.sqlite`、初期素材、変更後素材、実テストログ、全操作の `responses.json`、`summary.json` が含まれる。`file:` URIはこの作業ディレクトリを基準とする。
`summary.json` は独立したLLMセッションを検証済みと表示しない。これは既定シナリオの自動再現であり、ライブの対話デモとは区別する。

実テストは実行ごとに空のPythonバイトコード参照先へ分離する。同じ秒・同じサイズの更新で古いpycが使われることを防ぎ、観測したソースと実行結果を対応させる。

## 復旧と実演リセット

既定シナリオの出力から、DB・コード・テスト・固定証拠のログを一組で新しい場所へ戻す。

```sh
python3 scripts/reset_demo.py --source /tmp/latis-demo-run --destination /tmp/latis-demo-next --state baseline --format sqlite
python3 scripts/reset_demo.py --source /tmp/latis-demo-run --destination /tmp/latis-demo-final --state final --format json
```

`baseline` は通常ログ24時間、`final` は48時間の組み合わせ。監査ログは両方とも90日。SQLiteとJSONのどちらからも復元でき、選択した状態の完全JSONと全記録が一致すること、コードと固定証拠ログのハッシュがDBの観測版と一致することを公開前に検査する。既存の出力先、復元元の内側、外部へのsymlink、異なる版の組み合わせは拒否する。

復元補助はコードを実行せず、新しい検査証拠も登録しない。`reset.json` は復元元、状態、全ハッシュ、DBの識別情報を記録する。`snapshot.json` は復元した全履歴・来歴・成功済み再試行記録である。新しいDBの `meta` を確認し、LLMへ新しい作業場所・DBを渡す。以前のbasis・cursor・要求JSONを新しい作業へ持ち越さず、必要な探索・照合をやり直す。

手作業で戻す場合も、`baseline-project` の2ファイルと `baseline.sqlite/json`、または変更後の2ファイルと `final.sqlite/json` を同じ組み合わせにする。元のDBや復元元の履歴を上書きしない。証拠の `file:` URIは作業場所を基準に解決し、過去の実行結果を今回実行したものと説明しない。

## 途中障害と出力競合

DBの書き込みは原子的で、commit前にプロセスが停止した場合は部分更新や再試行キーが残らない。ロックで `BUSY` が返った要求も同じキーで再試行できる。結果不明の場合は同じ入力とキーを再送し、勝手に新しいキーを発行しない。

JSON・SQLite・Markdownの出力は完成後に排他的に公開し、既存の出力先を上書きしない。出力の競合では `DESTINATION_EXISTS` を返す。公開前の強制終了では完成先を作らないが、`finally` が動かないため親ディレクトリの `.latis-*` が残ることがある。これは未公開の残片であり復元元や完成品として使わない。書き込みプロセスが終了したことと、その試験専用領域に属することを確認して整理する。動いている別プロセスの一時ファイルをまとめて削除しない。

## 自動検査

```sh
~/.local/bin/log-window test
FORCE_COLOR=1 python3 -m unittest discover -v > /tmp/agent-logs/github.com-LATIS/test.log 2>&1
```

`tests/test_engine.py` と `tests/test_contracts.py` はAPI・DBの受け入れを、`tests/test_p1.py` は子孫Scope検索・投影・並行更新・出力失敗を、`tests/test_rehearsal.py` は実CLIと題材の実行を検査する。固定の正規化fixtureは `tests/fixtures/normalization.json`。外部通信は不要。

| 計画の項目 | 自動検査で確認する範囲 | 対話LLMで残す確認 |
| --- | --- | --- |
| A01〜A04 | 未整理・候補・重複の保存、追加取得、打ち切り表示 | 見つけた手掛かりから自発的に問いを作ること |
| A05〜A08、A17〜A18 | 合意改訂、監査ログ・原文の保持、priorityによる優先を計算しないこと | 曖昧な対象だけ打診し、明示済みの指示を再確認しないこと |
| A09〜A16、A19〜A20、A22、A25〜A26 | 版・Scope・確定関係・追加根拠の変化、原子性、冪等性、決定論性、cursor、日本語検索 | エラー差分から必要な探索・再照合へ戻ること |
| A21 | 旧形式の拒否 | 自動移行は展示後 |
| A23〜A24 | 両形式の退避・復元、履歴・証拠・成功済み再試行記録、JSON入出力 | 展示環境のパス・起動方法 |
| E01〜E11 | 実物のハッシュ、実テスト、新旧証拠、失敗結果、固定版の検査、未観測変更の限界 | 実際の作業で観測・検査を適切に選ぶこと |
| E12 | 新しいプロセスで理由・版・実行情報・証拠を再取得 | 会話を共有しない独立したLLMセッションでの再利用 |

## Claude CLIによる利用検査

現行の試験基盤はmacOSのBashサンドボックスを必須にし、子プロセスにも読み書き・通信の制限を適用する。`--restricted` によるファイル用ツールの制限も併用する。必要な実装だけを同一ハッシュの読み取り専用コピーで実行し、元リポジトリ全体を開放しない。隔離できない場合は停止する。適用範囲・例外・拒否試験の方法は [サンドボックス](LLM_SANDBOX.ja.md) を参照する。以下のM3の16ケースは、隔離導入前の対象版についての結果である。

LLMを含む利用テストはユーザー指定の `claude -p --safe-mode --model claude-opus-5-5 --effort high` で実施し、LLMのAPIを直接呼ばない。safe-modeではCLAUDE.mdやカスタム設定からの自動読込を前提にせず、Guide・API・CLI・DB・作業場所をプロンプトに明示する。コアの契約検証にはPython自動テストを使う。

M3では16ケース・17呼出しを実行し、CLI操作182件、DBの前後、現物、実テストと自然文の意味を確認した。曖昧な対象での待機、同一IDの改訂、既存指示の再利用、前提変更と結果不明からの回復、失敗結果と未観測変更、P1利用、独立セッションを含む。試験基盤の単体検査を含む全104件のPythonテストも合格した。

```sh
~/.local/bin/log-window e2e --keep
FORCE_COLOR=1 python3 -u scripts/llm_acceptance.py --output /tmp/latis-llm-run > /tmp/agent-logs/github.com-LATIS/e2e.log 2>&1
```

出力先は未存在の専用ディレクトリを使う。`log-window` はmacOSのアプリ操作ができる権限で開き、Claudeも既存のログインを利用できる環境から実行する。必要なツールを文書と専用作業コピー・固定コマンドへ限定し、操作・応答・終了結果を同じiTerm2ウインドウへ逐次表示する。ケースの定義・許可範囲・判定方法は [M3利用検査](M3_CASES.ja.md)、同一構成の隔離下16ケースの結果は [M5検証記録](M5_VERIFICATION.ja.md) を参照する。展示当日の起動・接続確認はDemo Guideに従う。

`AGENTS.md` と [LLM Guide](v0.3.0/LATIS_LLM_Guide.md) から利用方法を辿れる。展示用セッションの開始指示には、実際の絶対パスで次を渡す。

> Guideは `<リポジトリ>/docs/v0.3.0/LATIS_LLM_Guide.md`、CLIは `<リポジトリ>/bin/latis`、DBは `<展示作業場所>/demo.sqlite` です。
> 作業場所は `<展示作業場所>` です。開始時にGuideとmetaを確認してください。過去の判断が関係するときに検索し、合意変更前は照合してください。全編集の事前照会は不要です。
> 複数種類の合意があり対象の種類が未指定なら、現状の値や理由だけから対象を決めず、回答まで合意・コード・テストは変更しないでください。同じ既存合意の条件値変更は、同じIDの改訂を既定にしてください。既存の指示・授権で対象と扱いが明確なら、同じ許可を取り直さないでください。
> 現在の実装を説明するときは現物と記録された証拠の対応を確認してください。

初期状態で「ログを48時間に」と依頼し、必要な対象の打診だけが行われるかを確認する。次に、最初から「通常ログだけ48時間、監査ログは変更しない」と指示し、同じ許可を取り直さないことを確認する。
別セッションにはGuide・CLI・DB・作業場所だけを渡す。48時間という答えや前の会話を渡さず、通常ログの期間・理由、監査ログ、現物と検証対象版を説明できるかを記録する。
通信障害時は `responses.json` と実テストログを使う保存結果の説明へ切り替え、ライブと区別する。11/6の機能・データの固定と11/7の起動確認は [Demo Guide](v0.3.0/LATIS_Demo_Guide.md) に従う。

## 代表データでの受け入れ

`scripts/verify_representative.py` は、架空の100ノードを通常のconsult/apply/save-draftで準備する。未分類メモ、複数Scopeの通常ログ合意、未採択の案とcandidate関係、条件付き例外、無関係の未解決事項、コード・テストと旧証拠を含む。LLMの依頼に変更後の答えや前の会話を埋め込まず、既存の必須隔離・restricted・Opus 5.5 / highを使用する。先に隔離拒否試験を通し、ログをiTerm2で表示する。

```sh
~/.local/bin/log-window task --keep
FORCE_COLOR=1 python3 -u scripts/verify_representative.py --output /tmp/latis-representative-new --stage prepare > /tmp/agent-logs/github.com-LATIS/task.log 2>&1
~/.local/bin/log-window e2e --keep
FORCE_COLOR=1 python3 -u scripts/verify_representative.py --output /tmp/latis-representative-new --stage change > /tmp/agent-logs/github.com-LATIS/e2e.log 2>&1
```

change終了後、`explicit/` の実応答・CLI操作・現物・実検査・DBをレビューし、その結果を同ディレクトリの `semantic-review.json` へ記録する。形式は `passed`（boolean）、`reviewer`、`notes`。機械検査の合格だけで `passed=true` とせず、実際に確認した根拠をnotesへ書く。不合格なら後続へ進まない。

```sh
FORCE_COLOR=1 python3 -u scripts/verify_representative.py --output /tmp/latis-representative-new --stage handover > /tmp/agent-logs/github.com-LATIS/e2e.log 2>&1
```

handoverは、完全JSONを新しいDBへ復元し全記録の一致を確認してから、前会話や要求ファイルを渡さない新しいClaudeセッションを起動する。`handover/` も同じ方法でレビューし、同ディレクトリへ `semantic-review.json` を保存する。

```sh
FORCE_COLOR=1 python3 -u scripts/verify_representative.py --output /tmp/latis-representative-new --stage report > /tmp/agent-logs/github.com-LATIS/task.log 2>&1
```

reportは無関係なノード・関係の保持、機械検査と両レビュー、CLI時間記録の件数を再確認する。`report.json` へ、Claudeセッション全体・APIの時間と、Python起動・IPCを含むLATIS CLIの経過時間を分けて保存する。100ノードの利用確認であり、20万合意の性能評価はM6で扱う。
