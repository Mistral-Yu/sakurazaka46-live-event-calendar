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

SOURCE_MD = SUMMARY_DIR / "sakurazaka46_live_summary.md"
EVENT_SOURCE_MD = SUMMARY_DIR / "sakurazaka46_event_summary.md"
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
    "FC2": "ticket", "先行": "ticket", "先着": "ticket", "三井": "ticket", "先行2": "ticket", "祝": "holiday", "情報": "ticket", "deadline": "deadline",
    "メッセージ": "live", "メッセージキャンペーン": "ticket", "CD": "live", "CD応募": "ticket", "ミーグリ": "live", "リアルミーグリ": "live",
    "ミーグリ応募": "ticket", "イベント": "live", "イベント応募": "ticket", "応募": "ticket", "発売": "live", "発売日": "live",
    "live": "live", "live開催": "live", "event開催": "live", "live抽選": "ticket", "event応募": "ticket",
    "ライブ開催": "live", "イベント開催": "live", "ライブ抽選": "ticket", "イベント応募": "ticket",
    "live締切": "deadline", "締切": "deadline", "live抽選締切": "deadline", "event応募締切": "deadline",
    "ライブ抽選締切": "deadline", "イベント応募締切": "deadline",
}

RGB_TONE = {
    "バックスライブ": (232, 163, 195), "四期生ライブ": (232, 163, 195), "静岡公演": (232, 163, 195), "神戸公演": (232, 163, 195),
    "広島公演": (232, 163, 195), "千葉公演": (232, 163, 195), "宮城公演": (232, 163, 195), "香川公演": (232, 163, 195),
    "アニラ": (232, 163, 195), "ジャイガ": (232, 163, 195), "FC": (91, 110, 240), "LeminoS": (91, 110, 240), "LeminoP": (91, 110, 240),
    "イオン": (91, 110, 240), "一般": (91, 110, 240), "FC2": (91, 110, 240), "先行": (91, 110, 240),
    "先着": (91, 110, 240), "三井": (91, 110, 240), "先行2": (91, 110, 240), "祝": (201, 183, 255), "情報": (91, 110, 240), "deadline": (220, 88, 104),
    "メッセージ": (232, 163, 195), "メッセージキャンペーン": (91, 110, 240), "CD": (232, 163, 195), "CD応募": (91, 110, 240),
    "ミーグリ": (232, 163, 195), "リアルミーグリ": (232, 163, 195), "ミーグリ応募": (91, 110, 240), "イベント": (232, 163, 195), "イベント応募": (91, 110, 240),
    "応募": (91, 110, 240), "event応募": (91, 110, 240), "イベント応募": (91, 110, 240), "発売": (232, 163, 195), "発売日": (232, 163, 195),
    "ライブ開催": (232, 163, 195), "イベント開催": (232, 163, 195), "ライブ抽選": (91, 110, 240),
    "live抽選締切": (220, 88, 104), "event応募締切": (220, 88, 104),
    "ライブ抽選締切": (220, 88, 104), "イベント応募締切": (220, 88, 104),
}

HOLIDAYS = {month: {} for month in range(1, 13)}

BG = (248, 248, 246)
WHITE = (255, 255, 255)
LINE = (226, 226, 222)
TEXT = (28, 28, 28)
MUTED = (120, 120, 120)


def empty_holiday_map() -> dict[int, dict[int, str]]:
    return {month: {} for month in range(1, 13)}


def get_today() -> dt.date:
    return dt.date.today()


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
    return SCRIPT_DIR / "holidays_template.json"


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
        if item.get("kind") not in {"lottery", "lottery_span", "all_event"}:
            merged.append(item)
            continue

        key = (item["kind"], item.get("text", ""))
        if key not in grouped:
            grouped[key] = dict(item)
            merged.append(grouped[key])
    return merged


def mobile_chip_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def mobile_chip_lines(text: str) -> list[str]:
    compact = mobile_chip_text(text)
    if len(compact) <= 4:
        return [compact]
    split_at = (len(compact) + 1) // 2
    return [compact[:split_at], compact[split_at:]]


def render_chip_html(item: dict[str, str]) -> str:
    text = item["text"]
    compact = mobile_chip_text(text)
    mobile_lines = "".join(f"<span>{html.escape(line)}</span>" for line in mobile_chip_lines(text))
    tone = html.escape(HTML_TONE.get(item["tone"], "ticket"))
    return (
        f"<div class='chip tone-{tone}' data-mobile-text='{html.escape(compact)}' aria-label='{html.escape(text)}'>"
        f"<span class='chip-text'>{html.escape(text)}</span>"
        f"<span class='chip-mobile-text' aria-hidden='true'>{mobile_lines}</span>"
        f"</div>"
    )


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


def continuous_display_months(months: list[dt.date]) -> list[dt.date]:
    if not months:
        return []
    return list(iter_month_starts(min(months), max(months)))


def summarize_all_day_item(item: dict, source_mode: str) -> dict | None:
    kind = item.get("kind")
    if kind == "holiday":
        return None
    return dict(item)


def build_all_months(
    live_months: dict,
    event_months: dict,
    display_months: list[dt.date],
    holidays_by_month: dict[dt.date, dict[int, str]],
) -> dict:
    all_months = {month_key: empty_month_struct() for month_key in display_months}
    for source_mode, source_months in (("live", live_months), ("event", event_months)):
        for month_key, source in source_months.items():
            if month_key not in all_months:
                continue
            target = all_months[month_key]
            target["events"].extend(source["events"])
            target["lotteries"].extend(source["lotteries"])
            target["sources"].extend(source["sources"])
            for day, items in source["days"].items():
                for item in items:
                    summarized = summarize_all_day_item(item, source_mode)
                    if summarized is not None:
                        target["days"][day].append(summarized)
            for day, details in source["detail_map"].items():
                target["detail_map"][day].extend(details)
    for month_key, holiday_map in holidays_by_month.items():
        if month_key not in all_months:
            continue
        for day in holiday_map:
            all_months[month_key]["days"][day].append({"text": "祝", "tone": "祝", "kind": "holiday"})
    for month_key in all_months:
        all_months[month_key]["sources"] = sorted(set(all_months[month_key]["sources"]))
    return all_months


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
    return f"{calendar_label}開始", f"{calendar_label}中", f"{calendar_label}締切", detail_label, detail_label


