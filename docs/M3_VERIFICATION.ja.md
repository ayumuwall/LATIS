# M3 LLM利用の検証記録

M3の16ケースを、ユーザー指定のOpus 5.5 / highで実行した。17回のClaude CLI呼出しと182件のLATIS CLI操作について、機械検査とCodexによる実記録の意味レビューが合格した。試験基盤を含む全104件のPythonテストも合格し、M3の8タスクを完了した。次はM4の運用・配布・復旧の確認へ進む。

ケースの入力・期待する変化・失敗条件は [M3ケース](M3_CASES.ja.md)、条項との対応は [仕様対応表](SPEC_COVERAGE.ja.md)、進捗は [管理票](TASKS.ja.md) を参照する。

## 対象と環境

この記録の17呼出しは、ツールのコマンド許可を使った隔離導入前の検証である。OSレベルの読み書き禁止を確認した記録ではない。その後の隔離設定・拒否試験・通常利用の再確認は [サンドボックス](LLM_SANDBOX.ja.md) に分け、ここに残す対象ソースのハッシュは変更しない。

- 基準コミット：`02a2ff3499d7396704f4511cdb7beb9d637a1448` にM3の変更を加えた作業ツリー。現在の対象ソースは後段のSHA-256で識別する。
- 記録時刻：`2026-11-04T16:39:42.824376Z`。
- Claude Code：`2.1.318`。既存のClaudeログインを、macOSのアプリ操作が可能な権限から利用した。
- 全17呼出しの指定：`claude -p --safe-mode --model claude-opus-5-5 --effort high`。返された実モデル名も `claude-opus-5-5` と一致した。effortはCLIへhighを明示した指定値として記録する。
- Python：`3.12.0`、Unicode：`15.0.0`、SQLite：`3.43.2`、OS：`macOS-15.8.1-x86_64-i386-64bit`。
- 契約：`spec_version=0.3-demo-draft`、`rules_version=core-0.3.0`、JSONの`format_version=2`。
- LLMのAPIは直接呼ばない。文書と専用作業コピーのRead/Edit、専用DBの監査CLIと固定の観測・実テストだけを許可し、権限の一括スキップは使わない。

各起動のlaunch.jsonにコマンド、プロンプト、作業場所、model/effort、起動時の対象ソースのSHA-256を保存した。Guideと試験基盤を改善しながら行った増分検証であり、個別起動時の構成はこの記録から辿る。確定した同一構成での最終受け入れはM5で行う。

## 実行結果

| 検証 | 結果 | 内容 |
| --- | --- | --- |
| `FORCE_COLOR=1 python3 -m unittest discover -v` | 合格、104件、43.085秒 | P0/P1の94件、LLM試験基盤の9件、バイトコード再利用の回帰1件。既定シナリオの実CLI・実テスト・退避復元も含む。LLMは起動しない |
| Claude CLIによる16ケース | 全件合格 | 17呼出し、CLI操作182件。全呼出しが正常終了し、モデル名一致を確認。CLI操作・DB・現物・実検査と自然文を別々にレビューした |
| 構文検査と差分検査 | 合格 | `python3 -m compileall -q latis scripts tests`、`git diff --check` |
| iTerm2の逐次ログ表示 | 確認済み | log-windowをアプリ操作が可能な権限で実行し、同じウインドウの再利用、操作・応答・終了結果の逐次表示を確認 |

下表の秒数は実際のCLI終了イベントのduration_ms合計であり、性能目標や大規模データの測定値ではない。Aは`/tmp/latis-m3-acceptance`、Dは`/tmp/latis-m3-demo`、Rは`/tmp/latis-m3-recovery`、Eは`/tmp/latis-m3-evidence`を表す。

