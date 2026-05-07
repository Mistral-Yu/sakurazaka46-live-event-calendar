# AGENTS.md — sakurazaka46-live-event-calendar

## Scope

このワークスペースでは、櫻坂46ライブ・イベント・チケット予定を整理した静的カレンダー `index.html` を保守する。
この repo は日本語中心なので、説明・運用メモ・コミットメッセージは日本語優先にする。

## Source of truth

- Public output: `index.html`
- Live input: `summary/sakurazaka46_live_summary.md`
- Event input: `summary/sakurazaka46_event_summary.md`
- Generator: `scripts/render_live_calendar.py`
- Workflow doc output: `scripts/sakurazaka_schedule_workflow.md`
- Holiday template: `scripts/holidays_template.json`
- `summary/` と `plan/` は別用途。`plan/` はカレンダー生成入力に使わない。
- `index.html` を直接手編集しない。表示・生成ロジックは `scripts/render_live_calendar.py` を直して再生成する。

## Current page specification

- `index.html` は単一の standalone HTML として公開する。外部 assets に依存しない。
- 表示モードは `live` / `event` / `all` の3タブ。
- デフォルト表示は `live`。
- URL state は `?mode=live` / `?mode=event` / `?mode=all` を使う。
- タブ名は `live` / `event` / `all` のままにする。
- 全タブのページ見出しと HTML `<title>` は `櫻坂46 カレンダー` に統一する。
- `all` は parsed live/event outputs から生成する。HTML手編集で統合しない。
- `all` は live/event の最初の月から最後の月まで連続表示する。途中の空月も残す。
- `all` では旧式の分類行（例: `内容分類: 開催`）を表示しない。色分け注釈だけ残す。
- 色分け注釈は高レベル分類のままにする: `開催` / `応募` / `締切` / `祝日`。
- `all` の日付セル chip は詳細分類する:
  - `live開催` と `event開催` は別 chip。ただし同じピンク live tone。
  - `live抽選` と `応募` は別 chip。ただし同じ青 ticket/application tone。
  - `live締切` と `締切` は別 chip。ただし同じ赤 deadline tone。
- `all` chip の重複は同一ラベル内だけ畳む。例: 複数 live 抽選は `live抽選` 1つに畳むが、`live抽選` と `応募` は両方表示する。
- `all` の day detail は live/event の元 detail payload を保持し、chip を要約してもクリック時の詳細は失わない。
- Holiday-only days should not create click/detail entries. 祝日はセル内で `祝` のみ表示し、詳細欄に祝日名説明を出さない。

## Data entry rules

- live 日程は `summary/sakurazaka46_live_summary.md` を編集する。
- live 以外のイベント、CD応募、ミーグリ、リアルミーグリは `summary/sakurazaka46_event_summary.md` を編集する。
- 各予定は `##` 見出し単位で管理する。
- live は `### ライブ公演の日程` / `### 抽選の日程` / `### 公式ソース` を基本にする。
- event は `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース` の順にする。
- live 日程は曜日付きにする。
- 連番日は1行でまとめ、同月範囲は短く書く。
- 抽選情報は時間・祝日を省く。
- calendar tag は日本語にする。
- 公式URLは `### 公式ソース` に置く。外部公式・主催者・Fortune Music・SPICE/eplus なども許容する。
- 公式情報を整理するときは、出典URL、日付、曜日、会場、応募期間、対象イベントを分けて抽出し、必要なら Python `datetime` で曜日を検算する。
- 櫻坂のリアルミーグリは、CD封入シリアル応募ならCD系イベントとして扱う。
- リアルミーグリ等の詳細確認は、公式本体より Fortune Music を優先する。

## Event/live display rules

- Event-mode event chips use the same shallow pink live tone as live chips.
- Event-mode application/lottery start and in-progress chips stay blue.
- Event-mode application/lottery deadline chips use the red deadline tone.
- Long CD/serial application periods should not fill every intermediate day; show only relevant endpoints when the visible range omits earlier months.
- Message campaign periods are application-side items, not event開催 items.
- `一般発売` は抽選開始として扱わない。`一般発売` / `一般発売中` / `販売終了` として扱う。
- Organizer-side sales labels such as `オフィシャル先着受付` are sales, not lotteries.
- For live lottery periods, show continuation with `中`; do not use `継続`.
- For 四期生 LIVE, use `四期生ライブ` and `四期生ライブ抽選`.
- For BACKS LIVE, use `バックスライブ`.
- For 全国アリーナツアー / 全国ツアー live days, use `地名+公演` such as `静岡公演`, `神戸公演`, `広島公演`, `千葉公演`, `宮城公演`, `香川公演`.

