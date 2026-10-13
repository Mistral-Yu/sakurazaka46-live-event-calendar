"""Regression coverage for year-scoped, non-destructive holiday caches."""
from pathlib import Path
import datetime as dt
import importlib.util
import json

import pytest

spec = importlib.util.spec_from_file_location(
    "calendar_holiday_cache", Path(__file__).resolve().parents[1] / "scripts" / "render_live_calendar.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CSV = "国民の祝日・休日月日,国民の祝日・休日名称\n2026/1/1,元日\n2026/1/12,成人の日\n2027/1/1,元日\n2027/1/11,成人の日\n".encode("cp932")


def test_years_have_separate_files_and_correct_days(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(module, "fetch_holiday_csv", lambda: CSV)
    months = [dt.date(2026, 1, 1), dt.date(2027, 1, 1)]
    lookup = module.build_holiday_lookup(months, refresh=True)
    assert lookup[months[0]] == {1: "元日", 12: "成人の日"}
    assert lookup[months[1]] == {1: "元日", 11: "成人の日"}
    for year in [2026, 2027]:
        path = module.get_holiday_template_path(year)
        assert path == tmp_path / f"holidays_template_{year}.json"
        assert json.loads(path.read_text())["year"] == year

    def no_network():
        raise AssertionError("Normal regeneration must use the cached data")

    monkeypatch.setattr(module, "fetch_holiday_csv", no_network)
    assert module.build_holiday_lookup(months) == lookup


@pytest.mark.parametrize("mode", ["network", "empty", "wrong_year", "invalid"])
def test_failed_refresh_preserves_bytes_and_uses_valid_cache(tmp_path, mode):
    path = tmp_path / "holidays_template_2027.json"
    old = module.load_or_fetch_holidays(2027, path, lambda: CSV)
    before = path.read_bytes()

    def failing_fetcher():
        if mode == "network":
            raise OSError("network down")
        if mode == "empty":
            return b""
        if mode == "wrong_year":
            return "国民の祝日・休日月日,国民の祝日・休日名称\n2026/1/12,成人の日\n".encode("cp932")
        return b"\x81"

    with pytest.warns(RuntimeWarning, match="既存"):
        result = module.load_or_fetch_holidays(2027, path, failing_fetcher, refresh=True)
    assert result == old
    assert path.read_bytes() == before


@pytest.mark.parametrize("payload", [None, b"broken JSON", b'{"1":{"12":"old"}}', b'{"year":2026,"holidays":{"1":{"12":"old"}}}', b'{"year":2027,"holidays":{}}'])
def test_missing_or_invalid_cache_failure_never_writes(tmp_path, payload):
    path = tmp_path / "holidays_template_2027.json"
    if payload is not None:
        path.write_bytes(payload)

    def failing_fetcher():
        raise OSError("network down")

    with pytest.raises(RuntimeError, match="変更していません"):
        module.load_or_fetch_holidays(2027, path, failing_fetcher, refresh=True)
    if payload is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == payload


def test_wrong_year_cache_is_replaced_with_requested_year_only(tmp_path):
    path = tmp_path / "cache.json"
    module.load_or_fetch_holidays(2026, path, lambda: CSV)
    result = module.load_or_fetch_holidays(2027, path, lambda: CSV)
    assert result[1] == {1: "元日", 11: "成人の日"}
    assert json.loads(path.read_text())["year"] == 2027


def test_empty_official_year_without_cache_is_an_error(tmp_path):
    path = tmp_path / "holidays_template_2028.json"
    with pytest.raises(RuntimeError):
        module.load_or_fetch_holidays(2028, path, lambda: CSV)
    assert not path.exists()


def test_write_failure_preserves_existing_cache(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    module.load_or_fetch_holidays(2026, path, lambda: CSV)
    before = path.read_bytes()

    def fail_replace(self, target):
        raise OSError("cannot replace")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        module.load_or_fetch_holidays(2026, path, lambda: CSV, refresh=True)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
