# 展示用の入力素材

このディレクトリはv0.3-demo-draftを実装・実演するための架空のサンプルであり、LATISエンジンの実装ではない。

## ファイル

| ファイル | 役割 |
| --- | --- |
| [seed_consult.request.json](seed_consult.request.json) | 空の展示DBへ初期設定を登録するための、通常のconsult要求 |
| [search_logs.request.json](search_logs.request.json) | 採択済み合意を日本語の部分一致で探す要求 |
| [demo_project/retention.py](demo_project/retention.py) | 通常ログ24時間、監査ログ90日の初期アプリ素材 |
| [demo_project/test_retention.py](demo_project/test_retention.py) | 初期設定と不明な種類の拒否を確認する実行可能なテスト素材 |

全ての保持期間は説明用の架空値であり、実在プロジェクトの規則として採択しない。展示には新しい専用DBを使う。

## 初期状態の準備

1. LATISの実装が9操作を提供してから、元のdemo_projectを新しい実演用の作業場所へコピーする。通常ログ24時間・監査ログ2160時間のコードとテストを使い、前回の48時間への変更を残さない。元の素材は保存しておく。
2. その作業ディレクトリへ移動し、使用するDBパスを指定して新しい展示用DBへinitする。以後も同じDBパスを使う。seed内のfile:retention.pyとfile:test_retention.pyはこの作業場所を基準にした参照であり、その場所を準備記録へ残す。LATISは自動的にファイルを開かない。
3. 呼出元が実バイトのSHA-256を計算し、seedの2 artifactのcontent_hashと照合する。不一致なら、まずコード・テストを元の初期素材へ戻す。意図的に別の初期素材を使う場合は、seedの合意内容とコード・テストの対応を確認してからハッシュも更新する。ハッシュだけを合わせて初期状態や検証成功を偽らない。
4. seed_consult.request.jsonを通常のconsultへ渡す。返されたnormalized_requestとbasisに、架空の展示設定を初期登録する設営上の指示・理由・実行者と、新しいidempotency_keyを添え、通常のapplyへ渡す。
5. 応答のcreated_refsを使ってノードIDと版を記録する。seed内の$local_refは実IDではない。
6. 実際にテストを実行する。demo_projectを作業ディレクトリとして `python -m unittest -v` を使える。
7. 実行したアプリとテストのartifactの版、方法、実際の結果、時刻を使い、新しい結果artifactをsave-draftする。固定したsubject_refsにはアプリとテストの両方を含める。
8. 結果がpassedの場合だけ、その結果を根拠に通常ログ・監査ログのverified_byをconsult/applyで確認する。失敗をpassedへ置き換えない。初期状態をbackupする。

seedは既に採択済みのDB dumpではない。SQLの直接投入や採択を迂回するimportを要求しない。設定の具体値・既存の確認結果を再利用する場合も、架空データであることを保つ。

## 24時間から48時間へ変更する実演

1. ユーザーの曖昧な「ログを48時間にして」という依頼を受け、通常ログと監査ログの既存合意を探索する。
2. 対象範囲が未決なら、どのログを変えるかだけを確認する。最初から「通常ログだけ48時間、監査は変更しない」と指示されていれば同じ確認は不要。
3. 通常ログの合意本文だけを、同じIDの新しい版としてconsult/applyで改訂する。
4. 通常ログのコードとテスト期待値を48時間に変更する。監査ログ2160時間の期待値を保持する。
5. 呼出元がアプリとテストの実物を観測し、通常artifactのcontent_hashをsave-draftで更新する。古い検証関係のbasis_statusはchangedになる。
6. 実テストを実行し、新しい結果artifactを保存する。古い結果のsubject_refsを編集したり、旧結果をreconfirmで新しいコードへ付け替えたりしない。
7. 新しいpassed結果へverified_byを結び、不要になった旧確認関係を通常のconsult/applyで終了する。共有コード・テストに対する監査ログの確認も更新し、その合意本文は維持する。
8. 会話履歴を共有しない別のセッションが、現在の合意と根拠をLATISから再取得する。

入力ファイルが実行中に変わった場合は、どの版を検査したか確定するまで結果を現在の成功根拠へ使わない。実行前後のハッシュ比較や固定した作業コピー等は呼出元の観測手順で行う。

完全なデモ運用、復元、ネットワーク障害時の扱いは[LATIS_Demo_Guide.md](../LATIS_Demo_Guide.md)を参照する。ここにあるコードのテストが通っても、LATIS本体の受け入れケースが通ったことにはならない。
