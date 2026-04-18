# sakurazaka schedule workflow

## 概要

- 生成フロー: `summary/sakurazaka46_live_summary.md` → `scripts/render_live_calendar.py` → `index.html`
- `summary/sakurazaka46_live_summary.md` を唯一の source of truth とする。
- `.plan/` は作業用であり、カレンダー生成には使わない。

## 元Markdownの書き方ルール

- 各イベントは `##` 見出し単位で管理する。
- 見出しは `### ライブ公演の日程` / `### 抽選の日程` / `### 公式ソース` を基本に崩さない。
- ライブ日程は `| 2026-07-23〜24 | 木金 | 静岡・エコパアリーナ |` のような表形式を維持する。
- 抽選日程も `| FC会員先行 | **4/13(月)〜4/19(日)** | 全席指定／親子・女性エリア |` のような表形式を維持する。
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
- `previews/sakurazaka46_live_calendar_preview.jpg`
- `scripts/sakurazaka_schedule_workflow.md`

必要なときだけ追加でMarkdownカレンダーも出力:

```bash
python3 scripts/render_live_calendar.py --output-calendar-md
```

- `summary/sakurazaka46_live_calendar.md`（通常は未出力）

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
  - `scripts/templates/holidays_2026_template.json`
- 通常運用では年に1回取得できれば十分で、毎回の更新は不要。
- CSV取得に失敗し、まだテンプレートが無い年は空テンプレートを作って後で再試行できるようにする。
- CSV取得に失敗しても既存テンプレートがあれば、そのまま既存テンプレートを使う。
- 日付セルには `祝` だけを表示し、祝日名の詳細は詳細欄や補足側で扱う。

## 現在のHTML仕様

- 単一のスタンドアロンHTML
- Markdown内の最後の確定月まで連続表示
- ライブも抽選もない月はデフォルトで折りたたみ
- 日付セル内にライブタグ / 抽選開始 / 抽選締切などを表示
- 祝日はセル内で `祝` 表示
- 日付クリックで同じ月カード内の詳細パネルを開く
- プレビュー画像は Python 生成の JPG
- 祝日テンプレートは年ごとに管理する

## 編集ルール

1. ライブ日程・抽選日程・公式URLを変えるときは、先に `summary/sakurazaka46_live_summary.md` を更新する。
2. レイアウトや表示挙動を変えるときは `scripts/render_live_calendar.py` を編集して再生成する。
3. 生成後のHTMLを手で直接編集しない。
4. `.plan/` をカレンダー入力に使わない。

## 確認手順

```bash
python3 scripts/render_live_calendar.py
open index.html
```

確認ポイント:

- HTMLの最終月が Markdown の最終確定月と一致している
- 対象月に正しいライブ日程が入っている
- 抽選タグが正しい
- 祝日が `祝` として見えている
- 予定なしの月が折りたたまれている
- 日付クリックで詳細パネルが出る
- 初回成功後に祝日テンプレートが生成されている

## Codex向け短縮指示テンプレート

```text
`summary/sakurazaka46_live_summary.md` を source of truth として扱う。
`python3 scripts/render_live_calendar.py` を実行して生成物を更新する。
`--output-calendar-md` は追加のMarkdownカレンダーが欲しいときだけ使う。
`--refresh-holidays` は保存済み祝日テンプレートを公式CSVで更新したいときだけ使う。
HTMLは常に単一ファイル `index.html`。
summaryに 2026 と 2027 が混在していても同じHTML内に連続表示する。
`### 抽選の日程` 配下の未定項目は表示範囲を延ばさない。
見出し名や表の形を変えるなら、先にパーサ側も直す。
生成済みHTMLを手で直接編集しない。
`.plan/` を入力に使わない。
表示変更は `scripts/render_live_calendar.py` で行う。
```
