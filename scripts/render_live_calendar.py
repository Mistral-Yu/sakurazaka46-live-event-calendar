from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import calendar
import csv
import datetime as dt
import html
import json
import re
import urllib.request
from typing import Callable, Dict, List

from PIL import Image, ImageDraw, ImageFont


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
SUMMARY_DIR = BASE_DIR / "summary"
PLAN_DIR = BASE_DIR / ".plan"
TEMPLATE_DIR = SCRIPT_DIR / "templates"

SOURCE_MD = SUMMARY_DIR / "sakurazaka46_live_summary.md"
OUTPUT_MD = SUMMARY_DIR / "sakurazaka46_live_calendar.md"
OUTPUT_HTML = BASE_DIR / "index.html"
WORKFLOW_MD = SCRIPT_DIR / "sakurazaka_schedule_workflow.md"
LEGACY_WORKFLOW_MD = SUMMARY_DIR / "sakurazaka_schedule_workflow.md"
LONG_PREVIEW = SUMMARY_DIR / "sakurazaka46_live_calendar_preview.jpg"
HOLIDAY_CSV_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
DEFAULT_YEAR = 2026

ROW_RE = re.compile(
    r"^\|\s*(\d{4})-(\d{2})-(\d{2})(?:〜(\d{2}))?\s*\|\s*([^|]+?)\s*\|\s*([^|\n]+)\|$",
    re.M,
)
LOTTERY_ROW_RE = re.compile(
    r"^\|\s*([^|\n]+?)\s*\|\s*\*\*?([^|\n*]+)\*\*?\s*\|\s*([^|\n]+?)\s*\|$",
    re.M,
)
SOURCE_URL_RE = re.compile(r"https://[^\s)]+")

LIVE_LABEL = {
    "幕張イベントホール": "幕張",
    "LaLa arena TOKYO-BAY": "千葉",
    "静岡・エコパアリーナ": "静岡",
    "兵庫・神戸ワールド記念ホール": "神戸",
    "広島・広島グリーンアリーナ": "広島",
    "千葉・LaLa arena TOKYO-BAY": "千葉",
    "宮城・セキスイハイムスーパーアリーナ": "宮城",
    "香川・あなぶきアリーナ香川": "香川",
    "ZOZOマリンスタジアム": "アニラ",
    "大阪・舞洲スポーツアイランド": "ジャイガ",
}

LOTTERY_SHORT = {
    "一般発売": "一般",
    "イオンカード先行": "イオン",
    "FC会員先行": "FC",
    "Leminoスペシャルシート先行": "LeminoS",
    "Lemino櫻坂46パック先行": "LeminoP",
    "FC会員2次先行": "FC2",
    "オフィシャル先行": "先行",
    "オフィシャル先着受付": "先着",
    "三井ショッピングパーク チケット先行（千葉公演）": "三井",
    "オフィシャル2次先行": "先行2",
}

HTML_TONE = {
    "バックスライブ": "live", "四期生ライブ": "live", "静岡公演": "live", "神戸公演": "live", "広島公演": "live",
    "千葉公演": "live", "宮城公演": "live", "香川公演": "live", "アニラ": "live", "ジャイガ": "live",
    "FC": "ticket", "LeminoS": "ticket", "LeminoP": "ticket", "イオン": "ticket", "一般": "ticket",
    "FC2": "ticket", "先行": "ticket", "先着": "ticket", "三井": "ticket", "先行2": "ticket", "祝": "holiday", "情報": "ticket",
}

RGB_TONE = {
    "バックスライブ": (20, 134, 109), "四期生ライブ": (20, 134, 109), "静岡公演": (20, 134, 109), "神戸公演": (20, 134, 109),
    "広島公演": (20, 134, 109), "千葉公演": (20, 134, 109), "宮城公演": (20, 134, 109), "香川公演": (20, 134, 109),
    "アニラ": (20, 134, 109), "ジャイガ": (20, 134, 109), "FC": (91, 110, 240), "LeminoS": (91, 110, 240), "LeminoP": (91, 110, 240),
    "イオン": (91, 110, 240), "一般": (91, 110, 240), "FC2": (91, 110, 240), "先行": (91, 110, 240),
    "先着": (91, 110, 240), "三井": (91, 110, 240), "先行2": (91, 110, 240), "祝": (229, 72, 77), "情報": (91, 110, 240),
}

HOLIDAYS = {month: {} for month in range(1, 13)}

BG = (248, 248, 246)
WHITE = (255, 255, 255)
LINE = (226, 226, 222)
TEXT = (28, 28, 28)
MUTED = (120, 120, 120)


def empty_holiday_map() -> dict[int, dict[int, str]]:
    return {month: {} for month in range(1, 13)}


def parse_holiday_csv_bytes(data: bytes, year: int = DEFAULT_YEAR) -> dict[int, dict[int, str]]:
    decoded = data.decode("cp932")
    rows = csv.DictReader(decoded.splitlines())
    holidays = empty_holiday_map()
    for row in rows:
        date_text = (row.get("国民の祝日・休日月日") or "").strip()
        name = (row.get("国民の祝日・休日名称") or "").strip()
        if not date_text or not name:
            continue
        matched = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_text)
        if not matched:
            continue
        row_year, month, day = map(int, matched.groups())
        if row_year != year:
            continue
        holidays[month][day] = name
    return holidays


def fetch_holiday_csv(url: str = HOLIDAY_CSV_URL) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "HermesAgent/1.0 (+holiday-template)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def load_holiday_template(template_path: Path) -> dict[int, dict[int, str]] | None:
    if not template_path.exists():
        return None
    raw = json.loads(template_path.read_text())
    holidays = empty_holiday_map()
    for month_key, day_map in raw.items():
        month = int(month_key)
        holidays[month] = {int(day): name for day, name in day_map.items()}
    return holidays


def get_holiday_template_path(year: int) -> Path:
    return TEMPLATE_DIR / f"holidays_{year}_template.json"


def write_holiday_template(template_path: Path, holidays: dict[int, dict[int, str]]) -> None:
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(holidays, ensure_ascii=False, indent=2))


def load_or_fetch_holidays(
    year: int = DEFAULT_YEAR,
    template_path: Path | None = None,
    fetcher: Callable[[], bytes] | None = None,
    refresh: bool = False,
) -> dict[int, dict[int, str]]:
    if template_path is None:
        template_path = get_holiday_template_path(year)

    existing_template = load_holiday_template(template_path)
    if existing_template is not None and not refresh:
        return existing_template

    if fetcher is None:
        fetcher = fetch_holiday_csv

    try:
        holidays = parse_holiday_csv_bytes(fetcher(), year=year)
    except Exception as exc:
        seeded = empty_holiday_map()
        write_holiday_template(template_path, seeded)
        raise RuntimeError(
            f"祝日CSVの取得に失敗したため、テンプレート {template_path.name} を作成しました。"
            "ネットワーク復旧後に再実行するか、このテンプレートへ手動入力してください。"
        ) from exc

    write_holiday_template(template_path, holidays)
    return holidays


