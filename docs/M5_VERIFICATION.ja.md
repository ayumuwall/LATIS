# M5 現行仕様の最終検証

規範は `docs/v0.3.0/LATIS_Spec.md` と `LATIS_API.md`。2026-11-05、現行の `v0.3-demo-draft` に定義されたP0とP1について、M5-01〜M5-05の完了条件を満たしたと判定した。仕様上の保証範囲を超える自然文の完全判定、大規模性能、M6の保留機能の完成を意味しない。

## 対象と環境

基準コミットは `a0ea5302c7ed56a678ab2c13e1e56e13b2d5db0d`。代表データ検査の `scripts/verify_representative.py` と3件のPython検査、検証結果と案内の更新を追加した作業ツリーを対象にする。コア、CLI、配布設定、規範のSpec/APIとLLM Guideは、M5-01で照合した基準 `904a44a` から変更されていない。README・Web・進捗文書は今回の結果へ更新した。

最終対象は、`latis/`、`scripts/`、`tests/`、`docs/v0.3.0/`、`website/`、CI構成と `bin/latis`、`pyproject.toml`、`AGENTS.md`、`.gitignore`、両READMEの66ファイル。結果・進捗文書、生成物、キャッシュはこのソース集計から分ける。パス→SHA-256の辞書をキー昇順・空白なし・非ASCIIを保持するUTF-8 JSONで集計したSHA-256は `f79b85eb8e9e6144b116dc266b929cf34f8aaf8de0aedab37fa27ef22f47fc84`。ファイル別は `/tmp/latis-m5-intel/final-sources.json`、環境・契約は `environment.json` と `contracts.json`、全体の判定と成果物ハッシュは `receipt.json` に保存した。

| 項目 | 今回の値 |
| --- | --- |
| OS・CPU | macOS 15.8.1（24H32）、x86_64 |
| Python・Unicode | pyenvの3.12.0から作った `/tmp/latis-m5-intel/env`、Unicode 15.0.0 |
| SQLite | 3.43.2 |
| Claude Code | 2.1.318 |
| 指定モデル・effort | `claude-opus-5-5` / high |
| 実際の返却モデル | 16ケースの17起動と代表データの2起動で `claude-opus-5-5`。effortはCLIへの指定値 |
| 契約 | API v1、spec `0.3-demo-draft`、rules `core-0.3.0`、JSON `format_version=2` |
| コア実行依存 | Python 3.12標準ライブラリのみ。導入後の配布メタデータも追加依存なし |

既存の `.venv` は別のApple Silicon機のHomebrewを参照し、この機では起動できなかったため使用していない。前回の一時記録もこの機にはない。専用環境を新しく作り、実Claudeの隔離拒否試験26項目が合格してから利用試験へ進んだ。全起動に `--safe-mode`、`--restricted`、必須OS隔離を併用し、隔離外への再試行や許可範囲の拡大は行っていない。

## 判定の根拠

| タスク・検査 | 今回の結果 |
| --- | --- |
| M5-01 条項照合 | 仕様対応表のC01〜C33・A01〜A26・E01〜E12とP1の対応を継承。規範とコアの同一ハッシュ、meta・8ノード種・12関係種・9操作・両P1・全上限・形式2を確認 |
| M5-02 Python全回帰 | 既存120件は64.683秒で合格。代表データ検査3件を追加した最終構成は123件、67.074秒で合格。LLM自体は起動しない |
| 隔離事前確認 | ダミーファイルの拒否試験26/26合格、`sandbox/report.json` の `passed=true` |
| M5-02 隔離下LLM利用 | 全16ケースの機械判定と実記録の意味レビューが合格。17起動、CLI176操作、Claudeイベントの時間合計1839.135秒 |
| M5-03 代表データ | 100→101ノード。変更時CLI22操作・実テスト3件・新証拠、完全JSONの全記録復元、独立セッションのCLI10操作が合格。無関係92ノード・91関係は不変 |
| 既定シナリオ・復旧 | 初期・変更後の実テスト各3件、旧証拠拒否、新証拠、JSON復元が合格。baseline/final × SQLite/JSONの4復旧と実テスト各3件、復元元保持も合格 |
| M5-04 配布物 | 別の新規環境でwheelを構築・導入。実CLI24呼出し、9操作・P1・両形式の全記録復元、同梱23ファイル一致、素材の実テスト3件が合格 |
| M5-04 文書・Web | 仕様・規則・形式・capabilities・上限と案内を整合。Python構文、日英Webのビルド・リンク・メタデータ、差分検査が合格 |
| M5-05 最終判定 | 現行Spec/APIのP0＋P1を実装・利用・運用の対象として受け入れ。未解消の仕様不一致は検出していない。管理票45/45、M5は5/5へ更新 |

