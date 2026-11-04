# LATIS

**Layered Agreement, Traceability & Intent System**  
**An Agreement Engine.**

- 版：v0.3-demo-draft
- 更新日：2026-11-04（日本時間）
- 対象：2026-11-07の展示に向けた実装仕様。
- 状況：P0とP1の参照実装、Claude CLIでの利用確認が進んでいます。現行仕様の完全実装・性能達成の最終判定は未完了です。現在の導入手順はソースリポジトリの [実装ガイド](https://github.com/ayumuwall/LATIS/blob/main/docs/IMPLEMENTATION.ja.md)、確認結果は [受け入れ記録](https://github.com/ayumuwall/LATIS/blob/main/docs/ACCEPTANCE.ja.md)、残作業は [タスク管理票](https://github.com/ayumuwall/LATIS/blob/main/docs/TASKS.ja.md) を参照してください。
- [English](README.md)

## 何をつくるか

LATISは、LLMが必要なときに合意を探し、要求を既存の決定と照合し、変更と根拠を記録するための合意エンジンです。
個人や組織が開発を続け、使うLLMやセッションが変わっても、何を決め、何を確認したかへ戻れることを目指します。
ユーザーは通常の言葉で依頼し、LLMがGitなどの道具と同様に利用を判断します。人間のCLI操作や、全作業共通の事前照会を要求しません。

本文は自然言語のまま保持し、ID、版、状態、明示関係、出所、判断の履歴を構造として扱います。
意味の解釈は呼出元LLMが担い、既存の指示では決まらない選択だけをユーザーへ確認します。

## 9ファイルの案内と読む順番

| 文書 | 役割 |
| --- | --- |
| [README.ja.md](README.ja.md) | 日本語の入口、対象範囲、文書の優先関係。 |
| [README.md](README.md) | 同じ内容の英語版。 |
| [LATIS_Spec.md](LATIS_Spec.md) | 中核モデル、意味、保証と責任の境界。 |
| [LATIS_API.md](LATIS_API.md) | JSON、CLI、照合・反映、失敗と再試行の具体契約。 |
| [LATIS_Operation.md](LATIS_Operation.md) | 日常の検索、記録、折衝、整理、外部成果物の観測。 |
| [LATIS_LLM_Guide.md](LATIS_LLM_Guide.md) | LLMが読み、必要時の利用と反復探索を進める手引き。 |
| [LATIS_Prototype_Plan.md](LATIS_Prototype_Plan.md) | 11/4〜11/7の実装順、必須・任意の範囲、受け入れケース。 |
| [LATIS_Design_Decisions.md](LATIS_Design_Decisions.md) | 旧提案の採否、今回の判断理由、展示後の検討条件。 |
| [LATIS_Demo_Guide.md](LATIS_Demo_Guide.md) | 展示シナリオ、準備、リハーサル、当日の起動と代替手順。 |

実装者はSpec → API → Prototype Planを読み、OperationとLLM Guideで利用の流れを確認してください。
利用するLLMはLLM Guideから入り、必要な操作のAPI契約を参照します。展示担当者はDemo Guideから準備を始めます。
Design Decisionsは判断理由を調べる文書です。LLM Guideは展示後も保守する製品の一部です。

**本版のSpecとAPIを規範とします。** 意味・保証はSpec、フィールド・操作・エラーはAPIが正本です。
Operation／LLM Guideはその使い方、Plan／Demo Guideは実装と検証、READMEは概要を説明します。
矛盾が見つかった場合は規範文書を整合させ、概要や例を根拠に検査を省略しません。
旧v0.2、添付の未採択v0.3改訂案、過去の検討資料を、本版と並列の仕様として混ぜません。

## 基本の利用

1. 必要に応じて検索し、用語・Scope・明示関係を手掛かりに追加探索します。
2. 既存の合意と要求を照合します。指示で扱いが決まらない食い違いがあれば、根拠と選択肢をユーザーへ示します。
3. 決まった変更をconsultし、applyで前提の再検査と更新を原子的に行います。
4. 理由、実行者、指示の参照、対象版を履歴に残し、次のセッションでも再利用します。
5. 実装を確認する場面では、外部成果物を観測し、実際の検査結果を記録して合意へ結び付けます。

すでに得た許可を、記録だけのために取り直しません。版の変化に伴う再照合も、新しい意味上の選択がなければLLMが進めます。
未分類・重複・未解決事項が残っていても使い始め、今回必要な範囲から整理します。構造不正や部分更新は別に防ぎます。
一度の検索の完全性や固定回数を要求しません。「2〜3回」「95%」は説明上の例であり、採択条件や達成値ではありません。
Scopeの階層、局所性、priority値から合意の勝者を決める規則は採用しません。

DecisionRAG等の推論検索は、将来組み合わせる候補探索の方法として扱います。合意・版・履歴の正本と、作り直せる検索用階層・索引を分け、候補から原文へ戻れる境界をSpec §8.4とDesign Decisions §10に追記しました。今回の9操作や展示の必須範囲は増やしていません。

## 展示に必要な中核

P0は、正しく動く9操作、判断と履歴、外部成果物と検査証拠の記録です。
日常操作はmeta、search、detail、relation-detail、relations、history、save-draft、consult、applyです。
初期化と退避・移送のためにinit、backup、JSON export、restoreも用意します。

SQLiteに正本の記録と履歴を保存し、JSONを標準入力で受け、応答を標準出力へ返すCLIを初期経路とします。
HTTPメソッド・パスは操作契約の表記です。常駐HTTPサーバーや専用UIは必要ありません。
参照実装にはPython 3.11以上と標準ライブラリのsqlite3を推奨します。保存形式と操作契約は言語から独立しています。
展示用の小規模データでは、正規化した文字列の走査で日本語2文字の部分一致を確保できます。FTSは任意の実装手段です。

## 何を検証したかを残す

通常のartifactは、外部ファイル等のlocatorと呼出元が計算したcontent_hashを保持できます。コアは参照先を取得しません。
検査証拠は、対象版、方法、結果、観測日時、実行者を持つartifactです。再実行や訂正では新しい証拠を作り、過去の結果を残します。
confirmedのverified_byにはpassedの証拠が必要で、アプリだけでなく、その検査が参照したテスト等の版も確認対象に含めます。

currentは記録した参照版の一致を意味します。未観測の実ファイル変更、未知の依存、意味の正しさまでは保証しません。
失敗した検査や版の変化があっても、合意そのものを自動失効させません。実行者・主体の参照・モデル情報も、認証や同意の証明にはなりません。

## 任意機能と展示後の範囲

P1は子孫Scope検索（search_descendants）と読み取り専用Markdown投影（markdown_export）です。
metaで利用可能なcapabilityを確認し、未対応なら通常の追加検索とCLI応答を使います。Markdownを編集しても正本は変わりません。
独立したdrift操作、権限エンジン・partyノード、ハッシュ由来の版ID、redaction、拡張語彙、時間評価、hybrid検索、Scope epoch、Markdown import、旧形式の自動移行は今回の範囲外です。
20万合意のベンチマークは展示後に行う目標であり、現時点では未測定・未達成です。展示の合格条件にはしません。

## 11/7までの進め方

以下は予定であり、完了の報告ではありません。

| 日付（日本時間） | 到達点 |
| --- | --- |
| 11/4 | 記録・検索とLLM Guideを動かし、草稿データでLLMの実利用を始める。 |
| 11/5 | consult／apply／historyを通し、根拠付きの採択と変更を確認する。 |
| 11/6 | 外部成果物・検査証拠、別セッションでの再利用、退避・復元を通し、リハーサル後に機能を凍結する。 |
| 11/7 | 検証済み構成を起動し、既存シナリオを確認して展示する。 |

展示素材は通常ログ24時間→48時間の変更と、別合意である監査ログ90日（2160時間）です。期間は説明用の架空設定です。
[retention.py](examples/demo_project/retention.py)、[test_retention.py](examples/demo_project/test_retention.py)、[seed_consult.request.json](examples/seed_consult.request.json)を使用します。
これらは展示用アプリ・テスト・要求例であり、LATIS本体の実装ではありません。具体的な手順と合格条件はDemo GuideとPrototype Planを参照してください。
