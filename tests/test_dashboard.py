"""Tests for the Streamlit dashboard.

Unit tests check the SQL filter builder without a database. The remaining
tests run read-only queries against the PostgreSQL database in DATABASE_URL
and are skipped automatically when it is not reachable.
"""

import datetime as dt
from html import escape
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "dashboard"
sys.path.insert(0, str(DASHBOARD_DIR))
load_dotenv(ROOT / ".env", override=False)

import analysis_rules as rules  # noqa: E402
import data_access  # noqa: E402
from views import components  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests (no database)
# ---------------------------------------------------------------------------

def test_no_filters_keeps_only_scope():
    where_sql, params = data_access.build_filter_clause()
    assert where_sql == data_access.SCOPE_SQL
    assert params == {}


def test_filters_are_parameterized_and_combined_with_and():
    where_sql, params = data_access.build_filter_clause(
        search_text="  mars'; DROP TABLE x; --  ",
        topics=("mars", "earth"),
        centers=("JPL",),
        start_date=dt.date(2000, 1, 1),
        end_date=dt.date(2010, 12, 31),
    )
    # User text only ever appears in the parameters, never in the SQL text.
    assert "DROP" not in where_sql
    assert params["pattern"] == "%mars'; DROP TABLE x; --%"
    assert params["topics"] == ["mars", "earth"]
    assert params["centers"] == ["JPL"]
    assert where_sql.count(" AND ") >= 5
    # Several topics are OR-ed through ANY() inside a single EXISTS, which avoids duplicates.
    assert "EXISTS" in where_sql and "ANY(:topics)" in where_sql


def test_like_wildcards_are_escaped():
    assert data_access.escape_like("100%_done\\") == "100\\%\\_done\\\\"


def test_unknown_sort_is_rejected():
    with pytest.raises(ValueError):
        data_access.search_images.__wrapped__(sort="title; DROP TABLE nasa_records")


def test_missing_values_fall_back_gracefully():
    assert components.format_date(None) == "Date unavailable"
    assert components.format_date(dt.date(2019, 3, 5)) == "Mar 5, 2019"
    assert components.PREVIEW_UNAVAILABLE in components.thumbnail_html(None, "x")
    html = components.card_html("https://example.com/a.jpg", 'A <b>"quoted"</b> title', ["Credit: NASA"])
    assert "<b>" not in html and "&lt;b&gt;" in html


# ---------------------------------------------------------------------------
# Database tests (read-only)
# ---------------------------------------------------------------------------

def database_available():
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        data_access.check_connection()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not database_available(), reason="PostgreSQL is not reachable")


def scalar(sql, params=None):
    return data_access.run_query(sql, params).iloc[0, 0]


@needs_db
def test_connection_is_read_only():
    assert scalar("SELECT current_setting('default_transaction_read_only')") == "on"


@needs_db
def test_kpis_match_postgres():
    kpis = data_access.get_kpis()
    assert kpis["total_images"] == scalar("SELECT COUNT(*) FROM nasa_records")
    assert kpis["total_relationships"] == scalar("SELECT COUNT(*) FROM nasa_search_matches")
    assert kpis["total_topics"] == scalar("SELECT COUNT(DISTINCT search_keyword) FROM nasa_search_matches")


@needs_db
def test_featured_images_come_from_planet_gallery_covers():
    featured = data_access.get_featured_images(limit=6)
    assert 0 < len(featured) <= 6
    assert featured["image_url"].str.startswith("https://").all()
    assert featured["source_id"].is_unique


# ---------------------------------------------------------------------------
# Planet Gallery
# ---------------------------------------------------------------------------

@needs_db
def test_planet_summary_covers_every_topic_in_solar_system_order():
    summary = data_access.get_planet_topic_summary()
    kpis = data_access.get_kpis()
    assert len(summary) == kpis["total_topics"]
    assert summary["topic"].tolist() == data_access.PLANET_TOPIC_ORDER
    assert summary["topic"].tolist()[:4] == ["galaxy", "jupiter", "mars", "venus"]
    assert (summary["curated_images"] > 0).all()
    assert (summary["curated_images"] <= summary["archive_images"]).all()


@needs_db
def test_planet_gallery_is_curated_and_excludes_future_dates():
    profile = data_access.get_dataset_profile()
    for topic in ["mars", "earth", "uranus"]:
        page = data_access.get_planet_gallery(topic, page=1)
        assert not page.empty
        assert (page["topic"] == topic).all()
        assert (page["planet_score"] >= data_access.PLANET_MIN_SCORE).all()
        assert page["planet_score"].is_monotonic_decreasing
        assert (page["date"] <= profile["analysis_date"]).all()
        assert page["source_id"].is_unique
        # People and event photos are pushed out by the score.
        titles = " ".join(page["title"]).lower()
        assert "briefing" not in titles and "ceremony" not in titles