def infer_source_year(text: str) -> int:
    match = re.search(r"\|\s*(\d{4})-(\d{2})-(\d{2})", text)
    return int(match.group(1)) if match else DEFAULT_YEAR


def detect_source_years(text: str) -> list[int]:
    years = sorted({int(year) for year, _month, _day in re.findall(r"\|\s*(\d{4})-(\d{2})-(\d{2})", text)})
    return years


def resolve_target_year(text: str, requested_year: int | None) -> int:
    if requested_year is not None:
        return requested_year
    years = detect_source_years(text)
    if not years:
        return DEFAULT_YEAR
    if len(years) == 1:
        return years[0]
    raise ValueError(f"複数年のデータがあります ({', '.join(map(str, years))})。--year で対象年を指定してください。")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Sakurazaka live calendar assets")
    parser.add_argument(
        "--refresh-holidays",
        action="store_true",
        help="Ignore an existing holiday template for the detected year(s) and refetch from the official Cabinet Office CSV.",
    )
    parser.add_argument(
        "--output-calendar-md",
        action="store_true",
        help="Also generate summary/sakurazaka46_live_calendar.md. Default is off.",
    )
    parser.add_argument(
        "--output-preview",
        action="store_true",
        help="Also generate summary/sakurazaka46_live_calendar_preview.jpg. Default is off.",
    )
    return parser.parse_args(argv)


# generated from summary/sakurazaka46_live_summary.md
# usage: python3 scripts/render_live_calendar.py
# outputs:
#   - summary/sakurazaka46_live_calendar.md
#   - index.html
#   - summary/sakurazaka46_live_calendar_preview.jpg (optional)


def load_fonts() -> Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Menlo.ttc",
    ]
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            return {
                "title": ImageFont.truetype(path, 36),
                "month": ImageFont.truetype(path, 52),
                "day": ImageFont.truetype(path, 23),
                "chip": ImageFont.truetype(path, 15),
                "small": ImageFont.truetype(path, 18),
                "note": ImageFont.truetype(path, 16),
            }
        except Exception:
            continue
    default = ImageFont.load_default()
    return {k: default for k in ["title", "month", "day", "chip", "small", "note"]}


def empty_month_struct() -> dict:
    return {
        "events": [],
        "lotteries": [],
        "days": defaultdict(list),
        "detail_map": defaultdict(list),
        "sources": [],
    }


def month_has_schedule(month_data: dict) -> bool:
    return bool(month_data["events"] or month_data["lotteries"])


def add_detail(months: dict, month: int, day: int, payload: dict) -> None:
    months[month]["detail_map"][day].append(payload)


def merge_day_items(items: list[dict]) -> list[dict]:
    merged: list[dict] = []
    grouped: dict[tuple[str, str], dict] = {}

    for item in items:
        if item.get("kind") not in {"lottery", "lottery_span"}:
            merged.append(item)
            continue

        key = (item["kind"], item.get("text", ""))
        if key not in grouped:
            grouped[key] = dict(item)
            merged.append(grouped[key])
    return merged


def mobile_chip_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 3:
        return compact
    return f"{compact[:2]}…"


def lottery_calendar_label(title: str) -> str:
    normalized = re.sub(r"^\d+枚目シングル\s*", "", title.strip())
    if "BACKS LIVE" in normalized:
        return "バックスライブ抽選"
    if "四期生 LIVE" in normalized:
        return "四期生ライブ抽選"
    if "全国アリーナツアー" in normalized or "全国ツアー" in normalized:
        return "ツアー抽選"
    if "ANNIVERSARY LIVE" in normalized or "アニラ" in normalized:
        return "アニラ抽選"
    if "OSAKA GIGANTIC MUSIC FESTIVAL" in normalized or "ジャイガ" in normalized:
        return "ジャイガ抽選"
    normalized = re.sub(r"\s*LIVE!?！*$", "", normalized)
    return f"{normalized}抽選"


def live_calendar_label(title: str, venue: str) -> str:
    if "BACKS LIVE" in title:
        return "バックスライブ"
    if "四期生 LIVE" in title:
        return "四期生ライブ"
    if "OSAKA GIGANTIC MUSIC FESTIVAL" in title or "ジャイガ" in title:
        return "ジャイガ"
    base = LIVE_LABEL.get(venue, title[:4])
    if "全国アリーナツアー" in title or "全国ツアー" in title:
        return f"{base}公演"
    return base


def lottery_phase_labels(
    calendar_label: str,
    title: str,
    lottery_type: str,
) -> tuple[str, str, str, str, str]:
    sale_label = calendar_label.removesuffix("抽選") if calendar_label.endswith("抽選") else calendar_label
    if lottery_type == "一般発売":
        detail_label = f"一般発売: {title}"
        return (
            f"{sale_label}一般発売",
            f"{sale_label}一般発売中",
            f"{sale_label}販売終了",
            detail_label,
            detail_label,
        )
    if "先着" in lottery_type:
        compact_type = "先着受付" if lottery_type == "オフィシャル先着受付" else lottery_type
        detail_label = f"{lottery_type}: {title}"
        return (
            f"{sale_label}{compact_type}",
            f"{sale_label}{compact_type}中",
            f"{sale_label}販売終了",
            detail_label,
            detail_label,
        )
    detail_label = f"抽選: {title} {lottery_type}"
    return f"{calendar_label}開始", f"{calendar_label}継続", f"{calendar_label}締切", detail_label, detail_label


