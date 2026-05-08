# sakurazaka schedule workflow

## 概要

- 生成フロー: `summary/sakurazaka46_live_summary.md` / `summary/sakurazaka46_event_summary.md` → `scripts/render_live_calendar.py` → `index.html`
- live表示は `summary/sakurazaka46_live_summary.md`、event表示は `summary/sakurazaka46_event_summary.md` を source of truth とする。
- all表示は live/event の生成結果を統合し、カレンダー内の表示を `開催` / `応募` / `締切` に要約する。
- `.plan/` は作業用であり、カレンダー生成には使わない。

## 元Markdownの書き方ルール

- live/eventとも各予定は `##` 見出し単位で管理する。
- liveは `### ライブ公演の日程` / `### 抽選の日程` / `### 公式ソース` を基本に崩さない。
- eventは live と同じ考え方で `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース` の順で整理する。
- live日程は `| 2026-07-23〜24 | 木金 | 静岡・エコパアリーナ |` のような表形式を維持する。
- event日程は `| 2026-05-03 | 日 | 京都パルスプラザ |` や `| 2026-06-10 | 水 | 発売日 |` のような表形式を維持する。
- 抽選日程も `| FC会員先行 | **4/13(月)〜4/19(日)** | 全席指定／親子・女性エリア |` のような表形式を維持する。event側で年をまたがず明確にしたい場合は `**2026-03-11(水)〜2026-05-29(金)**` のように年付きで書ける。
- Fortune Music などの `支払い方法選択期限` は応募側の締切として扱い、日付セルでは `支払い方法選択期限` と表示する。
- 抽選日が未定のときは、`### 抽選の日程` 配下に `- チケット先行詳細は後日発表` のような箇条書きで置く。
- 公式URLは `### 公式ソース` の下にまとめる。
- Python 側のパーサがこのMarkdownを直接読むので、見出し名や表の形を変えると生成が壊れる。

## 生成コマンド

通常実行:

```bash
python3 scripts/render_live_calendar.py
```

祝日テンプレートを公式CSVから更新したいとき:

```bash
python3 scripts/render_live_calendar.py --refresh-holidays
```

この実行で更新されるもの:

- `index.html`
- `scripts/sakurazaka_schedule_workflow.md`

必要なときだけ追加でMarkdownカレンダーも出力:

```bash
python3 scripts/render_live_calendar.py --output-calendar-md
```

- `summary/sakurazaka46_live_calendar.md`（通常は未出力）

必要なときだけプレビュー画像も出力:

```bash
python3 scripts/render_live_calendar.py --output-preview
```

- `summary/sakurazaka46_live_calendar_preview.jpg`（通常は未出力）

## HTML表示範囲ルール

- HTML は常に単一ファイル `index.html`。
- `summary/sakurazaka46_live_summary.md` に `2026` と `2027` が混在していても、同じHTML内に連続表示する。
- 表示範囲は Markdown 内の最初の確定月から最後の確定月まで連続で描画する。
- `### 抽選の日程` 配下の未定箇条書きは表示月範囲を延ばさない。
- 現在検出している最終月: `2026年11月`

## 祝日データ

- 新しい年を初めて扱うときだけ、内閣府の祝日CSVを取得する。
  - `https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv`
- 取得結果は再利用用テンプレートとして保存する。
  - `scripts/holidays_template.json`
- 通常運用では年に1回取得できれば十分で、毎回の更新は不要。
- CSV取得に失敗し、まだテンプレートが無い年は空テンプレートを作って後で再試行できるようにする。
- CSV取得に失敗しても既存テンプレートがあれば、そのまま既存テンプレートを使う。
- 日付セルには `祝` だけを表示し、祝日名の詳細は詳細欄や補足側で扱う。

## 現在のHTML仕様