入力・状態・関係・固定証拠、検索と過去版、seed・basis・watch、before/afterの変更検知、成功済み再送を先に返す検査順、原子的更新、完全復元、Markdown投影を確認した。条項の対応は [仕様対応表](SPEC_COVERAGE.ja.md)、実装と再現は [実装ガイド](IMPLEMENTATION.ja.md)、進捗は [管理票](TASKS.ja.md) を参照する。

## 隔離下の16ケース

既存の `scripts/llm_acceptance.py` の準備・起動・機械検査を使用し、`/tmp/latis-m5-intel/llm_driver.py` でケース間と曖昧な依頼への回答前に意味レビュー待ちを加えた。driverのSHA-256は `c02c1a7bd82b244984650cdf38a302cebc9ea2e1950a01855972d13fcb95d1af`。全起動は `claude -p --safe-mode --restricted --model claude-opus-5-5 --effort high` と必須OS隔離で行った。

各起動の指定・返却モデル、同一ソース、専用コピーの実行後ハッシュを照合した。ケースごとの `check.json` と `initial-review.json`、曖昧な依頼の `reply-review.json` に実応答・操作・DB・現物を読んだ判定を残し、集計を `llm/receipt.json` に保存した。合意改訂だけを依頼したケースで、現在の実装を再検証したとは扱わない。実装と証拠の対応はexplicit・failed・unobserved・handoverで別に確認した。

各ケースは `/tmp/latis-m5-intel/llm/<ケース名>/`。下表のSHA-256は、そのケース配下の全ファイルについて、相対パス→SHA-256の辞書を上記と同じJSON方式で集計した値。秒数はClaudeの終了イベントのduration_ms合計であり、意味レビューの待機時間や大規模性能を表さない。

| ケース | 判定 | CLI操作 | 秒 | 記録集合のSHA-256 |
| --- | --- | --- | --- | --- |
| smoke | 合格 | 1 | 22.306 | `48c7239bfa93c56c386ce826d65dd07051580df9bf50ec370d1ff923464bbf6f` |
| discovery | 合格 | 14 | 85.341 | `3942141e54a49227fbd28157eec473e5872d7c10bd333f160e74a0a2d60c1cf6` |
| paging | 合格 | 6 | 61.639 | `0daba8f541c1f9e00ec6e6fd935e1e838baeaec43430206f536cb10ea91628e8` |
| ambiguous | 合格 | 11 | 145.123 | `497a96716e8c03da3e5e24eac96b4a22fe7a8bc746f9ed6cf0a9d48d1e15cd8d` |
| explicit | 合格 | 17 | 215.298 | `87bd54d739daaaa8523a203361c1f5311b3b74f45be30454c8ef1101717fa9f0` |
| organize | 合格 | 23 | 247.164 | `7f9a5d3c87d83a984cd6c62f5f609e68ed019f446520daabc39511019c3f8caa` |
| rebase-target | 合格 | 13 | 147.554 | `1450baf40ca628ed41a630ee5b15145141400fc108f1fb71119438314045e2a1` |
| rebase-basis | 合格 | 12 | 140.560 | `6a32ef5cfa37c40c7d5ac58c79ddf288456c61e3c56f56d1009e49cbe4928821` |
| rebase-scope | 合格 | 13 | 135.430 | `3a96ed70e2352f3adfbef10761e845dc307f0bcd42dbdb6fb50445a7bd7de08f` |
| rebase-relation | 合格 | 12 | 131.637 | `c0a89bdbfb9ee5c151571ac19a8de4044dce955ed04369980a77b3f0ba0cae6f` |
| unrelated | 合格 | 11 | 113.149 | `b4e48a3f777ef82af0c99ab532ded4803bd776fd7121f638a3ef5ed267c948a1` |
| retry | 合格 | 8 | 98.361 | `6e3c8805f62b1de469db50df34a7a03ef7d6d8e9d202561a3b12199e9c8e12c9` |
| failed | 合格 | 9 | 98.186 | `f2000ec107037474a8421e0cbaf309b3f082c88f3fa125697b539de89819f3f1` |
| unobserved | 合格 | 8 | 69.592 | `0763b93b6997b01d167c702361784d01b389e6bcb6b06d32f820934bc9a45715` |
| projection | 合格 | 8 | 54.953 | `20a9bb8975416fd96b19daa47630926f731a4dac827468cc2ffa2bf25d1fee66` |
| handover | 合格 | 10 | 72.842 | `0ea7ba6060fde0fa9e5f2645dbbec03a2404e94a9187900ce82dffeaeb73c8c9` |