def iter_date_range(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def month_start(year: int, month: int) -> dt.date:
    return dt.date(year, month, 1)


def iter_month_starts(start: dt.date, end: dt.date):
    current = month_start(start.year, start.month)
    final = month_start(end.year, end.month)
    while current <= final:
        yield current
        if current.month == 12:
            current = dt.date(current.year + 1, 1, 1)
        else:
            current = dt.date(current.year, current.month + 1, 1)


def parse_lottery_period(period: str, section_dates: list[dt.date]) -> tuple[dt.date, dt.date] | None:
    parsed = re.match(r"(\d{1,2})/(\d{1,2})\([^)]*\)(?:〜(?:(\d{1,2})/(\d{1,2})\([^)]*\)|))?", period)
    if not parsed or not section_dates:
        return None

    start_month = int(parsed.group(1))
    start_day = int(parsed.group(2))
    end_month = int(parsed.group(3)) if parsed.group(3) else start_month
    end_day = int(parsed.group(4)) if parsed.group(4) else start_day

    anchor = min(section_dates)
    start_year = anchor.year if start_month <= anchor.month else anchor.year - 1
    end_year = start_year if end_month >= start_month else start_year + 1
    return dt.date(start_year, start_month, start_day), dt.date(end_year, end_month, end_day)


def collect_display_months(text: str) -> list[dt.date]:
    dates: list[dt.date] = []
    sections = re.split(r"^## ", text, flags=re.M)[1:]

    for section in sections:
        _title, body = section.split("\n", 1)
        section_dates: list[dt.date] = []
        for match in ROW_RE.finditer(body):
            row_year, month, day1, day2, _wdays, _venue = match.groups()
            row_year = int(row_year)
            month = int(month)
            day1 = int(day1)
            day2 = int(day2) if day2 else day1
            for day in range(day1, day2 + 1):
                actual_date = dt.date(row_year, month, day)
                section_dates.append(actual_date)
                dates.append(actual_date)

        lottery_block = re.search(r"### 抽選の日程\n\n(.*?)(?:\n### 公式ソース|\Z)", body, re.S)
        if not lottery_block:
            continue
        for match in LOTTERY_ROW_RE.finditer(lottery_block.group(1)):
            _lottery_type, period, _target = [x.strip() for x in match.groups()]
            period_dates = parse_lottery_period(period, section_dates)
            if not period_dates:
                continue
            start_date, end_date = period_dates
            dates.extend([start_date, end_date])

    if not dates:
        fallback_year = infer_source_year(text)
        return [month_start(fallback_year, 1)]

    return list(iter_month_starts(min(dates), max(dates)))


def build_holiday_lookup(display_months: list[dt.date], refresh: bool = False) -> dict[dt.date, dict[int, str]]:
    holiday_templates_by_year: dict[int, dict[int, dict[int, str]]] = {}
    for year in sorted({month.year for month in display_months}):
        holiday_templates_by_year[year] = load_or_fetch_holidays(
            year=year,
            template_path=get_holiday_template_path(year),
            refresh=refresh,
        )
    return {
        month_key: holiday_templates_by_year[month_key.year].get(month_key.month, {})
        for month_key in display_months
    }


def parse_summary_timeline(text: str, display_months: list[dt.date], holidays_by_month: dict[dt.date, dict[int, str]]):
    sections = re.split(r"^## ", text, flags=re.M)[1:]
    months = {month_key: empty_month_struct() for month_key in display_months}
    legend_live = {}
    legend_lottery = {}

    for section in sections:
        title, body = section.split("\n", 1)
        title = title.strip()
        source_block = re.search(r"### 公式ソース\n\n(.*?)(?:\n### |\Z)", body, re.S)
        section_sources = SOURCE_URL_RE.findall(source_block.group(1)) if source_block else []
        section_dates: list[dt.date] = []

        for match in ROW_RE.finditer(body):
            row_year, month, day1, day2, wdays, venue = match.groups()
            row_year = int(row_year)
            month = int(month)
            day1 = int(day1)
            day2 = int(day2) if day2 else day1
            venue = venue.strip()
            month_key = month_start(row_year, month)
            tag = live_calendar_label(title, venue)
            event_data = {
                "tag": tag,
                "range": f"{month:02d}/{day1:02d}〜{day2:02d}" if day1 != day2 else f"{month:02d}/{day1:02d}",
                "wdays": wdays.strip(),
                "title": title,
                "venue": venue,
                "sources": section_sources,
            }
            if month_key in months:
                months[month_key]["events"].append(event_data)
                months[month_key]["sources"].extend(section_sources)
            legend_live[tag] = f"{title} / {venue}"
            for day in range(day1, day2 + 1):
                actual_date = dt.date(row_year, month, day)
                section_dates.append(actual_date)
                actual_month_key = month_start(actual_date.year, actual_date.month)
                if actual_month_key not in months:
                    continue
                months[actual_month_key]["days"][day].append({"text": tag, "tone": tag, "kind": "live"})
                add_detail(months, actual_month_key, day, {
                    "label": f"LIVE: {title}",
                    "sub": f"会場: {venue}",
                    "meta": f"{row_year}/{event_data['range']} {event_data['wdays']}",
                    "sources": section_sources,
                })

        lottery_block = re.search(r"### 抽選の日程\n\n(.*?)(?:\n### 公式ソース|\Z)", body, re.S)
        if lottery_block:
            rows = list(LOTTERY_ROW_RE.finditer(lottery_block.group(1)))
            for match in rows:
                lottery_type, period, target = [x.strip() for x in match.groups()]
                short = LOTTERY_SHORT.get(lottery_type, lottery_type[:4])
                calendar_label = lottery_calendar_label(title)
                legend_lottery[short] = lottery_type
                start_chip_text, middle_chip_text, end_chip_text, start_detail_label, end_detail_label = lottery_phase_labels(calendar_label, title, lottery_type)
                period_dates = parse_lottery_period(period, section_dates)
                if not period_dates:
                    continue
                start_date, end_date = period_dates
                start_month_key = month_start(start_date.year, start_date.month)
                lottery_data = {"period": period, "title": title, "type": lottery_type, "target": target, "sources": section_sources}
                if start_month_key in months:
                    months[start_month_key]["lotteries"].append(lottery_data)
                for current_date in iter_date_range(start_date, end_date):
                    current_month_key = month_start(current_date.year, current_date.month)
                    if current_month_key not in months:
                        continue
                    if current_date == start_date:
                        item = {"text": start_chip_text, "tone": short, "kind": "lottery"}
                        detail_label = start_detail_label
                    elif current_date == end_date:
                        item = {"text": end_chip_text, "tone": short, "kind": "lottery"}
                        detail_label = end_detail_label
                    else:
                        item = {"text": middle_chip_text, "tone": short, "kind": "lottery_span"}
                        detail_label = start_detail_label
                    months[current_month_key]["days"][current_date.day].append(item)
                    add_detail(months, current_month_key, current_date.day, {
                        "label": detail_label,
                        "sub": f"対象: {target}" if target else title,
                        "meta": period,
                        "sources": section_sources,
                    })

    for month_key, holiday_map in holidays_by_month.items():
        if month_key not in months:
            continue
        for day in holiday_map:
            months[month_key]["days"][day].append({"text": "祝", "tone": "祝", "kind": "holiday"})

    for month_key in months:
        months[month_key]["sources"] = sorted(set(months[month_key]["sources"]))

    return months, legend_live, legend_lottery


def parse_summary(text: str, year: int):
    sections = re.split(r"^## ", text, flags=re.M)[1:]
    months = {m: empty_month_struct() for m in range(1, 13)}
    legend_live = {}
    legend_lottery = {}

    for section in sections:
        title, body = section.split("\n", 1)
        title = title.strip()
        source_block = re.search(r"### 公式ソース\n\n(.*?)(?:\n### |\Z)", body, re.S)
        section_sources = SOURCE_URL_RE.findall(source_block.group(1)) if source_block else []
        section_years = set()

        for match in ROW_RE.finditer(body):
            row_year, month, day1, day2, wdays, venue = match.groups()
            row_year = int(row_year)
            section_years.add(row_year)
            if row_year != year:
                continue
            month = int(month)
            day1 = int(day1)
            day2 = int(day2) if day2 else day1
            venue = venue.strip()
            tag = live_calendar_label(title, venue)
            event_data = {
                "tag": tag,
                "range": f"{month:02d}/{day1:02d}〜{day2:02d}" if day1 != day2 else f"{month:02d}/{day1:02d}",
                "wdays": wdays.strip(),
                "title": title,
                "venue": venue,
                "sources": section_sources,
            }
            months[month]["events"].append(event_data)
            months[month]["sources"].extend(section_sources)
            legend_live[tag] = f"{title} / {venue}"
            for day in range(day1, day2 + 1):
                months[month]["days"][day].append({"text": tag, "tone": tag, "kind": "live"})
                add_detail(months, month, day, {
                    "label": f"LIVE: {title}",
                    "sub": f"会場: {venue}",
                    "meta": f"{event_data['range']} {event_data['wdays']}",
                    "sources": section_sources,
                })

        lottery_block = re.search(r"### 抽選の日程\n\n(.*?)(?:\n### 公式ソース|\Z)", body, re.S)
        if lottery_block:
            if section_years and year not in section_years:
                continue
            rows = list(LOTTERY_ROW_RE.finditer(lottery_block.group(1)))
            if rows:
                for match in rows:
                    lottery_type, period, target = [x.strip() for x in match.groups()]
                    short = LOTTERY_SHORT.get(lottery_type, lottery_type[:4])
                    calendar_label = lottery_calendar_label(title)
                    legend_lottery[short] = lottery_type
                    start_chip_text, middle_chip_text, end_chip_text, start_detail_label, end_detail_label = lottery_phase_labels(calendar_label, title, lottery_type)
                    parsed = re.match(r"(\d{1,2})/(\d{1,2})\([^)]*\)(?:〜(?:(\d{1,2})/(\d{1,2})\([^)]*\)|))?", period)
                    if not parsed:
                        continue
                    start_month, start_day, end_month, end_day = parsed.group(1), parsed.group(2), parsed.group(3), parsed.group(4)
                    start_month = int(start_month)
                    start_day = int(start_day)
                    lottery_data = {"period": period, "title": title, "type": lottery_type, "target": target, "sources": section_sources}
                    months[start_month]["lotteries"].append(lottery_data)
                    months[start_month]["days"][start_day].append({"text": start_chip_text, "tone": short, "kind": "lottery"})
                    add_detail(months, start_month, start_day, {
                        "label": start_detail_label,
                        "sub": f"対象: {target}" if target else title,
                        "meta": period,
                        "sources": section_sources,
                    })
                    if end_month and end_day:
                        end_month = int(end_month)
                        end_day = int(end_day)
                        if end_month < start_month:
                            start_date = dt.date(year - 1, start_month, start_day)
                            end_date = dt.date(year, end_month, end_day)
                        else:
                            start_date = dt.date(year, start_month, start_day)
                            end_date = dt.date(year, end_month, end_day)
                        for current_date in iter_date_range(start_date + dt.timedelta(days=1), end_date - dt.timedelta(days=1)):
                            if current_date.year == year:
                                months[current_date.month]["days"][current_date.day].append({"text": middle_chip_text, "tone": short, "kind": "lottery_span"})
                                add_detail(months, current_date.month, current_date.day, {
                                    "label": start_detail_label,
                                    "sub": f"対象: {target}" if target else title,
                                    "meta": period,
                                    "sources": section_sources,
                                })
                        if end_date.year == year:
                            months[end_month]["days"][end_day].append({"text": end_chip_text, "tone": short, "kind": "lottery"})
                            add_detail(months, end_month, end_day, {
                                "label": end_detail_label,
                                "sub": f"対象: {target}" if target else title,
                                "meta": period,
                                "sources": section_sources,
                            })
            else:
                for line in re.findall(r"^-\s+(.+)$", lottery_block.group(1), re.M):
                    months[11]["lotteries"].append({"period": line.strip(), "title": title, "type": "抽選", "target": "", "sources": section_sources})
                    add_detail(months, 11, 14, {
                        "label": f"抽選情報: {title}",
                        "sub": line.strip(),
                        "meta": "後日発表",
                        "sources": section_sources,
                    })

    for month, holiday_map in HOLIDAYS.items():
        for day, label in holiday_map.items():
            months[month]["days"][day].append({"text": "祝", "tone": "祝", "kind": "holiday"})

    for month in range(1, 13):
        months[month]["sources"] = sorted(set(months[month]["sources"]))

    return months, legend_live, legend_lottery


def build_markdown(months, legend_live, legend_lottery, year: int, display_months: list[dt.date] | None = None, holidays_by_month: dict[dt.date, dict[int, str]] | None = None) -> str:
    cell_w = 12
    cell_h = 5
    cal = calendar.Calendar(firstweekday=6)
    dow = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]

    if display_months is None:
        display_months = [month_start(year, month) for month in range(1, 13)]
        holidays_by_month = {month_key: HOLIDAYS.get(month_key.month, {}) for month_key in display_months}
        normalized_months = {month_key: months[month_key.month] for month_key in display_months}
    else:
        normalized_months = months
        holidays_by_month = holidays_by_month or {month_key: {} for month_key in display_months}

    def cell_lines(month_key: dt.date, day: int) -> List[str]:
        if day == 0:
            return [" " * cell_w for _ in range(cell_h)]
        tags = [item["text"] for item in merge_day_items(normalized_months[month_key]["days"][day])]
        lines = [str(day).rjust(2).ljust(cell_w)]
        for i in range(cell_h - 1):
            txt = tags[i] if i < len(tags) else ""
            lines.append(txt[:cell_w].ljust(cell_w))
        return lines

    lines = [
        "# 櫻坂46 ライブカレンダー",
        "",
        "Slack / Discord で崩れにくいよう、コードブロック内に月間カレンダーを置き、予定タグを各日付セルに直接入れた版です。",
        "",
        "## タグ凡例",
        "",
        "- LIVEタグ: " + " / ".join(f"`{k}`={v}" for k, v in legend_live.items()),
        "- 抽選タグ: 抽選は `開始` / `継続` / `締切`、販売系は `一般発売` / `一般発売中` / `先着受付` / `販売終了` を表記",
        "- 抽選コード: " + " / ".join(f"`{k}`={v}" for k, v in legend_lottery.items()),
        "- 祝日: 日付セル内は `祝` のみ表示（正式名はメモと詳細で保持）",
        "",
    ]

    for month_key in display_months:
        month_data = normalized_months[month_key]
        lines.append(f"## {month_key.year}-{month_key.month:02d}")
        lines.append("")
        lines.append("```text")
        lines.append(" ".join(day.center(cell_w) for day in dow))
        weeks = cal.monthdayscalendar(month_key.year, month_key.month)
        for wi, week in enumerate(weeks):
            block = [cell_lines(month_key, day) for day in week]
            for i in range(cell_h):
                lines.append("│".join(cell[i] for cell in block))
            if wi != len(weeks) - 1:
                lines.append("─" * (cell_w * 7 + 6))
        lines.append("```")
        lines.append("")

        if month_data["events"]:
            lines.append("### ライブ")
            lines.append("")
            for item in month_data["events"]:
                lines.append(f"- `{item['tag']}` {item['range']} {item['wdays']} — {item['title']} / {item['venue']}")
            lines.append("")

        holiday_items = holidays_by_month.get(month_key, {})
        lottery_items = month_data["lotteries"]
        if holiday_items or lottery_items:
            lines.append("### 抽選メモ・祝日")
            lines.append("")
            if holiday_items:
                lines.append("- 祝日: " + " / ".join(f"{month_key.month}/{day} {name}" for day, name in holiday_items.items()))
            seen = set()
            for note in lottery_items:
                key = (note["period"], note["title"], note["type"])
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"- {note['period']} {note['title']} {note['type']}")
            lines.append("")

    return "\n".join(lines)


