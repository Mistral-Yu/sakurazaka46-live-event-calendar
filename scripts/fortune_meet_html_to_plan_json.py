#!/usr/bin/env python3
"""Convert a saved forTUNE meet & greet HTML page into PLAN JSON.

Usage:
  python3 scripts/fortune_meet_html_to_plan_json.py 14thシングルミーグリ.html > plan.json
  python3 scripts/fortune_meet_html_to_plan_json.py page.html --date 2026-05-24 --event "14枚目シングル ミーグリ" > plan.json

The parser groups rows under each detected event date, e.g.:
  2026年5月24日
  第4部 16:00～17:00  村井 優  3枚  3枚
and emits slots such as "4:3". Duplicate same-member/same-part rows are summed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import unicodedata
from pathlib import Path

DATE_TOKEN_RE = re.compile(
    r"(?P<full>(?P<y>20\d{2})\s*[年/.\-]\s*(?P<m>\d{1,2})\s*[月/.\-]\s*(?P<d>\d{1,2})\s*日?)"
    r"|(?P<short>(?P<sm>\d{1,2})/(?P<sd>\d{1,2})\([^)]*\))"
)
ROW_RE = re.compile(
    r"第\s*(?P<part>\d+)\s*部[\s\S]{0,80}?"
    r"(?P<name>[一-龠々〆ヵヶぁ-んァ-ヶー]+[\s　]+[一-龠々〆ヵヶぁ-んァ-ヶー]+)"
    r"[\s　]+(?P<count>\d+)\s*枚",
)
TOKEN_RE = re.compile(DATE_TOKEN_RE.pattern + r"|" + ROW_RE.pattern)


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:tr|p|div|li|dd|dt|td|th|span|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def normalize_spaces(text: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", text).strip()


def date_from_match(match: re.Match[str], fallback_year: int | None = None) -> str | None:
    if match.group("y"):
        year = int(match.group("y"))
        month = int(match.group("m"))
        day = int(match.group("d"))
    elif match.group("sm"):
        year = fallback_year or dt.date.today().year
        month = int(match.group("sm"))
        day = int(match.group("sd"))
    else:
        return None
    return dt.date(year, month, day).isoformat()


def add_member(group: dict[str, dict[int, int]], name: str, part: int, count: int) -> None:
    group.setdefault(name, {})
    group[name][part] = group[name].get(part, 0) + count


def members_from_group(group: dict[str, dict[int, int]]) -> list[dict[str, str]]:
    return [
        {"name": name, "slots": ",".join(f"{part}:{count}" for part, count in sorted(parts.items()))}
        for name, parts in group.items()
    ]


def parse_items(text: str, forced_date: str | None, fallback_year: int | None, event_name: str) -> list[dict]:
    groups: dict[str, dict[str, dict[int, int]]] = {}
    current_date = forced_date
    for match in TOKEN_RE.finditer(text):
        detected_date = date_from_match(match, fallback_year)
        if detected_date:
            if not forced_date:
                current_date = detected_date
            continue
        if not match.group("part"):
            continue
        if not current_date:
            raise SystemExit("日付をHTMLから検出できませんでした。--date YYYY-MM-DD を指定してください。")
        name = normalize_spaces(match.group("name")).replace(" ", "")
        add_member(groups.setdefault(current_date, {}), name, int(match.group("part")), int(match.group("count")))
    if not groups:
        raise SystemExit("第N部 / メンバー名 / N枚 の行を検出できませんでした。")
    return [
        {"date": date, "event": event_name, "attending": True, "members": members_from_group(group)}
        for date, group in sorted(groups.items())
    ]


def convert(path: Path, date: str | None, event: str | None, year: int | None) -> dict:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = strip_html(raw)
    event_name = unicodedata.normalize("NFC", event or path.stem)
    if "ミーグリ" not in event_name:
        event_name = f"{event_name} ミーグリ"
    return {"version": 1, "items": parse_items(text, date, year, event_name)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert saved forTUNE meet HTML to PLAN JSON")
    parser.add_argument("html", type=Path)
    parser.add_argument("--date", help="YYYY-MM-DD. Forces all rows into one event date.")
    parser.add_argument("--event", help="Event name to store in PLAN JSON. Defaults to input filename stem.")
    parser.add_argument("--year", type=int, help="Fallback year for M/D style dates in the HTML.")
    args = parser.parse_args()
    print(json.dumps(convert(args.html, args.date, args.event, args.year), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
