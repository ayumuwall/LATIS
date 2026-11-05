# LATIS Agreement Explorer — 2026-11-06 改訂内容

このZIPは、11月7日の展示に向けた**展示用UI**の計画文書3点をまとめたもの。LATIS Coreの規範仕様を置き換えない。

## 同梱文書（読む順）

1. `LATIS_Graph_UI_Visual_Design_2026-11-06.md` — 添付PDFを参考にしたデザインの新しい基準。
2. `LATIS_Graph_UI_Implementation_Plan_v2_2026-11-06.md` — 現行Coreへ接続する技術計画とP0/P1タスク。
3. `LATIS_Graph_UI_Demo_Scenario_v2_2026-11-06.md` — 通常の自然言語入力から追加・改訂・引き継ぎを見せる当日台本。

参照資料：ユーザー提供 `LATIS_Graph_Pulse_Design_2026-11-06.pdf` のp.2〜5。PDFの画面をそのまま実装するための計画ではない。

## 前版からの主要な変更

- 画面名を**`LATIS / Agreement Explorer`**へ統一し、仮称`GRAPH PULSE`の採用をやめる。
- 藍色・ネオン・多色のノード分類・放射状ネットワークを廃止。**紙色・黒・グレー、罫線、文字、白黒反転**を基調にする。
- **`Scope → Agreement → Rationale/Question/Artifact`の固定3列**と明瞭な階層リストを中心にする。関係の意味と画面上の親子表現を混同しない。
- 追加は**行が増える**、改訂は**同じIDの行で24時間→48時間の差分**。監査ログ90日は不変。
- PDFの一色シグナルは**任意**。使う場合は実`apply`の成功確認後だけ、短時間表示。`save-draft`でも`graph_revision`が増えるため、revision増分だけで確定表示しない。
- LIVE／REPLAY／RECORDED／DISCONNECTEDを明瞭に区別し、録画や過去記録をライブに見せない。
- **既存Coreの契約は変更しない**。SQLiteからread-only投影を構築し、通常のCLIで確定したデータだけを展示する。
- 展示までの必須範囲を階層・検索・Inspector・実更新・復元へ絞り、装飾アニメーションとREPLAYの追加実装はP1とする。

## 実装の着手点

`AGENTS.md`、`docs/v0.3.0/LATIS_Spec.md`、`docs/v0.3.0/LATIS_API.md`を規範として確認したうえで、`tools/graph_demo/server.py`のread-only取得、投影、階層ブラウザの順に着手。詳しい受け入れ条件は実装計画のG-01〜G-14。

**注意：** 文書とビジュアル方向を改訂したものであり、Graph Viewerの実装完了を意味しない。
