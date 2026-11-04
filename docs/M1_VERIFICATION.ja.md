# M1 コア仕様の検証記録

M1では現行Spec/APIのP0コア契約を照合し、仕様との差分を修正した。[仕様対応表](SPEC_COVERAGE.ja.md) に条項・実装・回帰テスト・残るLLM利用確認をまとめた。

## 対象と環境

- 基準コミット：`3b52bebdee3d73a1a9afb102d5a933b9dec1f5f1`。M1の修正後のソースは下表のSHA-256で識別する。
- 記録時刻：`2026-11-04T14:17:34.180924Z`。
- Python：`3.12.0`、Unicode：`15.0.0`、SQLite：`3.43.2`。
- OS：`macOS-15.8.1-x86_64-i386-64bit`。
- 契約：`spec_version=0.3-demo-draft`、`rules_version=core-0.3.0`、`format_version=2`。新しい操作・保存フィールドは追加していない。

## 実行結果

| 検証 | 結果 | 内容 |
| --- | --- | --- |
| `FORCE_COLOR=1 python3 -m unittest discover -v` | 合格、75件、21.454秒 | 既存42件とM1の契約テスト33件。状態・関係・入力境界・変更検知・再試行・復元と実CLIの再現を含む |
| 実CLIの既定シナリオ | 合格 | 上記テスト内で通常ログ24→48時間、監査ログ90日維持、現物のハッシュ、実テスト各3件、新旧証拠、退避・復元、新しいプロセスでの再取得を確認 |
| 構文・wheel構築・一時仮想環境への導入 | 合格 | インストールしたCLIのinit/meta/consult、正規化fixtureとの一致、同梱Guideを確認 |
| `git diff --check` | 合格 | 差分の空白・改行を確認 |

`test_contracts.py` の各メソッドは複数の型・状態・境界値を含むため、メソッド数を要件の網羅率としては使わない。対応する条項と実際のassertionは仕様対応表とソースから辿る。

生ログは `/tmp/agent-logs/github.com-LATIS/test.log` と `/tmp/agent-logs/github.com-LATIS/build.log` に保存。固定名で再実行時に上書きされるので、この記録では実行結果と対象ソースの識別情報を保持する。

## M1で確認した差分

- 新規evidenceを追加根拠にした照合でもsubjectを監視する。100件のsubjectを含む場合も表示件数でbasisを縮めない。
- 個別版の不一致を変更範囲の検査より先に返す。Scope内の保存済み競合と、明示参照した終了済み判断の古い根拠を診断する。
- 仮IDと既存の不透明IDの衝突を避け、草稿終了時の新規confirmed所属による保存制限の迂回を防ぐ。
- CLIと復元のJSON読取を共通化し、重複キー・不正なUnicode・深すぎる構造を拒否する。UTC時刻の表記と原文を保持する。
- 復元時に版の型、来歴とdecision、変更計画、基準時点の参照版、成功応答の作成・更新分類を照合する。正しい過去の証拠や、個々の記録時刻が異なるsnapshotは維持する。

## 後続へ引き継ぐ確認

LLM利用テストは実施していない。M3で `claude -p --safe-mode` を使い、自発的な探索、未解決の選択の打診、既存授権の再利用、独立したセッションへの引き継ぎを確認する。LLMのAPIは直接呼ばない。

P1は未実装で、対応するcapabilityは告知しない。M2で子孫Scope検索とMarkdown投影を実装する。ホストされたCI、より広い障害・環境の検証、最終的な完全実装の判定はM4〜M5へ引き継ぐ。

## 対象ソースのSHA256

下表をパス順に並べたJSON配列のSHA-256：`0fa90e7f394cdf61929c5d82d982409a4e63bcd230126f44aadc7a898602510a`。各要素は `path` と `sha256` を持ち、UTF-8・キー昇順・空白なしでシリアライズした値を使う。

| ファイル | SHA-256 |
| --- | --- |
| `bin/latis` | `10dd8ab3b7ba5670ae54b013cd0a5c5d7c06ff68e5d38bebbff2134872844b8b` |
| `docs/v0.3.0/LATIS_API.md` | `cdf56e9e8b6e0808a5ae2971a72601a7cd83d046a5688e7d6dadaed15c08831c` |
| `docs/v0.3.0/LATIS_Spec.md` | `a11a6f90dff1f2ff7bf99bbfc4b43cc513007b97b72be87e9229209bc84c0eb3` |
| `latis/__init__.py` | `ca5b6e56cc71d6c8510de41e8e3f61103126255d3c241118e2b9d7f88bba4330` |
| `latis/__main__.py` | `935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d` |
| `latis/cli.py` | `6ee688481fa0c1f9421edcdc7a7fddfebbc563ae40a2ce52cb4bd0cea5f819e3` |
| `latis/engine.py` | `f7c92a5b1e6797570f3edd26767681502152c029c66b11f076b4fedf0db038a0` |
| `latis/model.py` | `aceeb0525107ef3bdfcb8397a368c3d41261033fd423a3fd3ba8c5d3c39ed776` |
| `latis/storage.py` | `047dc8a6732a7bcd3748262a0a6f1ec681ec63e334a683891e64f27042b3caf6` |
| `pyproject.toml` | `d3b9b4b696bc2a1a3b9e24dc8ea6e1e80f742aaebe3ad20a67e0527703ad3320` |
| `scripts/rehearse.py` | `7645f9681019eaeb2167b2b77580a5918b96c6984b8e8b63f8318899e8a74890` |
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/fixtures/normalization.json` | `f2740c48b1c616807e8a89c9b1af425659f2d9af6e3c04cd100ba29ce5d28424` |
| `tests/support.py` | `b74c93cba71b85fd6be8737e1ca785ceb86f0f2d345e34b200bca57fd0b75810` |
| `tests/test_contracts.py` | `46966290ee731f4297467fe520ece02ac9329e59828a55167372b5d2d07fc598` |
| `tests/test_engine.py` | `f9aeb1d91e9068df03d8603a9049c1e4b9f21bc0c264e3e5916786b3d69991f9` |
| `tests/test_rehearsal.py` | `0e630917836ac62d095f0703156f9ccfa9a7ca73927540a2754800a8e15ee443` |