def iter_date_range(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


JAPANESE_WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")


def month_start(year: int, month: int) -> dt.date:
    return dt.date(year, month, 1)


def format_detail_date(year: int, month: int, day: int) -> str:
    date_value = dt.date(year, month, day)
    return f"{date_value:%Y/%m/%d} ({JAPANESE_WEEKDAYS[date_value.weekday()]})"


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



def extract_iso_dates(text: str) -> list[dt.date]:
    dates: list[dt.date] = []
    for year, month, day in re.findall(r"(\d{4})-(\d{2})-(\d{2})", text):
        try:
            dates.append(dt.date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return dates


def collect_event_display_months(text: str) -> list[dt.date]:
    dates = extract_iso_dates(text)
    event_start = dt.date(2026, 4, 1)
    dates = [date_value for date_value in dates if date_value >= event_start]
    if not dates:
        fallback_year = DEFAULT_YEAR
        year_match = re.search(r"(\d{4})", text)
        if year_match:
            fallback_year = int(year_match.group(1))
        return [month_start(fallback_year, 1)]
    return list(iter_month_starts(min(dates), max(dates)))


def event_tag(category: str, title: str) -> str:
    joined = f"{category} {title}"
    if "リアル" in joined and ("ミーグリ" in joined or "ミート＆グリート" in joined):
        return "リアルミーグリ"
    if "ミーグリ" in joined or "ミート＆グリート" in joined:
        return "ミーグリ"
    if "シングル" in joined or "CD" in joined or "購入者" in joined:
        return "CD"
    if "メッセージ" in joined:
        return "メッセージ"
    return "イベント"


def format_event_range(start: dt.date, end: dt.date | None = None) -> str:
    if end is None or end == start:
        return f"{start:%m/%d}"
    if start.year == end.year and start.month == end.month:
        return f"{start:%m/%d}〜{end.day:02d}"
    return f"{start:%m/%d}〜{end:%m/%d}"


def event_period_label(tag: str, text: str) -> str:
    joined = f"{tag} {text}"
    if "CD" in joined or "シリアル" in joined or "購入者" in joined:
        return "CD応募"
    if "リアル" in joined and ("ミーグリ" in joined or "ミート＆グリート" in joined):
        return "ミーグリ応募"
    if "応募" in joined or "期限" in joined or "締切" in joined:
        return f"{tag}応募"
    if tag == "メッセージ":
        return "メッセージキャンペーン"
    return tag


def event_single_date_label(tag: str, title: str, venue: str = "") -> str:
    joined = f"{title} {venue}"
    if "発売日" in joined:
        return "発売日"
    if tag == "ミーグリ" and "リアル" in joined:
        return "リアルミーグリ"
    if tag == "メッセージ":
        return "メッセージキャンペーン"
    return tag


def parse_event_period(period: str, section_dates: list[dt.date]) -> tuple[dt.date, dt.date] | None:
    full_dates = extract_iso_dates(period)
    if full_dates:
        return full_dates[0], full_dates[-1]
    return parse_lottery_period(period, section_dates)


def event_calendar_label(title: str, venue: str) -> str:
    return event_single_date_label(event_tag("", title), title, venue)


def is_long_event_period(start: dt.date, end: dt.date) -> bool:
    return (end - start).days >= 13


def mark_long_event_chip(chip: str, is_long: bool) -> str:
    return f"長期{chip}" if is_long else chip


def event_chip_tone_label(chip: str) -> str:
    tone_label = chip[2:] if chip.startswith("長)") else chip
    tone_label = tone_label[2:] if tone_label.startswith("長期") else tone_label
    return re.sub(r"(開始|中|締切)$", "", tone_label)


def is_message_campaign_application_chip(label: str) -> bool:
    clean_label = label[2:] if label.startswith("長)") else label
    clean_label = clean_label[2:] if clean_label.startswith("長期") else clean_label
    return (
        event_chip_tone_label(label) == "メッセージキャンペーン"
        and clean_label.endswith(("開始", "締切"))
    )


def add_event_day(months: dict, date_value: dt.date, label: str, title: str, sub: str, meta: str, sources: list[str]) -> None:
    month_key = month_start(date_value.year, date_value.month)
    if month_key not in months:
        return
    tone_label = event_chip_tone_label(label)
    is_application = is_message_campaign_application_chip(label)
    day_kind = "lottery" if is_application else "event"
    detail_prefix = "応募" if is_application else "EVENT"
    if is_application and label.endswith("締切"):
        tone_label = "deadline"
    months[month_key]["days"][date_value.day].append({"text": label, "tone": tone_label, "kind": day_kind})
    add_detail(months, month_key, date_value.day, {
        "label": f"{detail_prefix}: {title}",
        "sub": sub,
        "meta": meta,
        "sources": sources,
    })


def parse_event_summary_timeline(text: str, display_months: list[dt.date], holidays_by_month: dict[dt.date, dict[int, str]]):
    sections = re.split(r"^## ", text, flags=re.M)[1:]
    months = {month_key: empty_month_struct() for month_key in display_months}
    legend_event: dict[str, str] = {}
    legend_dates: dict[str, str] = {}

    for section in sections:
        title, body = section.split("\n", 1)
        title = title.strip()
        if "公式ソースまとめ" in title:
            continue

        source_block = re.search(r"### 公式ソース\n\n(.*?)(?:\n### |\Z)", body, re.S)
        section_sources = SOURCE_URL_RE.findall(source_block.group(1)) if source_block else SOURCE_URL_RE.findall(body)
        section_dates: list[dt.date] = []
        base_tag = event_tag("", title)
        legend_event[base_tag] = title

        for match in ROW_RE.finditer(body):
            row_year, month, day1, day2, wdays, venue = match.groups()
            row_year = int(row_year)
            month = int(month)
            day1 = int(day1)
            day2 = int(day2) if day2 else day1
            venue = venue.strip()
            label = event_calendar_label(title, venue)
            start_date = dt.date(row_year, month, day1)
            end_date = dt.date(row_year, month, day2)
            month_key = month_start(row_year, month)
            event_data = {
                "tag": label,
                "range": format_event_range(start_date, end_date),
                "wdays": wdays.strip(),
                "title": title,
                "venue": venue,
                "sources": section_sources,
            }
            is_message_campaign_period = label == "メッセージキャンペーン" and start_date != end_date
            if month_key in months:
                if is_message_campaign_period:
                    months[month_key]["lotteries"].append({
                        "period": format_event_range(start_date, end_date),
                        "title": title,
                        "type": "メッセージキャンペーン",
                        "target": venue,
                        "sources": section_sources,
                    })
                else:
                    months[month_key]["events"].append(event_data)
                months[month_key]["sources"].extend(section_sources)
            legend_dates[label] = title
            is_long = is_long_event_period(start_date, end_date)
            for current_date in iter_date_range(start_date, end_date):
                section_dates.append(current_date)
                if label == "メッセージキャンペーン" and current_date not in {start_date, end_date}:
                    continue
                if start_date != end_date:
                    if current_date == start_date:
                        chip = f"{label}開始"
                    elif current_date == end_date:
                        chip = f"{label}締切"
                    else:
                        chip = f"{label}中"
                else:
                    chip = label
                add_event_day(
                    months,
                    current_date,
                    mark_long_event_chip(chip, is_long),
                    title,
                    venue,
                    f"{event_data['range']} {event_data['wdays']}",
                    section_sources,
                )

        lottery_block = re.search(r"### 抽選の日程\n\n(.*?)(?:\n### 公式ソース|\Z)", body, re.S)
        if lottery_block:
            for match in LOTTERY_ROW_RE.finditer(lottery_block.group(1)):
                lottery_type, period, target = [x.strip() for x in match.groups()]
                label = event_period_label(base_tag, f"{title} {lottery_type} {target}")
                legend_dates[label] = lottery_type
                period_dates = parse_event_period(period, section_dates or extract_iso_dates(body))
                if not period_dates:
                    continue
                start_date, end_date = period_dates
                is_long = is_long_event_period(start_date, end_date)
                summary_month_key = month_start(start_date.year, start_date.month)
                if summary_month_key not in months:
                    summary_month_key = month_start(end_date.year, end_date.month)
                if summary_month_key in months:
                    months[summary_month_key]["lotteries"].append({
                        "period": format_event_range(start_date, end_date),
                        "title": title,
                        "type": lottery_type,
                        "target": target,
                        "sources": section_sources,
                    })
                    months[summary_month_key]["sources"].extend(section_sources)
                for current_date in iter_date_range(start_date, end_date):
                    if label in {"CD応募", "メッセージキャンペーン"} and current_date not in {start_date, end_date}:
                        continue
                    is_single_day_deadline = start_date == end_date and ("期限" in lottery_type or "締切" in lottery_type)
                    if is_single_day_deadline:
                        chip = "支払い方法選択期限" if "支払い方法選択期限" in lottery_type else f"{label}締切"
                    elif current_date == start_date:
                        chip = f"{label}開始"
                    elif current_date == end_date:
                        chip = f"{label}締切"
                    else:
                        chip = f"{label}中"
                    current_month_key = month_start(current_date.year, current_date.month)
                    if current_month_key not in months:
                        continue
                    item_tone = "deadline" if current_date == end_date else label
                    months[current_month_key]["days"][current_date.day].append({"text": mark_long_event_chip(chip, is_long), "tone": item_tone, "kind": "lottery"})
                    add_detail(months, current_month_key, current_date.day, {
                        "label": f"応募: {title} {lottery_type}",
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
    return months, legend_event, legend_dates

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
                        start_tone = "deadline" if lottery_type == "一般発売" else short
                        item = {"text": start_chip_text, "tone": start_tone, "kind": "lottery"}
                        detail_label = start_detail_label
                    elif current_date == end_date:
                        item = {"text": end_chip_text, "tone": "deadline", "kind": "lottery"}
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
                    start_tone = "deadline" if lottery_type == "一般発売" else short
                    months[start_month]["days"][start_day].append({"text": start_chip_text, "tone": start_tone, "kind": "lottery"})
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
                            months[end_month]["days"][end_day].append({"text": end_chip_text, "tone": "deadline", "kind": "lottery"})
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
    active_css_rules = []
    today = get_today()
    page_title = getattr(render_html, "page_title", "櫻坂46 ライブカレンダー")
    hero_copy = getattr(render_html, "hero_copy", "5th YEAR ANNIVERSARY LIVE以降のライブ情報を、見やすく整理してまとめています。")
    list_label = getattr(render_html, "list_label", "ライブ一覧")
    live_meaning = getattr(render_html, "live_meaning", "開催")
    ticket_meaning = getattr(render_html, "ticket_meaning", "抽選")
    deadline_meaning = getattr(render_html, "deadline_meaning", "締切")
    primary_meta_label = getattr(render_html, "primary_meta_label", "ライブ情報")
    ticket_meta_label = getattr(render_html, "ticket_meta_label", "チケット情報")

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
            chips = "".join(render_chip_html(item) for item in items)
            panel_id = f"m{month_value:02d}" if legacy_mode else f"m{year_value}{month_value:02d}"
            detail_key = f"{panel_id}-d{day:02d}"
            details = month_data["detail_map"][day]
            is_today = today == dt.date(year_value, month_value, day)
            is_weekend = dt.date(year_value, month_value, day).weekday() in (5, 6)
            is_holiday = day in holiday_map
            day_classes = ["day-cell"]
            if is_today:
                day_classes.append("today")
            if is_weekend:
                day_classes.append("weekend")
            if is_holiday:
                day_classes.append("holiday")
            day_class = " ".join(day_classes)
            clickable_class = f"{day_class} clickable" if details else day_class
            if details:
                detail_payload[detail_key] = {"date": format_detail_date(year_value, month_value, day), "items": details}
                active_css_rules.append(
                    f".day-cell.clickable:has(.detail-target#{detail_key}:target){{background:#f3f5ff;box-shadow:inset 0 0 0 2px rgba(93,119,255,.22);border-color:rgba(93,119,255,.18)}}"
                )
                if is_today:
                    active_css_rules.append(
                        f".day-cell.clickable.today:has(.detail-target#{detail_key}:target){{background:rgba(201,183,255,.14);box-shadow:inset 0 0 0 1px rgba(201,183,255,.42), inset 0 0 0 2px rgba(93,119,255,.18);border-color:rgba(201,183,255,.48)}}"
                    )
                cells.append(
                    f"<a class='{clickable_class}' href='#{detail_key}' data-month='{panel_id}' data-detail-key='{detail_key}'>"
                    f"<span class='detail-target' id='{detail_key}' aria-hidden='true'></span><div class='day-num'>{day}</div><div class='chips'>{chips}</div></a>"
                )
            else:
                cells.append(f"<div class='{day_class}'><div class='day-num'>{day}</div><div class='chips'>{chips}</div></div>")
        while len(cells) % 7 != 0:
            cells.append("<div class='day-cell empty'></div>")

        live_items = "".join(
            f"<div class='meta-item'>{html.escape(item['tag'])}  {html.escape(item['range'])} {html.escape(item['wdays'])}  {html.escape(item['title'])} / {html.escape(item['venue'])}</div>"
            for item in month_data["events"]
        ) or f"<div class='meta-item'>この月の{html.escape(primary_meta_label)}なし</div>"

        seen = set()
        lot_items = []
        for item in month_data["lotteries"]:
            key = (item["period"], item["title"], item["type"])
            if key in seen:
                continue
            seen.add(key)
            lot_items.append(f"<div class='meta-item'>{html.escape(item['period'])}  {html.escape(item['title'])}  {html.escape(item['type'])}</div>")
        lot_html = "".join(lot_items) or f"<div class='meta-item'>この月の{html.escape(ticket_meta_label)}なし</div>"

        has_schedule = month_has_schedule(month_data)
        month_end = dt.date(year_value, month_value, total)
        is_past_month = month_end < today
        collapsed = " collapsed" if (not has_schedule or is_past_month) else ""
        open_attr = " open" if (has_schedule and not is_past_month) else ""
        month_heading = f"{month_value}月"
        live_count = len(month_data["events"])
        lot_count = len(lot_items)
        month_id = f"m{month_value:02d}" if legacy_mode else f"m{year_value}{month_value:02d}"
        cards.append(
            f"""
<details class='month-card{collapsed}' id='{month_id}' data-year='{year_value}' data-month-number='{month_value:02d}' data-has-schedule='{'true' if has_schedule else 'false'}'{open_attr}>
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
      <div class='detail-title'></div>
      <div class='detail-list'></div>
      <div class='detail-sections'>
        <details class='meta-fold'>
          <summary><span>{month_heading}の{primary_meta_label}</span><span class='meta-count'>{live_count}件</span></summary>
          <div class='meta-list'>{live_items}</div>
        </details>
        <details class='meta-fold'>
          <summary><span>{month_heading}の{ticket_meta_label}</span><span class='meta-count'>{lot_count}件</span></summary>
          <div class='meta-list'>{lot_html}</div>
        </details>
      </div>
    </div>
  </div>
</details>"""
        )

    detail_json = json.dumps(detail_payload, ensure_ascii=False)
    active_css = "".join(active_css_rules)
    page_title = getattr(render_html, "page_title", "櫻坂46 ライブカレンダー")
    hero_copy = getattr(render_html, "hero_copy", "5th YEAR ANNIVERSARY LIVE以降のライブ情報を、見やすく整理してまとめています。")
    list_label = getattr(render_html, "list_label", "ライブ一覧")
    live_meaning = getattr(render_html, "live_meaning", "開催")
    ticket_meaning = getattr(render_html, "ticket_meaning", "抽選")
    deadline_meaning = getattr(render_html, "deadline_meaning", "締切")
    primary_meta_label = getattr(render_html, "primary_meta_label", "ライブ情報")
    ticket_meta_label = getattr(render_html, "ticket_meta_label", "チケット情報")
    legend_row_html = (
        f"    <div class='legend-row'>{html.escape(list_label)}: {html.escape(' / '.join(legend_live.keys()))}</div>\n"
        if list_label
        else ""
    )
    return f"""<!doctype html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{html.escape(page_title)}</title>
<style>
:root {{--bg:#f6f6f3;--card:#ffffff;--line:#e7e5de;--text:#1e1e1c;--muted:#6f6f6a;--live:#e8a3c3;--ticket:#5b6ef0;--deadline:#dc5868;--event:#76955a;--holiday:#c9b7ff;--weekend:#d8505f;}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;background:var(--bg);color:var(--text)}}
.page{{max-width:1200px;margin:0 auto;padding:20px 14px 60px}} .hero{{margin-bottom:18px}} .hero h1{{margin:0;font-size:clamp(32px,4.2vw,52px);letter-spacing:-.04em}} .hero p{{margin:10px 0 0;color:var(--muted);font-size:15px;line-height:1.7;max-width:72ch}}
.legend{{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:16px 18px;box-shadow:0 16px 40px rgba(30,30,28,.06);margin-bottom:18px}} .legend h2{{font-size:18px;margin:0 0 10px}} .legend-row{{color:var(--muted);font-size:14px;line-height:1.75}} .legend-meaning{{display:flex;flex-wrap:wrap;gap:10px 14px;margin-top:10px}} .legend-item{{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-size:13px;line-height:1.4}} .legend-chip{{display:inline-block;width:12px;height:12px;border-radius:999px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.35)}}
.month-nav{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}} .month-nav a{{text-decoration:none;color:var(--text);background:var(--card);border:1px solid var(--line);padding:8px 12px;border-radius:999px;font-size:14px;box-shadow:0 8px 20px rgba(30,30,28,.04)}}
.month-list{{display:grid;gap:18px}} .month-card{{background:var(--card);border:1px solid var(--line);border-radius:30px;box-shadow:0 18px 44px rgba(30,30,28,.05);overflow:hidden;scroll-margin-top:14px}} .month-summary{{list-style:none;cursor:pointer;padding:20px 18px}} .month-summary::-webkit-details-marker{{display:none}} .month-card.collapsed .month-summary{{background:rgba(0,0,0,.01)}}
.month-header{{display:flex;align-items:flex-end;justify-content:space-between;gap:12px}} .month-title{{font-size:clamp(30px,3.6vw,38px);line-height:1;letter-spacing:-.035em;font-weight:600;color:#3b3a36;font-feature-settings:'palt' 1}} .month-sub{{color:var(--muted);font-size:13px}}
.month-body{{padding:0 16px 16px}} .weekdays,.grid{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}} .weekdays{{margin:0 0 6px}} .weekday{{text-align:center;color:var(--muted);font-size:13px;padding:4px 0}} .weekday.weekend{{color:var(--weekend)}}
.day-cell{{position:relative;min-height:96px;border-top:1px solid var(--line);border-left:1px solid var(--line);padding:6px;display:flex;flex-direction:column;gap:4px;background:#fff;text-align:center;overflow:hidden}} .day-cell:nth-child(7n+1){{border-left:none}} .day-cell.empty{{background:rgba(0,0,0,.012)}} .day-cell.today{{background:rgba(201,183,255,.10);box-shadow:inset 0 0 0 1px rgba(201,183,255,.42)}} .day-cell.today .day-num{{font-weight:700}} .day-cell.today:not(.weekend):not(.holiday) .day-num{{color:#6d5bb3}} .day-cell.weekend .day-num,.day-cell.holiday .day-num{{color:var(--weekend)}}
.day-cell.clickable{{cursor:pointer;transition:transform .18s ease, background .18s ease, box-shadow .18s ease, border-color .18s ease;position:relative;border-radius:14px;background:linear-gradient(180deg,#fff,#f8f8f5);border:1px solid rgba(231,229,222,.82);-webkit-tap-highlight-color:transparent;touch-action:manipulation;text-decoration:none;color:inherit;outline:none;appearance:none;-webkit-appearance:none}} .day-cell.clickable::after{{content:'';position:absolute;left:8px;right:8px;top:6px;height:1px;border-radius:999px;background:rgba(255,255,255,.5);pointer-events:none}} .day-cell.clickable:hover{{background:#faf9f6;transform:translateY(-1px);border-color:rgba(231,229,222,.9);box-shadow:0 2px 6px rgba(30,30,28,.02)}} .day-cell.clickable.is-pressed,.day-cell.clickable:active{{background:#eef2ff;box-shadow:inset 0 0 0 2px rgba(93,119,255,.18);border-color:rgba(93,119,255,.18)}} .day-cell.clickable.is-pressed{{transform:translateY(1px)}} .day-cell.clickable:active{{transform:scale(.992)}} .day-cell.clickable:focus-visible{{box-shadow:inset 0 0 0 2px rgba(91,110,240,.28),0 0 0 3px rgba(91,110,240,.10)}} .day-cell.active{{background:#f3f5ff;box-shadow:inset 0 0 0 2px rgba(93,119,255,.22);border-color:rgba(93,119,255,.18)}} .day-cell.clickable.active.today{{background:rgba(201,183,255,.14);box-shadow:inset 0 0 0 1px rgba(201,183,255,.42), inset 0 0 0 2px rgba(93,119,255,.18);border-color:rgba(201,183,255,.48)}}
.day-num{{font-size:19px;line-height:1;letter-spacing:-.03em}} .chips{{display:flex;flex-direction:column;gap:4px;min-width:0}} .chip{{align-self:stretch;padding:3px 7px 4px;border-radius:10px;color:#fff;font-size:11px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center}} .chip-text{{text-align:center;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .chip-mobile-text{{display:none}}
.tone-live{{background:var(--live)}} .tone-ticket{{background:var(--ticket)}} .tone-deadline{{background:var(--deadline)}} .tone-event{{background:var(--event)}} .tone-holiday{{background:var(--holiday)}}
.detail-target{{display:block;height:0;overflow:hidden;pointer-events:none;visibility:hidden;scroll-margin-top:70vh}} .day-detail{{margin-top:18px;border:1px solid var(--line);border-radius:22px;padding:16px 16px 14px;background:linear-gradient(180deg,#fcfcfa,#f8f8f5);box-shadow:0 10px 24px rgba(30,30,28,.04);scroll-margin-top:18vh}} .detail-title{{display:inline-flex;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;border-radius:999px;background:rgba(91,110,240,.08);color:#3644a8;font-size:15px;font-weight:700;letter-spacing:-.01em}} .detail-title:empty{{display:none}} .detail-list{{display:grid;gap:8px}} .detail-item{{border-top:1px solid rgba(0,0,0,.05);padding-top:8px}} .detail-item:first-child{{border-top:none;padding-top:0}} .detail-label{{font-size:14px;font-weight:600}} .detail-sub,.detail-meta,.detail-source{{font-size:13px;color:var(--muted);line-height:1.6}} .detail-source a{{color:inherit}}
.detail-sections{{display:grid;gap:10px;margin-top:16px;padding-top:14px;border-top:1px solid rgba(0,0,0,.06)}} .detail-sections.is-hidden{{display:none}} .meta-fold{{border:1px solid rgba(0,0,0,.06);border-radius:16px;background:rgba(255,255,255,.72);overflow:hidden}} .meta-fold summary{{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;font-size:14px;font-weight:600}} .meta-fold summary::-webkit-details-marker{{display:none}} .meta-count{{color:var(--muted);font-size:12px;font-weight:500}} .meta-fold .meta-list{{padding:0 14px 14px}} .meta-list{{display:grid;gap:8px;color:var(--muted);font-size:14px}} .meta-item{{line-height:1.6}}
.site-footer{{margin-top:22px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;line-height:1.6;text-align:center}} .site-footer a{{color:inherit}}
{active_css}
@media (min-width:900px){{.page{{max-width:1080px}} .detail-sections{{grid-template-columns:1.15fr 1fr}}}} @media (max-width:720px){{.page{{padding:16px 10px 42px}} .month-summary{{padding:16px 12px}} .month-body{{padding:0 10px 14px}} .month-card{{border-radius:24px}} .month-title{{font-size:34px}} .day-cell{{min-height:88px;padding:5px}} .day-num{{font-size:17px}} .chip{{padding:2px 3px 3px;font-size:8.2px;line-height:1.04;letter-spacing:-.055em;border-radius:8px}} .legend-row{{font-size:13px}} .day-detail{{scroll-margin-top:14vh}}}} @media (max-width:520px){{.chip{{font-size:7.2px;padding-left:2px;padding-right:2px;letter-spacing:-.075em}} .chip-text{{display:none}} .chip-mobile-text{{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:1px;min-height:1em;white-space:normal;overflow:hidden}} .chip-mobile-text span{{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .chips{{gap:3px}}}} @media (hover:none), (pointer:coarse){{.day-cell.clickable{{transition:none}} .day-cell.clickable:hover{{transform:none;box-shadow:none;background:linear-gradient(180deg,#fff,#f8f8f5)}} .day-cell.clickable:active{{transform:none}}}}
</style>
</head>
<body>
<div class='page'>
  <section class='hero'>
    <h1>{html.escape(page_title)}</h1>
  </section>
  <section class='legend'>
{legend_row_html}    <div class='legend-meaning'>
      <div class='legend-item'><span>凡例: </span><span class='legend-chip tone-live' aria-hidden='true'></span><span>{html.escape(live_meaning)}</span><span class='legend-chip tone-ticket' aria-hidden='true'></span><span>{html.escape(ticket_meaning)}</span><span class='legend-chip tone-deadline' aria-hidden='true'></span><span>{html.escape(deadline_meaning)}</span><span class='legend-chip tone-holiday' aria-hidden='true'></span><span>祝日</span></div>
    </div>
  </section>
  <nav class='month-nav'>{month_nav}</nav>
  <section class='month-list'>{''.join(cards)}</section>
  <footer class='site-footer'>© 2026 Mistral-Yu. 非公式ファン制作ページです。各種権利は権利者に帰属します。CC BY-NC 4.0</footer>
</div>
<script>
(function() {{
const scriptElement = document.currentScript;
const rootMode = scriptElement && scriptElement.dataset ? scriptElement.dataset.rootMode : '';
const root = (rootMode ? document.querySelector('[data-mode="' + rootMode + '"]') : null) || scriptElement?.closest('.calendar-view') || document;
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
const pendingTapTops = new Map();
const isCoarsePointer = window.matchMedia('(hover:none), (pointer:coarse)').matches;
const shouldAutoScrollToPanel = true;
const shouldUseNativeHash = isCoarsePointer;
const getDetailKeyFromLocation = () => new URLSearchParams(window.location.search).get('d') || window.location.hash.slice(1);
const isMonthHash = (value) => /^m[0-9]{{2}}$/.test(value || '') || /^m[0-9]{{6}}$/.test(value || '');
const getCurrentDate = () => {{
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}};
const getMonthEndDate = (card) => {{
  const year = Number(card.dataset.year || '');
  const month = Number(card.dataset.monthNumber || '');
  if (!year || !month) return null;
  return new Date(year, month, 0);
}};
const setMonthOpen = (card, shouldOpen) => {{
  if (!card) return;
  card.open = shouldOpen;
  card.classList.toggle('collapsed', !shouldOpen);
}};
const applyAutoMonthCollapse = () => {{
  const today = getCurrentDate();
  for (const card of root.querySelectorAll('.month-card')) {{
    const hasSchedule = card.dataset.hasSchedule !== 'false';
    const monthEnd = getMonthEndDate(card);
    if (!hasSchedule) {{
      setMonthOpen(card, false);
      continue;
    }}
    if (monthEnd && monthEnd < today) {{
      setMonthOpen(card, false);
    }} else {{
      setMonthOpen(card, true);
    }}
  }}
}};
const openMonthFromHash = (monthId, scroll = false) => {{
  if (!isMonthHash(monthId)) return false;
  const card = root.querySelector(`#${{CSS.escape(monthId)}}`);
  if (!card) return false;
  setMonthOpen(card, true);
  forceVisualRefresh(card);
  if (scroll) {{
    requestAnimationFrame(() => {{
      const targetTop = card.getBoundingClientRect().top + window.scrollY - 12;
      window.scrollTo({{top: Math.max(targetTop, 0), behavior: 'smooth'}});
    }});
  }}
  return true;
}};
const setPressedState = (button, pressed) => {{
  if (!button) return;
  button.classList.toggle('is-pressed', pressed);
  forceVisualRefresh(button);
}};
const closeDetailPanel = (panel) => {{
  if (!panel) return;
  const title = panel.querySelector('.detail-title');
  const list = panel.querySelector('.detail-list');
  if (title) title.textContent = '';
  if (list) list.innerHTML = '';
}};
const maybeScrollToPanel = (panel, button) => {{
  if (!panel || !button || !shouldAutoScrollToPanel) return;
  const panelRect = panel.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  const minGapBelowButton = 6;
  const viewportBottomPadding = 20;
  const shiftToClearButton = Math.max(panelRect.top - (buttonRect.bottom + minGapBelowButton), 0);
  const shiftToFitBottom = Math.max(panelRect.bottom - (viewportHeight - viewportBottomPadding), 0);
  const shift = Math.max(shiftToClearButton, shiftToFitBottom);
  if (shift <= 0) return;
  window.scrollTo({{ top: Math.max(window.scrollY + shift, 0), behavior: 'smooth' }});
}};
const openDetailPanel = (button) => {{
  if (!button) return;
  const month = button.dataset.month;
  const key = button.dataset.detailKey;
  const panel = root.querySelector(`.day-detail[data-panel-month='${{month}}']`);
  if (!panel) return;
  const payload = detailData[key] || {{date: '', items: []}};
  const title = panel.querySelector('.detail-title');
  const list = panel.querySelector('.detail-list');
  const monthBody = button.closest('.month-body');
  if (monthBody) {{
    for (const candidate of monthBody.querySelectorAll('.day-cell.clickable.active')) {{
      if (candidate !== button) candidate.classList.remove('active');
    }}
  }}
  title.textContent = payload.date ? `${{payload.date}} の詳細` : '';
  list.innerHTML = (payload.items || []).map((item) => {{
    const sources = (item.sources || []).map((url) => `<div class='detail-source'><a href='${{url}}' target='_blank' rel='noreferrer'>${{url}}</a></div>`).join('');
    return `<div class='detail-item'>`
      + `<div class='detail-label'>${{item.label || ''}}</div>`
      + `<div class='detail-sub'>${{item.sub || ''}}</div>`
      + `<div class='detail-meta'>${{item.meta || ''}}</div>`
      + sources
      + `</div>`;
  }}).join('');
  button.classList.add('active');
  forceVisualRefresh(panel, monthBody, button);
  requestAnimationFrame(() => {{
    if (!shouldAutoScrollToPanel) {{
      pendingTapTops.delete(key);
      return;
    }}
    const savedTop = pendingTapTops.get(key);
    if (typeof savedTop === 'number') {{
      const currentTop = button.getBoundingClientRect().top;
      const desiredTop = Math.max(savedTop - 24, 12);
      const correction = currentTop - desiredTop;
      if (Math.abs(correction) > 1) {{
        window.scrollTo({{ top: Math.max(window.scrollY + correction, 0), behavior: 'auto' }});
      }}
      pendingTapTops.delete(key);
    }}
    maybeScrollToPanel(panel, button);
  }});
}};
const closeDetailForButton = (button) => {{
  if (!button) return;
  const month = button.dataset.month;
  const panel = root.querySelector(`.day-detail[data-panel-month='${{month}}']`);
  button.classList.remove('active');
  closeDetailPanel(panel);
  forceVisualRefresh(panel, button);
}};
const syncDetailFromLocation = () => {{
  const detailKey = getDetailKeyFromLocation();
  for (const candidate of root.querySelectorAll('.day-cell.clickable.active')) {{
    candidate.classList.remove('active');
  }}
  if (!detailKey) return;
  if (openMonthFromHash(detailKey, false)) return;
  const button = Array.from(root.querySelectorAll('.day-cell.clickable')).find((candidate) => candidate.dataset.detailKey === detailKey);
  if (!button) return;
  const monthCard = button.closest('.month-card');
  setMonthOpen(monthCard, true);
  openDetailPanel(button);
}};
for (const card of root.querySelectorAll('.month-card')) {{
  card.addEventListener('toggle', () => card.classList.toggle('collapsed', !card.open));
}}
for (const link of root.querySelectorAll('.month-nav a[href^="#"]')) {{
  link.addEventListener('click', (event) => {{
    const monthId = link.getAttribute('href').slice(1);
    if (!isMonthHash(monthId)) return;
    event.preventDefault();
    const url = new URL(window.location.href);
    url.searchParams.delete('d');
    url.hash = monthId;
    history.pushState(null, '', `${{url.pathname}}${{url.search}}${{url.hash}}`);
    openMonthFromHash(monthId, true);
  }});
}}
for (const button of root.querySelectorAll('.day-cell.clickable')) {{
  button.addEventListener('pointerdown', () => setPressedState(button, true));
  button.addEventListener('pointerup', () => setPressedState(button, false));
  button.addEventListener('pointercancel', () => setPressedState(button, false));
  button.addEventListener('pointerleave', () => setPressedState(button, false));
  button.addEventListener('touchstart', () => setPressedState(button, true), {{passive:true}});
  button.addEventListener('touchend', () => setPressedState(button, false));
  button.addEventListener('touchcancel', () => setPressedState(button, false));
  button.addEventListener('click', (event) => {{
    setPressedState(button, false);
    const url = new URL(window.location.href);
    const currentDetailKey = getDetailKeyFromLocation();
    if (shouldUseNativeHash) {{
      if (currentDetailKey === button.dataset.detailKey) {{
        event.preventDefault();
        url.hash = '';
        history.replaceState(null, '', `${{url.pathname}}${{url.search}}`);
        closeDetailForButton(button);
        return;
      }}
      if (url.searchParams.has('d')) {{
        url.searchParams.delete('d');
        history.replaceState(null, '', `${{url.pathname}}${{url.search}}${{url.hash}}`);
      }}
      openDetailPanel(button);
      return;
    }}
    event.preventDefault();
    if (url.searchParams.get('d') === button.dataset.detailKey) {{
      url.searchParams.delete('d');
      history.replaceState(null, '', `${{url.pathname}}${{url.search}}${{url.hash}}`);
      closeDetailForButton(button);
      return;
    }}
    url.searchParams.set('d', button.dataset.detailKey);
    history.pushState(null, '', `${{url.pathname}}${{url.search}}${{url.hash}}`);
    openDetailPanel(button);
  }});
}}
applyAutoMonthCollapse();
window.addEventListener('popstate', syncDetailFromLocation);
window.addEventListener('hashchange', syncDetailFromLocation);
if (getDetailKeyFromLocation()) {{
  syncDetailFromLocation();
}}
}})();
</script>
</body>
</html>"""


def render_workflow(display_months: list[dt.date] | int, holiday_template_paths: list[Path] | Path) -> str:
    if isinstance(display_months, int):
        display_months = [month_start(display_months, month) for month in range(1, 13)]
    if isinstance(holiday_template_paths, Path):
        holiday_template_paths = [holiday_template_paths]
    last_month = display_months[-1]
    holiday_lines = "\n".join(
        f"  - `{path.relative_to(BASE_DIR)}`"
        for path in dict.fromkeys(holiday_template_paths)
    )
    return f"""# sakurazaka schedule workflow

## 概要

- 生成フロー: `summary/sakurazaka46_live_summary.md` / `summary/sakurazaka46_event_summary.md` → `scripts/render_live_calendar.py` → `index.html`
- live表示は `summary/sakurazaka46_live_summary.md`、event表示は `summary/sakurazaka46_event_summary.md` を source of truth とする。
- all表示は live/event の生成結果を統合し、カレンダー内の表示を `開催` / `応募` / `締切` に要約する。
- `.plan/` は作業用であり、カレンダー生成には使わない。

## 元Markdownの書き方ルール

- live/eventとも各予定は `##` 見出し単位で管理する。
- liveは `### ライブ公演の日程` / `### 抽選の日程` / `### 公式ソース` を基本に崩さない。
- eventは live と同じ考え方で `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース` の順で整理する。
- live日程は `| 2026-07-23〜24 | 木金 | 静岡・エコパアリーナ |` のような表形式を維持する。
- event日程は `| 2026-05-03 | 日 | 京都パルスプラザ |` や `| 2026-06-10 | 水 | 発売日 |` のような表形式を維持する。
- 抽選日程も `| FC会員先行 | **4/13(月)〜4/19(日)** | 全席指定／親子・女性エリア |` のような表形式を維持する。event側で年をまたがず明確にしたい場合は `**2026-03-11(水)〜2026-05-29(金)**` のように年付きで書ける。
- Fortune Music などの `支払い方法選択期限` は応募側の締切として扱い、日付セルでは `支払い方法選択期限` と表示する。
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
- LIVE / EVENT / ALL / 直近2週間 を単一HTML内のタブとして表示
- `直近2週間` はブラウザJSで Asia/Tokyo 基準の今日を取得し、今日を含む14日分を1日1行で表示。予定なしの日も表示し、live/event の元チップ文言・色を使い、祝日チップは出さない
- ライブも抽選もない月はデフォルトで折りたたみ
- 日付セル内にライブタグ / 抽選開始 / 抽選締切などを表示
- all表示では live/event タブ内の日付セルチップ文言をそのまま統合表示
- 祝日はセル内で `祝` 表示
- 曜日行の土日と、土日・祝日の日付数字は赤文字表示（セル内チップ文言と `祝` チップは通常通り）。カレンダー内の日付数字とチップ文言はPC/スマホとも中央揃え
- スマホ幅ではチップ文言を最大2行にし、長い文言は中央付近で分けて行ごとの文字数をできるだけ均等化
- 日付クリックで同じ月カード内の詳細パネルを開く。初期状態の `日付をタップすると詳細を表示` 注釈は出さない
- 月見出しは太く出しすぎず、やや小さめ・軽めのモダンな日本語フォント感にする
- プレビュー画像は Python 生成の JPG（`--output-preview` 指定時のみ `summary/` に出力）
- 祝日テンプレートは `scripts/holidays_template.json` で管理する

## 編集ルール

1. ライブ日程・抽選日程・公式URLを変えるときは、先に `summary/sakurazaka46_live_summary.md` を更新する。
2. ライブ以外のイベント、CD応募、ミーグリ、リアルミーグリを変えるときは、先に `summary/sakurazaka46_event_summary.md` を更新する。
3. レイアウトや表示挙動を変えるときは `scripts/render_live_calendar.py` を編集して再生成する。
4. 生成後のHTMLを手で直接編集しない。
5. `.plan/` をカレンダー入力に使わない。

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
`summary/sakurazaka46_live_summary.md` と `summary/sakurazaka46_event_summary.md` を source of truth として扱う。
event側は `## イベント名` → `### イベント開催の日程` → `### 抽選の日程` → `### 公式ソース` の順と表形式を維持する。
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


def build_next14_schedule_payload(
    live_months: dict[dt.date, dict],
    event_months: dict[dt.date, dict],
    display_months: list[dt.date],
) -> dict[str, dict]:
    payload: dict[str, dict] = {}
    for month_key in display_months:
        merged_months = [live_months.get(month_key), event_months.get(month_key)]
        total = calendar.monthrange(month_key.year, month_key.month)[1]
        for day in range(1, total + 1):
            date_key = dt.date(month_key.year, month_key.month, day).isoformat()
            items = []
            details = []
            for month_data in merged_months:
                if not month_data:
                    continue
                for item in merge_day_items(month_data["days"][day]):
                    if item.get("kind") == "holiday" or item.get("text") == "祝":
                        continue
                    text = item["text"]
                    tone = item.get("tone", "ticket")
                    items.append({
                        "text": text,
                        "tone": tone,
                        "toneClass": HTML_TONE.get(tone, "ticket"),
                    })
                details.extend(month_data["detail_map"][day])
            if items or details:
                payload[date_key] = {"items": items, "details": details}
    return payload


def render_next14_html(
    live_months: dict[dt.date, dict],
    event_months: dict[dt.date, dict],
    display_months: list[dt.date],
) -> str:
    payload = build_next14_schedule_payload(live_months, event_months, display_months)
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""
<section class='calendar-view next14-view' data-mode='next14' hidden>
  <div class='page'>
    <section class='hero'>
      <h1>櫻坂46 カレンダー</h1>
      <nav class='mode-switch' aria-label='表示切替'>
        <div class='mode-switch-inner'>
          <a class='mode-button' href='?mode=live'>LIVE</a>
          <a class='mode-button' href='?mode=event'>EVENT</a>
          <a class='mode-button' href='?mode=all'>ALL</a>
          <a class='mode-button active' href='?mode=next14' aria-current='page'>直近2週間</a>
        </div>
      </nav>
    </section>
    <section class='legend next14-legend'>
      <div class='legend-meaning'>
        <div class='legend-item'><span>凡例: </span><span class='legend-chip tone-live' aria-hidden='true'></span><span>開催</span><span class='legend-chip tone-ticket' aria-hidden='true'></span><span>応募</span><span class='legend-chip tone-deadline' aria-hidden='true'></span><span>締切</span></div>
      </div>
    </section>
    <section class='next14-card' aria-live='polite'>
      <div class='next14-header'>
        <div>
          <div class='next14-title'>直近2週間</div>
          <div class='next14-range' data-next14-range>Asia/Tokyo 基準で読み込み中</div>
        </div>
      </div>
      <div class='next14-list' data-next14-list></div>
    </section>
  </div>
  <script>
(function() {{
const NEXT14_DAYS = 14;
const scheduleData = {payload_json};
const root = document.querySelector("[data-mode='next14']") || document;
const list = root.querySelector('[data-next14-list]');
const range = root.querySelector('[data-next14-range]');
const weekdays = ['日', '月', '火', '水', '木', '金', '土'];
const getTokyoToday = () => {{
  const parts = new Intl.DateTimeFormat('en-CA', {{timeZone:'Asia/Tokyo', year:'numeric', month:'2-digit', day:'2-digit'}}).formatToParts(new Date());
  const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
  return new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day)));
}};
const addDays = (date, days) => {{
  const next = new Date(date.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}};
const dateKey = (date) => date.toISOString().slice(0, 10);
const dateLabel = (date) => `${{date.getUTCMonth() + 1}}/${{String(date.getUTCDate()).padStart(2, '0')}}(${{weekdays[date.getUTCDay()]}})`;
const fullDateLabel = (date) => `${{date.getUTCFullYear()}}/${{String(date.getUTCMonth() + 1).padStart(2, '0')}}/${{String(date.getUTCDate()).padStart(2, '0')}}(${{weekdays[date.getUTCDay()]}})`;
const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
const renderSources = (sources = []) => sources.map((url) => `<div class='next14-source'><a href='${{escapeHtml(url)}}' target='_blank' rel='noreferrer'>${{escapeHtml(url)}}</a></div>`).join('');
const renderDetails = (details = []) => details.map((item) => `<div class='next14-detail-item'><div class='detail-label'>${{escapeHtml(item.label)}}</div>${{item.sub ? `<div class='detail-sub'>${{escapeHtml(item.sub)}}</div>` : ''}}${{item.meta ? `<div class='detail-meta'>${{escapeHtml(item.meta)}}</div>` : ''}}${{renderSources(item.sources || [])}}</div>`).join('');
function toggleNext14Detail(button) {{
  const detail = button.closest('.next14-row').querySelector('.next14-detail');
  const expanded = button.getAttribute('aria-expanded') === 'true';
  button.setAttribute('aria-expanded', String(!expanded));
  detail.hidden = expanded;
}}
const renderNext14 = () => {{
  if (!list) return;
  const today = getTokyoToday();
  const end = addDays(today, NEXT14_DAYS - 1);
  if (range) range.textContent = `${{fullDateLabel(today)}}〜${{fullDateLabel(end)}}`;
  list.innerHTML = '';
  for (let offset = 0; offset < NEXT14_DAYS; offset += 1) {{
    const date = addDays(today, offset);
    const key = dateKey(date);
    const data = scheduleData[key] || {{items: [], details: []}};
    const isWeekend = date.getUTCDay() === 0 || date.getUTCDay() === 6;
    const row = document.createElement('div');
    row.className = `next14-row${{offset === 0 ? ' next14-today' : ''}}`;
    const chips = (data.items || []).map((item) => `<span class='chip tone-${{escapeHtml(item.toneClass || 'ticket')}}'><span class='chip-text'>${{escapeHtml(item.text)}}</span></span>`).join('') || `<span class='next14-empty'>予定なし</span>`;
    const hasDetails = (data.details || []).length > 0;
    row.innerHTML = `<button class='next14-row-main' type='button' aria-expanded='false' ${{hasDetails ? '' : 'disabled'}}><span class='next14-date${{isWeekend ? ' next14-weekend' : ''}}'>${{dateLabel(date)}}</span><span class='next14-items'>${{chips}}</span></button><div class='next14-detail' hidden>${{renderDetails(data.details || [])}}</div>`;
    const button = row.querySelector('.next14-row-main');
    if (hasDetails) button.addEventListener('click', () => toggleNext14Detail(button));
    list.appendChild(row);
  }}
}};
renderNext14();
}})();
  </script>
</section>"""


def extract_calendar_parts(rendered_html: str) -> tuple[str, str, str]:
    style = re.search(r"<style>\n(.*?)\n</style>", rendered_html, re.S).group(1)
    body = re.search(r"<div class='page'>\n(.*?)\n</div>\n<script>", rendered_html, re.S).group(1)
    script = re.search(r"<script>\n(.*?)\n</script>", rendered_html, re.S).group(1)
    return style, body, script


def render_mode_html(months, legend_live, legend_lottery, *, display_months, holidays_by_month, page_title, hero_copy, list_label, live_meaning, ticket_meaning, deadline_meaning="締切・販売終了", primary_meta_label="ライブ情報", ticket_meta_label="チケット情報") -> str:
    previous = {name: getattr(render_html, name, None) for name in ("page_title", "hero_copy", "list_label", "live_meaning", "ticket_meaning", "deadline_meaning", "primary_meta_label", "ticket_meta_label")}
    render_html.page_title = page_title
    render_html.hero_copy = hero_copy
    render_html.list_label = list_label
    render_html.live_meaning = live_meaning
    render_html.ticket_meaning = ticket_meaning
    render_html.deadline_meaning = deadline_meaning
    render_html.primary_meta_label = primary_meta_label
    render_html.ticket_meta_label = ticket_meta_label
    try:
        return render_html(months, legend_live, legend_lottery, display_months=display_months, holidays_by_month=holidays_by_month)
    finally:
        for name, value in previous.items():
            if value is None:
                try:
                    delattr(render_html, name)
                except AttributeError:
                    pass
            else:
                setattr(render_html, name, value)


def render_combined_html(live_html: str, event_html: str, all_html: str | None = None, next14_html: str | None = None) -> str:
    live_style, live_body, live_script = extract_calendar_parts(live_html)
    _event_style, event_body, event_script = extract_calendar_parts(event_html)
    all_body = all_script = None
    if all_html is not None:
        _all_style, all_body, all_script = extract_calendar_parts(all_html)
    root_setup_re = re.compile(
        r"const scriptElement = document\.currentScript;\n"
        r"const rootMode = scriptElement && scriptElement\.dataset \? scriptElement\.dataset\.rootMode : '';\n"
        r"const root = \(rootMode \? document\.querySelector\('\[data-mode=\"' \+ rootMode \+ '\"\]'\) : null\) \|\| scriptElement\?\.closest\('\.calendar-view'\) \|\| document;"
    )
    live_script = root_setup_re.sub("const root = document.querySelector(\"[data-mode='live']\") || document;", live_script)
    event_script = root_setup_re.sub("const root = document.querySelector(\"[data-mode='event']\") || document;", event_script)
    if all_script is not None:
        all_script = root_setup_re.sub("const root = document.querySelector(\"[data-mode='all']\") || document;", all_script)
    mode_css = """
.mode-switch{margin:12px 0 0}
.mode-switch-inner{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.mode-button{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:999px;padding:9px 14px;font-size:14px;font-weight:700;cursor:pointer;box-shadow:0 8px 20px rgba(30,30,28,.04);text-decoration:none;display:inline-flex;align-items:center;justify-content:center;-webkit-tap-highlight-color:transparent;touch-action:manipulation}
.mode-button.active,.mode-button[aria-current='page']{background:#1e1e1c;color:#fff;border-color:#1e1e1c}
.mode-button:active{background:#1e1e1c;color:#fff;border-color:#1e1e1c;box-shadow:inset 0 0 0 2px rgba(255,255,255,.12)}
.calendar-view[hidden]{display:none}
.next14-card{background:var(--card);border:1px solid var(--line);border-radius:28px;box-shadow:0 18px 44px rgba(30,30,28,.05);padding:16px;overflow:hidden}.next14-title{font-size:clamp(26px,3vw,34px);line-height:1;font-weight:600;letter-spacing:-.035em;color:#3b3a36}.next14-range{margin-top:8px;color:var(--muted);font-size:13px}.next14-list{display:grid;gap:8px;margin-top:16px}.next14-row{border:1px solid rgba(231,229,222,.86);border-radius:18px;background:#fff;overflow:hidden}.next14-row.next14-today{box-shadow:inset 0 0 0 1px rgba(201,183,255,.42);background:rgba(201,183,255,.08)}.next14-row-main{width:100%;display:grid;grid-template-columns:92px 1fr;align-items:center;gap:10px;padding:10px 12px;border:none;background:transparent;color:inherit;text-align:left;font:inherit;cursor:pointer}.next14-row-main:disabled{cursor:default}.next14-date{font-size:14px;font-weight:700;color:var(--text);white-space:nowrap}.next14-date.next14-weekend{color:var(--weekend)}.next14-items{display:flex;gap:5px;flex-wrap:wrap;align-items:center}.next14-items .chip{align-self:auto;display:inline-flex;max-width:100%;padding:3px 7px 4px}.next14-empty{color:var(--muted);font-size:13px}.next14-detail{border-top:1px solid rgba(0,0,0,.06);padding:10px 12px 12px;background:linear-gradient(180deg,#fcfcfa,#f8f8f5)}.next14-detail[hidden]{display:none}.next14-detail-item{padding-top:8px;border-top:1px solid rgba(0,0,0,.05)}.next14-detail-item:first-child{padding-top:0;border-top:none}.next14-source a{color:inherit}@media (max-width:520px){.next14-row-main{grid-template-columns:74px 1fr;padding:9px 10px}.next14-date{font-size:13px}.next14-card{padding:12px;border-radius:22px}.next14-items .chip .chip-text{display:block;white-space:normal;overflow:visible;text-overflow:clip}.next14-items .chip{font-size:10px;line-height:1.12;padding:3px 6px}.next14-items{gap:4px}}
"""
    live_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button active' href='?mode=live' aria-current='page'>LIVE</a>
        <a class='mode-button' href='?mode=event'>EVENT</a>
        <a class='mode-button' href='?mode=all'>ALL</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    event_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button' href='?mode=live'>LIVE</a>
        <a class='mode-button active' href='?mode=event' aria-current='page'>EVENT</a>
        <a class='mode-button' href='?mode=all'>ALL</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    all_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button' href='?mode=live'>LIVE</a>
        <a class='mode-button' href='?mode=event'>EVENT</a>
        <a class='mode-button active' href='?mode=all' aria-current='page'>ALL</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    live_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + live_mode_switch_html, live_body, count=1, flags=re.S)
    event_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + event_mode_switch_html, event_body, count=1, flags=re.S)
    if all_body is not None:
        all_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + all_mode_switch_html, all_body, count=1, flags=re.S)
    all_section = ""
    if all_body is not None and all_script is not None:
        all_section = f"""
<section class='calendar-view' data-mode='all' hidden>
  <div class='page'>
{all_body}
  </div>
  <script data-root-mode='all'>
{all_script}
  </script>
</section>"""
    return f"""<!doctype html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>櫻坂46 カレンダー</title>
<style>
{live_style}
{mode_css}
</style>
</head>
<body>
<section class='calendar-view' data-mode='live'>
  <div class='page'>
{live_body}
  </div>
  <script data-root-mode='live'>
{live_script}
  </script>
</section>
<section class='calendar-view' data-mode='event' hidden>
  <div class='page'>
{event_body}
  </div>
  <script data-root-mode='event'>
{event_script}
  </script>
</section>
{all_section}
{next14_html or ''}
<script>
const requestedMode = new URL(document.URL).searchParams.get('mode');
const selectedMode = ['live', 'event', 'all', 'next14'].includes(requestedMode) ? requestedMode : 'live';
for (const view of document.querySelectorAll('.calendar-view')) {{
  view.hidden = view.dataset.mode !== selectedMode;
}}
</script>
</body>
</html>"""

def main(argv: list[str] | None = None) -> None:
    global HOLIDAYS

    args = parse_args(argv)

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_DIR.mkdir(parents=True, exist_ok=True)

    source_text = SOURCE_MD.read_text()
    event_source_text = EVENT_SOURCE_MD.read_text() if EVENT_SOURCE_MD.exists() else ""
    live_display_months = collect_display_months(source_text)
    event_display_months = collect_event_display_months(event_source_text) if event_source_text else live_display_months
    all_display_months = continuous_display_months(live_display_months + event_display_months)
    holidays_by_month_all = build_holiday_lookup(all_display_months, refresh=args.refresh_holidays)
    holidays_by_live_month = {month: holidays_by_month_all.get(month, {}) for month in live_display_months}
    holidays_by_event_month = {month: holidays_by_month_all.get(month, {}) for month in event_display_months}
    holiday_template_paths = [get_holiday_template_path(year) for year in sorted({month.year for month in all_display_months})]
    latest_year = max(all_display_months).year
    HOLIDAYS = load_holiday_template(get_holiday_template_path(latest_year)) or empty_holiday_map()

    months, legend_live, legend_lottery = parse_summary_timeline(source_text, live_display_months, holidays_by_live_month)
    event_months, legend_event, legend_event_dates = parse_event_summary_timeline(event_source_text, event_display_months, holidays_by_event_month) if event_source_text else ({}, {}, {})
    combined_months = build_all_months(months, event_months, all_display_months, holidays_by_month_all)

    if args.output_calendar_md:
        OUTPUT_MD.write_text(build_markdown(months, legend_live, legend_lottery, latest_year, display_months=live_display_months, holidays_by_month=holidays_by_live_month))
    elif OUTPUT_MD.exists():
        OUTPUT_MD.unlink()
    live_html = render_mode_html(
        months,
        legend_live,
        legend_lottery,
        display_months=live_display_months,
        holidays_by_month=holidays_by_live_month,
        page_title="櫻坂46 カレンダー",
        hero_copy="ライブ情報をまとめています。",
        list_label="ライブ一覧",
        live_meaning="開催",
        ticket_meaning="抽選",
        deadline_meaning="締切",
    )
    if event_source_text:
        event_html = render_mode_html(
            event_months,
            legend_event,
            legend_event_dates,
            display_months=event_display_months,
            holidays_by_month=holidays_by_event_month,
            page_title="櫻坂46 カレンダー",
            hero_copy="ライブ以外の予定をまとめています。",
            list_label="イベント一覧",
            live_meaning="開催",
            ticket_meaning="応募",
            deadline_meaning="締切",
            primary_meta_label="イベント情報",
            ticket_meta_label="応募・締切情報",
        )
        all_html = render_mode_html(
            combined_months,
            {},
            {},
            display_months=all_display_months,
            holidays_by_month=holidays_by_month_all,
            page_title="櫻坂46 カレンダー",
            hero_copy="ライブとイベントをまとめています。",
            list_label="",
            live_meaning="開催",
            ticket_meaning="応募",
            deadline_meaning="締切",
            primary_meta_label="開催情報",
            ticket_meta_label="応募・締切情報",
        )
        next14_html = render_next14_html(months, event_months, all_display_months)
        OUTPUT_HTML.write_text(render_combined_html(live_html, event_html, all_html, next14_html))
    else:
        OUTPUT_HTML.write_text(live_html)
    WORKFLOW_MD.write_text(render_workflow(live_display_months, holiday_template_paths))
    if LEGACY_WORKFLOW_MD.exists():
        LEGACY_WORKFLOW_MD.unlink()

    preview = None
    if args.output_preview:
        fonts = load_fonts()
        preview = render_preview_image(months, fonts, latest_year, display_months=live_display_months, holidays_by_month=holidays_by_live_month)

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
