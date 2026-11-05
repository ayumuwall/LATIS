# LATIS / Agreement Explorer

11/7展示用の読み取り専用ビューア。Python 3.12と標準ライブラリ、ローカルのHTML/CSS/JavaScriptで動く。初期UIはCoreを変更しない読取投影とする。追加指示D-27のプロジェクト名必須化はCoreへも反映し、仕様・規則と保存形式を更新した。外部実行依存は追加していない。

画面は正本SQLiteの一つの読取トランザクションから、Scopeの分類、合意、文脈、原文と判断の履歴を表示する。書込みは既存のLATIS CLIだけで行う。階層は分類であり、合意の優先順位や自動継承を表さない。

## この環境で準備済みの組

2026-11-06の検査後、専用データをGit管理外の`.latis/exhibition/`へ保持した。通常の`.latis/latis.sqlite`は使わない。現在のプロジェクト名はユーザー指定の「ログ管理サービス」。003の組は、名前のない002から名前を指定して明示移行したもの。002の元ファイルと過去の実検査記録は保持している。移行を新しい実行証拠とは扱わない。

| 場所 | 内容 |
| --- | --- |
| `.latis/exhibition/prepared-003/` | 正規CLIで作ったbaseline/final、コードと固定証拠の復元元。上書きしない |
| `.latis/exhibition/live-003/` | 通常24時間・監査90日・UTC追加前の実演開始状態。現在8765番が接続 |
| `.latis/exhibition/replay-003/` | UTC追加・通常48時間への改訂まで実applyを済ませた復旧用。接続してREPLAYできる |

起動する場合はリポジトリ直下で次を使う。すでに8765番が起動中なら、先に下記の停止手順で確認する。

```sh
DEMO_ROOT="$PWD/.latis/exhibition"
python3.12 tools/graph_demo/server.py --db "$DEMO_ROOT/live-003/demo.sqlite" --port 8765
```

URLは`http://127.0.0.1:8765`。準備済みDBも元の素材も架空の展示専用で、実在プロジェクトの合意ではない。現在の実機の受け入れ待ちは`質問事項.md`に記録する。映像収録はユーザー指示により必須範囲から除外し、追加作業は省く。各本文の展示注記は初期登録前に除去し、履歴にも残らない組へ再生成した。

## 展示データの準備

リポジトリ直下でPython 3.12を使う。出力先・復元先は毎回未存在のパスを指定する。以下の既存パスを使い直す場合は、末尾の連番を変える。

```sh
python3.12 tools/graph_demo/prepare.py --output /tmp/latis-explorer-prepared
python3.12 scripts/reset_demo.py \
  --source /tmp/latis-explorer-prepared \
  --destination /tmp/latis-explorer-live-001 \
  --state baseline --format sqlite
```

初期状態は通常ログ24時間・監査ログ90日、13件の架空の合意、Scope階層、理由、未分類・複数所属・候補を含む。義務は「しなければならない」、禁止は「してはならない」で記録する。理由や補足を新しい義務へ自動変換しない。

`prepare.py`は既存の`rehearse.py`・`reset_demo.py`と正規CLIを使い、初期・変更後の実テスト、新しい固定証拠、SQLite/完全JSONのbaseline/finalを作る。これはPythonの既定シナリオであり、実LLMの受け入れではない。元の素材、退避元、過去の証拠は保持する。

`--state final`はUTC合意追加後・通常ログ48時間の状態。`--format json`でも復元できる。DB・コード・テスト・実行ログを一組で戻し、DBだけを差し替えて現物も戻ったと扱わない。

## DBのプロジェクト名

すべての現行DBにproject_nameが必須。新規初期化では名前を指定する。ヘッダーはDBの名前を取得し、58pxの高さを保って表示する。長い名前は省略し、マウスを置くと全文を確認できる。

```sh
./bin/latis --db /tmp/new-project.sqlite init <<'JSON'
{"project_name":"ログ管理サービス"}
JSON
```

SQLiteはuser_version=3、JSONはformat_version=3、仕様は0.3-demo-draft.1、規則はcore-0.3.1。名前のない旧形式2を通常操作やrestoreで黙って開かない。名前を指定したmigrateで新しいDBへ移行する。