def render_preview_image(months, fonts, year: int, display_months: list[dt.date] | None = None, holidays_by_month: dict[dt.date, dict[int, str]] | None = None) -> Path:
    cal = calendar.Calendar(firstweekday=6)
    columns = 3

    if display_months is None:
        display_months = [month_start(year, month) for month in range(1, 13)]
        holidays_by_month = {month_key: HOLIDAYS.get(month_key.month, {}) for month_key in display_months}
        normalized_months = {month_key: months[month_key.month] for month_key in display_months}
    else:
        normalized_months = months
        holidays_by_month = holidays_by_month or {month_key: {} for month_key in display_months}

    rows = max(1, (len(display_months) + columns - 1) // columns)
    width = 1500
    height = 2060 if len(display_months) == 12 else 100 + 28 + rows * 480 + (rows - 1) * 20
    gap_x = 18
    gap_y = 20
    outer_x = 24
    outer_top = 100
    outer_bottom = 28
    card_w = (width - outer_x * 2 - gap_x * (columns - 1)) // columns
    card_h = (height - outer_top - outer_bottom - gap_y * (rows - 1)) // rows
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    draw.text((36, 20), "櫻坂46 ライブカレンダー プレビュー", font=fonts["title"], fill=TEXT)
    draw.text((38, 60), "Python レンダリング / timeline preview", font=fonts["small"], fill=MUTED)

    for idx, month_key in enumerate(display_months):
        month_data = normalized_months[month_key]
        holiday_map = holidays_by_month.get(month_key, {})
        row = idx // columns
        col = idx % columns
        x = outer_x + col * (card_w + gap_x)
        y = outer_top + row * (card_h + gap_y)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=22, fill=WHITE, outline=LINE)
        draw.text((x + 16, y + 14), f"{month_key.year}年{month_key.month}月", font=fonts["month"], fill=TEXT)
        sub = "予定なし（祝日だけ確認用）" if not month_has_schedule(month_data) else "ライブ・抽選・祝日"
        draw.text((x + 16, y + 56), sub, font=fonts["small"], fill=MUTED)

        left = x + 16
        right = x + card_w - 16
        grid_top = y + 86
        grid_w = right - left
        col_w = grid_w / 7
        row_h = 28
        for i, label in enumerate(["日", "月", "火", "水", "木", "金", "土"]):
            draw.text((left + i * col_w + 6, grid_top - 20), label, font=fonts["chip"], fill=MUTED)
        weeks = cal.monthdayscalendar(month_key.year, month_key.month)
        for r, week in enumerate(weeks):
            top = grid_top + r * row_h
            draw.line((left, top, left + grid_w, top), fill=LINE, width=1)
            for c, day in enumerate(week):
                x0 = left + c * col_w
                if c:
                    draw.line((x0, top, x0, top + row_h), fill=LINE, width=1)
                if not day:
                    continue
                is_holiday = day in holiday_map
                draw.text((x0 + 3, top + 3), str(day), font=fonts["chip"], fill=RGB_TONE["祝"] if is_holiday else TEXT)
                items = merge_day_items(month_data["days"][day])[:1]
                if items:
                    fill = RGB_TONE.get(items[0]["tone"], RGB_TONE["情報"])
                    chip_x = x0 + 20
                    chip_w = min(col_w - 24, 58)
                    draw.rounded_rectangle((chip_x, top + 3, chip_x + chip_w, top + 16), radius=7, fill=fill)
                    draw.text((chip_x + 4, top + 2), items[0]["text"][:8], font=fonts["chip"], fill=(255, 255, 255))
        draw.line((left, grid_top + len(weeks) * row_h, left + grid_w, grid_top + len(weeks) * row_h), fill=LINE, width=1)

        info_y = y + card_h - 34
        if month_data["events"]:
            event_tags = " / ".join(item["tag"] for item in month_data["events"][:3])
            draw.text((x + 16, info_y), f"LIVE: {event_tags}", font=fonts["note"], fill=MUTED)
        elif holiday_map:
            holis = " / ".join(holiday_map.values())
            draw.text((x + 16, info_y), f"祝日: {holis}", font=fonts["note"], fill=MUTED)
        else:
            draw.text((x + 16, info_y), "予定なし", font=fonts["note"], fill=MUTED)

    LONG_PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    img = img.convert("RGB")
    img.save(LONG_PREVIEW, format="JPEG", quality=92, optimize=True, progressive=True)
    return LONG_PREVIEW


