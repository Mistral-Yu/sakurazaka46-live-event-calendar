from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import calendar
import csv
import datetime as dt
import hashlib
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
MEMBERS_TEMPLATE_JSON = SCRIPT_DIR / "sakurazaka46_members_template.json"

SOURCE_MD = SUMMARY_DIR / "sakurazaka46_live_summary.md"
EVENT_SOURCE_MD = SUMMARY_DIR / "sakurazaka46_event_summary.md"
OUTPUT_MD = SUMMARY_DIR / "sakurazaka46_live_calendar.md"
OUTPUT_HTML = BASE_DIR / "index.html"
ICS_DIR = BASE_DIR / "ics"
OUTPUT_ICS_ALL = ICS_DIR / "sakurazaka46_all.ics"
OUTPUT_ICS_DEADLINES = ICS_DIR / "sakurazaka46_deadlines.ics"
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

RULES_PATH = SCRIPT_DIR / "calendar_rules.json"


def load_calendar_rules(path: Path = RULES_PATH) -> dict:
    rules = json.loads(path.read_text(encoding="utf-8"))
    required_top = {"labels", "tones", "style"}
    missing_top = required_top - set(rules)
    if missing_top:
        raise ValueError(f"calendar rules missing sections: {sorted(missing_top)}")
    colors = rules.get("style", {}).get("colors", {})
    for name, value in colors.items():
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"invalid style color for {name}: {value!r}")
    return rules


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def style_root_css() -> str:
    declarations = "".join(f"--{name}:{value};" for name, value in STYLE_COLORS.items())
    return f":root {{{declarations}}}"


def rule_contains(title: str, rule: dict) -> bool:
    return any(keyword in title for keyword in rule.get("contains", []))


CALENDAR_RULES = load_calendar_rules()
LABEL_RULES = CALENDAR_RULES["labels"]
LIVE_LABEL = LABEL_RULES["venue_labels"]
LIVE_TITLE_RULES = LABEL_RULES["live_title_rules"]
LOTTERY_TITLE_RULES = LABEL_RULES["lottery_title_rules"]
LOTTERY_SHORT = LABEL_RULES["lottery_short_labels"]
HTML_TONE = CALENDAR_RULES["tones"]["html"]
STYLE_COLORS = CALENDAR_RULES["style"]["colors"]
PREVIEW_COLORS = CALENDAR_RULES["style"].get("preview_colors", {})
TONE_RGB = {
    "live": hex_to_rgb(STYLE_COLORS["live"]),
    "ticket": hex_to_rgb(STYLE_COLORS["ticket"]),
    "deadline": hex_to_rgb(STYLE_COLORS["deadline"]),
    "holiday": hex_to_rgb(STYLE_COLORS["holiday"]),
    "event": hex_to_rgb(STYLE_COLORS["event"]),
}
RGB_TONE = {label: TONE_RGB.get(tone, TONE_RGB["ticket"]) for label, tone in HTML_TONE.items()}

HOLIDAYS = {month: {} for month in range(1, 13)}

BG = tuple(PREVIEW_COLORS.get("bg", [248, 248, 246]))
WHITE = tuple(PREVIEW_COLORS.get("card", [255, 255, 255]))
LINE = tuple(PREVIEW_COLORS.get("line", [226, 226, 222]))
TEXT = tuple(PREVIEW_COLORS.get("text", [28, 28, 28]))
MUTED = tuple(PREVIEW_COLORS.get("muted", [120, 120, 120]))


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
    parser.add_argument(
        "--output-workflow",
        action="store_true",
        help="Also regenerate scripts/sakurazaka_schedule_workflow.md. Default is off.",
    )
    return parser.parse_args(argv)


# generated from summary/sakurazaka46_live_summary.md
# usage: python3 scripts/render_live_calendar.py
# outputs:
#   - index.html
#   - ics/sakurazaka46_all.ics
#   - ics/sakurazaka46_deadlines.ics
#   - summary/sakurazaka46_live_calendar.md (optional)
#   - summary/sakurazaka46_live_calendar_preview.jpg (optional)
#   - scripts/sakurazaka_schedule_workflow.md (optional)


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
    if month_data["events"] or month_data["lotteries"]:
        return True
    return any(
        item.get("kind") != "holiday"
        for items in month_data["days"].values()
        for item in items
    )


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
    for rule in LOTTERY_TITLE_RULES:
        if rule_contains(normalized, rule):
            return rule["label"]
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


PLAN_EXCLUDE_KEYWORDS = (
    "応募",
    "抽選",
    "締切",
    "期限",
    "発売",
    "販売",
    "受付",
    "支払い",
    "視聴用ID",
)
PLAN_INCLUDE_KEYWORDS = (
    "ミーグリ",
    "リアルミーグリ",
    "公演",
    "ライブ",
    "LIVE",
    "イベント",
    "フェス",
    "番組",
    "出演",
    "ミニライブ",
)


def is_plan_candidate_item(item: dict) -> bool:
    text = item.get("text", "")
    kind = item.get("kind")
    if kind == "holiday":
        return False
    if any(keyword in text for keyword in PLAN_EXCLUDE_KEYWORDS):
        return False
    if kind in {"live", "event", "all_event"}:
        return True
    return any(keyword in text for keyword in PLAN_INCLUDE_KEYWORDS)


def is_plan_detail_item(detail: dict) -> bool:
    label = str(detail.get("label", ""))
    if label.startswith(("LIVE:", "EVENT:")):
        return True
    text = " ".join(str(detail.get(key, "")) for key in ("label", "sub", "meta"))
    if any(keyword in text for keyword in PLAN_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in text for keyword in PLAN_INCLUDE_KEYWORDS)


def build_plan_months(all_months: dict, display_months: list[dt.date]) -> dict:
    plan_months = {month_key: empty_month_struct() for month_key in display_months}
    for month_key in display_months:
        source = all_months.get(month_key)
        if not source:
            continue
        target = plan_months[month_key]
        target["sources"] = list(source.get("sources", []))
        for day, items in source["days"].items():
            holiday_items = [dict(item) for item in merge_day_items(items) if item.get("kind") == "holiday" or item.get("text") == "祝"]
            candidates = [dict(item) for item in merge_day_items(items) if is_plan_candidate_item(item)]
            if holiday_items:
                target["days"][day].extend(holiday_items)
            if not candidates:
                continue
            target["days"][day].extend(candidates)
            target["detail_map"][day].extend(
                detail for detail in source["detail_map"].get(day, []) if is_plan_detail_item(detail)
            )
        target["events"] = [item for item in source["events"] if True]
    return plan_months


def ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", r"\n")
    )


def fold_ics_line(line: str) -> list[str]:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    folded = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        limit = 75 if not folded else 74
        if current and current_len + char_len > limit:
            folded.append(current if not folded else f" {current}")
            current = char
            current_len = char_len
        else:
            current += char
            current_len += char_len
    if current:
        folded.append(current if not folded else f" {current}")
    return folded


def ics_text_line(name: str, value: str) -> list[str]:
    return fold_ics_line(f"{name}:{ics_escape(value)}")


def ics_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value).strip("-").lower()
    if slug:
        return slug[:48]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def all_day_ics_event(date_value: dt.date, summary: str, description: str, uid_suffix: str) -> list[str]:
    end_date = date_value + dt.timedelta(days=1)
    lines = [
        "BEGIN:VEVENT",
        f"UID:sakurazaka46-{date_value:%Y%m%d}-{uid_suffix}@mistral-yu",
        "DTSTAMP:20260101T000000Z",
        f"DTSTART;VALUE=DATE:{date_value:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end_date:%Y%m%d}",
    ]
    lines.extend(ics_text_line("SUMMARY", summary))
    if description:
        lines.extend(ics_text_line("DESCRIPTION", description))
    lines.append("END:VEVENT")
    return lines


def is_deadline_calendar_item(item: dict) -> bool:
    text = item.get("text", "")
    tone = item.get("tone", "")
    return "締切" in text or "期限" in text or "販売終了" in text or tone == "deadline"


def is_event_calendar_item(item: dict) -> bool:
    return item.get("kind") in {"live", "event", "all_event"}


def detail_description(details: list[dict]) -> str:
    lines = []
    seen = set()
    for detail in details:
        label = detail.get("label", "")
        sub = detail.get("sub", "")
        meta = detail.get("meta", "")
        sources = detail.get("sources", [])
        parts = [part for part in (label, sub, meta) if part]
        if sources:
            parts.extend(sources)
        text = "\n".join(parts)
        if text and text not in seen:
            seen.add(text)
            lines.append(text)
    return "\n\n".join(lines)


def iter_ics_items(all_months: dict, include_filter: Callable[[dict], bool] | None = None):
    for month_key in sorted(all_months):
        month_data = all_months[month_key]
        for day in sorted(month_data["days"]):
            date_value = dt.date(month_key.year, month_key.month, day)
            details = month_data["detail_map"].get(day, [])
            description = detail_description(details)
            seen = set()
            for item in merge_day_items(month_data["days"][day]):
                if item.get("kind") == "holiday":
                    continue
                if include_filter is not None and not include_filter(item):
                    continue
                text = item.get("text", "")
                if not text:
                    continue
                key = (date_value, text, item.get("kind", ""))
                if key in seen:
                    continue
                seen.add(key)
                yield date_value, text, description, item