```sh
./bin/latis --db /tmp/named-project.sqlite migrate <<'JSON'
{"source":"/absolute/path/old-project.sqlite","format":"sqlite","project_name":"ログ管理サービス"}
JSON
```

JSONの旧snapshotもformat=jsonで移行できる。元ファイル・内部ID・オブジェクトID・版・来歴・commit・成功済み応答を保つ。未成功の旧basisは規則版が変わるため再照合する。名前の変更も、現行DBを入力に同じmigrateで新しい出力先へ移す。既存DBは上書きしない。

## 起動と停止

```sh
python3.12 -m latis --db /tmp/latis-explorer-live-001/demo.sqlite meta <<'JSON'
{}
JSON
python3.12 tools/graph_demo/server.py \
  --db /tmp/latis-explorer-live-001/demo.sqlite \
  --host 127.0.0.1 --port 8765
```

`http://127.0.0.1:8765`を開く。`meta`でspec=`0.3-demo-draft.1`、rules=`core-0.3.1`と9操作を確認する。ViewerとLLMへ同じDBの絶対パスを渡す。サーバーの停止は起動した端末でCtrl+C、再起動は同じコマンドを使う。サーバー起動でDBを初期化しない。

エージェント起動中のiTerm2ウインドウはログ表示専用なので、そこでCtrl+Cしてもサーバー本体は止まらない。`lsof -nP -iTCP:8765 -sTCP:LISTEN`でPID、`ps -p PID -o command=`で専用サーバーとDBパスを確認し、そのPIDだけへ`kill -TERM PID`を送る。ほかのPythonをまとめて停止しない。

エージェントが起動・検査する長いコマンドは、`~/.local/bin/log-window dev`等の返す固定ログへ`FORCE_COLOR=1`付きで出力する。macOSでは`log-window`をアプリ操作可能な権限で実行し、既存ウインドウの再利用は`--keep`を使う。

例としてこの作業のログは`/tmp/agent-logs/github.com-LATIS/{dev,test,e2e,task}.log`。実行のたびに上書きする。API応答のstdoutへ進捗を混ぜない。

## 閲覧操作と状態

- Scopeを折り畳み、検索で本文とタイトルを絞る。同一IDの複数所属は参照行として表示し、合意件数は重複計数しない。
- 合意を選ぶとInspectorへ全文・ID・版・所属・関係・来歴を表示する。過去版には現在の所属や診断を混ぜない。
- 初回は静的に同期する。`NEW`・`REVISED`は実際のapply成功の履歴から判定する。草稿保存、consult、失敗、成功済み再送を新しい採択として演出しない。
- `LIVE`は正本を取得できている状態。切断・ロック・不正応答では最後の正常画面を保持して`DISCONNECTED`とする。復旧は静的同期。
- 別DB・巻戻し・別のsnapshotへの分岐は`RESET`。古い変更を新しいLIVEイベントとして再演しない。
- `CHANGE LOG`は保存されたcommitを開き、同じIDの保存前後の原文・差分・判断、関係のみの変更も読める。過去版を選んだ場合は現在の所属・診断を混ぜない。
- Inspectorの「関係にフォーカス」は、選択した記録に直接接続する実関係だけを表示する。向き・型・候補/確定・有効/終了を併記する。
- オブジェクトIDは合意A、提案P、意図I、理由R、問いQ、範囲S、成果物AR、タスクTの各系列で、1からゼロ埋めなし。作成履歴から導出し、同一commit内はid順。改訂・絞込み・複数所属・REPLAY・完全復元でも同じノードには同じ番号を使う。合意番号による検索は完全一致で、A-1とA-10を区別する。元のid・版は詳細に残す。
- scoped_toのリンクを選ぶと、番号が対応するScopeの見出しを展開・選択してスクロールする。範囲は見出し、合意はその下の行として表示する。
- 各Scopeの「↓ Markdown」で、S-3.md等の1ファイルを直接保存する。Purpose・Requirementsの構成で、合意は「Requirement: A-1 タイトル」、理由・ほかの種類は同じ文書のContextから読める。所属・関係は番号で辿り、元のid・版・関係の対応はHTMLコメントへ保持する。Scopeの直接所属と確認済みの関連理由を対象にし、子Scopeを自動追加しない。表示中の版へ固定し、REPLAY中は過去時点を書き出す。DBは変更しない。

