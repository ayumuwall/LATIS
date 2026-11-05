# M5 現行仕様の最終検証

規範は `docs/v0.3.0/LATIS_Spec.md` と `LATIS_API.md`。2026-11-05のApple Silicon環境で、現行P0とP1の同一構成を検証する。結果が揃うまで完全実装とは判定しない。

## 対象と記録

基準コミットは `904a44a3d04a846bd115ade4bc94f64c65bb3148`。M5前のPython起動経路修正を含む作業ツリーを対象にする。実装・試験基盤・テスト・v0.3.0文書・CLI・配布設定の46ファイルのSHA-256を `/tmp/latis-m5-20261105/sources.json` に固定した。環境は同ディレクトリの `environment.json`、条項照合は `audit.json`、実行ログはリポジトリ内 `.logs/m5.log`。

macOS 26.7.1／arm64／Python 3.12.11／Unicode 15.0.0／SQLite 3.51.3を使用する。隔離の事前確認は [サンドボックス記録](LLM_SANDBOX.ja.md#2026-11-05-apple-silicon環境でのm5前確認) の26項目合格とsmoke。開始時にも対象ソースとのハッシュ一致を確認した。

## 条項の最終照合

[仕様対応表](SPEC_COVERAGE.ja.md) のSpec・APIの条項を `model`、`engine`、`storage`、`cli`、`projection` の実装と照合した。C01〜C33の検査索引が現存するメソッドを指し、A01〜A26・E01〜E12とP1の対応を追跡できることを確認した。

入力・正規化・状態遷移・関係・固定証拠、検索と過去版の分離、seed・basis・watch、before/afterの変更検知、冪等性を先に返す検査順、原子的更新、完全JSON・SQLite復元、Markdownの読取専用投影を現物で確認した。コアが外部URI・テスト・LLMを実行しない責務と、未採用の優先規則・推論検索等を追加しない境界も確認した。今回の照合で現行P0・P1の未対応条項は検出していない。

## 実施状況

| 検査 | 現在の結果 |
| --- | --- |
| Python全回帰 | `python -m unittest discover -v`、120件、31.224秒、合格。LLM自体は起動しない |
| 隔離下のLLM16ケース | 着手中。smoke・discovery・paging・ambiguous（回答前後）・explicit・organize・rebase-targetの7ケースが合格。各ケースの機械判定と実応答のレビューを終えてから次へ進む |
| 代表データでの一連の利用 | 未実施 |
| 保存用の既定シナリオ・復旧 | 既定シナリオ2.587秒、初期・変更後の実テスト各3件、旧証拠拒否、新証拠、JSON復元が合格。baseline/final × SQLite/JSONの4通りの復旧と実テスト各3件、復元元保持も合格 |
| 同一ソースからの配布検査 | 新規環境でwheel構築・別環境への導入、CLI24呼出し、同梱23ファイル、素材3テスト、両形式の復元が合格。最終の利用文書更新後にも同梱内容を確認する |
| 完全実装の最終判定 | 未実施 |

LLM利用は `scripts/llm_acceptance.py` のケース・起動・機械検査をそのまま用い、`/tmp/latis-m5-20261105/llm_driver.py` がケース間のレビュー待ちだけを加える。全起動は `claude -p --safe-mode --restricted --model claude-opus-5-5 --effort high` と必須OS隔離で行う。実際の返却モデル、操作、DB、現物、実検査と証拠を別に確認する。意味レビュー前の自己申告を合格にしない。