未定義kindや空配列の入力で `INVALID_REQUEST` を受けたケースは、仕様を確認して修正・再取得した経緯も保持している。正常な0件と失敗を混同していない。一部ではCLI入力生成のechoや文書へのwc等、Claude Codeが元から許可する標準読取専用コマンドも観測した。追加のBash一括許可や隔離外実行ではなく、これらもOS隔離の対象である。境界と例外は [サンドボックス](LLM_SANDBOX.ja.md) に従う。

## 代表データとJSON復元後の再利用

[scripts/verify_representative.py](../scripts/verify_representative.py) の4段階を使用した。初期100ノードはagreement 89、scope 3、artifact 4、question 2、rationale 1、proposal 1。未分類メモ、通常ログの複数Scope、未採択30日案とcandidate、条件付き例外、無関係の未解決事項、コード・テストと旧証拠を含む。

通常ログだけを同一IDで48時間へ改訂し、実ファイルを観測・編集して3テストを実行、新しいpassed証拠を両合意へ結んだ。監査ログ90日、旧証拠、無関係92ノード・91関係の全保存内容は不変だった。新証拠の追加後は101ノードとなった。支持関係が旧合意版を指す診断はそのまま残し、検証関係のcurrentや未採択案と区別して説明できた。

完全JSONを未存在のDBへ復元して全履歴・来歴・再試行記録の一致を確認した後、現物・DB・実証拠ログだけをコピーした新セッションを起動した。前の会話・要求JSON・48時間という答えは渡していない。新セッションは合意・理由・監査・固定対象版を再取得し、現物2ハッシュとの一致を確認した。以前の実行場所と今回の場所、過去の成功と今回未実行、証拠ログのハッシュ未照合も区別した。

| 段階 | CLI操作 | 呼出全体の壁時計秒 | Claudeイベント秒 | API秒（CLI申告） |
| --- | --- | --- | --- | --- |
| 変更・実検査・新証拠 | 22 | 248.151 | 244.398 | 230.663 |
| JSON復元後の独立セッション | 10 | 76.285 | 72.468 | 67.816 |

変更段階のLATIS CLI22操作を別に計測した合計は **9.187秒**。Python起動とIPCを含み、コア内部だけのCPU時間ではない。引き継ぎ段階のCLI時間は個別計測していない。100ノードの利用確認であり、20万合意の性能評価へ外挿しない。

`representative/report.json` に両機械判定・意味レビュー・時間を保存。記録集合のSHA-256は変更側 `f02bfcf7843546d528ae4b87573cd63c8c7860326a6acc246a19d697447027d7`、引き継ぎ側 `bef029204fd189d8c2499098913118d8a8b361b38de0d8b94a75ec25f4940c45`。集計方法は16ケースと同じである。

## 配布物・表示・残る範囲

最終文書を含むソースの専用コピーから構築し、別の新しい環境へローカルwheelだけを導入した。版は0.3.0、実行依存は空、同梱23ファイルは元ソースと一致した。実CLI24操作の入力・応答は `release/check/calls.json`、導入環境と対応は `release/check/report.json`、構築元は `release/build-source.json`、Web等の実行結果は `build.json` に保存した。

wheel: `/tmp/latis-m5-intel/release/wheels/latis-0.3.0-py3-none-any.whl`

SHA-256: `ca11b12d8af5028d0e50b0716cc4846be354ebf8565d27388c52439dfbe61f9d`

現在のホストCIを新たに実行した結果ではなく、M4のLinux結果は過去の対象として保持する。公開先への反映、展示当日の接続、20万合意の測定、推論検索・権限・優先規則・移行等のM6項目はこの判定範囲に含めない。Coreが外部ファイルを自動観測しないこと、evidenceが呼出元の申告であること等、Spec/APIが定める保証の限界は維持する。

## 再現とログ