- 単一のスタンドアロンHTML
- LIVE / EVENT / ALL / 直近2週間 を単一HTML内のタブとして表示
- `直近2週間` はブラウザJSで Asia/Tokyo 基準の今日を取得し、今日を含む14日分を1日1行で表示。予定なしの日も表示し、live/event の元チップ文言・色を使い、祝日チップは出さない
- ライブも抽選もない月はデフォルトで折りたたみ
- 日付セル内にライブタグ / 抽選開始 / 抽選締切などを表示
- all表示では日付セル内を `ライブ開催` / `イベント開催`（同じピンク）、`ライブ抽選` / `イベント応募`（同じ青）、`ライブ抽選締切` / `イベント応募締切`（同じ赤）に要約
- 祝日はセル内で `祝` 表示
- 曜日行の土日と、土日・祝日の日付数字は赤文字表示（セル内チップ文言と `祝` チップは通常通り）。カレンダー内の日付数字とチップ文言はPC/スマホとも中央揃え
- スマホ幅ではチップ文言を最大2行にし、長い文言は中央付近で分けて行ごとの文字数をできるだけ均等化
- 日付クリックで同じ月カード内の詳細パネルを開く。初期状態の `日付をタップすると詳細を表示` 注釈は出さない
- 月見出しは太く出しすぎず、やや小さめ・軽めのモダンな日本語フォント感にする
- プレビュー画像は Python 生成の JPG（`--output-preview` 指定時のみ `summary/` に出力）
- 祝日テンプレートは `scripts/holidays_template.json` で管理する

## 編集ルール

1. ライブ日程・抽選日程・公式URLを変えるときは、先に `summary/sakurazaka46_live_summary.md` を更新する。
2. ライブ以外のイベント、CD応募、ミーグリ、リアルミーグリを変えるときは、先に `summary/sakurazaka46_event_summary.md` を更新する。
3. レイアウトや表示挙動を変えるときは `scripts/render_live_calendar.py` を編集して再生成する。
4. 生成後のHTMLを手で直接編集しない。
5. `.plan/` をカレンダー入力に使わない。

## 確認手順

```bash
python3 scripts/render_live_calendar.py
open index.html
```

プレビュー画像も確認したいとき:

```bash
python3 scripts/render_live_calendar.py --output-preview
```

確認ポイント:

- HTMLの最終月が Markdown の最終確定月と一致している
- 対象月に正しいライブ日程が入っている
- 抽選タグが正しい
- 祝日が `祝` として見えている
- 予定なしの月が折りたたまれている
- 日付クリックで詳細パネルが出る
- 初回成功後に祝日テンプレートが生成されている

## Codex向け Summary更新プロンプト例

```text
Summary更新依頼です。

対象ファイル:
- `summary/sakurazaka46_live_summary.md`

やってほしいこと:
- 櫻坂46の新しいライブ発表内容を、既存の書式に合わせて追記・更新してください。
- `### ライブ公演の日程`、`### 抽選の日程`、`### 公式ソース` の構成は崩さないでください。
- 日付は `2026-07-23〜24` のように整理し、曜日も入れてください。
- 抽選情報は金額を入れず、受付期間と対象だけを簡潔にまとめてください。
- 首都圏以外の公演で必要なら、`### 公式ソース` の次に `### 東京からの大まかな交通手段` を短く追記してください。
- 更新後は `python3 scripts/render_live_calendar.py` を実行して `index.html` と workflow を再生成してください。
- プレビュー画像が必要な場合だけ `python3 scripts/render_live_calendar.py --output-preview` を使ってください。
```

## Codex向け短縮指示テンプレート

```text
`summary/sakurazaka46_live_summary.md` と `summary/sakurazaka46_event_summary.md` を source of truth として扱う。
event側は `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース` の順と表形式を維持する。
`python3 scripts/render_live_calendar.py` を実行して生成物を更新する。
`--output-calendar-md` は追加のMarkdownカレンダーが欲しいときだけ使う。
`--output-preview` は追加のプレビュー画像が欲しいときだけ使い、出力先は `summary/` とする。
`--refresh-holidays` は保存済み祝日テンプレートを公式CSVで更新したいときだけ使う。
HTMLは常に単一ファイル `index.html`。
summaryに 2026 と 2027 が混在していても同じHTML内に連続表示する。
`### 抽選の日程` 配下の未定項目は表示範囲を延ばさない。
見出し名や表の形を変えるなら、先にパーサ側も直す。
生成済みHTMLを手で直接編集しない。
`.plan/` を入力に使わない。
表示変更は `scripts/render_live_calendar.py` で行う。
```