## UI / interaction rules

- 共有HTMLはミニマルに保ち、依頼なしにデザインを大きく変えない。
- Mode switch は各 `h1` 直下に置き、sticky/global bar にしない。
- Runtime DOM queries must be scoped to the current `.calendar-view` root to avoid live/event/all duplicate-ID cross-talk.
- Clickable day cells should remain lightweight anchor-style cells (`<a class='day-cell clickable' ...>`) rather than button chrome.
- Month-level sections should remain visible by default below the clicked-day detail area, preferably as collapsible `details` blocks.
- Keep at most one open detail within the same month card. Do not auto-close other month cards unless asked.
- Mobile compact chip labels should use the existing narrow breakpoint behavior; do not globally shorten desktop labels.
- If iPhone/Safari click feedback regresses, prefer the existing hash/`:target`/scoped JS approach before adding heavier pointer hacks.

## Commands

Focused tests:

```bash
python3 -m pytest tests/test_render_live_calendar.py -q
```

Regenerate default outputs:

```bash
python3 scripts/render_live_calendar.py
```

Refresh holidays from Cabinet Office CSV:

```bash
python3 scripts/render_live_calendar.py --refresh-holidays
```

Optional outputs:

```bash
python3 scripts/render_live_calendar.py --output-calendar-md
python3 scripts/render_live_calendar.py --output-preview
```

In this workspace, `python3` works directly; there is no repo-local `venv/` directory to source.

## Verification checklist

- `python3 -m pytest tests/test_render_live_calendar.py -q` passes.
- `python3 scripts/render_live_calendar.py` succeeds when generator/output behavior changes.
- `index.html` and `scripts/sakurazaka_schedule_workflow.md` regenerate only when intended.
- For all-mode changes, verify in browser or DOM:
  - `?mode=live`, `?mode=event`, `?mode=all` switch correctly.
  - visible heading is `櫻坂46 カレンダー`.
  - all mode has no `内容分類:` row.
  - `live開催` / `event開催` are pink, `live抽選` / `応募` are blue, `live締切` / `締切` are red.
  - clicking an all-mode day shows combined original details.
  - console has no JavaScript errors.
- For local browser verification, if CDP on `127.0.0.1:9333` is not running, launch:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9333 --user-data-dir="/Users/mistralyu/Library/Application Support/Chrome-Hermes"
```

Then open `file://.../index.html?mode=all&verify=<cache-buster>`.

## Repository hygiene

- `sakurazaka46-live-event-calendar` は原則 `main` に直接 push する。
- 公開repoは `index.html`、`summary/`、`README.md`、`LICENSE`、`AGENTS.md` などユーザー向け/保守向け静的ファイルを中心にする。
- `scripts/` は原則ローカル運用扱いだが、公開ページ生成に必要な以下は追跡対象にする:
  - `scripts/render_live_calendar.py`
  - `scripts/sakurazaka_schedule_workflow.md`
  - `scripts/holidays_template.json`
- `.gitignore` はGitHubに置かず、ローカル除外ルールは `.git/info/exclude` で管理する。
- 検証用の `tests/` と一時ファイル、Pythonキャッシュ、OS生成ファイルは公開repoへ混ぜない。
- `scripts/templates/` は使わない。祝日テンプレートは `scripts/holidays_template.json` に集約する。
- For README wording, preferred personal-use phrasing is: `自分用のチケット抽選管理と、確認メモを整理するためのページとして運用しています。`

## Skill relationship

Hermes skill `sakurazaka-live-calendar-generator-maintenance` is now a thin playbook for this repo. Repo-specific current rules live here in `AGENTS.md`; the skill should point here and keep only long operational playbooks, browser debugging notes, and source-collection procedures.