`basis_status=current`は記録された版の一致であり、現物の自動観測や検証の完全性を保証しない。検査結果がないものは未登録と表示する。

## レンダー設定画面の予定

ADR・OpenSpec風の仕様書・説明文など、同じ合意・理由・関係をどの形式で文章化するか、細かく設定できる専用画面を追加予定。今回はデモ用の固定形式。文書構成は[OpenSpec公式のSpec Format](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md#spec-format)を参考にした。HTMLコメントには将来の取り込みに必要な内部IDと元版を保持するが、取り込み機能自体は未実装。

## CLIによる表示確認

本物のLLM実演とは別に、正規CLIによる追加・改訂を再現できる。

```sh
python3.12 tools/graph_demo/scenario.py --work /tmp/latis-explorer-live-001 --action utc
python3.12 tools/graph_demo/scenario.py --work /tmp/latis-explorer-live-001 --action revise
```

UTC合意の追加後、通常ログを同じIDで48時間へ改訂する。後者は作業コピーのコード・テストを更新し、現物のハッシュ、実テスト、新しい証拠と検証関係を記録する。監査ログ90日は維持する。繰り返すときは別の未存在の作業ディレクトリへbaselineを復元する。

## 実履歴のREPLAYと復旧

「履歴を再生」で、接続中のDBに保存された実commitの先頭から読む。画面は常に`REPLAY / 過去の実記録`、右上には対象の版を表示する。再生・停止・前後・版の選択・先頭復帰は閲覧だけで、DBを更新しない。取得に失敗したら最後に取得できた実記録で停止し、遅れて戻るLIVEや過去版の応答を混ぜない。

「LIVEへ戻る」は、**現在接続中のDB**の最新状態を静的に取得する。別のDBへ戻す操作ではない。

LLMの不応答やネット不調で追加・改訂の実演を続けられない場合は、サーバーを停止して`--db "$DEMO_ROOT/replay-003/demo.sqlite"`で起動し直す。ページを再読込して「履歴を再生」を選ぶ。準備済みの復旧用DBではrev 6が通常24時間、rev 7がUTC追加、rev 8が同一IDで48時間へ改訂した記録。合意の古い原文も保存されたままなので、過去の表現を現在の本文として説明しない。

実行中に正本がロックされた場合は、最後の正常表示と取得時刻を保持する。ロックが解消したら自動で静的に同期する。DBが壊れた場合は原本を上書きせず、下記の新規復元先へ切り替える。

```sh
python3.12 scripts/reset_demo.py --source "$DEMO_ROOT/prepared-003" \
  --destination "$DEMO_ROOT/live-003" --state baseline --format sqlite
```

再実演も同じ手順で未存在の連番へ戻す。LLMの作業コピー、Viewerの接続DB、コード・テスト・証拠を同じ組へ切り替える。

## 当日の短い操作手順

1. 新しいbaselineを用意し、`meta`とViewer/LLMの絶対DBパスを確認する。
2. ACT 0では「保持期間」で検索し、通常24時間と監査90日を選んで本文と理由を見せる。複数所属の参照行を別の合意として数えない。
3. ACT 1の前に検索を空に戻す。台本のUTC追加依頼を入力し、実apply後の`NEW`と原文・理由を示す。未実装のUTC合意は検証済みと説明しない。
4. ACT 2で通常ログだけ48時間へ改訂する。Inspectorの実差分とCHANGE LOGの保存前後を開く。監査90日の合意は維持する。コード検証は実行した範囲だけ説明する。
5. ACT 3では前会話を渡さない新セッションで現在値と理由を取得する。時刻はLLM応答時間と、保存後の画面反映時間を分ける。
6. LLMが動かない場合は上記の復旧用DBとREPLAYへ切り替える。終了時は専用サーバーだけを停止する。

外部ディスプレイ・ケーブル・給電・スリープ・来場者距離からの可読性と、担当者による実操作は未確認。ここを済ませるまで展示全体を受け入れ済みにしない。

## Playwrightでの検査環境

ユーザー指定により、内蔵Browserとは独立したPlaywrightを利用できる。Coreの実行環境と分離して準備する。

```sh
python3.12 -m venv /tmp/latis-playwright-env
/tmp/latis-playwright-env/bin/python -m pip --isolated install --no-cache-dir playwright
```

現在の検査はインストール済みChromeを新しい一時プロファイルで起動する。普段のタブや認証情報は使わない。スクリプトはPlaywrightを必要とするものだけ、この専用環境で実行する。CLIとCoreは引き続きPython 3.12・標準ライブラリのみで動く。

実DBでのLIVEと復旧、実履歴の再生を確認するコマンドは次の通り。出力先は毎回未存在にする。

```sh
/tmp/latis-playwright-env/bin/python tools/graph_demo/check_browser.py \
  --source "$DEMO_ROOT/prepared-003" --output /tmp/latis-browser-check
/tmp/latis-playwright-env/bin/python tools/graph_demo/check_playback.py \
  --source "$DEMO_ROOT/prepared-003" --output /tmp/latis-replay-check
```

## 隔離下の実Claude検査

先に`docs/LLM_SANDBOX.ja.md`の拒否試験を通す。隔離できなければ停止し、許可範囲を広げて回避しない。safe-modeだけをファイルシステム隔離と説明しない。

```sh
python3.12 tools/graph_demo/llm_demo.py --output /tmp/latis-explorer-llm \
  --stage prepare --source /tmp/latis-explorer-prepared
python3.12 tools/graph_demo/llm_demo.py --output /tmp/latis-explorer-llm --stage utc
```

既存の`llm_acceptance.py`で`claude -p --safe-mode --restricted --model claude-opus-5-5 --effort high`を起動し、Guide・API・CLI・DB・作業場所を明示する。操作と応答を逐次表示する。LLMのAPIを直接呼ばない。

A-1等の正式名称は「オブジェクトID」。通常の利用では基本的にオブジェクトIDを使う。実行中は同じDBから`workspace/latis-display-numbers.json`を原子的に更新し、オブジェクトID・名称・内部ID・現在版とDB/snapshotをLLMへ共有する。本文や理由は対応表へ複製せず、CLIで取得する。書込み後にもLLMが対応表とmetaを照合する。

人向けログはオブジェクトID・名称と対象の第何版かで表示する。関係は端点のオブジェクトID・種別・向きで示す。これは表示用であり、そのまま再実行できるコマンドではない。実コマンドと応答は`*-events.json`・`calls.jsonl`へ元の内部ID・版を保って保存する。DB・履歴の差替えや読取失敗で対応が未確認なら、古い対応を使わず未確認と明示する。Coreの直接入力は現在も内部IDを必要とする。

**既定では収録を起動しない。** 画面で見る場合は、準備後にViewerを`/tmp/latis-explorer-llm/live/workspace/demo.sqlite`へ接続する。現在の`live-003`と試験用の作業コピーを取り違えない。以前の検査に使った任意の`--capture`と収録補助は保持しているが、今回の必須範囲から外す。

各段階で実応答・操作・DB・ブラウザー記録をレビューし、`live/utc-semantic-review.json`、次に`live/change-semantic-review.json`へ`passed`（boolean）・`reviewer`・`notes`を残す。機械検査だけで意味レビューを合格にしない。

```sh
python3.12 tools/graph_demo/llm_demo.py --output /tmp/latis-explorer-llm --stage change
python3.12 tools/graph_demo/llm_demo.py --output /tmp/latis-explorer-llm --stage handover
```

handoverは前会話・要求JSONを渡さない独立セッション。モデルの指定値と実際の返却モデル、CLI記録と全snapshotを保存する。収録を省いた場合も、未取得の画面記録を取得済みとは扱わない。

## 検証記録と残作業

完了判定は`docs/TASKS.ja.md`と`docs/GRAPH_DEMO_VERIFICATION.ja.md`に記録する。外部ディスプレイの実機確認・来場者の距離からの可読性は、ブラウザーの画面寸法検査とは別。未確認の機材や当日作業は`質問事項.md`へ残す。