| ケース | 判定 | CLI操作数 | 秒 | 記録の場所 | 記録集合のSHA-256 |
| --- | --- | --- | --- | --- | --- |
| smoke | 合格 | 1 | 16.589 | `A/smoke` | `ea2f8c22d0d69897ceb902c3d282e1b41e2bf26e10608babb5dced716c6292e6` |
| discovery | 合格 | 12 | 59.426 | `A/discovery` | `7ea75f86f04da78fe3977ad21716bb936efc3657f59d643f7174c48f5fe76af1` |
| paging | 合格 | 6 | 48.698 | `A/paging` | `ad3bedd6f918a57dae960aecdff86537e84ce2bd9325e77f2625b9fd03dff310` |
| ambiguous | 合格 | 9 | 106.718 | `A/ambiguous` | `7e61fb058119fb333f0c67ec03b1f4cde9ad4aaa27340e90385dbb76d4efc3fa` |
| explicit | 合格 | 18 | 203.318 | `D/explicit` | `eb0962fa8c8e34f005e3a4277d3e66add54138c0e4e17eb909bd9182b2c5a055` |
| handover | 合格 | 9 | 62.505 | `D/handover` | `1e129dc7c898d3682cc3606fdff9c48dedc2651495fae51e051b3a77454185f7` |
| organize | 合格 | 25 | 228.782 | `R/organize` | `1cdd9859a3743abac23684ff44941df4e7fcabad757b6e4ee4519dde4f4f10bb` |
| rebase-target | 合格 | 13 | 120.880 | `R/rebase-target` | `47767de6e4c3d8a5cac2021328467c5f388768cf755ccd8879467093a4789fe7` |
| rebase-basis | 合格 | 12 | 142.486 | `R/rebase-basis` | `239679361e69fe2421a3ba1f5a5f6c93996e24392211b3de7284d030720ef10e` |
| rebase-scope | 合格 | 13 | 119.699 | `R/rebase-scope` | `deccb3b1cb2ba907bed4be7d63da4de920b5a8398b02cd64a741486887fa6922` |
| rebase-relation | 合格 | 13 | 102.871 | `R/rebase-relation` | `d0064572e7ff89753252db11d136b27c95edff504b63188c04c855362a24bfb4` |
| unrelated | 合格 | 10 | 87.887 | `R/unrelated` | `e664202cb2680b79da87594ed7b430e94c3eed79d671911bd2c95bfe78da6879` |
| retry | 合格 | 11 | 94.651 | `R/retry` | `4a613ab567615bc130a8494f641f300a3cfa635b9fec39cc2e2c1420d1243a9a` |
| failed | 合格 | 10 | 90.692 | `E/failed` | `99465dfa37c42b2a1451af8ad19a74ebd7b890ee1b65278d9da736f32e1cf62b` |
| unobserved | 合格 | 10 | 53.928 | `E/unobserved` | `dd1a358d474dc25341d9f6333610141a5c9ff00652aef69318c6485accde6f3f` |
| projection | 合格 | 10 | 65.551 | `E/projection` | `4e508e59f5f73cbc6af709777f6d11693d05059166f8083d3d7c5244c4d81ec0` |

各記録集合はfixture、起動条件、イベント、終了結果、CLI操作、DBの前後、機械検査とレビューを含む。パスとSHA-256を持つJSON配列をパス順・UTF-8・キー昇順・空白なしでシリアライズした値のSHA-256を上表へ記した。16ケースの名前と記録集合のSHA-256の配列全体は`ed2bebdd41b57c1dfedba13f46c0f2cacb5e2ca1b256b0685586015625e208cc`。集約結果は`/tmp/latis-m3-result.json`に置く。

生ログは`/tmp/agent-logs/github.com-LATIS/e2e.log`、Python全回帰は`/tmp/agent-logs/github.com-LATIS/test.log`。固定名のログは実行ごとに上書きし、各ケースの実記録は上表の一時出力先に置いた。リポジトリへ生ログは追加していない。

## 確認した利用動作