def render_html(months, legend_live, legend_lottery, year: int | None = None, display_months: list[dt.date] | None = None, holidays_by_month: dict[dt.date, dict[int, str]] | None = None) -> str:
    legacy_mode = display_months is None
    if legacy_mode:
        assert year is not None
        display_months = [month_start(year, month) for month in range(1, 13)]
        holidays_by_month = {month_key: HOLIDAYS.get(month_key.month, {}) for month_key in display_months}
        normalized_months = {month_key: months[month_key.month] for month_key in display_months}
    else:
        normalized_months = months
        holidays_by_month = holidays_by_month or {month_key: {} for month_key in display_months}

    month_nav = "".join(
        f"<a href='#m{month_key.month:02d}'>{month_key.month}月</a>" if legacy_mode else f"<a href='#m{month_key.year}{month_key.month:02d}'>{month_key.year}/{month_key.month:02d}</a>"
        for month_key in display_months
    )
    detail_payload = {}
    cards = []

    for month_key in display_months:
        month_data = normalized_months[month_key]
        year_value = month_key.year
        month_value = month_key.month
        holiday_map = holidays_by_month.get(month_key, {})
        first = calendar.monthrange(year_value, month_value)[0]
        sunday_first = (first + 1) % 7
        total = calendar.monthrange(year_value, month_value)[1]
        cells = []
        for _ in range(sunday_first):
            cells.append("<div class='day-cell empty'></div>")
        for day in range(1, total + 1):
            items = merge_day_items(month_data["days"][day])[:3]
            span_items = [item for item in month_data["days"][day] if item["kind"] == "lottery_span"]
            chips = "".join(
                f"<div class='chip tone-{html.escape(HTML_TONE.get(item['tone'], 'ticket'))}' data-mobile-text='{html.escape(mobile_chip_text(item['text']))}' aria-label='{html.escape(item['text'])}'><span class='chip-text'>{html.escape(item['text'])}</span></div>"
                for item in items
            )
            span_html = ""
            if span_items:
                span_tone = html.escape(HTML_TONE.get(span_items[0]["tone"], "ticket"))
                span_label = html.escape(span_items[0]["text"])
                span_html = f"<div class='lottery-span' data-span-tone='{span_tone}' aria-label='{span_label}'></div>"
            panel_id = f"m{month_value:02d}" if legacy_mode else f"m{year_value}{month_value:02d}"
            detail_key = f"{panel_id}-d{day:02d}"
            details = month_data["detail_map"][day]
            if details:
                detail_payload[detail_key] = {"date": f"{year_value}/{month_value:02d}/{day:02d}", "items": details}
                cells.append(
                    f"<a class='day-cell clickable' href='#{panel_id}-detail' data-month='{panel_id}' data-detail-key='{detail_key}'>"
                    f"<div class='day-num'>{day}</div>{span_html}<div class='chips'>{chips}</div></a>"
                )
            else:
                cells.append(f"<div class='day-cell'><div class='day-num'>{day}</div>{span_html}<div class='chips'>{chips}</div></div>")
        while len(cells) % 7 != 0:
            cells.append("<div class='day-cell empty'></div>")

        live_items = "".join(
            f"<div class='meta-item'>{html.escape(item['tag'])}  {html.escape(item['range'])} {html.escape(item['wdays'])}  {html.escape(item['title'])} / {html.escape(item['venue'])}</div>"
            for item in month_data["events"]
        ) or "<div class='meta-item'>この月のライブ予定なし</div>"

        seen = set()
        lot_items = []
        for item in month_data["lotteries"]:
            key = (item["period"], item["title"], item["type"])
            if key in seen:
                continue
            seen.add(key)
            lot_items.append(f"<div class='meta-item'>{html.escape(item['period'])}  {html.escape(item['title'])}  {html.escape(item['type'])}</div>")
        lot_html = "".join(lot_items) or "<div class='meta-item'>この月の抽選メモなし</div>"

        collapsed = " collapsed" if not month_has_schedule(month_data) else ""
        open_attr = "" if not month_has_schedule(month_data) else " open"
        month_heading = f"{month_value}月"
        live_count = len(month_data["events"])
        lot_count = len(lot_items)
        cards.append(
            f"""
<details class='month-card{collapsed}' id='{'m' + f'{month_value:02d}' if legacy_mode else 'm' + f'{year_value}{month_value:02d}'}'{open_attr}>
  <summary class='month-summary'>
    <div class='month-header'>
      <div class='month-title'>{year_value}年{month_value}月</div>
      <div class='month-sub'>{'予定なし（祝日だけ確認用）' if not month_has_schedule(month_data) else ''}</div>
    </div>
  </summary>
  <div class='month-body'>
    <div class='weekdays'>{''.join(f"<div class='weekday{' weekend' if i in (0, 6) else ''}'>{d}</div>" for i, d in enumerate(['日', '月', '火', '水', '木', '金', '土']))}</div>
    <div class='grid'>{''.join(cells)}</div>
    <div class='day-detail' id='{'m' + f'{month_value:02d}' if legacy_mode else 'm' + f'{year_value}{month_value:02d}'}-detail' data-panel-month='{'m' + f'{month_value:02d}' if legacy_mode else 'm' + f'{year_value}{month_value:02d}'}'>
      <div class='detail-title'>日付をタップすると詳細を表示</div>
      <div class='detail-list'></div>
      <div class='detail-sections is-hidden'>
        <details class='meta-fold'>
          <summary><span>{month_heading}のライブ情報</span><span class='meta-count'>{live_count}件</span></summary>
          <div class='meta-list'>{live_items}</div>
        </details>
        <details class='meta-fold'>
          <summary><span>{month_heading}のチケット情報</span><span class='meta-count'>{lot_count}件</span></summary>
          <div class='meta-list'>{lot_html}</div>
        </details>
      </div>
    </div>
  </div>
</details>"""
        )

    detail_json = json.dumps(detail_payload, ensure_ascii=False)
    return f"""<!doctype html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>櫻坂46 ライブカレンダー</title>
<style>
:root {{--bg:#f6f6f3;--card:#ffffff;--line:#e7e5de;--text:#1e1e1c;--muted:#6f6f6a;--live:#14866d;--ticket:#5b6ef0;--holiday:#e5484d;}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;background:var(--bg);color:var(--text)}}
.page{{max-width:1200px;margin:0 auto;padding:20px 14px 60px}} .hero{{margin-bottom:18px}} .hero h1{{margin:0;font-size:clamp(32px,4.2vw,52px);letter-spacing:-.04em}} .hero p{{margin:10px 0 0;color:var(--muted);font-size:15px;line-height:1.7;max-width:72ch}}
.legend{{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:16px 18px;box-shadow:0 16px 40px rgba(30,30,28,.06);margin-bottom:18px}} .legend h2{{font-size:18px;margin:0 0 10px}} .legend-row{{color:var(--muted);font-size:14px;line-height:1.75}} .legend-meaning{{display:flex;flex-wrap:wrap;gap:10px 14px;margin-top:10px}} .legend-item{{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-size:13px;line-height:1.4}} .legend-chip{{display:inline-block;width:12px;height:12px;border-radius:999px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.35)}}
.month-nav{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}} .month-nav a{{text-decoration:none;color:var(--text);background:var(--card);border:1px solid var(--line);padding:8px 12px;border-radius:999px;font-size:14px;box-shadow:0 8px 20px rgba(30,30,28,.04)}}
.month-list{{display:grid;gap:18px}} .month-card{{background:var(--card);border:1px solid var(--line);border-radius:30px;box-shadow:0 18px 44px rgba(30,30,28,.05);overflow:hidden}} .month-summary{{list-style:none;cursor:pointer;padding:20px 18px}} .month-summary::-webkit-details-marker{{display:none}} .month-card.collapsed .month-summary{{background:rgba(0,0,0,.01)}}
.month-header{{display:flex;align-items:flex-end;justify-content:space-between;gap:12px}} .month-title{{font-size:40px;line-height:1;letter-spacing:-.05em;font-weight:700}} .month-sub{{color:var(--muted);font-size:13px}}
.month-body{{padding:0 16px 16px}} .weekdays,.grid{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}} .weekdays{{margin:0 0 6px}} .weekday{{text-align:center;color:var(--muted);font-size:13px;padding:4px 0}} .weekday.weekend{{color:var(--muted)}}
.day-cell{{position:relative;min-height:96px;border-top:1px solid var(--line);border-left:1px solid var(--line);padding:6px;display:flex;flex-direction:column;gap:4px;background:#fff;text-align:left;overflow:hidden}} .day-cell:nth-child(7n+1){{border-left:none}} .day-cell.empty{{background:rgba(0,0,0,.012)}}
.day-cell.clickable{{cursor:pointer;transition:transform .18s ease, background .18s ease, box-shadow .18s ease, border-color .18s ease;position:relative;border-radius:14px;background:linear-gradient(180deg,#fff,#f8f8f5);border:1px solid rgba(231,229,222,.82);-webkit-tap-highlight-color:transparent;touch-action:manipulation;text-decoration:none;color:inherit;outline:none;appearance:none;-webkit-appearance:none}} .day-cell.clickable::after{{content:'';position:absolute;left:8px;right:8px;top:6px;height:1px;border-radius:999px;background:rgba(255,255,255,.5);pointer-events:none}} .day-cell.clickable:hover{{background:#faf9f6;transform:translateY(-1px);border-color:rgba(231,229,222,.9);box-shadow:0 2px 6px rgba(30,30,28,.02)}} .day-cell.clickable:active{{transform:scale(.992)}} .day-cell.clickable:focus-visible{{box-shadow:inset 0 0 0 2px rgba(91,110,240,.28),0 0 0 3px rgba(91,110,240,.10)}} .day-cell.active{{background:#f3f5ff;box-shadow:inset 0 0 0 2px rgba(93,119,255,.22);border-color:rgba(93,119,255,.18)}}
.day-num{{font-size:19px;line-height:1;letter-spacing:-.03em}} .chips{{display:flex;flex-direction:column;gap:4px;min-width:0}} .chip{{align-self:stretch;padding:3px 7px 4px;border-radius:10px;color:#fff;font-size:11px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .chip-text{{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.lottery-span{{position:absolute;left:6px;right:6px;top:30px;height:8px;border-radius:999px;opacity:.3;pointer-events:none}} .lottery-span[data-span-tone='live']{{background:var(--live)}} .lottery-span[data-span-tone='ticket']{{background:var(--ticket)}} .lottery-span[data-span-tone='holiday']{{background:var(--holiday)}}
.tone-live{{background:var(--live)}} .tone-ticket{{background:var(--ticket)}} .tone-holiday{{background:var(--holiday)}}
.day-detail{{margin-top:18px;border:1px solid var(--line);border-radius:22px;padding:16px 16px 14px;background:linear-gradient(180deg,#fcfcfa,#f8f8f5);box-shadow:0 10px 24px rgba(30,30,28,.04);scroll-margin-top:18vh}} .detail-title{{display:inline-flex;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;border-radius:999px;background:rgba(91,110,240,.08);color:#3644a8;font-size:15px;font-weight:700;letter-spacing:-.01em}} .detail-list{{display:grid;gap:8px}} .detail-item{{border-top:1px solid rgba(0,0,0,.05);padding-top:8px}} .detail-item:first-child{{border-top:none;padding-top:0}} .detail-label{{font-size:14px;font-weight:600}} .detail-sub,.detail-meta,.detail-source{{font-size:13px;color:var(--muted);line-height:1.6}} .detail-source a{{color:inherit}}
.detail-sections{{display:grid;gap:10px;margin-top:16px;padding-top:14px;border-top:1px solid rgba(0,0,0,.06)}} .detail-sections.is-hidden{{display:none}} .meta-fold{{border:1px solid rgba(0,0,0,.06);border-radius:16px;background:rgba(255,255,255,.72);overflow:hidden}} .meta-fold summary{{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;font-size:14px;font-weight:600}} .meta-fold summary::-webkit-details-marker{{display:none}} .meta-count{{color:var(--muted);font-size:12px;font-weight:500}} .meta-fold .meta-list{{padding:0 14px 14px}} .meta-list{{display:grid;gap:8px;color:var(--muted);font-size:14px}} .meta-item{{line-height:1.6}}
@media (min-width:900px){{.page{{max-width:1080px}} .detail-sections{{grid-template-columns:1.15fr 1fr}}}} @media (max-width:720px){{.page{{padding:16px 10px 42px}} .month-summary{{padding:16px 12px}} .month-body{{padding:0 10px 14px}} .month-card{{border-radius:24px}} .month-title{{font-size:34px}} .day-cell{{min-height:88px;padding:5px}} .day-num{{font-size:17px}} .chip{{padding:2px 4px 3px;font-size:9px;line-height:1.05;letter-spacing:-.02em}} .legend-row{{font-size:13px}} .day-detail{{scroll-margin-top:14vh}}}} @media (max-width:520px){{.chip::before{{content:attr(data-mobile-text)}} .chip-text{{display:none}}}} @media (hover:none), (pointer:coarse){{.day-cell.clickable{{transition:none}} .day-cell.clickable:hover{{transform:none;box-shadow:none;background:linear-gradient(180deg,#fff,#f8f8f5)}} .day-cell.clickable:active{{transform:none}}}}
</style>
</head>
<body>
<div class='page'>
  <section class='hero'>
    <h1>櫻坂46 ライブカレンダー</h1>
    <p>5th YEAR ANNIVERSARY LIVE以降のライブ情報を、見やすく整理してまとめています。</p>
  </section>
  <section class='legend'>
    <div class='legend-row'>ライブ一覧: {html.escape(' / '.join(legend_live.keys()))}</div>
    <div class='legend-meaning'>
      <div class='legend-item'><span>色分け: </span><span class='legend-chip tone-live' aria-hidden='true'></span><span>ライブ開催日</span><span class='legend-chip tone-ticket' aria-hidden='true'></span><span>チケット抽選</span></div>
    </div>
  </section>
  <nav class='month-nav'>{month_nav}</nav>
  <section class='month-list'>{''.join(cards)}</section>
</div>
<script>
const detailData = {detail_json};
const forceVisualRefresh = (...elements) => {{
  for (const element of elements) {{
    if (!element) continue;
    void element.offsetHeight;
  }}
  requestAnimationFrame(() => {{
    for (const element of elements) {{
      if (!element) continue;
      void element.offsetHeight;
    }}
  }});
}};
const closeDetailPanel = (panel) => {{
  if (!panel) return;
  const title = panel.querySelector('.detail-title');
  const list = panel.querySelector('.detail-list');
  const sections = panel.querySelector('.detail-sections');
  if (title) title.textContent = '日付をタップすると詳細を表示';
  if (list) list.innerHTML = '';
  if (sections) sections.classList.add('is-hidden');
}};
const maybeScrollToPanel = (panel, button) => {{
  if (!panel || !button) return;
  const panelRect = panel.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  const desiredTop = Math.min(Math.max(Math.round(viewportHeight * 0.27), 96), 220);
  const targetTop = Math.max(window.scrollY + panelRect.top - desiredTop, 0);
  const panelBelowFold = panelRect.top > viewportHeight - 140;
  const panelCutOff = panelRect.bottom > viewportHeight - 24;
  const panelStillBelowButton = panelRect.top > buttonRect.bottom + 20;
  if (!(panelBelowFold || panelCutOff || panelStillBelowButton)) return;
  window.scrollTo({{ top: targetTop, behavior: 'smooth' }});
}};
let lastTouchToggleAt = 0;
const toggleDetailPanel = (button) => {{
  const month = button.dataset.month;
  const key = button.dataset.detailKey;
  const panel = document.querySelector(`.day-detail[data-panel-month='${{month}}']`);
  if (!panel) return;
  const payload = detailData[key] || {{date: '', items: []}};
  const title = panel.querySelector('.detail-title');
  const list = panel.querySelector('.detail-list');
  const sections = panel.querySelector('.detail-sections');
  if (button.classList.contains('active')) {{
    button.classList.remove('active');
    closeDetailPanel(panel);
    history.replaceState(null, '', `#${{month}}`);
    forceVisualRefresh(panel, button);
    return;
  }}
  const monthBody = button.closest('.month-body');
  if (monthBody) {{
    for (const candidate of monthBody.querySelectorAll('.day-cell.clickable.active')) {{
      if (candidate !== button) candidate.classList.remove('active');
    }}
  }}
  title.textContent = payload.date ? `${{payload.date}} の詳細` : '日付をタップすると詳細を表示';
  list.innerHTML = (payload.items || []).map((item) => {{
    const sources = (item.sources || []).map((url) => `<div class='detail-source'><a href='${{url}}' target='_blank' rel='noreferrer'>${{url}}</a></div>`).join('');
    return `<div class='detail-item'>`
      + `<div class='detail-label'>${{item.label || ''}}</div>`
      + `<div class='detail-sub'>${{item.sub || ''}}</div>`
      + `<div class='detail-meta'>${{item.meta || ''}}</div>`
      + sources
      + `</div>`;
  }}).join('');
  if (sections) sections.classList.remove('is-hidden');
  button.classList.add('active');
  history.replaceState(null, '', `#${{key}}`);
  forceVisualRefresh(panel, monthBody, button);
  requestAnimationFrame(() => {{
    maybeScrollToPanel(panel, button);
  }});
}};
for (const button of document.querySelectorAll('.day-cell.clickable')) {{
  button.addEventListener('click', (event) => {{
    event.preventDefault();
    if (Date.now() - lastTouchToggleAt < 700) return;
    toggleDetailPanel(button);
  }});
  button.addEventListener('touchend', (event) => {{
    event.preventDefault();
    if (Date.now() - lastTouchToggleAt < 700) return;
    lastTouchToggleAt = Date.now();
    toggleDetailPanel(button);
  }});
}}
</script>
</body>
</html>"""


