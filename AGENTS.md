# AGENTS.md — sakurazaka46-live-event-calendar

## 対象範囲

このワークスペースでは、櫻坂46ライブ・イベント・チケット予定を整理した静的カレンダー `index.html` を保守する。日本語中心の repo なので、説明・運用メモ・コミットメッセージは日本語優先にする。

## 正とするファイル

- 入力: `summary/sakurazaka46_live_summary.md`（live）、`summary/sakurazaka46_event_summary.md`（event/CD/ミーグリ/リアルミーグリ）
- 生成器: `scripts/render_live_calendar.py`
- 公開出力: `index.html`、`ics/sakurazaka46_all.ics`、`ics/sakurazaka46_deadlines.ics`
- 生成補助: `scripts/calendar_rules.json`、`scripts/sakurazaka_schedule_workflow.md`、`scripts/holidays_template.json`、`scripts/sakurazaka46_members_template.json`
- `summary/` と `.plan/` は別用途。`.plan/` は公開カレンダー生成入力に使わない。
- `index.html` は生成物。直接手編集せず、入力Markdownか生成器を直して再生成する。

## 現在のページ仕様

- `index.html` は単一のスタンドアロンHTMLとして公開する。外部アセットに依存しない。
- 表示モードは `live` / `event` / `all` / `plan` / `next14`、タブ表示名は `LIVE` / `EVENT` / `ALL` / `PLAN` / `直近2週間`。デフォルト表示は `next14`（直近2週間）。
- URL状態は `?mode=live` / `?mode=event` / `?mode=all` / `?mode=plan` / `?mode=next14` を使う。
- 全タブのページ見出しとHTML `<title>` は `櫻坂46 カレンダー` に統一する。
- `all` は解析済みの live/event 生成結果から作る。HTML手編集で統合しない。
- `all` は live/event の最初の月から最後の月まで連続表示する。途中の空月も残す。
- `all` の凡例は高レベル分類（`開催` / `応募` / `締切` / `祝日`）だけ残し、旧式の分類行（例: `内容分類: 開催`）は表示しない。
- `all` の日付セルチップは live/event タブ内の文言をそのまま統合表示し、統一名への要約表示はしない。
- `all` チップの重複は同一ラベル内だけ畳む。例: 同じ応募チップが複数あれば1つに畳むが、異なるlive/event由来の文言はそれぞれ表示する。
- `all` の日付詳細は live/event の元詳細データを保持し、チップを要約してもクリック時の詳細は失わない。
- `PLAN` は既存の参加できる可能性がある予定（ミーグリ、ミーグリ(全国)、ライブ開催、他イベント参加）を、`ALL` と同じ月カレンダー様式で表示する。公開ページには個人用予定を埋め込まず、`input type=file` で選択したJSONだけをブラウザ内で読み込み、参加予定の日をカレンダー上で背景強調する。JSON未読み込みでもイベント日をクリックすると、その日を新規参加メモとして編集・ダウンロードできるが、クリックだけでは参加扱いにせず初期値は不参加にする。既存JSONに同日アイテムがある場合、セルクリックでチップ短縮名（例: `ミーグリ` / `バックスライブ` / `ミニライブ`）を別アイテムとして自動追加しない。参加日マークは右上の小さな `参加` 表示にし、セル中央を大きく覆わない。日付詳細タイトルはPLANでは表示せず、編集欄下の展開ボタンで詳細本文を開ける。参加メモは詳細本文より前に置き、同じ日のイベントごとに別カードでチェックボックスの `参加` / `不参加` を切り替える。通常イベントはメモ欄、ミーグリ/ミーグリ(全国)/リアルミーグリはメンバー別入力にし、`＋ メンバー追加` で1人ずつ追加する。ミーグリ(全国)は1枚で2人と話せる枠があるため、PLAN追加時はメンバー1/メンバー2の2人入力を出す。メンバー候補は櫻坂46公式メンバー一覧から作った `scripts/sakurazaka46_members_template.json` を生成時に読み込む。ミーグリ系のJSON編集モードは `1:3,2:5` のような簡易入力で、`表示を確定` に切り替えるとカレンダーセル内で `1部3枚・2部5枚` のように表示し、`編集に戻る` で簡易入力に戻れる。PLANの凡例は `開催` / `祝日` だけ表示し、祝日も `祝` チップとしてカレンダーに出す。保存JSONは `items` 配列で、`date` / `event` / `attending` と、通常イベントは `memo`、ミーグリ系は `members: [{name, slots}]` を持つ。PLANの参加メモ欄には作成方法として、1) 日付セルから手入力、2) `Upload JSON/HTML` で保存済みJSONまたはforTUNE music（フォーチュンミュージック）の申込/抽選結果ページをHTML保存して読み込む方法を示す。読み込み・変換はブラウザ内だけで行い、ファイルを外部送信しない旨と、表示確定後にユーザー自身で内容確認する旨を注記する。`Upload JSON/HTML` は `multiple` を付け、Ctrl/⌘選択した複数JSON/HTMLを追加・マージする。forTUNE HTMLは日付見出しごとに複数日を抽出し、同一メンバー・同一部の枚数は合算する。HTML変換はブラウザ内のUploadでもでき、CLI用に `scripts/fortune_meet_html_to_plan_json.py` も置く。操作ボタンは `Upload JSON/HTML` / `表示を確定` / `Save Page` / `Save JSON` の一列で、`表示確定` モードではボタン下に参加予定リストを出す。`Save JSON` は対応ブラウザで保存先を指定でき、カレンダー外の日付も含めて保存する。カレンダー外の日付はステータスに `カレンダー外 n件` と表示する。`Save Page` は表示確定状態のPLANページだけを保存し、カレンダー外の日付は除外し、他タブ、モード切替、`参加メモ` フレーム、編集UI、スクリプト、日付詳細パネルは含めない。PLANでは抽選・応募・締切系の詳細を除くが、`EVENT:` / `LIVE:` の開催詳細はタイトルに `発売記念` などが含まれても残す。月下部の候補予定一覧・応募/締切情報の折りたたみは表示しない。
- `直近2週間` はブラウザJSで Asia/Tokyo 基準の今日を取得し、今日を含む14日分を1日1行で表示する。予定なしの日も1行出す。
- `直近2週間` は all要約ではなく live/event の元チップ文言・色を使い、祝日チップは表示しない。行クリックでその日の詳細を行下に展開する。
- 祝日だけの日はクリック対象・詳細を作らない。祝日はセル内で `祝` のみ表示し、詳細欄に祝日名説明を出さない。
- 曜日行の土日は赤文字にし、土日・祝日の日付数字も赤文字にする。セル内のチップ文言や `祝` チップ色はこの指定で変えない。カレンダー内の日付数字とチップ文言はPC/スマホとも中央揃えにする。
- 通常生成では購読用ICSも `ics/` に出力する。`sakurazaka46_all.ics` はlive/event統合の全部入り、`sakurazaka46_deadlines.ics` はlive/event両方の締切・期限・販売終了・開催予定だけを入れる。`index.html` にはICS購読リンクをまだ置かない。

