# 櫻坂46 ライブ・イベントカレンダー

櫻坂46のライブ日程・チケット抽選・関連イベントを、見やすい形でまとめるための公開用リポジトリです。
自分用のチケット抽選管理と、確認メモを整理するためのページとして運用しています。

## AI利用について

本リポジトリでは、AIモデル（ChatGPT / GPT-5.5）による作成・整理支援を利用しています。  
また、AIエージェントである Hermes Agent を用いた、情報収集・整理・更新支援ワークフローの検証も兼ねています。

掲載内容は、AIによる作成・整理支援、エージェントによる調査支援、人間による確認・補正を組み合わせて管理しています。  
ただし、正確性が重要な予定については、公式サイト・公式SNS・配信元などの一次情報も確認してください。

公開ページはこちらです。  
https://mistral-yu.github.io/sakurazaka46-live-event-calendar/

## このページでできること

- ライブ日程を月ごとに確認できます
- チケット抽選や一般発売の時期をまとめて見られます
- 祝日を含めて、日付の流れをひと目で追えます
- スマートフォンでも見やすい形で確認できます

## 更新の元データ

このリポジトリでは、以下のMarkdown形式のテキストデータを管理しています。

- `summary/sakurazaka46_live_summary.md`  
  公開ページのHTML生成に使う、ライブカレンダーの元データです。
- `summary/sakurazaka46_event_summary.md`  
  関連イベント情報を整理するためのまとめファイルです。

## 主な公開ファイル

- `index.html`  
  GitHub Pagesで公開するカレンダー本体です。
- `summary/sakurazaka46_live_summary.md`  
  ライブ日程・チケット抽選情報の元データです。
- `summary/sakurazaka46_event_summary.md`  
  CD発売、ミーグリ、リアルミーグリ、関連イベント情報の元データです。
- `scripts/render_live_calendar.py`  
  Markdownの元データから `index.html` を生成するスクリプトです。
- `scripts/holidays_template.json`  
  祝日表示に使う祝日データです。
- `scripts/sakurazaka_schedule_workflow.md`  
  生成手順と現在の表示仕様をまとめた運用メモです。
- `AGENTS.md`  
  AIエージェント向けの保守ルール・表示仕様・検証手順です。
- `LICENSE`  
  掲載内容・構成・デザイン・HTMLのライセンスです。

## ライセンス

このリポジトリで公開している掲載内容・文章・構成・デザイン・公開用HTMLは、**CC BY-NC 4.0**（表示-非営利 4.0 国際）で公開しています。商用利用は許可していません。詳細は `LICENSE` を参照してください。
