# 櫻坂46 ライブ・イベントカレンダー

櫻坂46のライブ日程・チケット抽選・関連イベントを、見やすい形でまとめるための公開用リポジトリです。
自分用のチケット抽選管理と、確認メモを整理するためのページとして運用しています。

ページやサマリーなどの土台は Codex を使って作成し、人間が内容確認と文章校正を行いながら更新しています。

公開ページはこちらです。  
https://mistral-yu.github.io/sakurazaka46-live-event-calendar/

## このページでできること

- ライブ日程を月ごとに確認できます
- チケット抽選や一般発売の時期をまとめて見られます
- 祝日を含めて、日付の流れをひと目で追えます
- スマートフォンでも見やすい形で確認できます

## 更新の元データ

このリポジトリでは、以下のMarkdownを管理しています。

- `summary/sakurazaka46_live_summary.md`  
  公開ページのHTML生成に使う、ライブカレンダーの元データです。
- `summary/sakurazaka46_event_summary.md`  
  関連イベント情報を整理するためのまとめファイルです。

公開ページのHTMLは、`summary/sakurazaka46_live_summary.md` の内容をもとに Python スクリプトで生成しています。

## 主なファイル

- `index.html`  
  公開ページ本体です。
- `scripts/render_live_calendar.py`  
  カレンダーを生成するスクリプトです。
- `scripts/sakurazaka_schedule_workflow.md`  
  更新手順と運用ルールをまとめたファイルです。
- `summary/`  
  ライブ・イベント情報の元データです。

## ローカルで更新する方法

```bash
python3 scripts/render_live_calendar.py
```

実行すると、主に以下が更新されます。

- `index.html`
- `scripts/sakurazaka_schedule_workflow.md`

プレビュー画像も必要なときだけ、以下を実行します。

```bash
python3 scripts/render_live_calendar.py --output-preview
```

この場合は、以下も出力されます。

- `summary/sakurazaka46_live_calendar_preview.jpg`

## 補足

- `.plan/` は作業用ディレクトリで、公開や生成の入力には使いません
- 祝日データは公式CSVをもとにテンプレート化して再利用しています
- 公開ページは GitHub Pages で配信しています

櫻坂46の予定を、できるだけ見やすく・追いやすく整理していくためのページとして運用しています。