## データ入力ルール

- 予定は該当する入力Markdownに `##` 見出し単位で追加する。
  - live: `summary/sakurazaka46_live_summary.md`、基本形は `### ライブ公演の日程` / `### 抽選の日程` / `### 公式ソース`。
  - event/CD/ミーグリ/リアルミーグリ: `summary/sakurazaka46_event_summary.md`、基本形は `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース`。
- live 日程は曜日付きにする。
- 連番日は1行でまとめ、同月範囲は短く書く。
- 抽選情報は時間・祝日を省く。
- カレンダータグは日本語にする。
- 公式URLは `### 公式ソース` に置く。外部公式・主催者・Fortune Music・SPICE/eplus なども許容する。
- 公式情報を整理するときは、出典URL、日付、曜日、会場、応募期間、対象イベントを分けて抽出し、必要なら Python `datetime` で曜日を検算する。
- 櫻坂のリアルミーグリは、CD封入シリアル応募ならCD系イベントとして扱う。
- リアルミーグリ等の詳細確認は、公式本体より Fortune Music を優先する。

## live/event の表示ルール

- Fortune Music などの「支払い方法選択期限」は応募側の締切として扱うが、チップ文言は `ミーグリ応募締切` ではなく `支払い方法選択期限` と表示する。
- event側の開催チップは、liveチップと同じ薄いピンクの開催色を使う。
- event側の応募・抽選の開始/期間中チップは青のままにする。
- event側の応募・抽選の締切チップは赤の締切色を使う。
- live凡例は `開催` / `抽選` / `締切` / `祝日`、event凡例は `開催` / `応募` / `締切` / `祝日` に統一する。
- 長いCD/シリアル応募期間は、表示範囲に含まれる端点だけを表示し、中間日を全て埋めない。
- メッセージキャンペーン期間は応募側の項目として扱い、event開催扱いにしない。
- `一般発売` は抽選開始として扱わない。`一般発売` / `一般発売中` / `販売終了` として扱う。
- `オフィシャル先着受付` など主催者側の先着販売は、抽選ではなく販売として扱う。
- live抽選期間の中間日は `中` を使う。`継続` は使わない。
- 四期生 LIVE は `四期生ライブ` / `四期生ライブ抽選` を使う。
- BACKS LIVE は `バックスライブ` を使う。
- 全国アリーナツアー / 全国ツアーのlive日は `静岡公演`、`神戸公演`、`広島公演`、`千葉公演`、`宮城公演`、`香川公演` のように `地名+公演` にする。
- シングル特典のミニライブ視聴用IDは、開催日だけをlive入力に置き `ミニライブ` と表示する。応募締切はevent入力に置き `ミニライブ応募締切` と表示する。
- CD封入シリアル由来のオンラインミーグリは、基本表記を `オンラインミーグリ(全国)` とし、カレンダーでは開催を `ミーグリ(全国)` と表示する。リアルミーグリ/オンラインミーグリ(全国)は応募スケジュールが同じ場合、応募チップを `ミーグリ(シリアルコード)応募開始` / `ミーグリ(シリアルコード)応募中` / `ミーグリ(シリアルコード)応募締切` に統合する。forTUNE musicで購入する通常オンラインミーグリの応募チップは `ミーグリ応募開始` / `ミーグリ応募中` / `ミーグリ応募締切` のまま区別する。リアルミーグリの開催チップは `リアルミーグリ` とし、`リアルミーグリ(CD)` とは表示しない。