@needs_db
def test_planet_gallery_topic_and_exact_date_filter():
    busy_date = dt.date(2006, 12, 27)
    curated, archive = data_access.count_planet_gallery("mars", busy_date)

    # Count matches an independent query using the same score threshold.
    expected = scalar(f"""
        WITH c AS ({data_access.PLANET_CANDIDATES_SQL} AND m.search_keyword = 'mars')
        SELECT COUNT(*) FROM c WHERE planet_score >= :min_score AND date = :d
    """, {**data_access.PLANET_PATTERNS, "min_score": data_access.PLANET_MIN_SCORE, "d": busy_date})
    assert curated == expected > data_access.PAGE_SIZE
    assert archive >= curated

    # Every page holds only that date and topic, with no repeats, and the pages add up to the count.
    seen = []
    for page_number in range(1, -(-curated // data_access.PAGE_SIZE) + 1):
        page = data_access.get_planet_gallery("mars", page=page_number, metadata_date=busy_date)
        assert (page["date"] == busy_date).all()
        assert (page["topic"] == "mars").all()
        assert (page["planet_score"] >= data_access.PLANET_MIN_SCORE).all()
        seen += page["source_id"].tolist()
    assert len(seen) == len(set(seen)) == curated

    # No date filter gives the full topic gallery again.
    summary = data_access.get_planet_topic_summary().set_index("topic")
    assert data_access.count_planet_gallery("mars") == (
        int(summary.loc["mars", "curated_images"]), int(summary.loc["mars", "archive_images"]))


@needs_db
def test_planet_gallery_date_without_curated_matches_is_empty():
    # 2020-09-09 has one Mars archive record that falls below the score threshold.
    quiet_date = dt.date(2020, 9, 9)
    curated, archive = data_access.count_planet_gallery("mars", quiet_date)
    assert curated == 0 and archive == 1
    assert data_access.get_planet_gallery("mars", metadata_date=quiet_date).empty

    # Future dates are excluded from curated views, even when chosen explicitly.
    assert data_access.count_planet_gallery("mars", dt.date(2031, 7, 24)) == (0, 0)


@needs_db
def test_planet_years_come_from_curated_data():
    years = data_access.get_planet_years("mars")
    assert years["year"].is_monotonic_decreasing
    assert (years["curated_images"] > 0).all()
    summary = data_access.get_planet_topic_summary().set_index("topic")
    assert years["curated_images"].sum() == summary.loc["mars", "curated_images"]
    assert years["year"].max() <= data_access.get_dataset_profile()["analysis_date"].year


@needs_db
def test_planet_gallery_year_filter():
    for year, expected in data_access.get_planet_years("uranus").itertuples(index=False):
        curated, _ = data_access.count_planet_gallery("uranus", year=int(year))
        assert curated == expected
        page = data_access.get_planet_gallery("uranus", year=int(year), page_size=100)
        assert len(page) == expected
        assert all(day.year == year for day in page["date"])
        assert (page["topic"] == "uranus").all()


@needs_db
def test_nearest_date_fallback():
    # 2020-09-09 has no curated Mars image; the closest is 2020-09-04 (5 days earlier).
    nearest_date, count = data_access.find_nearest_planet_date("mars", dt.date(2020, 9, 9))
    assert nearest_date == dt.date(2020, 9, 4)
    assert count == data_access.count_planet_gallery("mars", nearest_date)[0] > 0
    page = data_access.get_planet_gallery("mars", metadata_date=nearest_date)
    assert (page["date"] == nearest_date).all() and (page["topic"] == "mars").all()

    # The result is always inside the 30-day window, or None.
    for topic, day in [("uranus", dt.date(1986, 1, 30)), ("uranus", dt.date(2020, 6, 1))]:
        nearest = data_access.find_nearest_planet_date(topic, day)
        if nearest is not None:
            assert abs((nearest[0] - day).days) <= data_access.NEAREST_DATE_WINDOW_DAYS
    assert data_access.find_nearest_planet_date("uranus", dt.date(2020, 6, 1)) is None

    # Future-dated anomalies are never offered as the nearest date.
    assert data_access.find_nearest_planet_date("earth", dt.date(2031, 7, 20)) is None


@needs_db
def test_nearest_date_ties_choose_the_earlier_date():
    # Find two consecutive curated Mars dates an even number of days apart; the midpoint
    # is equally close to both, and nothing curated lies between them.
    pair = data_access.run_query(f"""
        WITH c AS ({data_access.PLANET_CANDIDATES_SQL} AND m.search_keyword = 'mars'),
        dates AS (SELECT DISTINCT date FROM c WHERE planet_score >= :min_score),
        gaps AS (SELECT LAG(date) OVER (ORDER BY date) AS earlier, date AS later FROM dates)
        SELECT earlier, later FROM gaps
        WHERE later - earlier BETWEEN 2 AND 40 AND (later - earlier) % 2 = 0
        ORDER BY later DESC LIMIT 1
    """, {**data_access.PLANET_PATTERNS, "min_score": data_access.PLANET_MIN_SCORE})
    earlier, later = pair.iloc[0]["earlier"], pair.iloc[0]["later"]
    midpoint = earlier + (later - earlier) / 2
    assert data_access.find_nearest_planet_date("mars", midpoint)[0] == earlier


@needs_db
def test_planet_gallery_pages_do_not_overlap_and_count_matches():
    summary = data_access.get_planet_topic_summary().set_index("topic")
    curated = int(summary.loc["neptune", "curated_images"])
    seen = []
    for page_number in range(1, -(-curated // data_access.PAGE_SIZE) + 1):
        seen += data_access.get_planet_gallery("neptune", page=page_number)["source_id"].tolist()
    assert len(seen) == len(set(seen)) == curated


@needs_db
def test_unfiltered_count_and_first_page():
    total = data_access.count_images()
    assert total == data_access.get_kpis()["total_images"]
    page = data_access.search_images(page=1)
    assert len(page) == data_access.PAGE_SIZE
    assert page["date"].is_monotonic_decreasing


@needs_db
def test_keyword_search_matches_title_description_or_id():
    page = data_access.search_images(search_text="curiosity", page=1)
    assert not page.empty
    for row in page.itertuples():
        text = f"{row.title} {row.explanation} {row.source_id}".lower()
        assert "curiosity" in text

    # An exact NASA ID finds that image.
    by_id = data_access.search_images(search_text="PIA21000")
    assert "PIA21000" in by_id["source_id"].tolist()


@needs_db
def test_multiple_topics_are_or_without_duplicates():
    mars = data_access.count_images(topics=("mars",))
    earth = data_access.count_images(topics=("earth",))
    both = data_access.count_images(topics=("earth", "mars"))
    shared = scalar("""
        SELECT COUNT(*) FROM nasa_search_matches a JOIN nasa_search_matches b
          USING (source_api, source_id)
        WHERE a.search_keyword = 'earth' AND b.search_keyword = 'mars'
    """)
    assert both == earth + mars - shared

    # Walk several pages: no NASA ID appears twice.
    seen = []
    for page_number in range(1, 6):
        seen += data_access.search_images(topics=("earth", "mars"), page=page_number)["source_id"].tolist()
    assert len(seen) == len(set(seen)) == 5 * data_access.PAGE_SIZE


@needs_db
def test_date_and_center_filters_combine_with_and():
    start, end = dt.date(2010, 1, 1), dt.date(2010, 12, 31)
    page = data_access.search_images(centers=("JPL",), start_date=start, end_date=end,
                                     sort="Oldest first", page=1)
    assert not page.empty
    assert (page["center"] == "JPL").all()
    assert page["date"].between(start, end).all()
    assert page["date"].is_monotonic_increasing

    expected = scalar("""
        SELECT COUNT(*) FROM nasa_records
        WHERE center = 'JPL' AND date BETWEEN :start AND :end
    """, {"start": start, "end": end})
    assert data_access.count_images(centers=("JPL",), start_date=start, end_date=end) == expected


@needs_db
def test_title_sort_and_last_page():
    total = data_access.count_images(topics=("uranus",))
    last_page = -(-total // data_access.PAGE_SIZE)
    page = data_access.search_images(topics=("uranus",), sort="Title (A–Z)", page=last_page)
    assert len(page) == total - (last_page - 1) * data_access.PAGE_SIZE
    # Compare with PostgreSQL's own ordering, since its collation differs from Python's sort.
    expected = data_access.run_query("""
        SELECT r.source_id FROM nasa_records r
        JOIN nasa_search_matches m USING (source_api, source_id)
        WHERE m.search_keyword = 'uranus'
        ORDER BY LOWER(r.title), r.source_id
    """)["source_id"].tolist()
    assert page["source_id"].tolist() == expected[(last_page - 1) * data_access.PAGE_SIZE:]


@needs_db
def test_empty_result():
    assert data_access.count_images(search_text="zzzz-no-such-image-zzzz") == 0
    assert data_access.search_images(search_text="zzzz-no-such-image-zzzz").empty


@needs_db
def test_centers_list_skips_invalid_values():
    centers = data_access.get_centers()["center"].tolist()
    assert "JPL" in centers and "KSC" in centers
    assert not any("@" in center for center in centers)


@needs_db
def test_insights_match_eda_definitions():
    kpis = data_access.get_kpis()
    profile = data_access.get_dataset_profile()

    # Insight 1: topic counts add up to relationships, not unique images.
    topic_counts = data_access.get_topic_counts()
    assert topic_counts["topic_matches"].sum() == kpis["total_relationships"]
    assert len(topic_counts) == kpis["total_topics"]

    # Insight 2: future dates are excluded and the last year is not in the future.
    annual = data_access.get_annual_counts()
    assert annual["unique_images"].sum() == profile["historical_images"]
    assert profile["historical_images"] + profile["future_dates"] == kpis["total_images"]
    assert annual["year"].max() <= profile["analysis_date"].year

    # Insight 3: per-image topic counts reconcile with both totals.
    per_image = data_access.get_topics_per_image()
    assert per_image["unique_images"].sum() == kpis["total_images"]
    assert (per_image["topic_count"] * per_image["unique_images"]).sum() == kpis["total_relationships"]

    # Insight 4: completeness percentages use unique images as the denominator.
    completeness = data_access.get_metadata_completeness()
    assert (completeness["available"] + completeness["missing"] == kpis["total_images"]).all()
    assert completeness["completeness"].between(0, 100).all()


@needs_db
def test_peak_mission_union_is_deduplicated():
    breakdown = data_access.get_peak_mission_breakdown()
    assert breakdown["year"].tolist() == list(rules.PEAK_YEARS)
    missions = list(rules.PEAK_MISSIONS)
    for _, row in breakdown.iterrows():
        # The union is at least the largest mission and at most their sum.
        assert row[missions].max() <= row["any_mission"] <= row[missions].sum()
        assert row["any_mission"] + row["other"] == row["total"]

    # Independent check of the union with one combined regular expression.
    combined = "|".join(f"({pattern})" for pattern in rules.PEAK_MISSIONS.values())
    union_2014 = scalar("""
        SELECT COUNT(*) FROM nasa_records r
        WHERE r.center = 'KSC' AND EXTRACT(YEAR FROM r.date) = 2014
          AND EXISTS (SELECT 1 FROM nasa_search_matches m
                      WHERE m.source_id = r.source_id AND m.search_keyword = 'earth')
          AND (r.title || ' ' || r.keywords::text) ~* :pattern
    """, {"pattern": combined})
    assert union_2014 == breakdown.set_index("year").loc[2014, "any_mission"]


@needs_db
def test_center_year_counts_and_ranking_reconcile():
    centers = data_access.get_center_year_counts((2013, 2014))
    for year in (2013, 2014):
        assert centers[year].sum() == scalar(
            "SELECT COUNT(*) FROM nasa_records WHERE EXTRACT(YEAR FROM date) = :year", {"year": year})
    ranking = data_access.get_center_ranking(10)
    assert ranking["images"].is_monotonic_decreasing
    assert ranking.loc[0, "images"] == scalar(
        "SELECT COUNT(*) FROM nasa_records WHERE center = :center", {"center": ranking.loc[0, "center"]})


@needs_db
def test_content_profile_covers_every_record_once():
    profile = data_access.get_center_content_profile(("KSC", "JPL", "JSC"))
    assert set(profile["content_group"]) <= set(rules.CONTENT_GROUPS)
    for center, group in profile.groupby("center"):
        assert group["images"].sum() == scalar(
            "SELECT COUNT(*) FROM nasa_records WHERE center = :center", {"center": center})
        assert abs(group["share"].sum() - 100) < 1e-6


@needs_db
def test_title_rules_behave_as_documented():
    def matches(title, pattern):
        return bool(scalar("SELECT :title ~* :pattern", {"title": title, "pattern": pattern}))

    assert matches("KSC-2011-7368", rules.ID_ONLY_TITLE)
    assert matches("iss068e054895", rules.ID_ONLY_TITLE)
    assert not matches("Artemis II Rollout", rules.ID_ONLY_TITLE)
    assert matches("Sentinel-6B Encapsulation", rules.OPERATIONS_TITLE)
    assert matches("Lopez-Alegria during EVA 8", rules.OPERATIONS_TITLE)
    assert not matches("Defrosting Dunes within Chasma Boreale", rules.OPERATIONS_TITLE)
    assert matches("Earth Observations taken by the Expedition 38 crew", rules.EARTH_OBSERVATION_TITLE)
    assert matches("Orion, EFT-1", rules.MISSION_ALIASES["Orion spacecraft (incl. EFT-1)"])
    assert not matches("Orion Nebula in infrared", rules.MISSION_ALIASES["Orion spacecraft (incl. EFT-1)"])


@needs_db
def test_mission_mentions_count_distinct_images():
    missions = data_access.get_mission_mentions()
    assert missions["mission"].is_unique
    assert missions["images"].is_monotonic_decreasing
    assert (missions["peak_year_images"] <= missions["images"]).all()
    juno = missions.set_index("mission").loc["Juno", "images"]
    expected = scalar("""
        SELECT COUNT(*) FROM nasa_records r
        WHERE r.date <= CURRENT_DATE
          AND (r.title || ' | ' || COALESCE((SELECT string_agg(k, ' | ')
                                             FROM jsonb_array_elements_text(r.keywords) k), '')) ~* :p
    """, {"p": rules.MISSION_ALIASES["Juno"]})
    assert juno == expected


@needs_db
def test_credit_and_location_groups_cover_available_values():
    formats = data_access.get_credit_formats()
    assert formats["images"].sum() == scalar("SELECT COUNT(*) FROM nasa_records WHERE credit ~ '[^[:space:]]'")
    groups = data_access.get_location_groups()
    assert groups["images"].sum() == scalar("SELECT COUNT(*) FROM nasa_records WHERE location ~ '[^[:space:]]'")
    assert set(groups["location_group"]) <= set(rules.LOCATION_GROUPS) | {rules.OTHER_LOCATION}
    top = data_access.get_top_locations(10)
    assert len(top) == 10 and top["images"].is_monotonic_decreasing


@needs_db
def test_archive_years_only_list_years_with_records():
    years = data_access.get_archive_years()
    assert years["year"].min() >= data_access.NASA_FIRST_YEAR
    assert years["year"].max() <= dt.date.today().year
    assert (years["images"] > 0).all()
    # Combined filters: every listed year really has KSC Earth-topic records.
    ksc_earth = data_access.get_archive_years(topics=("earth",), centers=("KSC",)).set_index("year")
    assert ksc_earth.loc[2014, "images"] == data_access.get_peak_mission_breakdown().set_index("year").loc[2014, "total"]


def test_year_bounds_never_pass_today():
    today = dt.date(2026, 11, 25)
    assert data_access.year_bounds(2014, today) == (dt.date(2014, 1, 1), dt.date(2014, 12, 31))
    assert data_access.year_bounds(2026, today) == (dt.date(2026, 1, 1), today)


# ---------------------------------------------------------------------------
# App smoke tests: every page renders without exceptions
# ---------------------------------------------------------------------------

def run_view(view_name):
    """Render a single dashboard view in Streamlit's headless test runner."""
    from streamlit.testing.v1 import AppTest

    def script(view_name, dashboard_dir):
        import importlib
        import sys

        sys.path.insert(0, dashboard_dir)
        importlib.import_module(f"views.{view_name}").render()

    app = AppTest.from_function(script, args=(view_name, str(DASHBOARD_DIR)), default_timeout=90)
    return app.run()


@needs_db
def test_home_page_renders_through_app_entry_point():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(DASHBOARD_DIR / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert not app.error
    kpi_html = " ".join(block.value for block in app.markdown)
    assert f"{data_access.get_kpis()['total_images']:,}" in kpi_html


@needs_db
def test_planet_gallery_page_topic_selection():
    app = run_view("gallery")
    assert not app.exception
    assert app.session_state["gallery_topic"] == "mars"

    # Clicking a topic button switches the gallery to that topic.
    next(b for b in app.button if b.label == "Saturn").click().run()
    assert not app.exception
    assert app.session_state["gallery_topic"] == "saturn"
    assert any("curated images" in block.value for block in app.markdown)

    # Uranus has fewer strong matches; the page still renders and shows its pagination state.
    next(b for b in app.button if b.label == "Uranus").click().run()
    assert not app.exception
    assert app.session_state["gallery_page_number"] == 1

    # Explore by Year is the default; "All years" shows the full topic gallery.
    next(b for b in app.button if b.label == "Mars").click().run()
    assert app.radio(key="gallery_mode").value == "Explore by Year"
    assert app.selectbox(key="gallery_year").value == "All years"
    assert sum(b.label == "View details" for b in app.button) == data_access.PAGE_SIZE

    # Picking a year narrows the gallery and resets pagination.
    next(b for b in app.button if b.label == "Next →").click().run()
    assert app.session_state["gallery_page_number"] == 2
    app.selectbox(key="gallery_year").set_value(2020).run()
    assert not app.exception
    assert app.session_state["gallery_page_number"] == 1
    mars_2020, _ = data_access.count_planet_gallery("mars", year=2020)
    assert any(f"{mars_2020:,} curated Mars images" in block.value for block in app.markdown)

    # Explore by Date with an exact match: Mars on 2006-12-27 has 43 curated images (4 pages).
    app.radio(key="gallery_mode").set_value("Explore by Date").run()
    app.date_input(key="gallery_date").set_value(dt.date(2006, 12, 27)).run()
    assert not app.exception
    assert any("43 curated Mars images" in block.value for block in app.markdown)
    assert any("Page 1 of 4" in block.value for block in app.markdown)

    # No exact match: the nearest curated date is shown and clearly labelled.
    app.date_input(key="gallery_date").set_value(dt.date(2020, 9, 9)).run()
    notice = " ".join(block.value for block in app.info)
    assert "No curated images were found for your selected date" in notice
    assert "Closest available date: Sep 4, 2020 — 5 days before your selection" in notice
    assert sum(b.label == "View details" for b in app.button) == 1

    # Nothing within 30 days: friendly warning plus a button to explore that year instead.
    next(b for b in app.button if b.label == "Uranus").click().run()
    app.date_input(key="gallery_date").set_value(dt.date(2020, 6, 1)).run()
    assert any("within 30 days" in block.value for block in app.warning)
    assert not any(b.label == "View details" for b in app.button)
    next(b for b in app.button if b.label == "Explore Uranus in 2020").click().run()
    assert app.radio(key="gallery_mode").value == "Explore by Year"
    assert app.session_state["gallery_year"] == 2020
    assert sum(b.label == "View details" for b in app.button) == 1


def shows_count(app, count, suffix=""):
    """True when the Archive Search result line shows this many matches."""
    noun = "image" if count == 1 else "images"
    expected = f'<span class="num">{count:,}</span> matching {noun} <span class="range">{suffix}'
    return any(expected in block.value for block in app.markdown)


@needs_db
def test_insights_page_has_one_chart_and_one_finding_per_insight():
    app = run_view("insights")
    assert not app.exception
    text = " ".join(block.value for block in app.markdown)
    assert text.count('class="insight-title"') == 3
    assert text.count("Key Finding.") == 3
    # One chart per insight, plus the small yearly overview that shows 2014 is the peak.
    assert len(app.get("plotly_chart")) == 4
    for vague in ("actually document", "Mention Orion", "mentioning", "What was behind",
                  "priorities or budget"):
        assert vague not in text
    assert len(app.dataframe) == 0
    assert "Interpretation & Limitation" not in text and "Four" not in text

    # Key Findings are computed from the live queries.
    breakdown = data_access.get_peak_mission_breakdown()
    first, last = breakdown.iloc[0], breakdown.iloc[-1]
    growth = int(last["total"] - first["total"])
    mission_growth = int(last["any_mission"] - first["any_mission"])
    assert f"added {mission_growth:,} of them" in text
    assert f"**about {mission_growth / growth * 100:.0f}% of that increase**" in text
    missions = data_access.get_mission_mentions().set_index("mission")
    assert f"Artemis ranks first with {missions.loc['Artemis program (incl. EM-1)', 'images']:,} image records" in text
    assert f"2001 Mars Odyssey comes in second with {missions.loc['2001 Mars Odyssey', 'images']:,} records" in text
    assert "two other Mars missions also make the top eight" in text
    top_three = data_access.get_center_ranking(6).head(3)["share"].sum()
    assert f"contribute about {top_three:.0f}% of our records" in text


@needs_db
def test_annual_overview_highlights_peak_year():
    from views import insights

    annual = data_access.get_annual_counts()
    annual = annual[annual["year"] >= data_access.NASA_FIRST_YEAR]
    peak = int(annual.loc[annual["unique_images"].idxmax(), "year"])
    figure = insights.annual_overview_chart(annual, peak)
    colors = list(figure.data[0].marker.color)
    assert colors.count(insights.GOLD) == 1
    assert colors[list(figure.data[0].x).index(peak)] == insights.GOLD

    # The timeline reaches the latest year with records up to today, and labels it.
    latest = int(annual["year"].max())
    assert latest == min(dt.date.today().year, scalar(
        "SELECT MAX(EXTRACT(YEAR FROM date))::int FROM nasa_records WHERE date <= CURRENT_DATE"))
    assert int(annual.set_index("year").loc[latest, "unique_images"]) == scalar(
        "SELECT COUNT(*) FROM nasa_records WHERE EXTRACT(YEAR FROM date) = :year AND date <= CURRENT_DATE",
        {"year": latest})
    ticks = list(figure.layout.xaxis.tickvals)
    assert ticks[-1] == latest and max(figure.data[0].x) == latest
    assert all(b - a >= 10 for a, b in zip(ticks, ticks[1:]))


@needs_db
def test_peak_chart_keeps_years_categorical():
    """Regression: year labels must not stretch the axis and hide the bars."""
    from views import insights

    figure = insights.peak_chart(data_access.get_peak_mission_breakdown())
    assert figure.layout.xaxis.type == "category"
    assert tuple(figure.layout.xaxis.range) == (-0.5, 1.5)
    assert all(isinstance(note.x, int) for note in figure.layout.annotations)


@needs_db
def test_home_copy_describes_three_findings():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(DASHBOARD_DIR / "app.py"), default_timeout=60).run()
    text = " ".join(block.value for block in app.markdown)
    assert "Three findings" in text and "Four interactive charts" not in text
    assert 'class="hero animated"' in text


@needs_db
def test_explore_page_search_pagination_and_reset():
    from views import explore

    app = run_view("explore")
    assert not app.exception
    assert any("matching images" in block.value for block in app.markdown)
    # Intro is one sentence; the old explanation cards are gone.
    text = " ".join(block.value for block in app.markdown)
    assert explore.INTRO in text and "You are here" not in text

    # Next page moves forward and enables Previous.
    next(b for b in app.button if b.label == "Next →").click().run()
    assert any("Page 2 of" in block.value for block in app.markdown)

    # Sorting oldest first keeps every result inside NASA's era by default.
    app.selectbox(key="filter_sort").set_value("Oldest first").run()
    assert not app.exception
    assert any("Page 1 of" in block.value for block in app.markdown)

    # A new search resets to page 1 and narrows the results.
    app.text_input(key="filter_search").set_value("PIA21000").run()
    assert not app.exception
    assert any("Page 1 of 1" in block.value for block in app.markdown)

    # A search with no results shows a friendly message instead of an error.
    app.text_input(key="filter_search").set_value("zzzz-no-such-image-zzzz").run()
    assert any(explore.NO_RESULTS in block.value for block in app.info)

    # Reset restores the default results: NASA's era, 1958 up to today.
    next(b for b in app.button if b.key == "reset_filters").click().run()
    assert app.text_input(key="filter_search").value == ""
    assert app.session_state["filter_date_mode"] == explore.MODE_YEAR
    assert app.selectbox(key="filter_year").value == explore.ALL_YEARS
    total = scalar("""SELECT COUNT(*) FROM nasa_records
                      WHERE date >= DATE '1958-01-01' AND date <= CURRENT_DATE""")
    assert shows_count(app, total)


@needs_db
def test_explore_year_mode_and_combined_filters():
    from views import explore

    app = run_view("explore")
    year_box = app.selectbox(key="filter_year")
    years = [option for option in year_box.options if option != explore.ALL_YEARS]
    # Only years with records, from 1958 up to the current year, newest first, with counts.
    numbers = [int(option.split(" ")[0]) for option in years]
    assert numbers == sorted(numbers, reverse=True)
    assert min(numbers) >= data_access.NASA_FIRST_YEAR and max(numbers) <= dt.date.today().year
    expected_2014 = scalar("SELECT COUNT(*) FROM nasa_records WHERE EXTRACT(YEAR FROM date) = 2014")
    assert f"2014 — {expected_2014:,} images" in years

    # 2014, the archive's peak year.
    year_box.set_value(2014).run()
    assert not app.exception
    assert shows_count(app, expected_2014, "in 2014")

    # Year + center + topic + keyword together.
    app.multiselect(key="filter_centers").set_value(["KSC"]).run()
    app.multiselect(key="filter_topics").set_value(["earth"]).run()
    assert not app.exception
    expected = data_access.get_peak_mission_breakdown().set_index("year").loc[2014, "total"]
    assert shows_count(app, int(expected), "in 2014")
    app.text_input(key="filter_search").set_value("OCO-2").run()
    expected_oco = data_access.count_images(search_text="OCO-2", topics=("earth",), centers=("KSC",),
                                            start_date=dt.date(2014, 1, 1), end_date=dt.date(2014, 12, 31))
    assert expected_oco > 0 and shows_count(app, expected_oco, "in 2014")
    # Each year label already reflects the other filters.
    assert any(o.startswith(f"2014 — {expected_oco:,} image") for o in app.selectbox(key="filter_year").options)

    # Narrowing to a topic with few records keeps only that topic's years.
    app.text_input(key="filter_search").set_value("").run()
    app.multiselect(key="filter_centers").set_value([]).run()
    app.multiselect(key="filter_topics").set_value(["uranus"]).run()
    uranus_years = data_access.get_archive_years(topics=("uranus",))["year"].tolist()
    options = [o for o in app.selectbox(key="filter_year").options if o != explore.ALL_YEARS]
    assert [int(o.split(" ")[0]) for o in options] == uranus_years
    if 2014 not in uranus_years:
        assert app.selectbox(key="filter_year").value == explore.ALL_YEARS


@needs_db
def test_explore_classroom_demo_orion_2014():
    """Search "Orion", pick 2014: real records with thumbnails load."""
    app = run_view("explore")
    app.text_input(key="filter_search").set_value("Orion").run()
    app.selectbox(key="filter_year").set_value(2014).run()
    assert not app.exception
    expected = data_access.count_images(search_text="Orion", start_date=dt.date(2014, 1, 1),
                                        end_date=dt.date(2014, 12, 31))
    assert expected > 0 and shows_count(app, expected, "in 2014")
    assert sum(b.label == "View details" for b in app.button) == min(expected, data_access.PAGE_SIZE)


@needs_db
def test_explore_date_range_mode_and_historical_archive():
    from views import explore

    app = run_view("explore")
    text = " ".join(block.value for block in app.markdown)
    pre_nasa = scalar("SELECT COUNT(*) FROM nasa_records WHERE date < DATE '1958-01-01'")
    assert f"Historical Records — {pre_nasa:,} records before 1958" in text
    assert any(explore.HISTORICAL_NOTE in block.value for block in app.caption)

    # One click shows every pre-1958 record, oldest first, even after another search.
    app.text_input(key="filter_search").set_value("Orion").run()
    app.selectbox(key="filter_year").set_value(2014).run()
    next(b for b in app.button if b.key == "show_historical").click().run()
    assert not app.exception
    assert app.session_state["filter_date_mode"] == explore.MODE_RANGE
    assert app.selectbox(key="filter_year").value == explore.CUSTOM_RANGE
    assert app.selectbox(key="filter_sort").value == "Oldest first"
    earliest, _, _ = data_access.get_date_bounds()
    assert app.date_input(key="filter_dates").value == (earliest, dt.date(1957, 12, 31))
    assert shows_count(app, pre_nasa)
    assert sum(b.label == "View details" for b in app.button) == min(pre_nasa, data_access.PAGE_SIZE)
    oldest = scalar("SELECT title FROM nasa_records ORDER BY date, source_id LIMIT 1")
    assert any(escape(oldest)[:20] in block.value or oldest[:20] in block.value for block in app.markdown)

    # 1912 alone: the earliest record (a von Braun childhood photo dated with his birth date).
    app.date_input(key="filter_dates").set_value((earliest, dt.date(1912, 12, 31))).run()
    count_1912 = scalar("SELECT COUNT(*) FROM nasa_records WHERE EXTRACT(YEAR FROM date) = 1912")
    assert shows_count(app, count_1912, f"from {earliest:%b} {earliest.day}, 1912")

    # A range with no records shows the friendly message and a reset button.
    app.date_input(key="filter_dates").set_value((dt.date(1920, 1, 1), dt.date(1940, 12, 31))).run()
    assert not app.exception
    assert any(explore.NO_RESULTS in block.value for block in app.info)
    next(b for b in app.button if b.key == "reset_after_empty").click().run()
    assert app.session_state["filter_date_mode"] == explore.MODE_YEAR
    assert any("matching images" in block.value for block in app.markdown)

    # Editing the custom range switches the date filter; picking a year switches back.
    app.date_input(key="filter_dates").set_value((dt.date(1969, 7, 1), dt.date(1969, 7, 31))).run()
    assert app.selectbox(key="filter_year").value == explore.CUSTOM_RANGE
    app.selectbox(key="filter_year").set_value(1958).run()
    assert app.session_state["filter_date_mode"] == explore.MODE_YEAR
    count_1958 = scalar("SELECT COUNT(*) FROM nasa_records WHERE EXTRACT(YEAR FROM date) = 1958")
    assert shows_count(app, count_1958, "in 1958")

    # Every stored date, including future-dated metadata.
    next(b for b in app.button if b.key == "show_all_dates").click().run()
    assert shows_count(app, scalar("SELECT COUNT(*) FROM nasa_records"))


def test_app_shows_friendly_error_when_database_is_down(monkeypatch):
    """A bad connection shows a clear message and never the connection string."""
    from streamlit.testing.v1 import AppTest

    bad_url = "postgresql+psycopg2://demo_user:secret-password@127.0.0.1:1/nasa"
    monkeypatch.setenv("DATABASE_URL", bad_url)
    data_access.get_engine.clear()
    try:
        app = AppTest.from_file(str(DASHBOARD_DIR / "app.py"), default_timeout=30).run()
        assert not app.exception
        assert len(app.error) == 1
        assert "Could not connect" in app.error[0].value
        assert "secret-password" not in app.error[0].value
    finally:
        data_access.get_engine.clear()
