# LATIS 受け入れ記録

P0とP1の参照実装に対する、確認した対象・環境・範囲を記録する。現行仕様の完全実装の最終判定はM5で行う。本書だけで最終受け入れや性能達成を宣言しない。

規範は [Spec](v0.3.0/LATIS_Spec.md) と [API](v0.3.0/LATIS_API.md)。条項との対応は [仕様対応表](SPEC_COVERAGE.ja.md)、導入・再現・復旧は [実装ガイド](IMPLEMENTATION.ja.md)、残作業は [管理票](TASKS.ja.md) を参照する。

## 対象と環境

実装の対象コミットは `fc879d4de15f2a6ee0fe3391576087d6b98626b9`（基準 `02a2ff3` にM3・M4の変更を追加）。`work/m4-validation` へ送信し、同じコミットでホストCIを確認した。実装・テスト・仕様・Web・CI構成のファイル別SHA-256とローカル結果は `/tmp/latis-m4-receipt.json` に保存する。この後のCI結果・進捗文書だけの更新は実装ソースの集計と分ける。

64ファイルのハッシュ対応表を、キー順・空白なしのUTF-8 JSONにした集計SHA-256は `3b1b3f066dfe8ddd2374b52ece755447f2f42376f40c0c120b004e38f98e315b`。対象は `latis/`、`scripts/`、`tests/`、`docs/v0.3.0/`、`website/`、`.github/workflows/` と、`bin/latis`、`pyproject.toml`、`AGENTS.md`、`.gitignore`、両README。`__pycache__`、`dist`、`.DS_Store` は除く。

| 追加した検査・復旧の主要ソース | SHA-256 |
| --- | --- |
| `scripts/reset_demo.py` | `0e9b4201e270b19f1fcd5c3ebdf880bce283c010272e99458b3b211f9bf5e136` |
| `scripts/verify_release.py` | `e2b1b0b2652cd7f719ba1f75cbdda654823161131583c8c690b48acd5ec454fb` |
| `scripts/check_distribution.py` | `65ad85ece2efc18f8de665f2c577dbf2f081bcb0cb5c938a9cfbd2a0e60334ab` |
| `tests/test_processes.py` | `d06a4fbc529def22ee601ff8716ebec23f422f63730589e1690c92b6163eb3d5` |
| `tests/test_reset_demo.py` | `b5311417cfea09e4860ba40ab631e4ad16b5f7b21e6ac703fdbbbb364f5d6d9c` |

| 項目 | 確認した値 |
| --- | --- |
| OS | macOS 15.8.1、x86_64 |
| Python | 3.12.0 |
| Unicode | 15.0.0。異なるデータ版はRULES_CHANGEDで拒否 |
| SQLite | 3.43.2 |
| 配布版 | 0.3.0 |
| API / 仕様 / 規則 | v1 / 0.3-demo-draft / core-0.3.0 |
| JSONスナップショット | format_version=2 |
| Coreの実行依存 | Python 3.12標準ライブラリのみ。新しい仮想環境の配布メタデータでも追加依存なしを確認 |
| LLM利用 | Claude Code 2.1.318、Opus 5.5 / high。LLMのAPIは直接呼ばない |

## 検証の区分

