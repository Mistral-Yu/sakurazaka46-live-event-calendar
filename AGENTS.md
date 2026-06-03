# AGENTS.md — sakurazaka46-live-event-calendar

## 範囲と優先順位
- このリポジトリ固有の運用はこのファイルを正とし、`~/.hermes/skills/media/sakurazaka-live-calendar-generator-maintenance` は入口として使用する。
- 日本語中心のrepoなので説明・メモ・コミットメッセージは日本語優先。
- `.plan/` はカレンダー生成入力に使わない。

## 正とするファイル
- 入力
  - `summary/sakurazaka46_live_summary.md`（live）
  - `summary/sakurazaka46_event_summary.md`（event/CD/ミーグリ/リアルミーグリ）
- 生成器・設定
  - `scripts/render_live_calendar.py`
  - `scripts/calendar_rules.json` / `scripts/holidays_template.json`
  - `scripts/sakurazaka46_members_template.json`
  - `scripts/fortune_meet_html_to_plan_json.py`
- 出力
  - `index.html`
  - `ics/sakurazaka46_all.ics`
  - `ics/sakurazaka46_deadlines.ics`
- `index.html` は生成物。直接手編集しない。

## 最小フロー（必須）
1. 対象 `summary/*.md` を更新。
2. `python3 scripts/render_live_calendar.py` で再生成。
3. `python3 -m pytest tests/test_render_live_calendar.py -q` で検証。
4. `index.html` と `ics` の差分を確認。

## 運用ルール（必須）
- URLモードは `live / event / all / plan / next14` の5つ。
- 表示見出しと `<title>` は `櫻坂46 カレンダー`。
- `all` と `plan` は手編集禁止（`live/event` の再生成結果を統合）。
- `main` への直接運用を前提（必要時のみ別ブランチ）。
- `.git/info/exclude` でローカル除外を管理。

## 検証チェック
- テストPASS。
- `index.html` が通常再生成で更新。
- `mode` 切替が正しく動作（live/event/all）。
- `all` で `内容分類:` 表示を出さない。
- console エラーなし。
- `?mode=next14` は今日基準14日、祝日は「祝」のみ（詳細なし）。

## 参照先（詳細）
- 追加のlive/event仕様・入力・表示ルールは
  `scripts/sakurazaka-validation-policy.md`
  に集約。
- スキルはここへの導線で、実務手順は最小化。