- 未分類の草稿メモから別表現の合意へ進み、採択済み・候補・重複した未採択案を区別した。27件の取得と確認範囲を説明し、Scopeなしや0件をDB全体の不存在と取り違えなかった。
- 曖昧な対象では質問して待ち、DB・コード・テストを保持した。返答後と最初から明示された対象では、同じ許可を取り直さず同一IDを改訂し、監査と無関係の未整理事項を保持した。
- 明示された例外・全体置換・撤回・分割・提案の採択と候補の確定を実行した。一般合意、元の原文、意図とrationaleのkind・本文を保持し、分割の出所と変更理由を記録した。
- 対象の版ではPRECONDITION_CHANGED、明示した根拠ではBASIS_CHANGED、Scopeと確定関係ではCONTEXT_CHANGEDを受け、差分の再取得と新しい照合へ戻った。並行更新を保持し、意味が変わらない指示の再承認は求めなかった。無関係の未分類questionの追加は確定を止めなかった。
- 確定済みのapplyの応答だけを失わせ、同じ入力とidempotency_keyで同一の成功応答を回復した。graph_revisionの増分は1で、二重の合意・commitはなかった。
- 実装とテストのハッシュを観測し、実テストの成功を新しい固定subjectの証拠へ記録して両合意へ結んだ。失敗はfailed証拠へ残し、confirmed verified_byへ結ばなかった。旧証拠は変更せず、実ファイルだけの変更では記録上currentでも現在の成功とは言えないことを説明した。
- 子孫検索をcapability確認後に使い、見つかった合意だけをnode_idsでMarkdownへ投影した。DBは保持され、分類のページは出力しなかった。
- 新しいセッションへ前会話・要求JSON・変更後の値を渡さず、合意・理由・監査・固定証拠と現物のハッシュを再取得した。実行済みの検査と、このセッションでは再実行していない範囲も区別した。

## 検出した問題と修正

初回の曖昧な依頼では、対象への返答前に合意・コード・テストを変更して不合格になった。Guide §12と開始指示に、複数種類の合意がある場合は現状の値や理由から対象を決めず、回答まで変更せず待つ条件を明記した。質問前のファイル保持も検査へ追加し、質問と返答後の改訂を再確認した。

明示済みの変更の初回では、同一IDの改訂ではなく新しい合意への全体置換を選んで不合格になった。Guide §10と開始指示に、同じ合意の期間・条件値の変更は同じIDの改訂を既定とし、全体置換はその意図が明示された場合に使うことを明記した。再実行では同一IDの改訂と実検査・新しい証拠を確認した。

試験基盤の初期設定では事前確認コマンドが許可されず、実操作へ進めないケースがあった。Bash全体の許可案は自動承認レビューに拒否され、実行しなかった。最終的には、文書・作業コピーのRead/Edit、専用DBと出力先だけを扱うCLI、引数なしの観測・実テスト補助へ限定した。

独立セッションの検査器は、detailだけを合意本文の取得とみなしていたため、全文の検索結果と現在版の履歴を使った有効な取得を最初は不合格にした。現在版と全文の一致を確かめて取得と認め、短い抜粋だけでは通らない単体検査を追加した。実LLMの同じ記録を修正した検査器とCodexで再評価した。

失敗ケースの初回では、準備時に同じ秒・同じサイズでコードを24から48へ変えたため、Pythonが古いpycを使い、失敗すべきテストが成功した。Claudeは現物との矛盾を検出してinconclusiveを新しい証拠へ記録し、成功として確定しなかった。独立した再現では、通常のキャッシュで終了コード0、空の参照先へ分離すると終了コード1（48 != 24）となった。

この問題に対し、実検査の参照先を毎回空のPYTHONPYCACHEPREFIXへ分離し、PYTHONDONTWRITEBYTECODE=1で実行する共通補助を追加した。LLM試験基盤とrehearseへ適用し、同じmtimeとサイズを意図的に作る回帰検査を追加した。修正後のClaudeは実際の失敗をfailed証拠へ記録できた。初回の不合格・判定不能の記録は一時出力先に保持し、上の成功ケースへ混ぜていない。

## M4とM5へ引き継ぐ確認

M3はここに定義した代表ケースの確認を終えた。ホストされたCI、配布物の再構築、復旧と展示環境の整合、同一構成での最終受け入れはM4〜M5で行う。LLMへCURSOR_STALEを返す分岐やJSON復元後のLLM再利用は今回の16ケースに含めず、Core側は既存の自動テストで確認している。