Python 3.12を使用し、`log-window` が返す固定名ログへ `FORCE_COLOR=1` 付きで上書き出力する。全回帰は `python -m unittest discover -v`、隔離の事前確認は `scripts/check_claude_sandbox.py --output <新しい専用出力先>`。26項目の合格後、`scripts/llm_acceptance.py --output <新しい専用出力先>` を実行し、機械判定と意味レビューを行う。ケース間のレビュー待ちは既存のprepare_case/run_claude/evaluateを使い、未確認なら次へ進まない。

代表データは実装ガイドのprepare/change/handover/reportの4段階、配布は `scripts/verify_release.py --output <新しい専用出力先>`、既定シナリオは `scripts/rehearse.py` と `scripts/reset_demo.py` を使う。

固定名表示ログは `/tmp/agent-logs/github.com-LATIS/test.log`、`e2e.log`、`task.log`、`build.log`。全実記録は `/tmp/latis-m5-intel/` に保存し、生ログはリポジトリへ追加しない。一時領域は永続保管ではなく、消失後はコマンドから再実施する。

## 前回のApple Silicon機の中間記録

以下は別の機種・環境での過去の記録であり、今回の実行結果ではない。元の一時記録はこの機に存在しないため、上記のIntel機で受け入れを再実施している。

### 前回の対象と記録

基準コミットは `904a44a3d04a846bd115ade4bc94f64c65bb3148`。M5前のPython起動経路修正を含む作業ツリーを対象にする。実装・試験基盤・テスト・v0.3.0文書・CLI・配布設定の46ファイルのSHA-256を `/tmp/latis-m5-20261105/sources.json` に固定した。環境は同ディレクトリの `environment.json`、条項照合は `audit.json`、実行ログはリポジトリ内 `.logs/m5.log`。

macOS 26.7.1／arm64／Python 3.12.11／Unicode 15.0.0／SQLite 3.51.3を使用する。隔離の事前確認は [サンドボックス記録](LLM_SANDBOX.ja.md#2026-11-05-apple-silicon環境でのm5前確認) の26項目合格とsmoke。開始時にも対象ソースとのハッシュ一致を確認した。

### 前回の条項の最終照合

[仕様対応表](SPEC_COVERAGE.ja.md) のSpec・APIの条項を `model`、`engine`、`storage`、`cli`、`projection` の実装と照合した。C01〜C33の検査索引が現存するメソッドを指し、A01〜A26・E01〜E12とP1の対応を追跡できることを確認した。

入力・正規化・状態遷移・関係・固定証拠、検索と過去版の分離、seed・basis・watch、before/afterの変更検知、冪等性を先に返す検査順、原子的更新、完全JSON・SQLite復元、Markdownの読取専用投影を現物で確認した。コアが外部URI・テスト・LLMを実行しない責務と、未採用の優先規則・推論検索等を追加しない境界も確認した。今回の照合で現行P0・P1の未対応条項は検出していない。

### 前回の実施状況

| 検査 | 現在の結果 |
| --- | --- |
| Python全回帰 | `python -m unittest discover -v`、120件、31.224秒、合格。LLM自体は起動しない |
| 隔離下のLLM16ケース | 着手中。smoke・discovery・paging・ambiguous（回答前後）・explicit・organize・rebase-targetの7ケースが合格。各ケースの機械判定と実応答のレビューを終えてから次へ進む |
| 代表データでの一連の利用 | 未実施 |
| 保存用の既定シナリオ・復旧 | 既定シナリオ2.587秒、初期・変更後の実テスト各3件、旧証拠拒否、新証拠、JSON復元が合格。baseline/final × SQLite/JSONの4通りの復旧と実テスト各3件、復元元保持も合格 |
| 同一ソースからの配布検査 | 新規環境でwheel構築・別環境への導入、CLI24呼出し、同梱23ファイル、素材3テスト、両形式の復元が合格。最終の利用文書更新後にも同梱内容を確認する |
| 完全実装の最終判定 | 未実施 |

LLM利用は `scripts/llm_acceptance.py` のケース・起動・機械検査をそのまま用い、`/tmp/latis-m5-20261105/llm_driver.py` がケース間のレビュー待ちだけを加える。全起動は `claude -p --safe-mode --restricted --model claude-opus-5-5 --effort high` と必須OS隔離で行う。実際の返却モデル、操作、DB、現物、実検査と証拠を別に確認する。意味レビュー前の自己申告を合格にしない。
