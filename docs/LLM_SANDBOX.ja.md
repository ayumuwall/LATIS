# Claude利用試験のサンドボックス

この設定は `scripts/llm_acceptance.py` が起動するClaudeにだけ適用する。通常のClaudeセッション、Codex自身、ユーザーの設定ファイルは変更しない。LATIS Coreの機能ではなく、自動利用試験の実行環境である。

M5ではmacOS 15.8.1／Intel／Python 3.12.0で拒否試験26項目を通し、同一構成による隔離下の全16ケース・17起動・CLI176操作を再確認した。結果と対象版は [M5検証記録](M5_VERIFICATION.ja.md) を参照する。以下の検証記録とApple Silicon機の事前確認は、それぞれの実施時点の対象・結果として保持する。

## 境界

Claude CodeのBashサンドボックスを起動引数の `--settings` で必須にし、Bashとその子プロセスをmacOSのOS機能で制限する。Pythonテストが別のコマンドを起動した場合も、この制限を継承する。`--safe-mode` だけではこの隔離は有効にならない。[公式の適用範囲](https://code.claude.com/docs/en/sandboxing#what-runs-outside-the-sandbox) を参照。

| 対象 | 設定 |
| --- | --- |
| ファイルの読み取り | 原則 `/` から拒否。専用作業コピー、固定ツール、必要なfixture・監査ファイル、v0.3.0文書、Python・OS・共有ライブラリ、専用一時領域だけを例外にする |
| ファイルの書き込み | 作業コピー、4種類の専用監査ファイル、専用一時領域を使用。元リポジトリと実行ツールは明示的に書き込み拒否 |
| Bashの通信 | 許可ドメインなし。任意のUnixソケットとローカル待受も許可しない |
| 隔離外での再試行 | `allowUnsandboxedCommands: false`。例外コマンドは空にする |
| 隔離できない環境 | `failIfUnavailable: true`。この実装ではmacOS以外や依存ライブラリを解決できない場合も、起動を中止する |
| コマンドの承認 | `dontAsk` と従来の固定コマンド許可を維持。隔離内のBashの一括自動許可は使わない |
| Read・Write・Edit・Glob・Grep | OSのBash隔離とは別に、`--restricted` で作業場所と追加した文書へ制限。元リポジトリの編集は拒否 |
| 環境変数 | 起動に必要な項目だけを渡す。APIキー、AWSの秘密、任意のシェル・Python起動設定等を引き継がない |

監査ファイルの例外は各ケースの `calls.jsonl`、`helpers.jsonl`、`injected.json`、`lost-response.json`。設定・起動記録・以前の会話を含むケース全体への読み取り許可や、親ディレクトリ全体への書き込み許可は付けない。

実行用ソースは `tool/runtime/` に必要なファイルだけ複写し、元ソースとのSHA-256一致を `runtime-sources.json` に記録する。このコピーもBashから書き込み拒否にする。元リポジトリ全体を読み取り可能にしてPythonのパッケージ探索を通す方法は使わない。

共有ライブラリは `otool -L` で実体を辿る。Homebrewのパッケージリンクと必要なlibディレクトリも読み取り例外になる。ホーム全体、`/usr/local` 全体、`/System/Volumes/Data` は許可しない。起動時の許可一覧は各ケースの `initial-launch.json` の `sandbox` に保存する。

パス解決に必要なディレクトリの属性参照等は、Claude Codeの隔離ランタイムが許可する場合がある。ディレクトリ外について、存在や属性も含めて何も観測できないという保証ではない。拒否試験で確認した一覧取得は、専用ダミーファイルの外側ディレクトリに対するものである。

Claude内部の一時ファイルには、短い `/private/tmp/ls-*` を実行ごとに用意し、終了時に削除する。これは生ログ用のディレクトリとは別である。長いパスではClaudeが既定の一時領域へ切り替わるため、短い専用パスを使う。[一時領域の公式説明](https://code.claude.com/docs/en/env-vars#claude-code-tmpdir) を参照。

## 再現方法

既存のClaudeログイン、macOS、Python 3.12、`sandbox-exec`、`otool` が必要。CLIはOpus 5.5 / highを明示し、LLMのAPIを直接呼ばない。出力先には未存在の専用ディレクトリを指定する。

```sh
~/.local/bin/log-window e2e --keep
FORCE_COLOR=1 python3 -u scripts/check_claude_sandbox.py --output /tmp/latis-sandbox-check-new > /tmp/agent-logs/github.com-LATIS/e2e.log 2>&1
```

自分で作ったダミーファイルだけを使い、実在の秘密や認証ファイルを読み取らない。外側の読み取り・書き込み・作成・一覧、シンボリックリンクとハードリンク、子Python、子シェル、リダイレクト、直接通信、ツールと設定への書き込みを検査する。Readツールの範囲制限、内側の読み書き、監査ファイルへの必要な書き込み、一時領域の分離と削除、Bashの正常終了も確認する。

`report.json` の `passed` がfalseなら、通常のLLM試験へ進めない。Claudeの終了コードが0でも、試験プログラムが起動しなかった場合や、途中のBashが失敗した場合は合格にしない。

通常利用の確認は同じ設定で行う。

```sh
FORCE_COLOR=1 python3 -u scripts/llm_acceptance.py --output /tmp/latis-sandbox-usage-new --cases explicit retry > /tmp/agent-logs/github.com-LATIS/e2e.log 2>&1
```

## 保証の範囲

これはClaude本体を丸ごと閉じ込めるコンテナやVMではない。Claude本体の認証・LLM通信・管理用ファイルへのアクセスはBashの隔離外にある。ファイル用ツールの制限もClaude Codeの権限処理であり、BashのOS隔離とは実施箇所が異なる。したがって「PC上のすべてのプロセスが専用作業場所の外を一切読み書きできない」とは説明しない。

専用fixture・監査ファイルはこの試験のために読み取り可能にしている。試験コード内の値から秘密を隠したり、悪意のあるコードが作る検査結果の真正性を認証したりする仕組みではない。LLMの自己申告だけで合格にせず、呼出記録・実物・DBの別検査を引き続き使う。M3で実施した16ケースは隔離導入前の対象版への結果であり、今回の隔離下で全件を再実行した結果へ読み替えない。

CPU・メモリ・プロセス数の制限、他OSでの隔離、Claude本体まで含むVM等の隔離は、この実装の対象外である。

## 検証記録

macOS 15.8.1（x86_64）、Claude Code 2.1.318、Python 3.12.0、Unicode 15.0.0、SQLite 3.43.2で確認した。指定と実際の返却モデルはOpus 5.5（`claude-opus-5-5`）、effort指定はhigh。基準コミット `02a2ff3` に変更を加えた作業ツリーが対象である。

| 検査 | 結果 |
| --- | --- |
| 実Claudeからの隔離検査 | 26項目すべて合格。専用ダミーファイルを使用し、Bashの正常終了と一時領域の削除まで確認 |
| explicit | CLI操作17件。通常ログを同一IDで48時間へ改訂し、監査90日を保持。コード・テストを編集、実テスト3件成功、新しい証拠を保存。機械検査・意味レビュー・snapshot検査が合格 |
| retry | CLI操作10件。最初のapplyの成功応答だけを失わせ、同じ入力・キー・応答で回復。graph_revisionは2のままで二重commitなし。機械検査・意味レビュー・snapshot検査が合格 |
| Python全体テスト | `python3 -m unittest discover -v`、111件、43.959秒、合格。うち追加した7件は隔離設定・起動引数・環境変数除去・偽成功拒否・専用実装コピーをLLMなしで検査 |

隔離検査と通常利用を合わせたClaudeの呼出しは3回。各ケースのコピーと元実装のハッシュ一致を終了後にも照合した。M3の残り14ケースは、この隔離構成では未再実行。ホストされたCIや他OSでのOS隔離を確認した結果ではない。

途中の検査では、共有ライブラリとその途中のリンクを拒否してPythonが起動しない状態、長い一時パスから既定の `/tmp` へ切り替わりBashの後処理が失敗する状態、元リポジトリの一覧取得を拒否してPythonパッケージ探索が失敗する状態を検出した。必要なライブラリの所在だけの追加、短い専用一時領域、同一ハッシュの実装コピーで修正した。隔離外での実行やホーム全体の許可へ切り替えて合格させていない。

検査と起動の対象ソースは次のSHA-256で識別する。

| ファイル | SHA-256 |
| --- | --- |
| `scripts/claude_sandbox.py` | `1d9c29c57b0abfe8d1c390492a407343c8a338f065b891a71753f4d49db1c8ef` |
| `scripts/check_claude_sandbox.py` | `29a42d6a30170b5ec111b077cac3065b115887a453c048b810ec9e6407ba1a27` |
| `scripts/llm_acceptance.py` | `29c0b598e16a16c707656f19ab7e2a645d11a9382fe996aaf9440413e8c523af` |

実行記録は `/tmp/latis-sandbox-accepted/report.json` と `/tmp/latis-sandbox-usage/{explicit,retry}/` に置く。各ケースには起動・操作・結果、機械判定、意味レビュー、専用実装コピーのハッシュを保存した。環境・全ソースのハッシュ・集計は `/tmp/latis-sandbox-receipt.json`。固定名の表示ログは `/tmp/agent-logs/github.com-LATIS/e2e.log` と `/tmp/agent-logs/github.com-LATIS/test.log`。いずれも一時領域なので、後日の再現には上記コマンドを使い、消えたログを現在の検証済み状態と取り違えない。

## 2026-11-05 Apple Silicon環境でのM5前確認

基準コミット `904a44a3d04a846bd115ade4bc94f64c65bb3148` から起動経路を修正した作業ツリーを対象に、M5へ進む前の隔離を再確認した。以前のIntel環境の全体テスト・利用受け入れとは別の実行である。

| 項目 | 今回の環境・結果 |
| --- | --- |
| OS・CPU | macOS 26.7.1（25G241）、arm64 |
| Python | Homebrew 3.12.11から作った `.venv`。既定の3.14は使わない |
| 標準ライブラリ | Unicode 15.0.0、SQLite 3.51.3、OpenSSL 3.6.2 |
| ビルド用依存 | pip 25.1.1、setuptools 84.2.1、wheel 0.48.0、packaging 26.3。`pip check` 合格 |
| OS側の道具 | `/usr/bin/sandbox-exec`、`/usr/bin/otool` を確認。共有ライブラリは今回の実体から解決 |
| Claude | Code 2.1.318。指定・実際の返却モデルとも `claude-opus-5-5`、effort指定high |
| 拒否試験 | 26/26合格、`report.json` の `passed=true`、終了コード0 |
| 同じ隔離設定でのsmoke | Guide参照・API検索・実CLIのmeta取得1件。DB・コード保持、機械判定と実応答のレビューが合格 |
| 関連するPython検査 | `tests.test_claude_sandbox` と `tests.test_llm_acceptance` の17件が合格（10.308秒） |

初回と実体パスを直接指定した2回目は、検査プログラム自体を起動できず不合格だった。OSログでは `/opt/homebrew/Cellar/python@3.12/3.12.11/bin/python3.12` への `file-read-metadata` が拒否されていた。Homebrewの `sitecustomize.py` が `sys.executable` を中継symlinkへ戻すため、実体パスから起動するだけでは生成されるコマンドが変わらなかった。

修正は、試験用コマンドのshebangに解決済みのPython実体を使い、Claude起動環境の `PYTHONEXECUTABLE` も実体へ固定すること。親の同名変数は引き継がない。監査CLIも同じPythonで `bin/latis` を実行し、PATH上の別版・中継symlinkを使わない。`settings_for` と `runtime_read_paths` は基準コミットから変更しておらず、読み書き・通信の許可拡大や隔離外での再実行は行っていない。修正後は `.venv` からの起動で合格した。

拒否試験では外側の読取・書込・作成・一覧、symlink・hardlink、子Python・子シェル・リダイレクト、直接通信、ツール・設定への書込を拒否した。内側の読み書きと監査ファイルへの必要な書込、秘密環境変数の除去、一時領域の分離・削除、Bashの正常終了も確認した。smokeの専用実装コピー12ファイルは、元ソースと実行後も同じSHA-256だった。

再現コマンド（出力先は毎回、未存在のパスへ変更する）:

```sh
source .venv/bin/activate
FORCE_COLOR=1 python -m unittest tests.test_claude_sandbox tests.test_llm_acceptance -v
FORCE_COLOR=1 python -u scripts/check_claude_sandbox.py --output /tmp/latis-sandbox-pre-m5-20261105-arm64-fixed
# report.jsonのpassed=trueを確認してから、同じ設定で疎通を確認する。
FORCE_COLOR=1 python -u scripts/llm_acceptance.py --output /tmp/latis-sandbox-pre-m5-20261105-smoke --cases smoke
```

実行中の出力はプロジェクト内 `.logs/test.log` へ記録し、既存のiTerm2ウインドウで `tail -f` を表示した。この環境には `~/.local/bin/log-window` がなく、AppleScriptで表示を準備・確認した。ログと仮想環境はGitの対象外とする。

| 対象ソース | SHA-256 |
| --- | --- |
| `scripts/claude_sandbox.py` | `127e57ac97cadb43755f5e7d68b0850398d17330ca96dce15dd1687c59098107` |
| `scripts/check_claude_sandbox.py` | `d8766b8e88a5d7b0e8c836715721aaf16385cb591e98ccd6c011480a39fba5ea` |
| `scripts/llm_acceptance.py` | `10422118e53e21cef97739baf3f245316c78d2daaaa651d9f2afa2b3032a9ea2` |

失敗記録は `/tmp/latis-sandbox-pre-m5-20261105-arm64/` と末尾 `-realpath/`、合格記録は末尾 `-fixed/report.json`、smokeの起動・操作・終了・判定は `/tmp/latis-sandbox-pre-m5-20261105-smoke/smoke/` に保存した。環境・対象ソース・結果の集計は `/tmp/latis-sandbox-pre-m5-20261105-receipt.json`。今回の確認は隔離と疎通の事前検査であり、M5の全回帰・16ケースのLLM利用・代表データの受け入れにはチェックを入れない。