def render_ics_calendar(name: str, items) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Mistral-Yu//Sakurazaka46 Calendar//JA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    lines.extend(ics_text_line("X-WR-CALNAME", name))
    for date_value, summary, description, item in items:
        uid_suffix = f"{ics_slug(summary)}-{ics_slug(item.get('kind', 'item'))}"
        lines.extend(all_day_ics_event(date_value, summary, description, uid_suffix))
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        folded.extend(fold_ics_line(line))
    return "\r\n".join(folded) + "\r\n"


def write_ics_outputs(all_months: dict) -> tuple[Path, Path]:
    ICS_DIR.mkdir(parents=True, exist_ok=True)
    all_items = list(iter_ics_items(all_months))
    deadline_event_items = list(
        iter_ics_items(all_months, lambda item: is_deadline_calendar_item(item) or is_event_calendar_item(item))
    )
    OUTPUT_ICS_ALL.write_text(render_ics_calendar("櫻坂46 全予定", all_items), encoding="utf-8")
    OUTPUT_ICS_DEADLINES.write_text(
        render_ics_calendar("櫻坂46 締切・開催", deadline_event_items),
        encoding="utf-8",
    )
    return OUTPUT_ICS_ALL, OUTPUT_ICS_DEADLINES


def live_calendar_label(title: str, venue: str) -> str:
    for rule in LIVE_TITLE_RULES:
        if not rule_contains(title, rule):
            continue
        if "label" in rule:
            return rule["label"]
        if "venue_label_suffix" in rule:
            base = LIVE_LABEL.get(venue, title[:4])
            return f"{base}{rule['venue_label_suffix']}"
    return LIVE_LABEL.get(venue, title[:4])


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
    parsed = re.match(r"(\d{1,2})/(\d{1,2})\([^)]*\)[^〜|]*(?:〜(?:(\d{1,2})/(\d{1,2})\([^)]*\)[^〜|]*|))?", period)
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
    if "サクラミーツ" in joined:
        return "サクラミーツ"
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


def suffix_marker(text: str) -> str:
    if "(全国)" in text or "（全国）" in text:
        return "(全国)"
    if "(CD)" in text or "（CD）" in text:
        return "(CD)"
    return ""


def has_nationwide_suffix_marker(text: str) -> bool:
    return suffix_marker(text) == "(全国)"


def append_event_suffix(label: str, text: str) -> str:
    marker = suffix_marker(text)
    if marker and not label.endswith(marker):
        return f"{label}{marker}"
    return label


def append_nationwide_suffix(label: str, text: str) -> str:
    if has_nationwide_suffix_marker(text) and not label.endswith("(全国)"):
        return f"{label}(全国)"
    return label


def format_lottery_chip(label: str, status: str) -> str:
    marker = suffix_marker(label)
    if marker and label.endswith(marker):
        return f"{label[:-len(marker)]}{status}"
    return f"{label}{status}"


