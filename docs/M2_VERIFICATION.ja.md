# M2 P1の検証記録

M2では現行API §5.1の子孫Scope検索と§16.3のMarkdown投影を実装し、P0の回帰と配布CLIを確認した。条項と実装・assertionの対応は [仕様対応表](SPEC_COVERAGE.ja.md)、進捗は [タスク管理票](TASKS.ja.md) に記録する。

## 対象と環境

- 基準コミット：`7c95c6735de4011e48f0918c75a4652634105195`。M2の変更後の対象は下表のSHA-256で識別する。
- 記録時刻：`2026-11-04T15:01:07.479801Z`（日本時間2026年11月5日）。
- Python：`3.12.0`、Unicode：`15.0.0`、SQLite：`3.43.2`。
- OS：`macOS-15.8.1-x86_64-i386-64bit`。
- 契約：`spec_version=0.3-demo-draft`、`rules_version=core-0.3.0`、JSONの`format_version=2`。保存モデルや9操作は変えず、任意capabilityの`search_descendants`と`markdown_export`を追加した。

## 実行結果

| 検証 | 結果 | 内容 |
| --- | --- | --- |
| `FORCE_COLOR=1 python3 -m unittest discover -v` | 合格、94件、25.424秒 | 既存75件とP1の19件。実CLIの展示再現、通常ログ24→48時間、監査ログ90日維持、新旧証拠、退避・復元も含む |
| `python3 -m compileall -q latis scripts tests` | 合格 | 新規のprojectionモジュールとテストを含む構文検査 |
| wheel構築と一時仮想環境への導入 | 合格 | リポジトリ外の作業場所からインストール済みCLIを実行。site-packagesからの読込、同梱Guide・P1入力例、正規化fixture、seed採択、子孫検索、全7ノードの投影、完全JSON復元後の検索一致を確認 |
| `git diff --check` | 合格 | 差分の空白・改行を確認 |

配布検査は`python3 -m pip wheel --no-deps --no-cache-dir --wheel-dir <一時場所>/wheels .`で構築し、新しいvenvへ`pip install --no-index --no-deps <wheel>`で導入した。検査した`latis-0.3.0-py3-none-any.whl`のSHA-256は`13e3d89ede3526525805fa66f0a7c78b8b095a7659fd0d5bd76a2e9bd4ea44d0`。wheelとvenvは一時成果物であり、配布リリースにはしていない。

初回の検査では、追加テストのI/O障害時のstdout期待値と、一時配布検査のseed件数の固定値を修正した。上表はその後の成功結果を示す。

生ログは`/tmp/agent-logs/github.com-LATIS/test.log`と`/tmp/agent-logs/github.com-LATIS/build.log`に保存した。iTerm2ウインドウはこの実行環境では開けず、ログファイルへ出力した。固定名のログは再実行で上書きするため、結果と対象の識別情報を本記録へ残す。

## 確認したP1の境界

- 子孫検索はactive/confirmed containsを全深さで辿り、指定Scopeを含めて重複除去・ID昇順にする。複数起点・複数経路・候補/終了関係・空Scope・未分類と既定の直接検索を検査した。
- cursorはフラグと展開集合にも結び付ける。階層変更によって展開結果が変わっても、古いsnapshotは`CURSOR_STALE`を返す。consultのwatchは直接Scopeのまま維持する。
- Markdownは全体/明示ノード/直接Scopeを選べる。終端状態やkindで暗黙に除外せず、0件ならindexだけを作る。front matterの全保存情報、原文bodyのバイト、直接関係の全状態・方向・根拠版と固定evidenceを保持する。
- IDをUTF-8のbase64urlへ変換し、スラッシュ・日本語・改行を含む不透明IDでも安全な相対ファイル名にする。indexの表示文字をエスケープし、選択外のファイルへリンクしない。
- WALで別接続が投影中にcommitしても、index・ノード・応答は開始時のsnapshotで一致する。作成中のディレクトリは公開せず、完成後に排他的なrenameで公開する。
- 既存のファイル・空/非空ディレクトリ・symlinkと、公開直前の競合を上書きしない。書込・fsync・renameの障害後には一時出力を削除し、正本DBを維持する。投影編集やMarkdown restoreでDBを変更できない。

## 後続へ引き継ぐ確認

LLMの利用確認はM3で`claude -p --safe-mode`を使い、LLMのAPIを直接呼ばずに行う。M2ではPythonと実CLIによるコア契約を確認し、独立したLLMセッションによる探索・判断・説明の合格にはしていない。

排他的公開のローカル実行結果はmacOSのrenamex_npに対するもの。Linuxのrenameat2とWindowsのrenameは実装済みだが、この記録で両OSの実行合格を主張しない。UbuntuのCIにP1とインストール済みCLIの検査を加え、ホストされた実行と環境・配布・復旧の確認はM4〜M5へ引き継ぐ。

## 対象ソースのSHA256