def render_workflow(display_months: list[dt.date] | int, holiday_template_paths: list[Path] | Path) -> str:
    if isinstance(display_months, int):
        display_months = [month_start(display_months, month) for month in range(1, 13)]
    if isinstance(holiday_template_paths, Path):
        holiday_template_paths = [holiday_template_paths]
    last_month = display_months[-1]
    holiday_lines = "\n".join(f"  - `{path.relative_to(BASE_DIR)}`" for path in holiday_template_paths)
    return f"""# sakurazaka schedule workflow

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
- 現在検出している最終月: `{last_month.year}年{last_month.month}月`

## 祝日データ

- 新しい年を初めて扱うときだけ、内閣府の祝日CSVを取得する。
  - `{HOLIDAY_CSV_URL}`
- 取得結果は再利用用テンプレートとして保存する。
{holiday_lines}
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
- プレビュー画像は Python 生成の JPG（`--output-preview` 指定時のみ `summary/` に出力）
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
`summary/sakurazaka46_live_summary.md` を source of truth として扱う。
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
"""


def main(argv: list[str] | None = None) -> None:
    global HOLIDAYS

    args = parse_args(argv)

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    source_text = SOURCE_MD.read_text()
    display_months = collect_display_months(source_text)
    holidays_by_month = build_holiday_lookup(display_months, refresh=args.refresh_holidays)
    holiday_template_paths = [get_holiday_template_path(year) for year in sorted({month.year for month in display_months})]
    latest_year = display_months[-1].year
    HOLIDAYS = load_holiday_template(get_holiday_template_path(latest_year)) or empty_holiday_map()

    months, legend_live, legend_lottery = parse_summary_timeline(source_text, display_months, holidays_by_month)

    if args.output_calendar_md:
        OUTPUT_MD.write_text(build_markdown(months, legend_live, legend_lottery, latest_year, display_months=display_months, holidays_by_month=holidays_by_month))
    elif OUTPUT_MD.exists():
        OUTPUT_MD.unlink()
    OUTPUT_HTML.write_text(render_html(months, legend_live, legend_lottery, display_months=display_months, holidays_by_month=holidays_by_month))
    WORKFLOW_MD.write_text(render_workflow(display_months, holiday_template_paths))
    if LEGACY_WORKFLOW_MD.exists():
        LEGACY_WORKFLOW_MD.unlink()

    preview = None
    if args.output_preview:
        fonts = load_fonts()
        preview = render_preview_image(months, fonts, latest_year, display_months=display_months, holidays_by_month=holidays_by_month)

    if args.output_calendar_md:
        print(f"markdown: {OUTPUT_MD.relative_to(BASE_DIR)}")
    print(f"html: {OUTPUT_HTML.relative_to(BASE_DIR)}")
    print(f"workflow: {WORKFLOW_MD.relative_to(BASE_DIR)}")
    if preview is not None:
        print(f"preview: {preview.relative_to(BASE_DIR)}")
    print("holiday_templates:")
    for path in holiday_template_paths:
        print(f"  - {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