## UI / 操作ルール

- 月見出しは太く出しすぎず、やや小さめ・軽めのモダンな日本語フォント感にする。日付詳細欄の初期注釈（例: `日付をタップすると詳細を表示`）は表示しない。
- 共有HTMLはミニマルに保ち、依頼なしにデザインを大きく変えない。
- モード切替は各 `h1` 直下に置き、固定バーやグローバルバーにしない。
- 実行時のDOM検索は現在の `.calendar-view` 内に限定し、live/event/all の重複IDによる干渉を避ける。
- クリック可能な日付セルはリンク型セル（`<a class='day-cell clickable' ...>`）を維持し、クリック後はPC/スマホとも同じ月カード内の詳細欄へsmooth scrollする。
- 月単位の情報欄は、クリック日の詳細欄の下に初期表示する。必要なら折りたたみ `details` を使う。
- 同じ月カード内で開く日付詳細は最大1つ。明示されない限り、他の月カードの詳細は自動で閉じない。
- モバイル用のchip表示は既存の狭幅ブレークポイントで行い、デスクトップ表示を一律短縮しない。スマホでは最大2行にし、長い文言は中央付近で分けて行ごとの文字数をできるだけ均等にする。
- iPhone/Safari系のタップ反応が悪化した場合は、重いpointerハックを増やす前に、既存のhash / `:target` / スコープ済みJSの方針で直す。

## コマンド

基本コマンド:

```bash
python3 -m pytest tests/test_render_live_calendar.py -q
python3 scripts/render_live_calendar.py
python3 scripts/render_live_calendar.py --refresh-holidays
python3 scripts/render_live_calendar.py --output-calendar-md
python3 scripts/render_live_calendar.py --output-preview
```

- 1行目: テスト。
- 2行目: 通常再生成（`index.html` と `ics/*.ics` を出力）。
- 3行目: 内閣府CSVから祝日を更新する必要があるときだけ実行。
- 4〜5行目: 任意出力。通常実行で復活させない。
- このワークスペースでは `python3` をそのまま使える。repo内に有効化すべき `venv/` はない。

## 検証チェックリスト

- 上記のテストが通る。
- 生成器や出力に関わる変更では、通常再生成が成功する。
- `index.html` と `scripts/sakurazaka_schedule_workflow.md` は、意図したときだけ再生成される。
- all-mode変更では、仕様確認と重ねてブラウザまたはDOMで以下を確認する:
  - `?mode=live`、`?mode=event`、`?mode=all` が正しく切り替わる。
  - 表示中の見出しが `櫻坂46 カレンダー`。
  - all mode に `内容分類:` 行がない。
  - all-modeチップの色が仕様どおり（開催=ピンク、応募/抽選=青、締切=赤）。
  - all-modeの日付クリックで元のlive/event詳細が統合表示される。
  - JavaScriptコンソールにエラーがない。
- ローカルブラウザ確認で `127.0.0.1:9333` のCDPが起動していない場合は以下で起動する:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9333 --user-data-dir="/Users/mistralyu/Library/Application Support/Chrome-Hermes"
```

その後、`file://.../index.html?mode=all&verify=<cache-buster>` を開く。

## リポジトリ管理

- `sakurazaka46-live-event-calendar` は原則 `main` に直接pushする。
- 公開repoは `index.html`、`ics/`、`summary/`、`README.md`、`LICENSE`、`AGENTS.md` などユーザー向け/保守向け静的ファイルを中心にする。
- `scripts/` は原則ローカル運用扱いだが、公開ページ生成に必要な以下は追跡対象にする:
  - `scripts/render_live_calendar.py`
  - `scripts/calendar_rules.json`
  - `scripts/sakurazaka_schedule_workflow.md`
  - `scripts/holidays_template.json`
- `.gitignore` はGitHubに置かず、ローカル除外ルールは `.git/info/exclude` で管理する。
- 検証用の `tests/` と一時ファイル、Pythonキャッシュ、OS生成ファイルは公開repoへ混ぜない。
- `scripts/templates/` は使わない。祝日テンプレートは正とするファイル一覧の `scripts/holidays_template.json` に集約する。
- READMEでページ用途を書く場合は、次の個人利用表現を優先する: `自分用のチケット抽選管理と、確認メモを整理するためのページとして運用しています。`

## Skillとの関係

Hermes skill `sakurazaka-live-calendar-generator-maintenance` は、このrepoへ迷わず入るための薄い入口。repo固有の現在ルールはこの `AGENTS.md` を正とし、skill側は短い補助手順と必要なデバッグ参照だけを持つ。