下表の31ファイルをパス順に並べたJSON配列のSHA-256：`100dabd97f086dd0359ebdade475f2ba5f549de11fc0e3f233fde1b1bd00291d`。各要素は`path`と`sha256`を持ち、UTF-8・キー昇順・空白なしでシリアライズした値を使う。M1の対象ハッシュは履歴として [M1検証記録](M1_VERIFICATION.ja.md) に保持する。

| ファイル | SHA-256 |
| --- | --- |
| `.github/workflows/core.yml` | `a340f69434736cd2f5f175e3308f988a2ea8cec71d9e989d2c205e47ce6ca0c5` |
| `bin/latis` | `10dd8ab3b7ba5670ae54b013cd0a5c5d7c06ff68e5d38bebbff2134872844b8b` |
| `docs/v0.3.0/LATIS_API.md` | `cdf56e9e8b6e0808a5ae2971a72601a7cd83d046a5688e7d6dadaed15c08831c` |
| `docs/v0.3.0/LATIS_Demo_Guide.md` | `d4956dac279f2a0bb2ef035b113860ab8aff0fc9ddc051bfeeddb0a2bb9a7655` |
| `docs/v0.3.0/LATIS_Design_Decisions.md` | `432bced544511ad51fca8e53793eca3310a4092049fee0438859b106ee55c915` |
| `docs/v0.3.0/LATIS_LLM_Guide.md` | `bc8939e92feb0485a634b6081f74d17d8a778207cc0abde0167e6ad105e3472b` |
| `docs/v0.3.0/LATIS_Operation.md` | `8c1cb1f28160042351b6a319a45b95b5f1f12f2795dfe7b093be86b3f9610321` |
| `docs/v0.3.0/LATIS_Prototype_Plan.md` | `8de146bdd65c2b2ab7b09842652fa0c396411ee61007e5abf6a58320191ef8ae` |
| `docs/v0.3.0/LATIS_Spec.md` | `a11a6f90dff1f2ff7bf99bbfc4b43cc513007b97b72be87e9229209bc84c0eb3` |
| `docs/v0.3.0/README.ja.md` | `c79a99efce01f324934d58392375df48df70f3fe4425425d0fe16877ee181053` |
| `docs/v0.3.0/README.md` | `7b906b4b3819e4a4130f8f0e1e1ada24ab81332d2e7053268eaa482f119ab4b4` |
| `docs/v0.3.0/examples/export_markdown.request.json` | `7111cfe311fe7be508fbfa81ab588e1adb44511c8635f5528cfddf7d6c0187dd` |
| `docs/v0.3.0/examples/search_descendants.request.json` | `b1e7e01e1fe09d0c9e493365a494f9e4002432f149d6172a20b3e368f18dc621` |
| `docs/v0.3.0/examples/search_logs.request.json` | `4ab0284dd22bf526ffe846e415e6750e574c3ed9fcab12d8ae1cd89ead5362c7` |
| `docs/v0.3.0/examples/seed_consult.request.json` | `ec94eedd8d0e6d435c77b1f540f4be4c77fd986dfd20c917626d113af23750fa` |
| `latis/__init__.py` | `ca5b6e56cc71d6c8510de41e8e3f61103126255d3c241118e2b9d7f88bba4330` |
| `latis/__main__.py` | `935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d` |
| `latis/cli.py` | `6ee688481fa0c1f9421edcdc7a7fddfebbc563ae40a2ce52cb4bd0cea5f819e3` |
| `latis/engine.py` | `71bb4e2b146255e62aca7590a1971ad9ff8a9d5c9ad434c80e502275640ea398` |
| `latis/model.py` | `f2abc9e0d573397ab9ce07d05fee6f361aedd1679b3f9f12c9d76be94fedc5bb` |
| `latis/projection.py` | `53e63dd8d4cffd0aa15914327657538c3d31bff9e963480be9c633d85647c7c7` |
| `latis/storage.py` | `7399d9144ca7c9785c22b49fea321ae23839d6262a775eb542dd4670983fe75d` |
| `pyproject.toml` | `d3b9b4b696bc2a1a3b9e24dc8ea6e1e80f742aaebe3ad20a67e0527703ad3320` |
| `scripts/rehearse.py` | `7645f9681019eaeb2167b2b77580a5918b96c6984b8e8b63f8318899e8a74890` |
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/fixtures/normalization.json` | `f2740c48b1c616807e8a89c9b1af425659f2d9af6e3c04cd100ba29ce5d28424` |
| `tests/support.py` | `b74c93cba71b85fd6be8737e1ca785ceb86f0f2d345e34b200bca57fd0b75810` |
| `tests/test_contracts.py` | `b91ced1ecd7cb1507ea8b791277401470ce4352ad06451e61bc496b8b7317967` |
| `tests/test_engine.py` | `caec437c9530ca9de342020ff627d629ddd6f932e7be2449f85c0e4772fe16bf` |
| `tests/test_p1.py` | `aa99f418f3290c28a8c796e4c6c8950ed586e1453486be1fc9197660669b0fc4` |
| `tests/test_rehearsal.py` | `0e630917836ac62d095f0703156f9ccfa9a7ca73927540a2754800a8e15ee443` |
