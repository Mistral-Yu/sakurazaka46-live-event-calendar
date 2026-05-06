# AGENTS.md — sakurazaka46-live-event-calendar

## Scope

このワークスペースでは、櫻坂46ライブ・チケット予定を整理した静的カレンダー `index.html` を保守する。

## Source of truth

- Public output: `index.html`
- Calendar input: `summary/sakurazaka46_live_summary.md`
- Event input: `summary/sakurazaka46_event_summary.md`
- `summary/` と `plan/` は別用途。`plan/` はカレンダー生成入力に使わない。

## User preferences

- 共有HTMLはミニマルに保ち、依頼なしにデザインを大きく変えない。
- `sakurazaka46-live-event-calendar` は原則 `main` に直接 push する。
- 日本語中心のrepoなので、コミットメッセージも日本語優先。
- ライブ日程は曜日付きにする。
- 連番日は1行でまとめる。
- 同月範囲は短く書く。
- 抽選情報は時間・祝日を省く。
- calendarタグは日本語にする。
- 要約は箇条書き優先。
- 櫻坂のリアルミーグリは、CD封入シリアル応募ならCD系イベントとして扱う。
- リアルミーグリ等の詳細確認は、公式本体より Fortune Music を優先する。

## Maintenance workflow

- ライブの予定データ更新は `summary/sakurazaka46_live_summary.md` を編集する。
- ライブ以外のイベント、CD応募、ミーグリ、リアルミーグリは `summary/sakurazaka46_event_summary.md` を編集する。
- 表示・生成ロジック変更は `scripts/render_live_calendar.py` を編集して `index.html` を再生成する。
- `scripts/render_live_calendar.py` は通常実行時に `index.html` と `scripts/sakurazaka_schedule_workflow.md` を生成する。
- `index.html` を直接手編集するより、生成元を直して再生成する方を優先する。
- AIに情報整理を依頼するときは、公式サイト・公式ニュース・Fortune Music・主催者ページなどの一次情報を優先して確認し、既存のMarkdown構造に合わせて要点を整理する。
- AIエージェントによる調査支援では、出典URL、日付、曜日、会場、応募期間、対象イベントを分けて抽出し、必要に応じて曜日を検算してから summary を更新する。
- summary 更新後は `python3 scripts/render_live_calendar.py` を実行し、`index.html` と `scripts/sakurazaka_schedule_workflow.md` を再生成する。
- 生成結果はテストと差分で確認し、重要な予定は一次情報との照合を残す。
- UI変更後はローカルで視覚確認する。
- 検証後は使ったローカルサーバーやブラウザを閉じる。

## Repository hygiene

- 公開repoは `index.html`、`summary/`、`README.md`、`LICENSE`、`license.md` などユーザー向け静的ファイルを中心にする。
- `AGENTS.md` はAIエージェント向けの保守ルールとして公開repoに含める。
- `scripts/` は原則ローカル運用扱いだが、公開ページ生成に必要な `scripts/render_live_calendar.py`、`scripts/sakurazaka_schedule_workflow.md`、`scripts/holidays_template.json` は追跡対象にする。
- `.gitignore` はGitHubに置かず、ローカル除外ルールは `.git/info/exclude` で管理する。
- 検証用の `tests/` と一時ファイル、Pythonキャッシュ、OS生成ファイルは公開repoへ混ぜない。
- `scripts/templates/` は使わない。祝日テンプレートは `scripts/holidays_template.json` に集約する。