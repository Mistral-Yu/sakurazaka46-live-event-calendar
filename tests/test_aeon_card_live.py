"""AEON CARD live labels and cross-month lottery regression coverage."""
from pathlib import Path
import datetime as dt
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "aeon_card_calendar", ROOT / "scripts" / "render_live_calendar.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

TITLE = "SAKURAZAKA46 Live，AEON CARD with YOU！Vol.6"
SOURCE_URL = "https://sakurazaka46.com/s/s46/news/detail/E00695"
SOURCE = f"""## {TITLE}

### ライブ公演の日程

| 開催日 | 曜日 | 会場 |
|---|---|---|
| 2026-12-26 | 土 | Kanadevia Hall／開場18:00・開演19:00 |

### 抽選の日程

| 抽選種別 | 受付期間 | 対象 |
|---|---|---|
| イオンカード一次先行 | **11/27(金)〜12/2(水)** | イオンカード(櫻坂46)・イオン銀行キャッシュ+デビット会員限定 |

### 公式ソース

- {SOURCE_URL}
"""
NOVEMBER = dt.date(2026, 11, 1)
DECEMBER = dt.date(2026, 12, 1)


def test_aeon_card_live_legacy_label_and_tone():
    months, _, _ = module.parse_summary(SOURCE, 2026)
    live = months[12]["days"][26]
    assert live == [{"text": "イオンライブ", "tone": "イオンライブ", "kind": "live"}]
    assert module.HTML_TONE[live[0]["tone"]] == "live"
    start = months[11]["days"][27][0]
    assert start["text"] == "イオンライブ抽選開始"
    assert module.HTML_TONE[start["tone"]] == "ticket"


def test_aeon_card_live_timeline_cross_month_and_details():
    months, _, _ = module.parse_summary_timeline(SOURCE, [NOVEMBER, DECEMBER], {})
    for month, day, label, tone, kind in (
        (NOVEMBER, 27, "イオンライブ抽選開始", "ticket", "lottery"),
        (NOVEMBER, 30, "イオンライブ抽選中", "ticket", "lottery_span"),
        (DECEMBER, 1, "イオンライブ抽選中", "ticket", "lottery_span"),
        (DECEMBER, 2, "イオンライブ抽選締切", "deadline", "lottery"),
        (DECEMBER, 26, "イオンライブ", "live", "live"),
    ):
        items = months[month]["days"][day]
        assert len(items) == 1
        assert items[0]["text"] == label
        assert items[0]["kind"] == kind
        assert module.HTML_TONE[items[0]["tone"]] == tone
        details = months[month]["detail_map"][day]
        assert SOURCE_URL in details[0]["sources"]
        assert TITLE in details[0]["label"]
    assert "Kanadevia Hall／開場18:00・開演19:00" in months[DECEMBER]["detail_map"][26][0]["sub"]
    assert "会員限定" in months[NOVEMBER]["detail_map"][27][0]["sub"]


def test_repository_summary_includes_aeon_card_live_and_no_general_sale():
    summary = (ROOT / "summary" / "sakurazaka46_live_summary.md").read_text()
    assert f"## {TITLE}\n" in summary
    section = summary.split(f"## {TITLE}\n", 1)[1].split("\n## ", 1)[0]
    assert SOURCE_URL in section
    assert "一般発売はありません" in section
    assert "**11/27(金)〜12/2(水)**" in section