def event_period_label(tag: str, text: str) -> str:
    joined = f"{tag} {text}"
    if "ミニライブ" in joined and ("視聴用ID" in joined or "ミニライブ応募" in joined):
        return "ミニライブ応募"
    if tag in {"ミーグリ", "リアルミーグリ"}:
        if tag == "リアルミーグリ" or has_nationwide_suffix_marker(joined):
            return "ミーグリ(シリアルコード)応募"
        return "ミーグリ応募"
    if "CD" in joined or "シリアル" in joined or "購入者" in joined:
        return "CD応募"
    if tag == "サクラミーツ":
        return "サクラミーツ抽選"
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
        return append_nationwide_suffix("リアルミーグリ", joined)
    if tag == "メッセージ":
        return "メッセージキャンペーン"
    return append_nationwide_suffix(tag, joined)


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
    marker = suffix_marker(tone_label)
    if marker and tone_label.endswith(marker):
        tone_label = tone_label[:-len(marker)]
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
                    if label in {"CD応募", "ミーグリ(シリアルコード)応募", "メッセージキャンペーン"} and current_date not in {start_date, end_date}:
                        continue
                    is_single_day_deadline = start_date == end_date and (
                        "期限" in lottery_type or "締切" in lottery_type or "保障期間" in lottery_type
                    )
                    if is_single_day_deadline:
                        chip = "支払い方法選択期限" if "支払い方法選択期限" in lottery_type else format_lottery_chip(label, "締切")
                    elif current_date == start_date:
                        chip = format_lottery_chip(label, "開始")
                    elif current_date == end_date:
                        chip = format_lottery_chip(label, "締切")
                    else:
                        chip = format_lottery_chip(label, "中")
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
                    parsed = re.match(r"(\d{1,2})/(\d{1,2})\([^)]*\)[^〜|]*(?:〜(?:(\d{1,2})/(\d{1,2})\([^)]*\)[^〜|]*|))?", period)
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
        "- 抽選タグ: 抽選は `開始` / `中` / `締切`、販売系は `一般発売` / `一般発売中` / `先着受付` / `販売終了` を表記",
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
                iso_date = f"{year_value:04d}-{month_value:02d}-{day:02d}"
                cells.append(
                    f"<a class='{clickable_class}' href='#{detail_key}' data-month='{panel_id}' data-detail-key='{detail_key}' data-date='{iso_date}'>"
                    f"<span class='detail-target' id='{detail_key}' aria-hidden='true'></span><div class='day-num'>{day}</div><div class='chips'>{chips}</div></a>"
                )
            else:
                iso_date = f"{year_value:04d}-{month_value:02d}-{day:02d}"
                cells.append(f"<div class='{day_class}' data-date='{iso_date}'><div class='day-num'>{day}</div><div class='chips'>{chips}</div></div>")
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
    legend_parts = ["<span>凡例: </span>"]
    if live_meaning:
        legend_parts.append(f"<span class='legend-chip tone-live' aria-hidden='true'></span><span>{html.escape(live_meaning)}</span>")
    if ticket_meaning:
        legend_parts.append(f"<span class='legend-chip tone-ticket' aria-hidden='true'></span><span>{html.escape(ticket_meaning)}</span>")
    if deadline_meaning:
        legend_parts.append(f"<span class='legend-chip tone-deadline' aria-hidden='true'></span><span>{html.escape(deadline_meaning)}</span>")
    legend_parts.append("<span class='legend-chip tone-holiday' aria-hidden='true'></span><span>祝日</span>")
    legend_meaning_html = "".join(legend_parts)
    return f"""<!doctype html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{html.escape(page_title)}</title>
<style>
{style_root_css()}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;background:var(--bg);color:var(--text)}}
.page{{max-width:1200px;margin:0 auto;padding:20px 14px 60px}} .hero{{margin-bottom:18px}} .hero h1{{margin:0;font-size:clamp(32px,4.2vw,52px);letter-spacing:-.04em}} .hero p{{margin:10px 0 0;color:var(--muted);font-size:15px;line-height:1.7;max-width:72ch}}
.legend{{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:16px 18px;box-shadow:0 16px 40px rgba(30,30,28,.06);margin-bottom:18px}} .legend h2{{font-size:18px;margin:0 0 10px}} .legend-row{{color:var(--muted);font-size:14px;line-height:1.75}} .legend-meaning{{display:flex;flex-wrap:wrap;gap:10px 14px;margin-top:10px}} .legend-item{{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-size:13px;line-height:1.4}} .legend-chip{{display:inline-block;width:12px;height:12px;border-radius:999px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.35)}}
.month-nav{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}} .month-nav a{{text-decoration:none;color:var(--text);background:var(--card);border:1px solid var(--line);padding:8px 12px;border-radius:999px;font-size:14px;box-shadow:0 8px 20px rgba(30,30,28,.04)}}
.month-list{{display:grid;gap:18px}} .month-card{{background:var(--card);border:1px solid var(--line);border-radius:30px;box-shadow:0 18px 44px rgba(30,30,28,.05);overflow:hidden;scroll-margin-top:14px}} .month-summary{{list-style:none;cursor:pointer;padding:20px 18px}} .month-summary::-webkit-details-marker{{display:none}} .month-card.collapsed .month-summary{{background:rgba(0,0,0,.01)}}
.month-header{{display:flex;align-items:flex-end;justify-content:space-between;gap:12px}} .month-title{{font-size:clamp(21px,2.52vw,27px);line-height:1;letter-spacing:-.035em;font-weight:600;color:#3b3a36;font-feature-settings:'palt' 1}} .month-sub{{color:var(--muted);font-size:13px}}
.month-body{{padding:0 16px 16px}} .weekdays,.grid{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}} .weekdays{{margin:0 0 6px}} .weekday{{text-align:center;color:var(--muted);font-size:13px;padding:4px 0}} .weekday.weekend{{color:var(--weekend)}}
.day-cell{{position:relative;min-height:96px;border-top:1px solid var(--line);border-left:1px solid var(--line);padding:6px;display:flex;flex-direction:column;gap:4px;background:#fff;text-align:center;overflow:hidden}} .day-cell:nth-child(7n+1){{border-left:none}} .day-cell.empty{{background:rgba(0,0,0,.012)}} .day-cell.today{{background:rgba(201,183,255,.10);box-shadow:inset 0 0 0 1px rgba(201,183,255,.42)}} .day-cell.today .day-num{{font-weight:700}} .day-cell.today:not(.weekend):not(.holiday) .day-num{{color:#6d5bb3}} .day-cell.weekend .day-num,.day-cell.holiday .day-num{{color:var(--weekend)}}
.day-cell.clickable{{cursor:pointer;transition:transform .18s ease, background .18s ease, box-shadow .18s ease, border-color .18s ease;position:relative;border-radius:14px;background:linear-gradient(180deg,#fff,#f8f8f5);border:1px solid rgba(231,229,222,.82);-webkit-tap-highlight-color:transparent;touch-action:manipulation;text-decoration:none;color:inherit;outline:none;appearance:none;-webkit-appearance:none}} .day-cell.clickable::after{{content:'';position:absolute;left:8px;right:8px;top:6px;height:1px;border-radius:999px;background:rgba(255,255,255,.5);pointer-events:none}} .day-cell.clickable:hover{{background:#faf9f6;transform:translateY(-1px);border-color:rgba(231,229,222,.9);box-shadow:0 2px 6px rgba(30,30,28,.02)}} .day-cell.clickable.is-pressed,.day-cell.clickable:active{{background:#eef2ff;box-shadow:inset 0 0 0 2px rgba(93,119,255,.18);border-color:rgba(93,119,255,.18)}} .day-cell.clickable.is-pressed{{transform:translateY(1px)}} .day-cell.clickable:active{{transform:scale(.992)}} .day-cell.clickable:focus-visible{{box-shadow:inset 0 0 0 2px rgba(91,110,240,.28),0 0 0 3px rgba(91,110,240,.10)}} .day-cell.active{{background:#f3f5ff;box-shadow:inset 0 0 0 2px rgba(93,119,255,.22);border-color:rgba(93,119,255,.18)}} .day-cell.clickable.active.today{{background:rgba(201,183,255,.14);box-shadow:inset 0 0 0 1px rgba(201,183,255,.42), inset 0 0 0 2px rgba(93,119,255,.18);border-color:rgba(201,183,255,.48)}}
.day-num{{font-size:19px;line-height:1;letter-spacing:-.03em}} .chips{{display:flex;flex-direction:column;gap:4px;min-width:0}} .chip{{align-self:stretch;padding:3px 7px 4px;border-radius:10px;color:#fff;font-size:11px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center}} .chip-text{{text-align:center;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .chip-mobile-text{{display:none}}
.tone-live{{background:var(--live)}} .tone-ticket{{background:var(--ticket)}} .tone-deadline{{background:var(--deadline)}} .tone-event{{background:var(--event)}} .tone-holiday{{background:var(--holiday)}}
.detail-target{{display:block;height:0;overflow:hidden;pointer-events:none;visibility:hidden;scroll-margin-top:70vh}} .day-detail{{margin-top:18px;border:1px solid var(--line);border-radius:22px;padding:16px 16px 14px;background:linear-gradient(180deg,#fcfcfa,#f8f8f5);box-shadow:0 10px 24px rgba(30,30,28,.04);scroll-margin-top:18vh}} .detail-title{{display:inline-flex;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;border-radius:999px;background:rgba(91,110,240,.08);color:#3644a8;font-size:15px;font-weight:700;letter-spacing:-.01em}} .detail-title:empty{{display:none}} .detail-list{{display:grid;gap:8px}} .detail-item{{border-top:1px solid rgba(0,0,0,.05);padding-top:8px}} .detail-item:first-child{{border-top:none;padding-top:0}} .detail-label{{font-size:14px;font-weight:600}} .detail-sub,.detail-meta,.detail-source{{font-size:13px;color:var(--muted);line-height:1.6}} .detail-source a{{color:inherit}}
.detail-sections{{display:grid;gap:10px;margin-top:16px;padding-top:14px;border-top:1px solid rgba(0,0,0,.06)}} .detail-sections.is-hidden{{display:none}} .meta-fold{{border:1px solid rgba(0,0,0,.06);border-radius:16px;background:rgba(255,255,255,.72);overflow:hidden}} .meta-fold summary{{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;font-size:14px;font-weight:600}} .meta-fold summary::-webkit-details-marker{{display:none}} .meta-count{{color:var(--muted);font-size:12px;font-weight:500}} .meta-fold .meta-list{{padding:0 14px 14px}} .meta-list{{display:grid;gap:8px;color:var(--muted);font-size:14px}} .meta-item{{line-height:1.6}}
.site-footer{{margin-top:22px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;line-height:1.6;text-align:center}} .site-footer a{{color:inherit}}
{active_css}
@media (min-width:900px){{.page{{max-width:1080px}} .detail-sections{{grid-template-columns:1.15fr 1fr}}}} @media (max-width:720px){{.page{{padding:16px 10px 42px}} .month-summary{{padding:16px 12px}} .month-body{{padding:0 10px 14px}} .month-card{{border-radius:24px}} .month-title{{font-size:24px}} .day-cell{{min-height:88px;padding:5px}} .day-num{{font-size:17px}} .chip{{padding:2px 3px 3px;font-size:8.2px;line-height:1.04;letter-spacing:-.055em;border-radius:8px}} .legend-row{{font-size:13px}} .day-detail{{scroll-margin-top:14vh}}}} @media (max-width:520px){{.chip{{font-size:7.2px;padding-left:2px;padding-right:2px;letter-spacing:-.075em}} .chip-text{{display:none}} .chip-mobile-text{{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:1px;min-height:1em;white-space:normal;overflow:hidden}} .chip-mobile-text span{{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .chips{{gap:3px}}}} @media (hover:none), (pointer:coarse){{.day-cell.clickable{{transition:none}} .day-cell.clickable:hover{{transform:none;box-shadow:none;background:linear-gradient(180deg,#fff,#f8f8f5)}} .day-cell.clickable:active{{transform:none}}}}
</style>
</head>
<body>
<div class='page'>
  <section class='hero'>
    <h1>{html.escape(page_title)}</h1>
  </section>
  <section class='legend'>
{legend_row_html}    <div class='legend-meaning'>
      <div class='legend-item'>{legend_meaning_html}</div>
    </div>
  </section>
  <nav class='month-nav'>{month_nav}</nav>
  <section class='month-list'>{''.join(cards)}</section>
  <footer class='site-footer'>© 2026 Mistral-Yu. 非公式ファン制作ページです。各種権利は権利者に帰属します。CC BY-NC 4.0<br><a href='https://github.com/Mistral-Yu/sakurazaka46-live-event-calendar#readme'>README</a></footer>
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
  const parts = new Intl.DateTimeFormat('en-CA', {{timeZone:'Asia/Tokyo', year:'numeric', month:'2-digit', day:'2-digit'}}).formatToParts(new Date());
  const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
  return new Date(Number(values.year), Number(values.month) - 1, Number(values.day));
}};
const dateKeyFromDate = (date) => `${{date.getFullYear()}}-${{String(date.getMonth() + 1).padStart(2, '0')}}-${{String(date.getDate()).padStart(2, '0')}}`;
const applyTodayHighlight = () => {{
  const todayKey = dateKeyFromDate(getCurrentDate());
  for (const cell of root.querySelectorAll('.day-cell.today')) {{
    cell.classList.remove('today');
  }}
  for (const cell of root.querySelectorAll(`.day-cell[data-date="${{CSS.escape(todayKey)}}"]`)) {{
    cell.classList.add('today');
  }}
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
applyTodayHighlight();
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
          <a class='mode-button' href='?mode=plan'>PLAN</a>
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
    <footer class='site-footer'>© 2026 Mistral-Yu. 非公式ファン制作ページです。各種権利は権利者に帰属します。CC BY-NC 4.0<br><a href='https://github.com/Mistral-Yu/sakurazaka46-live-event-calendar#readme'>README</a></footer>
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




def render_plan_tools_html() -> str:
    """Render local JSON controls for the PLAN calendar tab."""
    member_options = json.dumps(json.loads(MEMBERS_TEMPLATE_JSON.read_text()).get("members", []), ensure_ascii=False)
    return f"""<section class='plan-tools' aria-label='PLAN JSON'>
  <div class='plan-tools-header'>
    <div>
      <div class='plan-tools-title'>参加メモ</div>
      <p class='plan-tools-copy'>保存済みJSON/HTMLを読み込むと、参加予定の日をカレンダー上で強調します。読み込み・変換はこのブラウザ内だけで行い、ファイルを外部へ送信しません。公開ページには個人用予定を埋め込みません。</p>
      <ol class='plan-howto'><li>手入力: 日付を選んで参加にチェックし、部数/枚数は <code>1:3,2:5</code> のように入力します。入力後は表示確定後の内容を自分で確認してください。</li><li>Upload JSON/HTML: 保存済みJSON、またはforTUNE music（フォーチュンミュージック）の申込/抽選結果ページをブラウザで開いて <code>Ctrl/⌘+S</code> → HTMLファイルとして保存したものを読み込めます。Ctrl/⌘選択で複数ファイルをまとめて追加・マージできます。カレンダー外の日付はログに <code>カレンダー外 n件</code> と出し、JSON保存には含め、HTML保存では除外します。HTMLからの変換は `scripts/fortune_meet_html_to_plan_json.py` でも実行できます。変換後は日付・メンバー・部数/枚数を自分で確認してください。</li></ol>
    </div>
  </div>
  <div class='plan-actions'>
    <label class='plan-file-button'>
      <span>Upload JSON/HTML</span>
        <input type='file' multiple accept='.json,.html,.htm,application/json,text/html' data-plan-file>
    </label>
    <button class='plan-confirm-toggle' type='button' data-plan-confirm-toggle disabled>表示を確定</button>
    <button class='plan-save-page' type='button' data-plan-save-page disabled>Save Page</button>
    <button class='plan-download' type='button' data-plan-download disabled>Save JSON</button>
    <span class='plan-status' data-plan-status>未読み込み</span>
  </div>
  <div class='plan-confirmed-list' data-plan-confirmed-list hidden></div>
