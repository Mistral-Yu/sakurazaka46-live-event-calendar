"""Regression coverage for anniversary labels with venue annotations."""
from pathlib import Path
import datetime as dt
import importlib.util

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_live_calendar.py"
spec = importlib.util.spec_from_file_location("anniversary_calendar", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SOURCE = """## 6th YEAR ANNIVERSARY LIVE

### アニバーサリーライブの公演日程

| 開催日 | 曜日 | 会場 |
|---|---|---|
| 2026-11-14 | 土 | ZOZOマリンスタジアム／開場15:30・開演17:30 |
| 2026-11-15 | 日 | ZOZOマリンスタジアム／開場15:00・開演17:00／松田里奈 卒業セレモニー |

### 抽選の日程

| 抽選種別 | 受付期間 | 対象 |
|---|---|---|
| オフィシャル先行 | **10/1(木)〜10/6(火)** | 全席指定 |
"""


def test_anniversary_live_label_and_color_ignore_venue_annotations():
    months, live_legend, lottery_legend = module.parse_summary(SOURCE, 2026)
    for day in (14, 15):
        assert months[11]["days"][day] == [{"text": "アニラ", "tone": "アニラ", "kind": "live"}]
        assert module.HTML_TONE[months[11]["days"][day][0]["tone"]] == "live"
    ticket = months[10]["days"][1][0]
    assert ticket["text"] == "アニラ抽選開始"
    assert module.HTML_TONE[ticket["tone"]] == "ticket"
    html = module.render_html(months, live_legend, lottery_legend, 2026)
    assert "class='chip tone-live' data-mobile-text='アニラ'" in html
    assert "class='chip tone-ticket' data-mobile-text='アニラ抽選開始'" in html


def test_anniversary_timeline_preserves_details_and_ticket_deadline_color():
    october, november = dt.date(2026, 10, 1), dt.date(2026, 11, 1)
    months, _, _ = module.parse_summary_timeline(SOURCE, [october, november], {})
    for day in (14, 15):
        assert months[november]["days"][day] == [{"text": "アニラ", "tone": "アニラ", "kind": "live"}]
        assert "開演" in months[november]["detail_map"][day][0]["sub"]
    assert "松田里奈 卒業セレモニー" in months[november]["detail_map"][15][0]["sub"]
    deadline = months[october]["days"][6][0]
    assert deadline["text"] == "アニラ抽選締切"
    assert module.HTML_TONE[deadline["tone"]] == "deadline"
