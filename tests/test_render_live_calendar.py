from pathlib import Path
import importlib.util
import json
import tempfile


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_live_calendar.py"
spec = importlib.util.spec_from_file_location("render_live_calendar", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_parse_holiday_csv_bytes_handles_cp932_and_filters_year():
    csv_text = "国民の祝日・休日月日,国民の祝日・休日名称\n2026/1/1,元日\n2026/11/3,文化の日\n2027/1/1,元日\n"
    result = module.parse_holiday_csv_bytes(csv_text.encode("cp932"), year=2026)

    assert result == {
        1: {1: "元日"},
        2: {},
        3: {},
        4: {},
        5: {},
        6: {},
        7: {},
        8: {},
        9: {},
        10: {},
        11: {3: "文化の日"},
        12: {},
    }


def test_get_holiday_template_path_places_file_under_scripts_templates():
    path = module.get_holiday_template_path(2027)

    assert path == module.SCRIPT_DIR / "templates" / "holidays_2027_template.json"


def test_infer_source_year_reads_year_from_summary_rows():
    text = """## sample\n\n| 2027-01-10 | 土 | 幕張イベントホール |\n"""

    assert module.infer_source_year(text) == 2027


def test_load_or_fetch_holidays_uses_template_after_first_fetch():
    csv_text = "国民の祝日・休日月日,国民の祝日・休日名称\n2026/1/1,元日\n2026/2/11,建国記念の日\n"
    calls = {"count": 0}

    def fetcher():
        calls["count"] += 1
        return csv_text.encode("cp932")

    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "holidays_2026_template.json"

        first = module.load_or_fetch_holidays(year=2026, template_path=template_path, fetcher=fetcher)
        assert calls["count"] == 1
        assert template_path.exists()
        assert first[1][1] == "元日"
        assert first[2][11] == "建国記念の日"

        def should_not_run():
            raise AssertionError("fetcher should not run when template already exists")

        second = module.load_or_fetch_holidays(year=2026, template_path=template_path, fetcher=should_not_run)
        assert second == first


def test_load_or_fetch_holidays_falls_back_to_existing_template_when_csv_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "holidays_2027_template.json"
        template_path.write_text(json.dumps({
            "1": {"1": "元日"},
            "2": {}, "3": {}, "4": {}, "5": {}, "6": {},
            "7": {}, "8": {}, "9": {}, "10": {}, "11": {}, "12": {}
        }, ensure_ascii=False, indent=2))

        def failing_fetcher():
            raise OSError("network down")

        result = module.load_or_fetch_holidays(year=2027, template_path=template_path, fetcher=failing_fetcher)
        assert result[1][1] == "元日"


def test_load_or_fetch_holidays_bootstraps_template_then_raises_when_csv_fails_without_template():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "holidays_2028_template.json"

        def failing_fetcher():
            raise OSError("network down")

        try:
            module.load_or_fetch_holidays(year=2028, template_path=template_path, fetcher=failing_fetcher)
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("RuntimeError was expected")

        assert "holidays_2028_template.json" in message
        assert template_path.exists()
        seeded = json.loads(template_path.read_text())
        assert seeded["1"] == {}
        assert seeded["12"] == {}


def test_parse_args_supports_refresh_holidays_flag():
    args = module.parse_args(["--refresh-holidays"])

    assert args.refresh_holidays is True


def test_load_or_fetch_holidays_refreshes_existing_template_when_requested():
    old_template = {
        "1": {"1": "旧祝日"},
        "2": {}, "3": {}, "4": {}, "5": {}, "6": {},
        "7": {}, "8": {}, "9": {}, "10": {}, "11": {}, "12": {}
    }
    csv_text = "国民の祝日・休日月日,国民の祝日・休日名称\n2026/1/1,元日\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "holidays_2026_template.json"
        template_path.write_text(json.dumps(old_template, ensure_ascii=False, indent=2))

        result = module.load_or_fetch_holidays(
            year=2026,
            template_path=template_path,
            fetcher=lambda: csv_text.encode("cp932"),
            refresh=True,
        )

        assert result[1][1] == "元日"
        saved = json.loads(template_path.read_text())
        assert saved["1"]["1"] == "元日"


def test_parse_summary_does_not_create_holiday_only_detail_entries():
    module.HOLIDAYS = {
        1: {1: "元日"},
        2: {}, 3: {}, 4: {}, 5: {}, 6: {},
        7: {}, 8: {}, 9: {}, 10: {}, 11: {}, 12: {},
    }
    summary = """## テスト公演\n\n| 2026-01-02 | 金 | 幕張イベントホール |\n\n### 公式ソース\n\nhttps://sakurazaka46.com/test\n"""

    months, _, _ = module.parse_summary(summary, 2026)

    assert months[1]["days"][1] == [{"text": "祝", "tone": "祝", "kind": "holiday"}]
    assert months[1]["detail_map"][1] == []
    assert len(months[1]["detail_map"][2]) == 1


def test_render_html_uses_compact_non_wrapping_chips_without_holiday_highlight_class():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[1]["days"][1].append({"text": "LeminoS開始", "tone": "LeminoS", "kind": "lottery"})
    months[1]["detail_map"][1].append({
        "label": "抽選開始: Leminoスペシャルシート先行",
        "sub": "対象: テスト",
        "meta": "1/1(木)〜1/2(金)",
        "sources": [],
    })
    module.HOLIDAYS = {1: {1: "元日"}, 2: {}, 3: {}, 4: {}, 5: {}, 6: {}, 7: {}, 8: {}, 9: {}, 10: {}, 11: {}, 12: {}}

    html = module.render_html(months, {}, {}, 2026)

    assert "holiday-day" not in html
    assert "white-space:nowrap" in html
    assert "text-overflow:ellipsis" in html
    assert "data-mobile-text='Le…'" in html


def test_render_html_gives_clickable_cells_a_lightweight_polished_button_style():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[1]["days"][4].append({"text": "幕張", "tone": "幕張", "kind": "live"})
    months[1]["detail_map"][4].append({"label": "LIVE: テスト", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert ".day-cell.clickable::after" in html
    assert "linear-gradient(180deg,#fff,#f8f8f5)" in html
    assert "transform:translateY(-1px)" in html
    assert "rgba(231,229,222,.82)" in html
    assert "border:1px solid rgba(231,229,222,.82)" in html


def test_render_html_uses_native_hash_day_disclosure_instead_of_touch_button_js():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[6]["days"][2].append({"text": "四期生ライブ", "tone": "四期生ライブ", "kind": "live"})
    months[6]["detail_map"][2].append({"label": "LIVE: 四期生 LIVE", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert "<a class='day-cell clickable'" in html
    assert "href='#m06-d02'" in html
    assert "id='m06-d02'" in html
    assert "data-detail-key='m06-d02'" in html
    assert "<button type='button' class='day-cell clickable'" not in html
    assert "touchend" not in html
    assert "pointerdown" not in html
    assert "forceVisualRefresh" not in html


def test_render_html_disables_clickable_cell_animations_on_touch_devices():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[1]["days"][4].append({"text": "幕張", "tone": "幕張", "kind": "live"})
    months[1]["detail_map"][4].append({"label": "LIVE: テスト", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert "@media (hover:none), (pointer:coarse)" in html
    assert "transition:none" in html
    assert "transform:none" in html
    assert "-webkit-tap-highlight-color:transparent" in html


def test_render_html_uses_focusable_link_states_instead_of_custom_touch_handlers():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[5]["days"][12].append({"text": "バックスライブ", "tone": "バックスライブ", "kind": "live"})
    months[5]["detail_map"][12].append({"label": "LIVE: テスト", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert ".day-cell.clickable:active" in html
    assert ".day-cell.clickable:focus-visible" in html
    assert "touchend" not in html
    assert "lastTouchToggleAt" not in html
    assert "event.preventDefault()" not in html


def test_render_html_uses_target_panels_with_close_link_for_selected_day_details():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[7]["days"][23].append({"text": "静岡公演", "tone": "静岡公演", "kind": "live"})
    months[7]["detail_map"][23].append({"label": "LIVE: テスト", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert "class='detail-panel'" in html
    assert ".detail-panel:target{display:block}" in html
    assert ".detail-panel:target ~ .detail-default{display:none}" in html
    assert "class='detail-reset' href='#m07'" in html
    assert "is-pressed" not in html
    assert "pointerdown" not in html


def test_render_html_uses_roomier_desktop_width_and_detail_readability_styles():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[6]["days"][2].append({"text": "四期生ライブ", "tone": "四期生ライブ", "kind": "live"})
    months[6]["detail_map"][2].append({
        "label": "LIVE: 四期生 LIVE",
        "sub": "会場: LaLa arena TOKYO-BAY",
        "meta": "2026/06/02 火",
        "sources": ["https://sakurazaka46.com/test"],
    })

    html = module.render_html(months, {}, {}, 2026)

    assert "@media (min-width:980px)" in html
    assert ".page{max-width:1400px;padding-inline:24px}" in html
    assert ".month-summary{padding:24px 24px 20px}" in html
    assert ".month-body{padding:0 24px 24px}" in html
    assert ".day-detail{padding:18px 20px 20px}" in html
    assert ".detail-list{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px}" in html
    assert ".detail-panel:target ~ .detail-sections{grid-template-columns:minmax(0,1.2fr) minmax(320px,.9fr)}" in html
    assert "@media (max-width:720px)" in html


def test_render_html_removes_redundant_month_subtitle_for_scheduled_months():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[1]["days"][4].append({"text": "幕張", "tone": "幕張", "kind": "live"})
    months[1]["detail_map"][4].append({"label": "LIVE: テスト", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert "ライブ・抽選・祝日を同じ面で確認" not in html


def test_live_and_lottery_labels_use_backs_and_shiki_names():
    module.HOLIDAYS = {m: {} for m in range(1, 13)}
    summary = """## 四期生 LIVE

| 2026-06-02〜03 | 火水 | LaLa arena TOKYO-BAY |

### 抽選の日程

| FC会員先行 | **5/1(木)〜5/3(土)** | 全席指定 |

### 公式ソース

https://sakurazaka46.com/test

## 14枚目シングル BACKS LIVE!!

| 2026-05-12〜13 | 火水 | 幕張イベントホール |

### 公式ソース

https://sakurazaka46.com/test-backs
"""

    months, legend_live, _ = module.parse_summary(summary, 2026)

    assert any(item["text"] == "四期生ライブ" for item in months[6]["days"][2])
    assert any(item["text"] == "バックスライブ" for item in months[5]["days"][12])
    assert any(item["text"] == "四期生ライブ抽選開始" for item in months[5]["days"][1])
    assert "四期生ライブ" in legend_live
    assert "バックスライブ" in legend_live


def test_render_html_uses_live_list_and_color_split_legend():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[5]["events"].append({"tag": "バックスライブ", "range": "05/12〜13", "wdays": "火水", "title": "14枚目シングル BACKS LIVE!!", "venue": "幕張イベントホール"})
    months[6]["events"].append({"tag": "四期生ライブ", "range": "06/02〜03", "wdays": "火水", "title": "四期生 LIVE", "venue": "LaLa arena TOKYO-BAY"})

    html = module.render_html(months, {"バックスライブ": "14枚目シングル BACKS LIVE!! / 幕張イベントホール", "四期生ライブ": "四期生 LIVE / LaLa arena TOKYO-BAY"}, {}, 2026)

    assert "単体1枚のHTML版" not in html
    assert "タグ凡例" not in html
    assert "LIVEタグ:" not in html
    assert "ライブ一覧:" in html
    assert "バックスライブ / 四期生ライブ" in html
    assert "色分け:" in html
    assert "legend-chip tone-live" in html
    assert "legend-chip tone-ticket" in html
    assert "ライブ開催日" in html
    assert "チケット抽選" in html
    assert "色の意味:" not in html
    assert "<span>色分け: </span><span class='legend-chip tone-live' aria-hidden='true'></span><span>ライブ開催日</span><span class='legend-chip tone-ticket' aria-hidden='true'></span><span>チケット抽選</span>" in html


def test_render_html_uses_mobile_ellipsis_short_labels_only_under_narrow_width():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[5]["days"][12].append({"text": "バックスライブ", "tone": "バックスライブ", "kind": "live"})
    months[5]["days"][16].append({"text": "四期生ライブ抽選開始", "tone": "四期生ライブ", "kind": "lottery"})
    months[11]["days"][14].append({"text": "アニラ", "tone": "アニラ", "kind": "live"})

    html = module.render_html(months, {}, {}, 2026)

    assert "data-mobile-text='バッ…'" in html
    assert "data-mobile-text='四期…'" in html
    assert "data-mobile-text='アニラ'" in html
    assert "@media (max-width:520px)" in html
    assert ".chip::before{content:attr(data-mobile-text)}" in html
    assert ".chip-text{display:none}" in html
    assert ".chip-text{display:block" in html


def test_render_html_uses_one_hash_target_panel_per_month_detail_area():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[6]["days"][2].append({"text": "四期生ライブ", "tone": "四期生ライブ", "kind": "live"})
    months[6]["detail_map"][2].append({"label": "LIVE: 四期生 LIVE", "sub": "", "meta": "", "sources": []})
    months[6]["days"][3].append({"text": "ツアー抽選開始", "tone": "FC", "kind": "lottery"})
    months[6]["detail_map"][3].append({"label": "抽選: ツアー FC会員先行", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert "id='m06-d02'" in html
    assert "id='m06-d03'" in html
    assert "href='#m06-d02'" in html
    assert "href='#m06-d03'" in html
    assert ".detail-panel:target ~ .detail-sections{display:grid}" in html
    assert "class='detail-default'" in html
    assert "button.classList.contains('active')" not in html
    assert "closeDetailPanel" not in html


def test_parse_summary_uses_general_sale_not_lottery_start_for_ippan():
    module.HOLIDAYS = {m: {} for m in range(1, 13)}
    summary = """## テスト公演

| 2026-05-10 | 日 | 幕張イベントホール |

### 抽選の日程

| 一般発売 | **5/16(土)〜** | 先着販売 |

### 公式ソース

https://sakurazaka46.com/test
"""

    months, _, _ = module.parse_summary(summary, 2026)

    assert any(item["text"] == "テスト公演一般発売" for item in months[5]["days"][16])
    assert not any(item["text"] == "テスト公演抽選開始" for item in months[5]["days"][16])
    assert any(item["label"] == "一般発売: テスト公演" for item in months[5]["detail_map"][16])


def test_parse_summary_marks_days_between_lottery_start_and_end():
    module.HOLIDAYS = {m: {} for m in range(1, 13)}
    summary = """## テスト公演

| 2026-05-10 | 日 | 幕張イベントホール |

### 抽選の日程

| FC会員先行 | **5/2(土)〜5/5(火)** | テスト対象 |

### 公式ソース

https://sakurazaka46.com/test
"""

    months, _, _ = module.parse_summary(summary, 2026)

    assert any(item["text"] == "テスト公演抽選開始" for item in months[5]["days"][2])
    assert any(item["kind"] == "lottery_span" and item["text"] == "テスト公演抽選継続" for item in months[5]["days"][3])
    assert any(item["kind"] == "lottery_span" and item["text"] == "テスト公演抽選継続" for item in months[5]["days"][4])
    assert any(item["text"] == "テスト公演抽選締切" for item in months[5]["days"][5])


def test_render_html_contains_lottery_span_marker_and_two_tone_style():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[5]["days"][2].append({"text": "バックスライブ", "tone": "バックスライブ", "kind": "live"})
    months[5]["days"][2].append({"text": "テスト公演抽選開始", "tone": "FC", "kind": "lottery"})
    months[5]["days"][3].append({"text": "テスト公演抽選継続", "tone": "FC", "kind": "lottery_span"})
    months[5]["days"][4].append({"text": "テスト公演抽選継続", "tone": "FC", "kind": "lottery_span"})
    months[5]["days"][5].append({"text": "テスト公演抽選締切", "tone": "FC", "kind": "lottery"})
    months[5]["detail_map"][2].append({"label": "LIVE: テスト公演", "sub": "", "meta": "", "sources": []})
    months[5]["detail_map"][3].append({"label": "抽選: テスト公演 FC会員先行", "sub": "", "meta": "", "sources": []})
    months[5]["detail_map"][5].append({"label": "抽選: テスト公演 FC会員先行", "sub": "", "meta": "", "sources": []})

    html = module.render_html(months, {}, {}, 2026)

    assert "lottery-span" in html
    assert "data-span-tone='ticket'" in html
    assert "tone-live" in html
    assert "tone-ticket" in html
    assert "--live:#14866d" in html
    assert "--holiday:#e5484d" in html
    assert "tone-rose" not in html
    assert "tone-indigo" not in html
    assert "data-detail-key='m05-d03'" in html


def test_parse_summary_adds_clickable_detail_for_lottery_span_days():
    module.HOLIDAYS = {m: {} for m in range(1, 13)}
    summary = """## テスト公演

| 2026-05-10 | 日 | 幕張イベントホール |

### 抽選の日程

| FC会員先行 | **5/2(土)〜5/5(火)** | テスト対象 |

### 公式ソース

https://sakurazaka46.com/test
"""

    months, _, _ = module.parse_summary(summary, 2026)

    assert any(item["label"] == "抽選: テスト公演 FC会員先行" for item in months[5]["detail_map"][2])
    assert any(item["label"] == "抽選: テスト公演 FC会員先行" for item in months[5]["detail_map"][3])
    assert any(item["label"] == "抽選: テスト公演 FC会員先行" for item in months[5]["detail_map"][4])
    assert any(item["label"] == "抽選: テスト公演 FC会員先行" for item in months[5]["detail_map"][5])


def test_merge_day_items_combines_same_phase_only():
    items = [
        {"text": "ツアー抽選開始", "tone": "FC", "kind": "lottery"},
        {"text": "ツアー抽選開始", "tone": "LeminoS", "kind": "lottery"},
        {"text": "アニラ抽選締切", "tone": "三井", "kind": "lottery"},
        {"text": "祝", "tone": "祝", "kind": "holiday"},
    ]

    merged = module.merge_day_items(items)

    assert len([item for item in merged if item["text"] == "ツアー抽選開始"]) == 1
    assert any(item["text"] == "アニラ抽選締切" for item in merged)
    assert not any(item["text"] == "ツアー抽選/アニラ抽選開始" for item in merged)


def test_render_html_integrates_click_revealed_month_specific_live_and_ticket_sections():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    months[6]["events"].append({"tag": "四期", "range": "06/02", "wdays": "火", "title": "四期生 LIVE", "venue": "LaLa arena TOKYO-BAY"})
    months[6]["lotteries"].append({"period": "5/1(木)〜5/3(土)", "title": "四期生 LIVE", "type": "FC会員先行", "target": "", "sources": []})
    months[6]["days"][2].append({"text": "四期", "tone": "四期", "kind": "live"})
    months[6]["detail_map"][2].append({"label": "LIVE: 四期生 LIVE", "sub": "会場: LaLa arena TOKYO-BAY", "meta": "06/02 火", "sources": []})

    html = module.render_html(months, {"四期": "四期生 LIVE / LaLa arena TOKYO-BAY"}, {"FC": "FC会員先行"}, 2026)

    assert "class='detail-sections'" in html
    assert ".detail-panel:target ~ .detail-sections{display:grid}" in html
    assert "<h3>6月のライブ情報</h3>" in html
    assert "<h3>6月のチケット情報</h3>" in html
    assert "日付をタップすると詳細を表示" in html
    assert "<div class='meta'>" not in html


def test_render_html_mentions_anniversary_starting_point_in_hero_copy():
    html = module.render_html({m: module.empty_month_struct() for m in range(1, 13)}, {}, {}, 2026)

    assert "5th YEAR ANNIVERSARY LIVE以降のライブ情報を、見やすく整理してまとめています。" in html
    assert "五周年のアニラからのライブをまとめる（文章校正）" not in html


def test_render_html_does_not_include_holiday_meta_explanations():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    module.HOLIDAYS = {1: {1: "元日"}, 2: {}, 3: {}, 4: {}, 5: {}, 6: {}, 7: {}, 8: {}, 9: {}, 10: {}, 11: {}, 12: {}}

    html = module.render_html(months, {}, {}, 2026)

    assert "元日" not in html
    assert "抽選メモ・祝日" not in html


def test_workflow_path_is_under_scripts_directory():
    assert module.WORKFLOW_MD == module.SCRIPT_DIR / "sakurazaka_schedule_workflow.md"


def test_output_html_defaults_to_index_html_for_github_pages():
    assert module.OUTPUT_HTML == module.BASE_DIR / "index.html"


def test_preview_output_path_is_under_summary_directory():
    assert module.LONG_PREVIEW == module.SUMMARY_DIR / "sakurazaka46_live_calendar_preview.jpg"


def test_plan_dir_is_hidden_dot_plan_directory():
    assert module.PLAN_DIR == module.BASE_DIR / ".plan"


def test_parse_summary_marks_lottery_span_across_month_boundary():
    module.HOLIDAYS = {m: {} for m in range(1, 13)}
    summary = """## 全国アリーナツアー2026

| 2026-06-10 | 水 | 幕張イベントホール |

### 抽選の日程

| イオンカード先行 | **5/30(土)〜6/7(日)** | テスト対象 |

### 公式ソース

https://sakurazaka46.com/test
"""

    months, _, _ = module.parse_summary(summary, 2026)

    assert any(item["text"] == "ツアー抽選開始" for item in months[5]["days"][30])
    assert any(item["kind"] == "lottery_span" and item["text"] == "ツアー抽選継続" for item in months[5]["days"][31])
    assert any(item["kind"] == "lottery_span" and item["text"] == "ツアー抽選継続" for item in months[6]["days"][1])
    assert any(item["kind"] == "lottery_span" and item["text"] == "ツアー抽選継続" for item in months[6]["days"][6])
    assert any(item["text"] == "ツアー抽選締切" for item in months[6]["days"][7])


def test_render_workflow_mentions_summary_to_python_to_html_pipeline():
    text = module.render_workflow(2026, module.SCRIPT_DIR / "templates" / "holidays_2026_template.json")

    assert "summary/sakurazaka46_live_summary.md" in text
    assert "scripts/render_live_calendar.py" in text
    assert "index.html" in text
    assert "生成フロー" in text or "source of truth" in text
    assert "sakurazaka46_live_calendar_preview.jpg" in text
    assert "summary/" in text
    assert "Summary更新依頼" in text


def test_parse_args_calendar_markdown_output_is_default_off():
    args = module.parse_args([])

    assert args.output_calendar_md is False
    assert args.output_preview is False


def test_parse_args_can_enable_calendar_markdown_output():
    args = module.parse_args(["--output-calendar-md"])

    assert args.output_calendar_md is True


def test_parse_args_can_enable_preview_output():
    args = module.parse_args(["--output-preview"])

    assert args.output_preview is True


def test_render_preview_image_uses_3x4_grid_layout():
    months = {m: module.empty_month_struct() for m in range(1, 13)}
    fonts = module.load_fonts()

    with tempfile.TemporaryDirectory() as tmpdir:
        original = module.LONG_PREVIEW
        try:
            module.LONG_PREVIEW = Path(tmpdir) / "preview.jpg"
            output = module.render_preview_image(months, fonts, 2026)
            from PIL import Image
            img = Image.open(output)
            assert img.width == 1500
            assert img.height == 2060
        finally:
            module.LONG_PREVIEW = original


def test_collect_display_months_extends_until_last_month_in_summary():
    summary = """## 年またぎテスト

| 2026-12-31 | 木 | 幕張イベントホール |
| 2027-02-14 | 日 | LaLa arena TOKYO-BAY |

### 公式ソース

https://sakurazaka46.com/test
"""

    months = module.collect_display_months(summary)

    assert months == [
        module.month_start(2026, 12),
        module.month_start(2027, 1),
        module.month_start(2027, 2),
    ]


def test_parse_summary_uses_location_plus_performance_for_national_tour_live_tags():
    module.HOLIDAYS = {m: {} for m in range(1, 13)}
    summary = """## 全国アリーナツアー2026

| 2026-07-23〜24 | 木金 | 静岡・エコパアリーナ |

### 公式ソース

https://sakurazaka46.com/test
"""

    months, legend_live, _ = module.parse_summary(summary, 2026)

    assert any(item["text"] == "静岡公演" for item in months[7]["days"][23])
    assert legend_live["静岡公演"] == "全国アリーナツアー2026 / 静岡・エコパアリーナ"


def test_collect_display_months_ignores_undetermined_lottery_bullets_for_range():
    summary = """## 年またぎテスト

| 2026-12-31 | 木 | 幕張イベントホール |

### 抽選の日程

- チケット先行は後日発表

### 公式ソース

https://sakurazaka46.com/test
"""

    months = module.collect_display_months(summary)

    assert months == [module.month_start(2026, 12)]


def test_parse_summary_timeline_includes_next_year_schedule_in_same_html_source():
    holiday_lookup = {
        module.month_start(2026, 12): {},
        module.month_start(2027, 1): {},
    }
    summary = """## 年またぎテスト

| 2026-12-31 | 木 | 幕張イベントホール |
| 2027-01-01 | 金 | LaLa arena TOKYO-BAY |

### 公式ソース

https://sakurazaka46.com/test
"""

    display_months = module.collect_display_months(summary)
    months, _, _ = module.parse_summary_timeline(summary, display_months, holiday_lookup)

    assert any(item["text"] == "幕張" for item in months[module.month_start(2026, 12)]["days"][31])
    assert any(item["text"] == "千葉" for item in months[module.month_start(2027, 1)]["days"][1])


def test_render_html_timeline_shows_months_through_last_year_month():
    month_2026_12 = module.month_start(2026, 12)
    month_2027_01 = module.month_start(2027, 1)
    month_2027_02 = module.month_start(2027, 2)
    months = {
        month_2026_12: module.empty_month_struct(),
        month_2027_01: module.empty_month_struct(),
        month_2027_02: module.empty_month_struct(),
    }
    months[month_2026_12]["days"][31].append({"text": "幕張", "tone": "幕張", "kind": "live"})
    months[month_2026_12]["detail_map"][31].append({"label": "LIVE: 幕張", "sub": "", "meta": "", "sources": []})
    months[month_2027_02]["days"][14].append({"text": "四期", "tone": "四期", "kind": "live"})
    months[month_2027_02]["detail_map"][14].append({"label": "LIVE: 四期", "sub": "", "meta": "", "sources": []})

    html = module.render_html(
        months,
        {"幕張": "幕張イベント", "四期": "四期生 LIVE"},
        {},
        display_months=[month_2026_12, month_2027_01, month_2027_02],
        holidays_by_month={month_2026_12: {}, month_2027_01: {}, month_2027_02: {}},
    )

    assert "2026年12月" in html
    assert "2027年1月" in html
    assert "2027年2月" in html
    assert "id='m202702'" in html