## 対象ソースのSHA256

下表の25ファイルをパス順に並べたJSON配列のSHA-256：`20bef8dcf7bf1a46eba3a2a3582580300301c370c6860ff4d6d148065a9ff43f`。各要素はpathとsha256を持ち、UTF-8・キー昇順・空白なしでシリアライズする。M1・M2の当時の対象ハッシュは、それぞれの検証記録に保持する。

| ファイル | SHA-256 |
| --- | --- |
| `AGENTS.md` | `ae8b79f0fac01035202b566f7af7049cc1c137a4ce78dcb4af50016cebde255b` |
| `bin/latis` | `10dd8ab3b7ba5670ae54b013cd0a5c5d7c06ff68e5d38bebbff2134872844b8b` |
| `docs/v0.3.0/LATIS_API.md` | `cdf56e9e8b6e0808a5ae2971a72601a7cd83d046a5688e7d6dadaed15c08831c` |
| `docs/v0.3.0/LATIS_LLM_Guide.md` | `e87c01ebff43fb9b21d740c011a5467567f6e553fae423f54754b255ba148eda` |
| `docs/v0.3.0/LATIS_Spec.md` | `a11a6f90dff1f2ff7bf99bbfc4b43cc513007b97b72be87e9229209bc84c0eb3` |
| `latis/__init__.py` | `ca5b6e56cc71d6c8510de41e8e3f61103126255d3c241118e2b9d7f88bba4330` |
| `latis/__main__.py` | `935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d` |
| `latis/cli.py` | `6ee688481fa0c1f9421edcdc7a7fddfebbc563ae40a2ce52cb4bd0cea5f819e3` |
| `latis/engine.py` | `71bb4e2b146255e62aca7590a1971ad9ff8a9d5c9ad434c80e502275640ea398` |
| `latis/model.py` | `f2abc9e0d573397ab9ce07d05fee6f361aedd1679b3f9f12c9d76be94fedc5bb` |
| `latis/projection.py` | `53e63dd8d4cffd0aa15914327657538c3d31bff9e963480be9c633d85647c7c7` |
| `latis/storage.py` | `7399d9144ca7c9785c22b49fea321ae23839d6262a775eb542dd4670983fe75d` |
| `pyproject.toml` | `d3b9b4b696bc2a1a3b9e24dc8ea6e1e80f742aaebe3ad20a67e0527703ad3320` |
| `scripts/__init__.py` | `9202420b6a37d1a75ee74e4847d42f9933f2bef478cf68e1c1f411a889663fe8` |
| `scripts/llm_acceptance.py` | `cff12eca791c9e7e324f7c6a589f0a6327891c97a384e66cf337c31fadc16353` |
| `scripts/rehearse.py` | `d2ec3411018adaa23388ffc3de2f4ad90abc4939c3bf48eddfb95c14f2789492` |
| `scripts/test_support.py` | `e9bfbbd1b251ba1c53afaaf4c506c3429ddf58dd21b342b335f92d0d15c13c35` |
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/fixtures/normalization.json` | `f2740c48b1c616807e8a89c9b1af425659f2d9af6e3c04cd100ba29ce5d28424` |
| `tests/support.py` | `b74c93cba71b85fd6be8737e1ca785ceb86f0f2d345e34b200bca57fd0b75810` |
| `tests/test_contracts.py` | `b91ced1ecd7cb1507ea8b791277401470ce4352ad06451e61bc496b8b7317967` |
| `tests/test_engine.py` | `caec437c9530ca9de342020ff627d629ddd6f932e7be2449f85c0e4772fe16bf` |
| `tests/test_llm_acceptance.py` | `3547bd618b485c16c26da77cb3c8cf1bce89f82280a72464ab63932ff1df7ed8` |
| `tests/test_p1.py` | `aa99f418f3290c28a8c796e4c6c8950ed586e1453486be1fc9197660669b0fc4` |
| `tests/test_rehearsal.py` | `6b7caaccd08df84a3dcc8a1d32ae0821d02ac6fa7399c2a5e937d54166129d77` |
