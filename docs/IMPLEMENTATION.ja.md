# P0参照実装

規範は [v0.3.0のSpec](v0.3.0/LATIS_Spec.md) と [API](v0.3.0/LATIS_API.md)。本書は実装の起動・検査手順を説明する。安定版リリースや展示受け入れの完了を意味しない。

日付に依存しない作業順、チェック付きの進捗、現行仕様の完全実装までの計画は [タスク管理票](TASKS.ja.md) で管理する。

P0の条項ごとの確認先は [仕様と実装の対応表](SPEC_COVERAGE.ja.md)、M1での修正と実行結果は [M1検証記録](M1_VERIFICATION.ja.md) を参照する。LLMの行動の確認はM3、P1の実装はM2へ引き継ぐ。

## 実行環境

Python 3.12.xと標準ライブラリだけで動く。SQLite以外のサーバー、外部AI、HTTP、MCPは不要。
`core-0.3.0` の検索規則にはUnicode 15.0.0を使う。同じrules_versionで検索結果が変わらないよう実行環境を固定し、異なるUnicodeデータ版は `RULES_CHANGED` で拒否する。Python更新時には正規化fixtureの確認と規則版の判断を行う。

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

P1の `search_descendants/markdown_export` は提供しない。要求には `UNSUPPORTED_FEATURE` を返す。仕様にないフィールド・旧保存形式・Markdown import等も拒否する。
コアは外部ファイルを取得せず、テストを実行しない。下記のリハーサルは呼出元スクリプトが現物を観測・実行して結果をCLIへ渡す。

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

展示のやり直しには新しい作業ディレクトリへ `baseline-project` の2ファイルをコピーし、`baseline.sqlite` を未存在のDBパスへrestoreする。履歴や証拠を上書きせず、DBとコードを一組で戻す。

## 自動検査

```sh
~/.local/bin/log-window test
FORCE_COLOR=1 python3 -m unittest discover -v > /tmp/agent-logs/github.com-LATIS/test.log 2>&1
```

`tests/test_engine.py` はAPI・DBの受け入れを、`tests/test_rehearsal.py` は実CLIと題材の実行を検査する。固定の正規化fixtureは `tests/fixtures/normalization.json`。外部通信は不要。

| 計画の項目 | 自動検査で確認する範囲 | 対話LLMで残す確認 |
| --- | --- | --- |
| A01〜A04 | 未整理・候補・重複の保存、追加取得、打ち切り表示 | 見つけた手掛かりから自発的に問いを作ること |
| A05〜A08、A17〜A18 | 合意改訂、監査ログ・原文の保持、priorityによる優先を計算しないこと | 曖昧な対象だけ打診し、明示済みの指示を再確認しないこと |
| A09〜A16、A19〜A20、A22、A25〜A26 | 版・Scope・確定関係・追加根拠の変化、原子性、冪等性、決定論性、cursor、日本語検索 | エラー差分から必要な探索・再照合へ戻ること |
| A21 | 旧形式の拒否 | 自動移行は展示後 |
| A23〜A24 | 両形式の退避・復元、履歴・証拠・成功済み再試行記録、JSON入出力 | 展示環境のパス・起動方法 |
| E01〜E11 | 実物のハッシュ、実テスト、新旧証拠、失敗結果、固定版の検査、未観測変更の限界 | 実際の作業で観測・検査を適切に選ぶこと |
| E12 | 新しいプロセスで理由・版・実行情報・証拠を再取得 | 会話を共有しない独立したLLMセッションでの再利用 |

## 展示前に行う対話の受け入れ

LLMを含む利用テストは `claude -p --safe-mode` で実施し、LLMのAPIを直接呼ばない。safe-modeではCLAUDE.mdやカスタム設定からの自動読込を前提にせず、以下のGuide・CLI・DB・作業場所をプロンプトに明示する。コアの契約検証には既存のPython自動テストを使う。具体的な残作業は [タスク管理票のM3](TASKS.ja.md#m3-claude-cliによるllm利用の受け入れ) を参照する。

`AGENTS.md` と [LLM Guide](v0.3.0/LATIS_LLM_Guide.md) から利用方法を辿れる。展示用セッションの開始指示には、実際の絶対パスで次を渡す。

> Guideは `<リポジトリ>/docs/v0.3.0/LATIS_LLM_Guide.md`、CLIは `<リポジトリ>/bin/latis`、DBは `<展示作業場所>/demo.sqlite` です。
> 作業場所は `<展示作業場所>` です。開始時にGuideとmetaを確認してください。過去の判断が関係するときに検索し、合意変更前は照合してください。全編集の事前照会は不要です。
> 現在の実装を説明するときは現物と記録された証拠の対応を確認してください。

初期状態で「ログを48時間に」と依頼し、必要な対象の打診だけが行われるかを確認する。次に、最初から「通常ログだけ48時間、監査ログは変更しない」と指示し、同じ許可を取り直さないことを確認する。
別セッションにはGuide・CLI・DB・作業場所だけを渡す。48時間という答えや前の会話を渡さず、通常ログの期間・理由、監査ログ、現物と検証対象版を説明できるかを記録する。
通信障害時は `responses.json` と実テストログを使う保存結果の説明へ切り替え、ライブと区別する。11/6の機能・データの固定と11/7の起動確認は [Demo Guide](v0.3.0/LATIS_Demo_Guide.md) に従う。