| 区分 | 結果と対象 |
| --- | --- |
| 現行のPython自動検査 | 119件、59.622秒、合格。API・保存・P1・実CLI・LLM試験基盤・実プロセス障害・復元を含む。LLM自体は呼ばない |
| 現行の既定シナリオ | 初期24時間→通常ログ48時間、監査90日の保持、現物の観測、実テスト、旧証拠の拒否、新証拠、両形式の退避・JSON復元が合格。対話LLMの行動確認とは区別 |
| 一組の復元 | baseline/final × SQLite/JSONの4通りが合格。復元後の実テスト各3件も成功。元の全ファイルのハッシュは不変 |
| 新規環境の配布物 | wheelだけを別の仮想環境へ導入し、ソースツリー外のconsole CLIで24呼出し。9操作、P1の実際の子孫検索・選択投影、両形式の全記録の復元、素材の実テスト3件、23ファイルの一致が合格 |
| M3のClaude利用 | 16ケース・17呼出し・CLI操作182件。機械検査と意味レビューが合格。隔離導入前の対象版・増分検証の記録である。詳細は [M3検証記録](M3_VERIFICATION.ja.md) |
| 隔離後のClaude利用 | ダミーファイルによる隔離26項目と、explicit/retryの2ケース・CLI操作27件が合格。対象と例外は [サンドボックス](LLM_SANDBOX.ja.md)。M3全件の再実行ではない |
| Webのローカル検査 | 構文・ビルド・リンク・メタデータ検査が合格。日英の本文を現行のCLIとP1、既存授権の再利用、未実装機能の表示へ更新。公開先の状態や全画面幅の見た目を再検証した結果ではない |
| ホストされたCore CI | `fc879d4` に対する [実行41890221875](https://github.com/ayumuwall/LATIS/actions/runs/41890221875) が成功。Linux／Python 3.12.15／Unicode 15.0.0／SQLite 3.45.1で119テストが31.783秒で合格。配布物の構築・別環境への導入・実CLI24呼出し・素材の実テスト3件も合格。M2の旧版に対する成功とは別の実行である |
| ホストされたWeb CI | `02a2ff3` に対する [実行41854719004](https://github.com/ayumuwall/LATIS/actions/runs/41854719004) は構文・ビルド・リンク検査に成功し、Configure PagesでNot Found。公開の成功を示さない |

## 競合と途中障害

[test_processes.py](../tests/test_processes.py) の4検査と、既存の同一キーの複数CLI検査を使う。障害注入は試験用子プロセス内で行い、製品へ停止用のフラグや任意コード実行機能を追加しない。

- 書き込みの全SQLを実行した後、commit前に待機した実プロセスを停止。別の読取プロセスは以前の確定状態だけを取得し、停止後の全テーブル・メタデータは開始前と一致した。
- 並行writerのBUSYを確認。停止した要求とBUSYになった要求は、どちらも元のキーで成功し、成功後の同一再送は同じ応答を返した。
- 同じ対象版への異なるキーのapplyは成功1件、PRECONDITION_CHANGED 1件。履歴は一回だけ追加された。
- 完成済みの出力を公開直前で二つ同時に待機させ、JSON・Markdownとも成功1件、DESTINATION_EXISTS 1件。公開された結果は一式揃い、DBは変わらなかった。
- Markdown公開直前の停止で完成先が存在しないこと、同じ完成先へ再実行できることを確認。強制終了時は未公開の `.latis-*` が残り得る。完成品と扱わず、所有する試験領域とプロセス終了を確認して整理する。

## 復旧の境界

[reset_demo.py](../scripts/reset_demo.py) は、DBとコード・テスト・固定証拠ログの組み合わせを検査して、新しいディレクトリへ公開する。コード自体を実行したり、新しい検査結果を過去の証拠へ書き足したりしない。

[test_reset_demo.py](../tests/test_reset_demo.py) では、両形式の全履歴・来歴・成功済み再試行記録の一致、既存出力先の保持、DBと異なるコード・ログの拒否、復元元の外側へのsymlinkと復元元内への出力の拒否を確認した。実CLIで、復元直後の未来のbasisと、同じdatabase_id・graph_revisionでsnapshotが異なる分岐のbasis/cursorを、それぞれBASIS_UNAVAILABLE・CURSOR_STALEで拒否した。

保存した現物とDBの一致は、復元時に保持した版に対するものである。以前のbasis・cursorを新しい作業へ持ち越さず、必要な検索とconsultをやり直す。

## 再現コマンド

ログのパスは `log-window` が返した値へ置き換える。出力ディレクトリは毎回未存在のものを指定し、以前の結果を上書きしない。

```sh
~/.local/bin/log-window test --keep
FORCE_COLOR=1 python3 -m unittest discover -v > /tmp/agent-logs/github.com-LATIS/test.log 2>&1

~/.local/bin/log-window build --keep
FORCE_COLOR=1 python3 -u scripts/verify_release.py --output /tmp/latis-release-new > /tmp/agent-logs/github.com-LATIS/build.log 2>&1

~/.local/bin/log-window task --keep
FORCE_COLOR=1 python3 -u scripts/rehearse.py --output /tmp/latis-demo-new > /tmp/agent-logs/github.com-LATIS/task.log 2>&1
python3 scripts/reset_demo.py --source /tmp/latis-demo-new --destination /tmp/latis-reset-new --state baseline --format sqlite
```

配布検査はビルド用と実行用の環境を分ける。ビルド依存の取得にはネットワークが必要な場合があるが、実行用にはローカルwheelを `--no-index --no-deps` で導入する。今回のwheelのGeneratorはsetuptools 84.2.1。CIも同じ配布検査スクリプトを使う。wheelのバイト単位での再現性を保証する手順ではなく、検査した成果物は次のハッシュで識別する。

`/tmp/latis-m4-release/wheels/latis-0.3.0-py3-none-any.whl`

SHA-256: `590b4085f5c231b3a710cef1acd4a22bc96fd0558b5d003c952ec6b90d7104af`

ホストCIでは同じソースから別に構築し、wheelのSHA-256は `5eedf8d5a79ea1f2b3f6bc4ecb549ec4aa6cc4582f1f5cac869bf4d3dcfe97d2`。CI上のwheelは配布先へ公開せず、取得可能なActions artifactとしても保存していない。検査対象のソースと導入後23ファイルの一致を確認した結果であり、ローカルwheelとのバイト一致を主張しない。

入力ソースは `build-source.json`、導入環境・同梱ファイル・操作一覧は `check/report.json`、全CLI応答は `check/calls.json` に残す。復元の実演結果は `/tmp/latis-m4-operations/report.json` と配下の4組、Core自動検査は `/tmp/agent-logs/github.com-LATIS/test.log` を参照する。表示用ログは固定名で次回に上書きされ、一時領域の記録も永続保管ではない。

ホストCIの対象・環境・集計は `/tmp/latis-m4-ci.json`、取得した詳細ログは `/tmp/agent-logs/github.com-LATIS/task.log`。リモートに残る実行結果は上記のGitHub Actionsのリンクを参照する。

## 未確認と残作業

- 実装の対象コミット `fc879d4` のホストCIは合格。後続の結果記録だけのコミットは、実装・テスト・配布対象を変更しない。文書だけの変更ではCore CIは再起動しないため、成功した対象コミットを明示して扱う。
- Web変更はCI専用ブランチに保存したもの。mainの更新・Pagesの設定変更・デプロイは実施していない。mainへWeb変更をpushすると現行workflowが公開を試みるため、CIだけの確認と公開を区別する。
- M5の同一構成での全LLM回帰、1,000ノード以下の代表データ、全条項の最終照合と完全実装の判定は未完了。
- LLMへCURSOR_STALEを実際に返す分岐、JSON復元後のLLMによる再利用は、現在のLLM検証には含まない。Coreの該当分岐は自動検査済み。
- 20万合意、FTS・推論検索、グラフUI、Markdown import、本人性・権限の検証等は現行の実装範囲外。Coreが受け取る判断・主体情報を認証済みの権限へ読み替えない。
