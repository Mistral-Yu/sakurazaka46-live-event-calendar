# AGENTS.md — sakurazaka46-live-event-calendar

## 対象範囲

このワークスペースでは、櫻坂46ライブ・イベント・チケット予定を整理した静的カレンダー `index.html` を保守する。日本語中心の repo なので、説明・運用メモ・コミットメッセージは日本語優先にする。

## 正とするファイル

- 公開出力: `index.html`
- ライブ入力: `summary/sakurazaka46_live_summary.md`
- イベント入力: `summary/sakurazaka46_event_summary.md`
- 生成スクリプト: `scripts/render_live_calendar.py`
- 生成ワークフロー文書: `scripts/sakurazaka_schedule_workflow.md`
- 祝日テンプレート: `scripts/holidays_template.json`
- `summary/` と `plan/` は別用途。`plan/` はカレンダー生成入力に使わない。
- `index.html` を直接手編集しない。表示・生成ロジックは `scripts/render_live_calendar.py` を直して再生成する。

## 現在のページ仕様

- `index.html` は単一のスタンドアロンHTMLとして公開する。外部アセットに依存しない。
- 表示モードは `live` / `event` / `all` の3タブ。
- デフォルト表示は `live`。
- URL状態は `?mode=live` / `?mode=event` / `?mode=all` を使う。
- タブ名は `live` / `event` / `all` のままにする。
- 全タブのページ見出しとHTML `<title>` は `櫻坂46 カレンダー` に統一する。
- `all` は解析済みの live/event 生成結果から作る。HTML手編集で統合しない。
- `all` は live/event の最初の月から最後の月まで連続表示する。途中の空月も残す。
- `all` では旧式の分類行（例: `内容分類: 開催`）を表示しない。色分け注釈だけ残す。
- 色分け注釈は高レベル分類のままにする: `開催` / `応募` / `締切` / `祝日`。
- `all` の日付セルチップは詳細分類する:
  - `live開催` と `event開催` は別チップ。ただし同じピンクの開催色。
  - `live抽選` と `応募` は別チップ。ただし同じ青の応募・抽選色。
  - `live締切` と `締切` は別チップ。ただし同じ赤の締切色。
- `all` チップの重複は同一ラベル内だけ畳む。例: 複数の live 抽選は `live抽選` 1つに畳むが、`live抽選` と `応募` は両方表示する。
- `all` の日付詳細は live/event の元詳細データを保持し、チップを要約してもクリック時の詳細は失わない。
- 祝日だけの日はクリック対象・詳細を作らない。祝日はセル内で `祝` のみ表示し、詳細欄に祝日名説明を出さない。

## データ入力ルール

- live 日程は `summary/sakurazaka46_live_summary.md` を編集する。
- live 以外のイベント、CD応募、ミーグリ、リアルミーグリは `summary/sakurazaka46_event_summary.md` を編集する。
- 各予定は `##` 見出し単位で管理する。
- live は `### ライブ公演の日程` / `### 抽選の日程` / `### 公式ソース` を基本にする。
- event は `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース` の順にする。
- live 日程は曜日付きにする。
- 連番日は1行でまとめ、同月範囲は短く書く。
- 抽選情報は時間・祝日を省く。
- カレンダータグは日本語にする。
- 公式URLは `### 公式ソース` に置く。外部公式・主催者・Fortune Music・SPICE/eplus なども許容する。
- 公式情報を整理するときは、出典URL、日付、曜日、会場、応募期間、対象イベントを分けて抽出し、必要なら Python `datetime` で曜日を検算する。
- 櫻坂のリアルミーグリは、CD封入シリアル応募ならCD系イベントとして扱う。
- リアルミーグリ等の詳細確認は、公式本体より Fortune Music を優先する。

## live/event の表示ルール

- event側の開催チップは、liveチップと同じ薄いピンクの開催色を使う。
- event側の応募・抽選の開始/期間中チップは青のままにする。
- event側の応募・抽選の締切チップは赤の締切色を使う。
- 長いCD/シリアル応募期間は、表示範囲に含まれる端点だけを表示し、中間日を全て埋めない。
- メッセージキャンペーン期間は応募側の項目として扱い、event開催扱いにしない。
- `一般発売` は抽選開始として扱わない。`一般発売` / `一般発売中` / `販売終了` として扱う。
- `オフィシャル先着受付` など主催者側の先着販売は、抽選ではなく販売として扱う。
- live抽選期間の中間日は `中` を使う。`継続` は使わない。
- 四期生 LIVE は `四期生ライブ` / `四期生ライブ抽選` を使う。
- BACKS LIVE は `バックスライブ` を使う。
- 全国アリーナツアー / 全国ツアーのlive日は `静岡公演`、`神戸公演`、`広島公演`、`千葉公演`、`宮城公演`、`香川公演` のように `地名+公演` にする。