</section>
<script>
const initPlanTools = () => {{
const root = document.querySelector("[data-mode='plan']");
if (!root) return;
const fileInput = root.querySelector('[data-plan-file]');
const status = root.querySelector('[data-plan-status]');
const confirmedList = root.querySelector('[data-plan-confirmed-list]');
const downloadButton = root.querySelector('[data-plan-download]');
const savePageButton = root.querySelector('[data-plan-save-page]');
const confirmToggle = root.querySelector('[data-plan-confirm-toggle]');
const memberOptions = {member_options};
let currentPlan = null;
let planConfirmed = false;
let currentFilename = 'sakurazaka46_plan.json';
let planItemsByDate = new Map();
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[char]));
const toNumberOrEmpty = (value) => {{
  if (value === '' || value === null || value === undefined) return '';
  const number = Number(value);
  return Number.isFinite(number) ? number : '';
}};
const normalizeSlotText = (value) => String(value || '')
  .replace(/[０-９]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xFEE0))
  .replace(/[：]/g, ':')
  .replace(/[，、]/g, ',');
const formatSlotSummary = (value) => normalizeSlotText(value).split(',')
  .map((part) => part.trim())
  .filter(Boolean)
  .map((part) => {{
    const match = part.match(/^(\\d+)\\s*:\\s*(\\d+)$/);
    return match ? `${{match[1]}}部${{match[2]}}枚` : part;
  }})
  .join('・');
const slotTextToMap = (value) => {{
  const map = new Map();
  normalizeSlotText(value).split(',').map((part) => part.trim()).filter(Boolean).forEach((part) => {{
    const match = part.match(/^(\\d+)\\s*:\\s*(\\d+)$/);
    if (!match) return;
    const key = Number(match[1]);
    map.set(key, (map.get(key) || 0) + Number(match[2]));
  }});
  return map;
}};
const slotMapToText = (map) => Array.from(map.entries()).sort((a, b) => a[0] - b[0]).map(([part, count]) => `${{part}}:${{count}}`).join(',');
const getConfirmedSlotNotes = (items = []) => items
  .filter((item) => item && item.attending !== false && isMeetEventName(item.event))
  .flatMap((item) => (Array.isArray(item.members) ? item.members : [])
    .map((member) => {{
      const slots = formatSlotSummary(member && member.slots);
      if (!slots) return '';
      const name = formatMemberDisplayName(member);
      return name ? `${{name}} ${{slots}}` : slots;
    }})
    .filter(Boolean));
