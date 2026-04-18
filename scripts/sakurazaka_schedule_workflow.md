# sakurazaka schedule workflow

## Source of truth

- Pipeline: `summary/sakurazaka46_live_summary.md` -> `scripts/render_live_calendar.py` -> `index.html`
- `summary/sakurazaka46_live_summary.md` is the source of truth.
- `.plan/` files are not used for calendar generation.

## Source markdown format rules

- Keep each event as a `##` section.
- Use the existing headings exactly: `### ライブ公演の日程` or equivalent live schedule heading, `### 抽選の日程`, `### 公式ソース`.
- Live rows must stay as markdown table rows like `| 2026-07-23〜24 | 木金 | 静岡・エコパアリーナ |`.
- Lottery rows must stay as markdown table rows like `| FC会員先行 | **4/13(月)〜4/19(日)** | 全席指定／親子・女性エリア |`.
- If a lottery date is not fixed yet, keep it as a bullet under `### 抽選の日程` such as `- チケット先行詳細は後日発表`.
- Keep official URLs under `### 公式ソース`.
- The Python parser reads this markdown directly, so changing headings or table shape will break generation.

## Generator

Run:

```bash
python3 scripts/render_live_calendar.py
```

Force a holiday template refresh from the official CSV:

```bash
python3 scripts/render_live_calendar.py --refresh-holidays
```

This regenerates:

- `index.html`
- `previews/sakurazaka46_live_calendar_preview.jpg`
- `scripts/sakurazaka_schedule_workflow.md`

Optional:

```bash
python3 scripts/render_live_calendar.py --output-calendar-md
```

- `summary/sakurazaka46_live_calendar.md` (default off)

## HTML range rule

- HTML is always a single file: `index.html`.
- If `summary/sakurazaka46_live_summary.md` mixes `2026` and `2027`, the same HTML includes both years.
- The page always renders continuously from the earliest dated month through the last dated month in the markdown.
- Undetermined bullet items under `### 抽選の日程` do not extend the rendered month range.
- Current detected last month: `2026年11月`

## Holiday source

- Holidays are fetched from the official Cabinet Office CSV only when you first prepare a new year:
  - `https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv`
- The result is saved as reusable templates under:
  - `scripts/templates/holidays_2026_template.json`
- In practice, once per year is usually enough. You do not need to fetch every run.
- If CSV fetch fails and no template exists yet, the script creates an empty year template and tells you to retry later or fill it manually.
- If CSV fetch fails but a year template already exists, the script just keeps using that template.
- Date cells show only `祝`; the full holiday name remains in the details and notes.

## Current HTML behavior

- single standalone HTML file
- months are rendered continuously until the last dated month in the markdown
- months with no live or lottery schedule are collapsed by default
- live tags / lottery start / lottery end tags appear inside date cells
- holidays are shown as `祝` in the cell
- clicking a scheduled date opens a detail panel inside the same month card
- the preview image is a Python-rendered JPG preview
- holiday templates are year-specific under `scripts/templates/`

## Editing rules for Codex

1. If live dates, lottery dates, or source URLs change, update `summary/sakurazaka46_live_summary.md` first.
2. If layout or behavior changes, edit `scripts/render_live_calendar.py` and regenerate.
3. Do not hand-edit generated HTML.
4. Do not use `.plan/` files as calendar input.

## Verification

```bash
python3 scripts/render_live_calendar.py
open index.html
```

Check:

- the last month in the HTML matches the last dated month in the markdown
- the target month contains the correct live rows
- lottery tags are correct
- holidays are visible as `祝`
- no-schedule months are collapsed
- clicking a scheduled date shows the detail panel
- the holiday templates exist under `scripts/templates/` after the first successful run

## Short instruction template for Codex

```text
Treat summary/sakurazaka46_live_summary.md as the source of truth.
Run python3 scripts/render_live_calendar.py to regenerate the calendar assets.
Use --output-calendar-md only when you want the text calendar markdown as an extra generated file.
Use --refresh-holidays only when you intentionally want to replace saved holiday templates from the official CSV.
The HTML is always a single file named index.html.
If the summary mixes 2026 and 2027, include both years in the same HTML and render continuously through the last dated month.
Undetermined bullet items under 抽選の日程 should not extend the rendered range.
Do not change the summary markdown headings or table shape without updating the parser.
Do not hand-edit generated HTML.
Do not use .plan/ files as calendar input.
Make display changes in scripts/render_live_calendar.py.
```