## UI / 操作ルール

- 共有HTMLはミニマルに保ち、依頼なしにデザインを大きく変えない。
- モード切替は各 `h1` 直下に置き、固定バーやグローバルバーにしない。
- 実行時のDOM検索は現在の `.calendar-view` 内に限定し、live/event/all の重複IDによる干渉を避ける。
- クリック可能な日付セルは、ボタン風ではなく軽量なリンク型セル（`<a class='day-cell clickable' ...>`）を維持する。
- 月単位の情報欄は、クリック日の詳細欄の下に初期表示する。必要なら折りたたみ `details` を使う。
- 同じ月カード内で開く日付詳細は最大1つ。明示されない限り、他の月カードの詳細は自動で閉じない。
- モバイル用の短縮chip表示は既存の狭幅ブレークポイントで行い、デスクトップ表示を一律短縮しない。
- iPhone/Safari系のタップ反応が悪化した場合は、重いpointerハックを増やす前に、既存のhash / `:target` / スコープ済みJSの方針で直す。

## コマンド

テスト:

```bash
python3 -m pytest tests/test_render_live_calendar.py -q
```

通常再生成:

```bash
python3 scripts/render_live_calendar.py
```

内閣府CSVから祝日を更新:

```bash
python3 scripts/render_live_calendar.py --refresh-holidays
```

任意出力:

```bash
python3 scripts/render_live_calendar.py --output-calendar-md
python3 scripts/render_live_calendar.py --output-preview
```

このワークスペースでは `python3` をそのまま使える。repo内に有効化すべき `venv/` はない。

## 検証チェックリスト

- `python3 -m pytest tests/test_render_live_calendar.py -q` が通る。
- 生成器や出力に関わる変更では `python3 scripts/render_live_calendar.py` が成功する。
- `index.html` と `scripts/sakurazaka_schedule_workflow.md` は、意図したときだけ再生成される。
- all-mode変更ではブラウザまたはDOMで以下を確認する:
  - `?mode=live`、`?mode=event`、`?mode=all` が正しく切り替わる。
  - 表示中の見出しが `櫻坂46 カレンダー`。
  - all mode に `内容分類:` 行がない。
  - `live開催` / `event開催` はピンク、`live抽選` / `応募` は青、`live締切` / `締切` は赤。
  - all-modeの日付クリックで元のlive/event詳細が統合表示される。
  - JavaScriptコンソールにエラーがない。
- ローカルブラウザ確認で `127.0.0.1:9333` のCDPが起動していない場合は以下で起動する:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9333 --user-data-dir="/Users/mistralyu/Library/Application Support/Chrome-Hermes"
```

その後、`file://.../index.html?mode=all&verify=<cache-buster>` を開く。

## リポジトリ管理

- `sakurazaka46-live-event-calendar` は原則 `main` に直接pushする。
- 公開repoは `index.html`、`summary/`、`README.md`、`LICENSE`、`AGENTS.md` などユーザー向け/保守向け静的ファイルを中心にする。
- `scripts/` は原則ローカル運用扱いだが、公開ページ生成に必要な以下は追跡対象にする:
  - `scripts/render_live_calendar.py`
  - `scripts/sakurazaka_schedule_workflow.md`
  - `scripts/holidays_template.json`
- `.gitignore` はGitHubに置かず、ローカル除外ルールは `.git/info/exclude` で管理する。
- 検証用の `tests/` と一時ファイル、Pythonキャッシュ、OS生成ファイルは公開repoへ混ぜない。
- `scripts/templates/` は使わない。祝日テンプレートは `scripts/holidays_template.json` に集約する。
- READMEでページ用途を書く場合は、次の個人利用表現を優先する: `自分用のチケット抽選管理と、確認メモを整理するためのページとして運用しています。`

## Skillとの関係

Hermes skill `sakurazaka-live-calendar-generator-maintenance` は、このrepo用の薄い作業プレイブック。repo固有の現在ルールはこの `AGENTS.md` を正とし、skill側には長い作業手順、ブラウザ検証メモ、情報収集手順だけを置く。