const getConfirmedItemSummary = (item) => {{
  if (!item || item.attending === false) return '';
  if (isMeetEventName(item.event)) {{
    const notes = getConfirmedSlotNotes([item]);
    return notes.length ? `${{item.event || 'ミーグリ'}}: ${{notes.join(' / ')}}` : (item.event || 'ミーグリ');
  }}
  return item.memo ? `${{item.event || '予定'}}: ${{item.memo}}` : (item.event || '予定');
}};
const renderConfirmedList = () => {{
  if (!confirmedList) return;
  const items = getSortedItems().filter((item) => item.attending !== false);
  confirmedList.hidden = !planConfirmed || !items.length;
  if (confirmedList.hidden) {{
    confirmedList.innerHTML = '';
    return;
  }}
  confirmedList.innerHTML = `<div class='plan-confirmed-list-title'>参加予定</div>`
    + items.map((item) => `<div class='plan-confirmed-list-item'><span>${{escapeHtml(item.date)}}</span><span>${{escapeHtml(getConfirmedItemSummary(item))}}</span></div>`).join('');
}};
const itemSortKey = (item) => `${{item.date}}\n${{item.event || ''}}`;
const saveBlob = async (blob, suggestedName) => {{
  if (window.showSaveFilePicker) {{
    const handle = await window.showSaveFilePicker({{suggestedName}});
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }}
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = suggestedName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}};
const buildConfirmedPageHtml = () => {{
  const clone = document.documentElement.cloneNode(true);
  const planView = clone.querySelector("[data-mode='plan']");
  if (!planView) return '<!doctype html>\\n' + clone.outerHTML;
  for (const view of Array.from(clone.querySelectorAll('.calendar-view'))) {{
    if (view !== planView) view.remove();
  }}
  planView.hidden = false;
  planView.classList.add('plan-confirmed');
  for (const script of Array.from(clone.querySelectorAll('script'))) script.remove();
  planView.querySelector('.plan-tools')?.remove();
  planView.querySelector('.mode-switch')?.remove();
  for (const element of Array.from(planView.querySelectorAll('script,.day-detail,.detail-target,.plan-selected-editor'))) element.remove();
  for (const link of Array.from(planView.querySelectorAll('a.day-cell'))) {{
    const div = clone.ownerDocument.createElement('div');
    div.className = link.className;
    div.innerHTML = link.innerHTML;
    for (const attr of Array.from(link.attributes)) {{
      if (['class', 'href', 'data-detail-key', 'data-month'].includes(attr.name)) continue;
      div.setAttribute(attr.name, attr.value);
    }}
    link.replaceWith(div);
  }}
  return '<!doctype html>\\n' + clone.outerHTML;
}};
const planFromFortuneHtml = (text, filename) => {{
  const plain = String(text || '')
    .replace(/<br\s*\/?>/gi, '\\n')
    .replace(/<\/(?:tr|p|div|li|dd|dt|td|th|span|h\d)>/gi, '\\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ');
  const decoded = new DOMParser().parseFromString(`<textarea>${{plain}}</textarea>`, 'text/html').querySelector('textarea')?.value || plain;
  const eventNameRaw = String(filename || 'forTUNEミーグリ').replace(/\.(html?|json)$/i, '').normalize('NFC');
  const eventName = eventNameRaw.match(/ミーグリ/) ? eventNameRaw : `${{eventNameRaw}} ミーグリ`;
  const groups = new Map();
  let currentDate = '';
  const tokenRe = /(20\d{{2}})\s*[年\/.\-]\s*(\d{{1,2}})\s*[月\/.\-]\s*(\d{{1,2}})\s*日?|第\s*(\d+)\s*部[\s\S]{{0,80}}?([一-龠々〆ヵヶぁ-んァ-ヶー]+[\s　]+[一-龠々〆ヵヶぁ-んァ-ヶー]+)[\s　]+(\d+)\s*枚/g;
  let match;
  while ((match = tokenRe.exec(decoded)) !== null) {{
    if (match[1]) {{
      currentDate = `${{match[1]}}-${{String(Number(match[2])).padStart(2, '0')}}-${{String(Number(match[3])).padStart(2, '0')}}`;
      continue;
    }}
    if (!currentDate) throw new Error('HTMLから日付を検出できませんでした。scripts/fortune_meet_html_to_plan_json.py --date YYYY-MM-DD で変換してください。');
    const part = Number(match[4]);
    const name = match[5].replace(/[\s　]+/g, '');
    const count = Number(match[6]);
    const members = groups.get(currentDate) || new Map();
    const slots = members.get(name) || new Map();
    slots.set(part, (slots.get(part) || 0) + count);
    members.set(name, slots);
    groups.set(currentDate, members);
  }}
  if (!groups.size) throw new Error('HTMLから第N部・メンバー名・枚数の行を検出できませんでした。');
  return {{
    version: 1,
    items: Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([date, members]) => ({{
      date,
      event: eventName,
      attending: true,
      members: Array.from(members.entries()).map(([name, slots]) => ({{
        name,
        slots: Array.from(slots.entries()).sort((a, b) => a[0] - b[0]).map(([part, count]) => `${{part}}:${{count}}`).join(',')
      }}))
    }}))
  }};
}};
const normalizePlan = (raw) => {{
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('JSONの最上位は object にしてください。');
  const items = Array.isArray(raw.items) ? raw.items : null;
  if (!items) throw new Error('items 配列が見つかりません。');
  return {{
    version: raw.version || 1,
    items: items.map((item, index) => {{
      if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error(`items[${{index}}] は object にしてください。`);
      const normalized = {{
        date: String(item.date || '').trim(),
        event: String(item.event || item.title || '').trim(),
        attending: item.attending === false ? false : true,
        memo: String(item.memo || '').trim(),
        members: Array.isArray(item.members) ? item.members.map((member) => ({{
          name: String(member && (member.name || member.member) || '').trim(),
          name2: String(member && (member.name2 || member.secondName || member.pairName || '') || '').trim(),
          slots: String(member && (member.slots || member.parts || '') || '').trim()
        }})) : []
      }};
      if (!normalized.members.length && (item.member || item.parts || item.tickets)) {{
        const parts = String(item.parts || '').trim();
        const tickets = String(item.tickets || '').trim();
        normalized.members = [{{name: String(item.member || '').trim(), slots: parts || tickets ? `${{parts}}:${{tickets}}` : ''}}];
      }}
      if (!/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(normalized.date)) throw new Error(`items[${{index}}].date は YYYY-MM-DD 形式にしてください。`);
      return normalized;
    }}).sort((a, b) => itemSortKey(a).localeCompare(itemSortKey(b)))
  }};
}};
const mergePlans = (...plans) => {{
  const mergedItems = [];
  const byKey = new Map();
  const mergeMember = (target, source) => {{
    const name = String(source.name || '').trim();
    if (!name) return;
    let member = target.members.find((candidate) => candidate.name === name);
    if (!member) {{
      member = {{name, slots: ''}};
      target.members.push(member);
    }}
    const slots = slotTextToMap(member.slots);
    for (const [part, count] of slotTextToMap(source.slots).entries()) slots.set(part, (slots.get(part) || 0) + count);
    member.slots = slotMapToText(slots) || member.slots || source.slots || '';
  }};
  for (const plan of plans.filter(Boolean)) {{
    for (const item of normalizePlan(plan).items) {{
      const key = `${{item.date}}\n${{item.event || ''}}`;
      let target = byKey.get(key);
      if (!target) {{
        target = {{date: item.date, event: item.event, attending: item.attending, memo: item.memo || '', members: []}};
        byKey.set(key, target);
        mergedItems.push(target);
      }} else {{
        target.attending = target.attending !== false || item.attending !== false;
        if (item.memo && !target.memo) target.memo = item.memo;
      }}
      for (const member of item.members || []) mergeMember(target, member);
    }}
  }}
  return normalizePlan({{version: 1, items: mergedItems}});
}};
const getPanelForCell = (cell) => {{
  const panelId = cell?.dataset.month;
  return panelId ? root.querySelector(`[data-panel-month='${{CSS.escape(panelId)}}']`) : null;
}};
const getChipNamesFromCell = (cell) => {{
  const names = Array.from(cell?.querySelectorAll('.chip-text') || [])
    .map((node) => node.textContent.trim())
    .filter(Boolean);
  return Array.from(new Set(names));
}};
const cleanEventName = (value) => String(value || '').replace(/^(LIVE|EVENT):\\s*/, '').trim();
const getEventNamesFromCell = (cell) => {{
  const panel = getPanelForCell(cell);
  const detailNames = Array.from(panel?.querySelectorAll('.detail-item') || [])
    .map((item) => {{
      const label = cleanEventName(item.querySelector('.detail-label')?.textContent || '');
      const sub = String(item.querySelector('.detail-sub')?.textContent || '').trim();
      return [label, sub].filter(Boolean).join(' / ');
    }})
    .filter(Boolean);
  const names = detailNames.length ? detailNames : getChipNamesFromCell(cell);
  return Array.from(new Set(names));
}};
const isMeetEventName = (eventName) => /ミーグリ|ミート＆グリート|リアルミーグリ/.test(eventName || '');
const syncPlanDetailCollapse = (panel, collapsed = true) => {{
  if (!panel) return;
  panel.classList.toggle('plan-detail-collapsed', collapsed);
  const button = panel.querySelector('[data-plan-detail-toggle]');
  if (button) {{
    button.setAttribute('aria-expanded', String(!collapsed));
    button.textContent = collapsed ? '詳細を展開' : '詳細を閉じる';
  }}
  const title = panel.querySelector('.detail-title');
  if (title && title.textContent.trim()) {{
    title.setAttribute('role', 'button');
    title.setAttribute('tabindex', '0');
    title.setAttribute('aria-expanded', String(!collapsed));
    title.setAttribute('title', collapsed ? '詳細を展開' : '詳細を閉じる');
  }}
}};
const togglePlanDetail = (panel) => {{
  if (!panel) return;
  const collapsed = !panel.classList.contains('plan-detail-collapsed');
  syncPlanDetailCollapse(panel, collapsed);
}};
const wirePlanTitleToggle = (panel) => {{
  const title = panel?.querySelector('.detail-title');
  if (!title || title.dataset.planDetailTitleToggle === 'true') return;
  title.dataset.planDetailTitleToggle = 'true';
  title.addEventListener('click', () => togglePlanDetail(panel));
  title.addEventListener('keydown', (event) => {{
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    togglePlanDetail(panel);
  }});
}};
const compactPlanItem = (item) => {{
  const compact = {{date: item.date, event: item.event || '', attending: item.attending !== false}};
  if (isMeetEventName(item.event)) {{
    compact.members = Array.isArray(item.members) ? item.members
      .filter((member) => (member.name || '').trim() || (member.name2 || '').trim() || (member.slots || '').trim())
      .map((member) => ({{name: member.name || '', name2: member.name2 || '', slots: member.slots || ''}})) : [];
  }} else {{
    compact.memo = item.memo || '';
  }}
  return compact;
}};
const getSortedItems = () => Array.from(planItemsByDate.values()).flat().sort((a, b) => itemSortKey(a).localeCompare(itemSortKey(b)));
const countCalendarOutsideItems = () => getSortedItems().filter((item) => !root.querySelector(`[data-date='${{CSS.escape(item.date)}}']`)).length;
const withCalendarOutsideLog = (message, suffix = '') => {{
  const outside = countCalendarOutsideItems();
  return `${{message}}${{outside ? ` / カレンダー外 ${{outside}}件` : ''}}${{suffix}}`;
}};
const updateCurrentItem = (date, index, field, value) => {{
  const items = planItemsByDate.get(date);
  const item = items && items[index];
  if (!item) return;
  if (field === 'attending') {{
    item.attending = value === true || value === 'true';
  }} else {{
    item[field] = value;
  }}
}};
const ensureMembers = (item) => {{
  if (!Array.isArray(item.members)) item.members = [];
  if (!item.members.length) item.members.push({{name: '', slots: ''}});
  return item.members;
}};
const updateMemberItem = (date, itemIndex, memberIndex, field, value) => {{
  const item = (planItemsByDate.get(date) || [])[itemIndex];
  if (!item) return;
  const members = ensureMembers(item);
  if (!members[memberIndex]) members[memberIndex] = {{name: '', slots: ''}};
  members[memberIndex][field] = value;
}};
const renderMemberOptions = (selected) => ["", ...memberOptions].map((member) => `<option value='${{escapeHtml(member)}}' ${{member === selected ? 'selected' : ''}}>${{escapeHtml(member || '選択')}}</option>`).join('');
const isNationwideMeetEventName = (eventName) => /ミーグリ\(全国\)|オンラインミーグリ\(全国\)|全国/.test(eventName || '');
const formatMemberDisplayName = (member) => {{
  const first = String(member && member.name || '').trim();
  const second = String(member && member.name2 || '').trim();
  return [first, second].filter(Boolean).join('・');
}};
const renderMemberRows = (item, itemIndex) => {{
  const nationwide = isNationwideMeetEventName(item.event);
  return ensureMembers(item).map((member, memberIndex) => `
  <div class='plan-member-row ${{nationwide ? 'plan-member-row-wide' : ''}}' data-plan-member-index='${{memberIndex}}'>
    <select data-plan-edit-member aria-label='メンバー1'><option value=''>${{nationwide ? 'メンバー1' : '選択'}}</option>${{memberOptions.map((name) => `<option value='${{escapeHtml(name)}}' ${{name === member.name ? 'selected' : ''}}>${{escapeHtml(name)}}</option>`).join('')}}</select>
    ${{nationwide ? `<select data-plan-edit-member2 aria-label='メンバー2'><option value=''>メンバー2（任意）</option>${{memberOptions.map((name) => `<option value='${{escapeHtml(name)}}' ${{name === member.name2 ? 'selected' : ''}}>${{escapeHtml(name)}}</option>`).join('')}}</select>` : ''}}
    <label class='plan-slots-field'>
      <input type='text' inputmode='numeric' pattern='[0-9:,、， ]*' data-plan-edit-slots value='${{escapeHtml(member.slots || '')}}' placeholder='例 1:3,2:5'>
      <span>${{nationwide ? '全国: 1枚で2人と話せる枠は2人目も選択' : '例: 1:3=1部3枚、2:5=2部5枚'}}</span>
    </label>
    <button class='plan-member-remove' type='button' data-plan-member-remove>削除</button>
  </div>`).join('');
}};
const refreshSelectedEditor = (date) => setSelectedEditor(date, planItemsByDate.get(date) || []);
const refreshPlanCellState = (date) => {{
  const items = planItemsByDate.get(date) || [];
  const activeCount = items.filter((item) => item.attending !== false).length;
  const slotNotes = planConfirmed ? getConfirmedSlotNotes(items) : [];
  for (const cell of root.querySelectorAll(`[data-date='${{CSS.escape(date)}}']`)) {{
    cell.classList.toggle('plan-participating', activeCount > 0);
    cell.querySelector('.plan-slot-notes')?.remove();
    if (activeCount > 0) {{
      cell.dataset.planCount = String(activeCount);
      cell.title = `参加予定 ${{activeCount}}件`;
      if (slotNotes.length) {{
        const note = document.createElement('div');
        note.className = 'plan-slot-notes';
        note.innerHTML = slotNotes.map((line) => `<span>${{escapeHtml(line)}}</span>`).join('');
        (cell.querySelector('.chips') || cell).appendChild(note);
      }}
    }} else {{
      cell.removeAttribute('data-plan-count');
      cell.removeAttribute('title');
    }}
  }}
}};
const syncCurrentPlanFromMap = () => {{
  if (!currentPlan) currentPlan = {{version: 1, items: []}};
  currentPlan.items = getSortedItems().map(compactPlanItem);
  status.textContent = withCalendarOutsideLog(`${{currentPlan.items.length}}件を編集中`);
  downloadButton.disabled = false;
  if (savePageButton) savePageButton.disabled = currentPlan.items.length === 0;
  if (confirmToggle) confirmToggle.disabled = currentPlan.items.length === 0;
  renderConfirmedList();
}};
const refreshAllPlanCells = () => {{
  for (const date of planItemsByDate.keys()) refreshPlanCellState(date);
}};
const setPlanConfirmed = (confirmed) => {{
  planConfirmed = confirmed;
  root.classList.toggle('plan-confirmed', planConfirmed);
  if (confirmToggle) confirmToggle.textContent = planConfirmed ? '編集に戻る' : '表示を確定';
  refreshAllPlanCells();
  renderConfirmedList();
}};
const ensureEditableItemsForCell = (cell) => {{
  const date = cell?.dataset.date;
  if (!date) return [];
  let items = planItemsByDate.get(date);
  const eventNames = getEventNamesFromCell(cell);
  if (!items || !items.length) {{
    items = (eventNames.length ? eventNames : ['カレンダー予定']).map((eventName) => ({{
      date,
      event: eventName,
      attending: false,
      memo: '',
      members: []
    }}));
    planItemsByDate.set(date, items);
    refreshPlanCellState(date);
    syncCurrentPlanFromMap();
  }} else {{
    for (const [index, item] of items.entries()) {{
      if (!item.event) item.event = eventNames[index] || eventNames[0] || 'カレンダー予定';
    }}
  }}
  return items;
}};
const setSelectedEditor = (date, items) => {{
  const cell = root.querySelector(`[data-date='${{CSS.escape(date)}}']`);
  const panel = getPanelForCell(cell);
  if (!panel) return;
  let block = panel.querySelector('.plan-selected-editor');
  if (!block) {{
    block = document.createElement('section');
    block.className = 'plan-selected-editor';
    const detailList = panel.querySelector('.detail-list');
    panel.insertBefore(block, detailList || panel.firstChild);
  }}
  const cards = items.map((item, index) => {{
    const eventName = item.event || getEventNamesFromCell(cell)[index] || 'カレンダー予定';
    item.event = eventName;
    const isMeet = isMeetEventName(eventName);
    const meetFields = `
      <div class='plan-member-list'>${{renderMemberRows(item, index)}}</div>
      <button class='plan-member-add' type='button' data-plan-member-add>＋ メンバー追加</button>`;
    const memoField = `<label class='plan-edit-row plan-edit-row-memo'><span class='plan-edit-label'>メモ</span><textarea data-plan-edit-memo rows='2'>${{escapeHtml(item.memo || '')}}</textarea></label>`;
    return `
    <div class='plan-edit-card' data-plan-edit-index='${{index}}'>
      <div class='plan-edit-event'>${{escapeHtml(eventName)}}</div>
      <label class='plan-attending-check'><input type='checkbox' data-plan-edit-attending ${{item.attending !== false ? 'checked' : ''}}>参加</label>
      ${{isMeet ? meetFields : memoField}}
    </div>`;
  }}).join('');
  block.innerHTML = `<div class='plan-selected-editor-title'>参加メモ</div><div class='plan-edit-row'><span class='plan-edit-label'>日付</span><span class='plan-edit-static'>${{escapeHtml(date)}}</span></div>${{cards}}<button class='plan-detail-toggle' type='button' data-plan-detail-toggle aria-expanded='false'>詳細を展開</button>`;
  block.hidden = false;
  wirePlanTitleToggle(panel);
  syncPlanDetailCollapse(panel, true);
  block.querySelector('[data-plan-detail-toggle]')?.addEventListener('click', () => togglePlanDetail(panel));
  for (const card of block.querySelectorAll('.plan-edit-card')) {{
    const index = Number(card.dataset.planEditIndex || '0');
    card.querySelector('[data-plan-edit-attending]')?.addEventListener('change', (event) => {{
      updateCurrentItem(date, index, 'attending', event.target.checked);
      refreshPlanCellState(date);
      syncCurrentPlanFromMap();
    }});
    card.querySelector('[data-plan-edit-memo]')?.addEventListener('input', (event) => {{
      updateCurrentItem(date, index, 'memo', event.target.value);
      syncCurrentPlanFromMap();
    }});
    for (const row of card.querySelectorAll('.plan-member-row')) {{
      const memberIndex = Number(row.dataset.planMemberIndex || '0');
      row.querySelector('[data-plan-edit-member]')?.addEventListener('change', (event) => {{
        updateMemberItem(date, index, memberIndex, 'name', event.target.value);
        refreshPlanCellState(date);
        syncCurrentPlanFromMap();
      }});
      row.querySelector('[data-plan-edit-member2]')?.addEventListener('change', (event) => {{
        updateMemberItem(date, index, memberIndex, 'name2', event.target.value);
        refreshPlanCellState(date);
        syncCurrentPlanFromMap();
      }});
      row.querySelector('[data-plan-edit-slots]')?.addEventListener('input', (event) => {{
        updateMemberItem(date, index, memberIndex, 'slots', event.target.value);
        refreshPlanCellState(date);
        syncCurrentPlanFromMap();
      }});
      row.querySelector('[data-plan-member-remove]')?.addEventListener('click', () => {{
        const item = (planItemsByDate.get(date) || [])[index];
        if (!item) return;
        ensureMembers(item).splice(memberIndex, 1);
        if (!item.members.length) item.members.push({{name: '', name2: '', slots: ''}});
        refreshSelectedEditor(date);
        refreshPlanCellState(date);
        syncCurrentPlanFromMap();
      }});
    }}
    card.querySelector('[data-plan-member-add]')?.addEventListener('click', () => {{
      const item = (planItemsByDate.get(date) || [])[index];
      if (!item) return;
      ensureMembers(item).push({{name: '', name2: '', slots: ''}});
      refreshSelectedEditor(date);
      refreshPlanCellState(date);
      syncCurrentPlanFromMap();
    }});
  }}
}};
const clearSelectedEditor = () => {{
  for (const block of root.querySelectorAll('.plan-selected-editor')) {{
    block.hidden = true;
    block.innerHTML = '';
  }}
  for (const panel of root.querySelectorAll('.day-detail')) syncPlanDetailCollapse(panel, true);
}};
const applyPlanToCalendar = (plan) => {{
  planItemsByDate = new Map();
  for (const cell of root.querySelectorAll('.day-cell.plan-participating')) {{
    cell.classList.remove('plan-participating');
    cell.removeAttribute('data-plan-count');
    cell.querySelector('.plan-slot-notes')?.remove();
  }}
  clearSelectedEditor();
  for (const item of plan.items) {{
    const items = planItemsByDate.get(item.date) || [];
    items.push(item);
    planItemsByDate.set(item.date, items);
  }}
  for (const date of planItemsByDate.keys()) {{
    const cells = root.querySelectorAll(`[data-date='${{CSS.escape(date)}}']`);
    if (!cells.length) continue;
    refreshPlanCellState(date);
  }}
  status.textContent = withCalendarOutsideLog(`${{plan.items.length}}件を読み込み`);
  downloadButton.disabled = false;
  if (savePageButton) savePageButton.disabled = plan.items.length === 0;
  if (confirmToggle) confirmToggle.disabled = plan.items.length === 0;
  setPlanConfirmed(false);
}};
const showError = (message) => {{
  clearSelectedEditor();
  for (const cell of root.querySelectorAll('.day-cell.plan-participating')) {{
    cell.classList.remove('plan-participating');
    cell.querySelector('.plan-slot-notes')?.remove();
  }}
  planItemsByDate = new Map();
  status.textContent = `読み込みエラー: ${{message}}`;
  downloadButton.disabled = true;
  if (savePageButton) savePageButton.disabled = true;
  if (confirmToggle) confirmToggle.disabled = true;
  setPlanConfirmed(false);
}};
fileInput?.addEventListener('change', async () => {{
  const files = Array.from(fileInput.files || []);
  if (!files.length) return;
  currentFilename = files.length === 1 ? (files[0].name || currentFilename) : 'sakurazaka46_plan.json';
  try {{
    const loadedPlans = [];
    for (const file of files) {{
      const text = await file.text();
      const isHtml = /\.html?$/i.test(file.name || '') || /^text\/html/i.test(file.type || '');
      loadedPlans.push(isHtml ? planFromFortuneHtml(text, file.name) : JSON.parse(text));
    }}
    currentPlan = mergePlans(currentPlan, ...loadedPlans);
    applyPlanToCalendar(currentPlan);
    status.textContent = withCalendarOutsideLog(`${{currentPlan.items.length}}件を読み込み`, files.length > 1 ? ` / ${{files.length}}ファイルをマージ` : '');
  }} catch (error) {{
    currentPlan = null;
    showError(error && error.message ? error.message : String(error));
  }}
}});
root.addEventListener('click', (event) => {{
  const cell = event.target.closest('[data-date]');
  if (!cell || !root.contains(cell)) return;
  setTimeout(() => {{
    const panel = getPanelForCell(cell);
    syncPlanDetailCollapse(panel, true);
    const items = ensureEditableItemsForCell(cell);
    if (items.length) {{
      setSelectedEditor(cell.dataset.date, items);
    }} else {{
      clearSelectedEditor();
    }}
  }}, 0);
}});
confirmToggle?.addEventListener('click', () => {{
  if (confirmToggle.disabled) return;
  setPlanConfirmed(!planConfirmed);
}});
downloadButton?.addEventListener('click', async () => {{
  if (!currentPlan) return;
  syncCurrentPlanFromMap();
  const blob = new Blob([JSON.stringify(currentPlan, null, 2) + '\\n'], {{type: 'application/json'}});
  try {{
    await saveBlob(blob, currentFilename || 'sakurazaka46_plan.json');
    status.textContent = withCalendarOutsideLog(`${{currentPlan.items.length}}件のJSONを保存`, countCalendarOutsideItems() ? 'も含む' : '');
  }} catch (error) {{
    if (error && error.name === 'AbortError') return;
    status.textContent = `保存エラー: ${{error && error.message ? error.message : String(error)}}`;
  }}
}});
savePageButton?.addEventListener('click', async () => {{
  if (!currentPlan) return;
  syncCurrentPlanFromMap();
  setPlanConfirmed(true);
  const pageHtml = buildConfirmedPageHtml();
  const blob = new Blob([pageHtml], {{type: 'text/html'}});
  const suggested = (currentFilename || 'sakurazaka46_plan.json').replace(/\.(json|html?)$/i, '') + '_confirmed.html';
  try {{
    await saveBlob(blob, suggested);
    status.textContent = countCalendarOutsideItems() ? `表示確定ページを保存 / カレンダー外 ${{countCalendarOutsideItems()}}件はHTMLから除外` : '表示確定ページを保存';
  }} catch (error) {{
    if (error && error.name === 'AbortError') return;
    status.textContent = `ページ保存エラー: ${{error && error.message ? error.message : String(error)}}`;
  }}
}});
}};
if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', initPlanTools, {{once:true}});
}} else {{
  initPlanTools();
}}
</script>"""

def render_combined_html(live_html: str, event_html: str, all_html: str | None = None, next14_html: str | None = None, plan_html: str | None = None) -> str:
    live_style, live_body, live_script = extract_calendar_parts(live_html)
    _event_style, event_body, event_script = extract_calendar_parts(event_html)
    all_body = all_script = None
    if all_html is not None:
        _all_style, all_body, all_script = extract_calendar_parts(all_html)
    plan_body = plan_script = None
    if plan_html is None and all_html is not None:
        plan_html = all_html
    if plan_html is not None:
        _plan_style, plan_body, plan_script = extract_calendar_parts(plan_html)
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
.calendar-view:not([data-mode='next14']) .day-cell.clickable{cursor:pointer;transition:transform .18s ease, background .18s ease;position:relative;border-radius:0;background:#fff;border:0;border-top:1px solid var(--line);border-left:1px solid var(--line);box-shadow:none}
.calendar-view:not([data-mode='next14']) .day-cell:nth-child(7n+1){border-left:none}
.calendar-view:not([data-mode='next14']) .day-cell.clickable::after{content:none}
.calendar-view:not([data-mode='next14']) .day-cell.clickable:hover{background:#faf9f6;transform:translateY(-1px);box-shadow:none;border-color:var(--line)}
.calendar-view:not([data-mode='next14']) .day-cell.clickable.today{background-color:rgba(201,183,255,.10)!important;background-image:none!important;box-shadow:none;border-color:var(--line)}
.calendar-view:not([data-mode='next14']) .day-cell.clickable.is-pressed,.calendar-view:not([data-mode='next14']) .day-cell.clickable:active{background:#eef2ff;box-shadow:none;border-color:var(--line)}
.calendar-view:not([data-mode='next14']) .day-cell.clickable.active{background-color:#f3f5ff!important;background-image:none!important;box-shadow:none;border-color:var(--line)}
.calendar-view:not([data-mode='next14']) .day-cell.clickable.active.today{background-color:rgba(201,183,255,.14)!important;background-image:none!important;box-shadow:none;border-color:var(--line)}
.calendar-view:not([data-mode='next14']) .day-cell.clickable:has(.detail-target:target){background-color:#f3f5ff!important;background-image:none!important;box-shadow:none!important;border-color:var(--line)!important}
.calendar-view:not([data-mode='next14']) .day-cell.clickable.today:has(.detail-target:target){background-color:rgba(201,183,255,.14)!important;background-image:none!important;box-shadow:none!important;border-color:var(--line)!important}
.next14-card{background:var(--card);border:1px solid var(--line);border-radius:28px;box-shadow:0 18px 44px rgba(30,30,28,.05);padding:16px;overflow:hidden}.next14-title{font-size:clamp(26px,3vw,34px);line-height:1;font-weight:600;letter-spacing:-.035em;color:#3b3a36}.next14-range{margin-top:8px;color:var(--muted);font-size:13px}.next14-list{display:grid;gap:8px;margin-top:16px}.next14-row{border:1px solid rgba(231,229,222,.86);border-radius:18px;background:#fff;overflow:hidden}.next14-row.next14-today{box-shadow:inset 0 0 0 1px rgba(201,183,255,.42);background:rgba(201,183,255,.08)}.next14-row-main{width:100%;display:grid;grid-template-columns:92px 1fr;align-items:center;gap:10px;padding:10px 12px;border:none;background:transparent;color:inherit;text-align:left;font:inherit;cursor:pointer}.next14-row-main:disabled{cursor:default}.next14-date{font-size:14px;font-weight:700;color:var(--text);white-space:nowrap}.next14-date.next14-weekend{color:var(--weekend)}.next14-items{display:flex;gap:5px;flex-wrap:wrap;align-items:center}.next14-items .chip{align-self:auto;display:inline-flex;max-width:100%;padding:3px 7px 4px}.next14-empty{color:var(--muted);font-size:13px}.next14-detail{border-top:1px solid rgba(0,0,0,.06);padding:10px 12px 12px;background:linear-gradient(180deg,#fcfcfa,#f8f8f5)}.next14-detail[hidden]{display:none}.next14-detail-item{padding-top:8px;border-top:1px solid rgba(0,0,0,.05)}.next14-detail-item:first-child{padding-top:0;border-top:none}.next14-source a{color:inherit}@media (max-width:520px){.next14-row-main{grid-template-columns:74px 1fr;padding:9px 10px}.next14-date{font-size:13px}.next14-card{padding:12px;border-radius:22px}.next14-items .chip .chip-text{display:block;white-space:normal;overflow:visible;text-overflow:clip}.next14-items .chip{font-size:10px;line-height:1.12;padding:3px 6px}.next14-items{gap:4px}}
.plan-tools{background:var(--card);border:1px solid var(--line);border-radius:24px;box-shadow:0 16px 40px rgba(30,30,28,.06);padding:16px 18px;margin:0 0 18px}.plan-tools-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap}.plan-tools-title{font-size:18px;margin:0 0 6px;font-weight:700;color:#3b3a36}.plan-tools-copy{margin:0;color:var(--muted);font-size:14px;line-height:1.7;max-width:68ch}.plan-howto{margin:10px 0 0;padding-left:1.25em;color:var(--muted);font-size:13px;line-height:1.65;max-width:78ch}.plan-howto code{background:rgba(0,0,0,.05);border-radius:6px;padding:1px 5px;color:#3b3a36}.plan-tools-actions{display:flex;gap:8px;flex-wrap:wrap}.plan-file-button{display:inline-flex;align-items:center;justify-content:center;position:relative;overflow:hidden;border-radius:999px;border:1px solid #1e1e1c;background:#1e1e1c;color:#fff;font-size:13px;font-weight:700;padding:9px 14px;cursor:pointer;text-decoration:none}.plan-file-button input{position:absolute;inset:0;opacity:0;cursor:pointer}.plan-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px}.plan-download,.plan-detail-toggle,.plan-confirm-toggle,.plan-save-page{border:1px solid var(--line);background:#fff;color:var(--text);border-radius:999px;padding:9px 14px;font-size:13px;font-weight:700;cursor:pointer}.plan-confirm-toggle{background:#1e1e1c;color:#fff;border-color:#1e1e1c}.plan-download:disabled,.plan-confirm-toggle:disabled,.plan-save-page:disabled{opacity:.45;cursor:default}.plan-status{color:var(--muted);font-size:13px}.plan-confirmed-list{margin-top:12px;border-top:1px solid rgba(0,0,0,.06);padding-top:10px;display:grid;gap:6px}.plan-confirmed-list[hidden]{display:none}.plan-confirmed-list-title{font-size:13px;font-weight:800;color:#3b3a36}.plan-confirmed-list-item{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;font-size:13px;line-height:1.5;color:#3b3a36}.plan-confirmed-list-item span:first-child{color:var(--muted);font-weight:700}.calendar-view[data-mode='plan'] .day-cell.plan-participating{background-color:rgba(201,183,255,.16)!important;background-image:none!important;box-shadow:inset 0 0 0 1px rgba(91,110,240,.20)!important}.calendar-view[data-mode='plan'] .day-cell.plan-participating::before{content:'参加';position:absolute;right:5px;top:5px;border-radius:999px;background:#1e1e1c;color:#fff;font-size:10px;font-weight:800;letter-spacing:.03em;line-height:1;padding:4px 6px;z-index:3;box-shadow:0 5px 14px rgba(30,30,28,.14)}.calendar-view[data-mode='plan'] .plan-slot-notes{display:grid;gap:2px;margin-top:3px;color:#8a4060;font-size:10px;font-weight:700;line-height:1.25;text-align:center;white-space:normal}.calendar-view[data-mode='plan'] .plan-slot-notes span{display:block;overflow:hidden;text-overflow:ellipsis}.calendar-view[data-mode='plan'].plan-confirmed .plan-selected-editor,.calendar-view[data-mode='plan'].plan-confirmed .day-detail{display:none!important}.calendar-view[data-mode='plan'] .day-cell.plan-participating.active,.calendar-view[data-mode='plan'] .day-cell.plan-participating:has(.detail-target:target){background-color:rgba(201,183,255,.34)!important}.calendar-view[data-mode='plan'] .detail-sections{display:none}.calendar-view[data-mode='plan'] .detail-title{display:none!important}.calendar-view[data-mode='plan'] .day-detail.plan-detail-collapsed .detail-list{display:none}.plan-selected-editor{margin-top:12px;border:1px solid rgba(91,110,240,.18);border-radius:16px;background:#fff;padding:12px;display:grid;gap:10px}.plan-selected-editor[hidden]{display:none}.plan-selected-editor-title{font-size:13px;font-weight:700;color:#3b3a36}.plan-edit-card{display:grid;gap:8px;border-top:1px solid rgba(0,0,0,.05);padding-top:10px}.plan-edit-card:first-of-type{border-top:none;padding-top:0}.plan-edit-event{font-size:13px;font-weight:700;color:#3b3a36;line-height:1.5}.plan-edit-row{display:grid;grid-template-columns:64px minmax(0,1fr);align-items:center;gap:8px}.plan-edit-row-memo{align-items:start}.plan-edit-label{color:var(--muted);font-size:12px;font-weight:700}.plan-edit-static{font-size:13px;line-height:1.5;color:#3b3a36}.plan-edit-row select,.plan-edit-row textarea,.plan-edit-row input{width:100%;border:1px solid var(--line);border-radius:12px;background:#fff;color:var(--text);font:inherit;font-size:13px;padding:8px 10px}.plan-edit-row textarea{resize:vertical;line-height:1.5}.plan-attending-check{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700}.plan-attending-check input{width:auto}.plan-member-row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) auto;gap:8px;align-items:center}.plan-member-row.plan-member-row-wide{grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) auto}.plan-member-row select,.plan-member-row input{width:100%;border:1px solid var(--line);border-radius:12px;background:#fff;color:var(--text);font:inherit;font-size:13px;padding:8px 10px}.plan-slots-field{display:grid;gap:3px}.plan-slots-field span{color:var(--muted);font-size:11px;line-height:1.35}.plan-member-remove,.plan-member-add{border:1px solid var(--line);background:#fff;color:var(--text);border-radius:999px;font-size:13px;font-weight:700;padding:8px 10px;cursor:pointer}.plan-member-add{justify-self:start}.plan-detail-toggle{justify-self:start;margin-top:2px}@media (max-width:520px){.plan-tools{padding:14px;border-radius:22px}.plan-file-button,.plan-download,.plan-save-page,.plan-confirm-toggle{width:100%}.plan-edit-row{grid-template-columns:48px minmax(0,1fr)}.plan-confirmed-list-item{grid-template-columns:1fr}.calendar-view[data-mode='plan'] .day-cell.plan-participating::before{font-size:12px;padding:6px 10px}.plan-member-row{grid-template-columns:1fr}.plan-member-remove{justify-self:start}}
"""
    live_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button active' href='?mode=live' aria-current='page'>LIVE</a>
        <a class='mode-button' href='?mode=event'>EVENT</a>
        <a class='mode-button' href='?mode=all'>ALL</a>
        <a class='mode-button' href='?mode=plan'>PLAN</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    event_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button' href='?mode=live'>LIVE</a>
        <a class='mode-button active' href='?mode=event' aria-current='page'>EVENT</a>
        <a class='mode-button' href='?mode=all'>ALL</a>
        <a class='mode-button' href='?mode=plan'>PLAN</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    all_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button' href='?mode=live'>LIVE</a>
        <a class='mode-button' href='?mode=event'>EVENT</a>
        <a class='mode-button active' href='?mode=all' aria-current='page'>ALL</a>
        <a class='mode-button' href='?mode=plan'>PLAN</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    plan_mode_switch_html = """<nav class='mode-switch' aria-label='表示切替'>
      <div class='mode-switch-inner'>
        <a class='mode-button' href='?mode=live'>LIVE</a>
        <a class='mode-button' href='?mode=event'>EVENT</a>
        <a class='mode-button' href='?mode=all'>ALL</a>
        <a class='mode-button active' href='?mode=plan' aria-current='page'>PLAN</a>
        <a class='mode-button' href='?mode=next14'>直近2週間</a>
      </div>
    </nav>"""
    live_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + live_mode_switch_html, live_body, count=1, flags=re.S)
    event_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + event_mode_switch_html, event_body, count=1, flags=re.S)
    if all_body is not None:
        all_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + all_mode_switch_html, all_body, count=1, flags=re.S)
    if plan_body is not None:
        plan_body = re.sub(r"(<h1>.*?</h1>)", r"\1\n    " + plan_mode_switch_html, plan_body, count=1, flags=re.S)
        plan_body = re.sub(r"(<nav class='month-nav'>)", lambda match: render_plan_tools_html() + "\n  " + match.group(1), plan_body, count=1)
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
    plan_section = ""
    if plan_body is not None and plan_script is not None:
        plan_section = f"""
<section class='calendar-view' data-mode='plan' hidden>
  <div class='page'>
{plan_body}
  </div>
  <script data-root-mode='plan'>
{plan_script}
  </script>
</section>"""
    next14_section = (next14_html or "").replace("data-mode='next14' hidden", "data-mode='next14'", 1)
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
<section class='calendar-view' data-mode='live' hidden>
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
{plan_section}
{next14_section}
<script>
const requestedMode = new URL(document.URL).searchParams.get('mode');
const selectedMode = ['live', 'event', 'all', 'plan', 'next14'].includes(requestedMode) ? requestedMode : 'next14';
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
    ics_paths = write_ics_outputs(combined_months)

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
        plan_months = build_plan_months(combined_months, all_display_months)
        plan_html = render_mode_html(
            plan_months,
            {},
            {},
            display_months=all_display_months,
            holidays_by_month=holidays_by_month_all,
            page_title="櫻坂46 カレンダー",
            hero_copy="参加できる可能性のある予定をまとめています。",
            list_label="",
            live_meaning="開催",
            ticket_meaning="",
            deadline_meaning="",
            primary_meta_label="候補予定",
            ticket_meta_label="応募・締切情報",
        )
        next14_html = render_next14_html(months, event_months, all_display_months)
        OUTPUT_HTML.write_text(render_combined_html(live_html, event_html, all_html, next14_html, plan_html=plan_html))
    else:
        OUTPUT_HTML.write_text(live_html)
    if args.output_workflow:
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
    if args.output_workflow:
        print(f"workflow: {WORKFLOW_MD.relative_to(BASE_DIR)}")
    print("ics:")
    for path in ics_paths:
        print(f"  - {path.relative_to(BASE_DIR)}")
    if preview is not None:
        print(f"preview: {preview.relative_to(BASE_DIR)}")
    print("holiday_templates:")
    for path in holiday_template_paths:
        print(f"  - {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
