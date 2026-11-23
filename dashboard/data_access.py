"""Read-only PostgreSQL queries used by the Streamlit dashboard.

Every query is parameterized and runs inside a read-only transaction.
The SQL definitions for the Data Insights page follow notebooks/eda.ipynb.
"""

import datetime as dt
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The dashboard, like the EDA, only covers NASA Image Library images.
SCOPE_SQL = "r.source_api = 'nasa_library' AND r.media_type = 'image'"

PAGE_SIZE = 12

# Whitelisted ORDER BY clauses; user input never reaches the SQL text directly.
SORT_OPTIONS = {
    "Newest first": "r.date DESC, r.source_id",
    "Oldest first": "r.date ASC, r.source_id",
    "Title (A–Z)": "LOWER(r.title) ASC, r.source_id",
}


class DatabaseConfigError(RuntimeError):
    """Raised when DATABASE_URL is not configured."""


@st.cache_resource(show_spinner=False)
def get_engine():
    """Create one shared, read-only SQLAlchemy engine for the app."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise DatabaseConfigError("DATABASE_URL is not set in the project .env file.")

    # Read-only sessions protect the data; the Chicago timezone matches the EDA's date cutoff.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "options": "-c default_transaction_read_only=on -c timezone=America/Chicago",
            "connect_timeout": 5,
        },
    )


def run_query(sql, params=None):
    """Run a read-only query and return the rows as a DataFrame."""
    with get_engine().connect() as connection:
        return pd.read_sql(text(sql), connection, params=params or {})


def check_connection():
    """Raise an exception if PostgreSQL cannot be reached."""
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_kpis():
    """Count unique images, topic relationships, and search topics."""
    sql = f"""
        SELECT
            (SELECT COUNT(*) FROM nasa_records AS r WHERE {SCOPE_SQL}) AS total_images,
            (SELECT COUNT(*)
               FROM nasa_search_matches AS m
               JOIN nasa_records AS r USING (source_api, source_id)
              WHERE {SCOPE_SQL}) AS total_relationships,
            (SELECT COUNT(DISTINCT m.search_keyword)
               FROM nasa_search_matches AS m
               JOIN nasa_records AS r USING (source_api, source_id)
              WHERE {SCOPE_SQL}) AS total_topics
    """
    row = run_query(sql).iloc[0]
    return {key: int(value) for key, value in row.items()}


# ---------------------------------------------------------------------------
# Archive Search page
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_topics():
    """Return every search topic, largest first."""
    sql = """
        SELECT search_keyword AS topic, COUNT(*) AS images
        FROM nasa_search_matches
        GROUP BY search_keyword
        ORDER BY images DESC, topic
    """
    return run_query(sql)


@st.cache_data(ttl=3600, show_spinner=False)
def get_centers():
    """Return NASA center values with image counts.

    A few stored values are clearly not center names (for example an email
    address), so those are left out of the filter list.
    """
    sql = f"""
        SELECT r.center, COUNT(*) AS images
        FROM nasa_records AS r
        WHERE {SCOPE_SQL}
          AND r.center ~ '[^[:space:]]'
          AND r.center NOT LIKE '%@%'
        GROUP BY r.center
        ORDER BY images DESC, r.center
    """
    return run_query(sql)


@st.cache_data(ttl=3600, show_spinner=False)
def get_date_bounds():
    """Return the earliest and latest stored image dates, plus today's date."""
    sql = f"""
        SELECT MIN(r.date) AS earliest, MAX(r.date) AS latest, CURRENT_DATE AS today
        FROM nasa_records AS r
        WHERE {SCOPE_SQL} AND isfinite(r.date)
    """
    row = run_query(sql).iloc[0]
    return row["earliest"], row["latest"], row["today"]


def escape_like(value):
    """Escape LIKE wildcards so user text is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_filter_clause(search_text="", topics=(), centers=(), start_date=None, end_date=None):
    """Build a parameterized WHERE clause for the image filters.

    Different filter types are combined with AND. Several selected topics or
    centers are combined with OR. Topics use EXISTS instead of a JOIN so an
    image that matches two selected topics still appears only once.
    """
    conditions = [SCOPE_SQL]
    params = {}

    search_text = (search_text or "").strip()
    if search_text:
        conditions.append(
            "(r.title ILIKE :pattern OR r.explanation ILIKE :pattern OR r.source_id ILIKE :pattern)"
        )
        params["pattern"] = f"%{escape_like(search_text)}%"

    if topics:
        conditions.append("""EXISTS (
            SELECT 1 FROM nasa_search_matches AS m
            WHERE m.source_api = r.source_api
              AND m.source_id = r.source_id
              AND m.search_keyword = ANY(:topics))""")
        params["topics"] = list(topics)

    if centers:
        conditions.append("r.center = ANY(:centers)")
        params["centers"] = list(centers)

    if start_date is not None:
        conditions.append("r.date >= :start_date")
        params["start_date"] = start_date

    if end_date is not None:
        conditions.append("r.date <= :end_date")
        params["end_date"] = end_date

    return " AND ".join(conditions), params


@st.cache_data(ttl=600, max_entries=200, show_spinner=False)
def count_images(search_text="", topics=(), centers=(), start_date=None, end_date=None):
    """Count unique images that match the filters."""
    where_sql, params = build_filter_clause(search_text, topics, centers, start_date, end_date)
    sql = f"SELECT COUNT(*) AS total FROM nasa_records AS r WHERE {where_sql}"
    return int(run_query(sql, params).iloc[0]["total"])


@st.cache_data(ttl=600, max_entries=200, show_spinner=False)
def search_images(search_text="", topics=(), centers=(), start_date=None, end_date=None,
                  sort="Newest first", page=1, page_size=PAGE_SIZE):
    """Return one page of matching images using LIMIT/OFFSET."""
    if sort not in SORT_OPTIONS:
        raise ValueError(f"Unknown sort option: {sort}")

    where_sql, params = build_filter_clause(search_text, topics, centers, start_date, end_date)
    params.update({"limit": page_size, "offset": max(page - 1, 0) * page_size})

    # The topic list is collected only for the 12 rows on this page.
    sql = f"""
        SELECT r.source_id, r.date, r.title, r.image_url, r.page_url,
               r.explanation, r.credit, r.center, r.location, r.keywords,
               ARRAY(
                   SELECT m.search_keyword FROM nasa_search_matches AS m
                   WHERE m.source_api = r.source_api AND m.source_id = r.source_id
                   ORDER BY m.search_keyword
               ) AS topics
        FROM nasa_records AS r
        WHERE {where_sql}
        ORDER BY {SORT_OPTIONS[sort]}
        LIMIT :limit OFFSET :offset
    """
    return run_query(sql, params)


# ---------------------------------------------------------------------------
# Planet Gallery (curated view)
# ---------------------------------------------------------------------------
#
# Keyword search returns many briefings, launches, and people photos. To show
# images that actually look like planets and space, each record gets a simple,
# explainable score from its existing metadata:
#
#   +3  NASA ID starts with "PIA" (the Planetary Photojournal: mission science imagery)
#   +2  the title names the topic (e.g. "Saturn")
#   +2  the title or keywords use science-imagery words (crater, rings, nebula, rover, Hubble, ...)
#   -6  the title uses people/event words (briefing, ceremony, team, launch, testing, ...)
#   -2  the title suggests an illustration rather than a photo (artist, concept, diagram, ...)
#   -2  the record comes from a center whose photos are mostly launch processing or events
#   -3  the title is only an ID code (e.g. "KSC-2011-5720"), so it says nothing about the content
#
# Records scoring at least PLANET_MIN_SCORE are shown. Only real (non-future)
# dates and thumbnail URLs are used.

PLANET_MIN_SCORE = 4

# Solar-system order reads more naturally than order by size.
PLANET_TOPIC_ORDER = ["mercury", "venus", "earth", "mars", "jupiter", "saturn",
                      "uranus", "neptune", "galaxy"]


def word_pattern(words):
    """Case-insensitive PostgreSQL regex that matches any word at a word start."""
    return r"\m(" + "|".join(words) + ")"


PLANET_PATTERNS = {
    "science_words": word_pattern([
        "surface", "craters?", "rover", "orbiter", "hubble", "telescope", "true color", "false color",
        "color", "mosaic", "rings?", "clouds?", "storms?", "nebula", "galax", "cluster", "hirise",
        "cassini", "juno", "voyager", "webb", "messenger", "magellan", "curiosity", "perseverance",
        "opportunity", "spirit", "dunes?", "canyons?", "volcan", "polar", "terrain", "landscape",
        "panorama", "atmosphere", "moons?", "earth observation", "observations?", "horizon",
        "sunset", "sunrise", "limb", "globe", "hemisphere", "infrared", "ultraviolet", "spitzer",
        "chandra", "radar", "valley", "basin", "impact", "plains?", "ice\\M", "icy", "stars?", "stellar", "cosmic",
    ]),
    "people_words": word_pattern([
        "briefing", "press", "conference", "news", "ceremony", "visits?", "visitors?", "tour",
        "awards?", "awardees", "teams?", "engineers?", "technicians?", "employees", "students",
        "event", "celebration", "workshop", "speaks", "speaker", "panel", "lecture", "symposium",
        "poster", "crew", "astronauts?", "portrait", "launch", "liftoff", "arrival", "processing",
        "mockup", "assembly", "clean room", "rollout", "insignia", "logo", "patch", "meeting", "media",
        "interview", "signing", "reception", "exhibit", "complex", "parade", "training", "official",
        "administrator", "director", "presents", "participants?", "guests?", "attendees", "audience",
        "kids", "viewing", "testing", "test", "inspect", "hardware", "vault", "cruise stage",
        "install", "laboratory", "facility", "building",
    ]),
    "illustration_words": word_pattern([
        "artist", "concept", "illustration", "animation", "graphic", "diagram", "chart", "map",
        "model", "rendering",
    ]),
}

PLANET_SCORE_SQL = """
      (CASE WHEN r.source_id LIKE 'PIA%' THEN 3 ELSE 0 END)
    + (CASE WHEN r.title ~* ('\\m' || m.search_keyword) THEN 2 ELSE 0 END)
    + (CASE WHEN r.title ~* :science_words OR r.keywords::text ~* :science_words THEN 2 ELSE 0 END)
    - (CASE WHEN r.title ~* :people_words THEN 6 ELSE 0 END)
    - (CASE WHEN r.title ~* :illustration_words THEN 2 ELSE 0 END)
    - (CASE WHEN r.center IN ('KSC', 'HQ', 'MAF', 'SSC') THEN 2 ELSE 0 END)
    - (CASE WHEN r.title = r.source_id
              OR r.title ~ '^[A-Za-z]{2,4}[-_ ]?[0-9]'
              OR r.title = 'Untitled NASA Image' THEN 3 ELSE 0 END)
"""

# Every curated candidate, scored. Future-dated anomalies are excluded here.
PLANET_CANDIDATES_SQL = f"""
    SELECT r.source_id, r.date, r.title, r.image_url, r.page_url, r.explanation,
           r.credit, r.center, r.location, r.keywords, m.search_keyword AS topic,
           {PLANET_SCORE_SQL} AS planet_score
    FROM nasa_records AS r
    JOIN nasa_search_matches AS m USING (source_api, source_id)
    WHERE {SCOPE_SQL}
      AND isfinite(r.date) AND r.date <= CURRENT_DATE
      AND r.image_url LIKE '%~thumb.jpg'
"""

# Highest score first; md5 gives a stable shuffle within a score so one mission doesn't fill the page.
PLANET_ORDER_SQL = "planet_score DESC, md5(source_id), source_id"


@st.cache_data(ttl=3600, show_spinner=False)
def get_planet_topic_summary():
    """One row per topic: curated image count, archive count, and a cover image."""
    sql = f"""
        WITH candidates AS ({PLANET_CANDIDATES_SQL}),
        strong AS (
            SELECT * FROM candidates WHERE planet_score >= :min_score
        ),
        covers AS (
            SELECT DISTINCT ON (topic) topic, source_id AS cover_id, title AS cover_title,
                   image_url AS cover_url, date AS cover_date
            FROM strong
            -- Prefer titles that start with the topic name (often a portrait of the planet itself).
            ORDER BY topic, planet_score DESC, (title ILIKE topic || '%') DESC, md5(source_id), source_id
        ),
        counts AS (
            SELECT topic,
                   COUNT(*) AS archive_images,
                   COUNT(*) FILTER (WHERE planet_score >= :min_score) AS curated_images
            FROM candidates
            GROUP BY topic
        )
        SELECT c.topic, c.curated_images, c.archive_images,
               v.cover_id, v.cover_title, v.cover_url, v.cover_date
        FROM counts AS c
        LEFT JOIN covers AS v USING (topic)
    """
    summary = run_query(sql, {**PLANET_PATTERNS, "min_score": PLANET_MIN_SCORE})

    # Keep solar-system order, with any unexpected topics at the end.
    rank = {topic: index for index, topic in enumerate(PLANET_TOPIC_ORDER)}
    summary["order"] = summary["topic"].map(lambda topic: rank.get(topic, len(rank)))
    return summary.sort_values(["order", "topic"]).drop(columns="order").reset_index(drop=True)


NEAREST_DATE_WINDOW_DAYS = 30


def planet_topic_filter(topic, metadata_date=None, year=None):
    """SQL and parameters that narrow candidates to one topic, plus an optional exact date or year.

    All conditions are combined with AND. Dates are the stored nasa_records.date
    value (NASA Image Library metadata), not necessarily when the photo was taken.
    """
    sql = " AND m.search_keyword = :topic"
    params = {**PLANET_PATTERNS, "topic": topic, "min_score": PLANET_MIN_SCORE}
    if metadata_date is not None:
        sql += " AND r.date = :metadata_date"
        params["metadata_date"] = metadata_date
    if year is not None:
        # A date range (rather than EXTRACT) keeps the condition simple and exact.
        sql += " AND r.date >= :year_start AND r.date < :year_end"
        params["year_start"] = dt.date(int(year), 1, 1)
        params["year_end"] = dt.date(int(year) + 1, 1, 1)
    return sql, params


@st.cache_data(ttl=3600, max_entries=200, show_spinner=False)
def count_planet_gallery(topic, metadata_date=None, year=None):
    """Curated and total archive matches for a topic, optionally on one date or in one year."""
    filter_sql, params = planet_topic_filter(topic, metadata_date, year)
    sql = f"""
        WITH candidates AS ({PLANET_CANDIDATES_SQL}{filter_sql})
        SELECT COUNT(*) FILTER (WHERE planet_score >= :min_score) AS curated_images,
               COUNT(*) AS archive_images
        FROM candidates
    """
    row = run_query(sql, params).iloc[0]
    return int(row["curated_images"]), int(row["archive_images"])


@st.cache_data(ttl=3600, max_entries=300, show_spinner=False)
def get_planet_gallery(topic, page=1, page_size=PAGE_SIZE, metadata_date=None, year=None):
    """One page of curated images for a topic (optional exact date or year), best matches first.

    Date and year are part of the cache key, so changing them always runs a fresh query.
    Each row is one (source_api, source_id) image because the join is limited to one topic.
    """
    filter_sql, params = planet_topic_filter(topic, metadata_date, year)
    sql = f"""
        WITH candidates AS ({PLANET_CANDIDATES_SQL}{filter_sql})
        SELECT * FROM candidates
        WHERE planet_score >= :min_score
        ORDER BY {PLANET_ORDER_SQL}
        LIMIT :limit OFFSET :offset
    """
    params.update({"limit": page_size, "offset": max(page - 1, 0) * page_size})
    return run_query(sql, params)


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def get_planet_years(topic):
    """Years that contain at least one curated image for a topic, newest first, with counts."""
    filter_sql, params = planet_topic_filter(topic)
    sql = f"""
        WITH candidates AS ({PLANET_CANDIDATES_SQL}{filter_sql})
        SELECT EXTRACT(YEAR FROM date)::integer AS year, COUNT(*) AS curated_images
        FROM candidates
        WHERE planet_score >= :min_score
        GROUP BY 1
        ORDER BY year DESC
    """
    return run_query(sql, params)


@st.cache_data(ttl=3600, max_entries=200, show_spinner=False)
def find_nearest_planet_date(topic, target_date, window_days=NEAREST_DATE_WINDOW_DAYS):
    """Closest other date within the window that has curated images for the SAME topic.

    PostgreSQL does the search: it only looks at dates inside the window, ranks them by
    distance from the target, and breaks ties by choosing the earlier date.
    Returns (date, curated image count), or None if nothing is close enough.
    """
    filter_sql, params = planet_topic_filter(topic)
    params.update({
        "target_date": target_date,
        "window_start": target_date - dt.timedelta(days=window_days),
        "window_end": target_date + dt.timedelta(days=window_days),
    })
    sql = f"""
        WITH candidates AS (
            {PLANET_CANDIDATES_SQL}{filter_sql}
              AND r.date BETWEEN :window_start AND :window_end
              AND r.date <> :target_date
        )
        SELECT date, COUNT(*) AS curated_images
        FROM candidates
        WHERE planet_score >= :min_score
        GROUP BY date
        ORDER BY ABS(date - CAST(:target_date AS DATE)), date
        LIMIT 1
    """
    nearest = run_query(sql, params)
    if nearest.empty:
        return None
    return nearest.iloc[0]["date"], int(nearest.iloc[0]["curated_images"])


def get_featured_images(limit=6):
    """Home-page highlights: the cover image of each of the largest topics."""
    summary = get_planet_topic_summary().dropna(subset=["cover_url"])
    largest = summary.sort_values("archive_images", ascending=False).head(limit)
    return largest.rename(columns={"cover_id": "source_id", "cover_title": "title",
                                   "cover_url": "image_url", "cover_date": "date"})


# ---------------------------------------------------------------------------
# Data Insights page (same definitions as notebooks/eda.ipynb)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_dataset_profile():
    """Return totals and date-quality counts used by the insight text."""
    sql = f"""
        SELECT COUNT(*) AS total_images,
               CURRENT_DATE AS analysis_date,
               MIN(r.date) FILTER (WHERE isfinite(r.date)) AS earliest_date,
               MAX(r.date) FILTER (WHERE isfinite(r.date) AND r.date <= CURRENT_DATE) AS historical_end,
               COUNT(*) FILTER (WHERE isfinite(r.date) AND r.date > CURRENT_DATE) AS future_dates,
               COUNT(*) FILTER (WHERE isfinite(r.date) AND r.date <= CURRENT_DATE) AS historical_images,
               COUNT(*) FILTER (WHERE r.title = 'Untitled NASA Image') AS placeholder_titles
        FROM nasa_records AS r
        WHERE {SCOPE_SQL}
    """
    return run_query(sql).iloc[0].to_dict()


@st.cache_data(ttl=3600, show_spinner=False)
def get_topic_counts():
    """Unique images per search topic (EDA Insight 1)."""
    sql = f"""
        SELECT m.search_keyword AS topic,
               COUNT(DISTINCT (r.source_api, r.source_id)) AS topic_matches
        FROM nasa_records AS r
        JOIN nasa_search_matches AS m
          ON r.source_api = m.source_api AND r.source_id = m.source_id
        WHERE {SCOPE_SQL}
        GROUP BY m.search_keyword
        ORDER BY topic_matches DESC, topic
    """
    return run_query(sql)


@st.cache_data(ttl=3600, show_spinner=False)
def get_annual_counts():
    """Unique images per year, excluding NULL, non-finite, and future dates (EDA Insight 2)."""
    sql = f"""
        SELECT EXTRACT(YEAR FROM r.date)::integer AS year, COUNT(*) AS unique_images
        FROM nasa_records AS r
        WHERE {SCOPE_SQL}
          AND r.date IS NOT NULL AND isfinite(r.date) AND r.date <= CURRENT_DATE
        GROUP BY EXTRACT(YEAR FROM r.date)::integer
        ORDER BY year
    """
    annual = run_query(sql)
    if annual.empty:
        return annual

    # Fill missing years with zero so the line does not hide coverage gaps.
    all_years = range(int(annual["year"].min()), int(annual["year"].max()) + 1)
    return (annual.set_index("year").reindex(all_years, fill_value=0)
            .rename_axis("year").reset_index())


@st.cache_data(ttl=3600, show_spinner=False)
def get_topic_pairs():
    """Shared unique images for each pair of topics (EDA Insight 3)."""
    sql = f"""
        WITH matches AS (
            SELECT DISTINCT m.source_api, m.source_id, m.search_keyword
            FROM nasa_search_matches AS m
            JOIN nasa_records AS r USING (source_api, source_id)
            WHERE {SCOPE_SQL}
        )
        SELECT a.search_keyword AS topic_a, b.search_keyword AS topic_b,
               COUNT(*) AS shared_images
        FROM matches AS a
        JOIN matches AS b
          ON a.source_api = b.source_api AND a.source_id = b.source_id
         AND a.search_keyword < b.search_keyword
        GROUP BY a.search_keyword, b.search_keyword
        ORDER BY shared_images DESC, topic_a, topic_b
    """
    return run_query(sql)


@st.cache_data(ttl=3600, show_spinner=False)
def get_topics_per_image():
    """How many images match 0, 1, 2, ... topics (EDA Insight 3)."""
    sql = f"""
        WITH topics_per_image AS (
            SELECT r.source_api, r.source_id, COUNT(DISTINCT m.search_keyword) AS topic_count
            FROM nasa_records AS r
            LEFT JOIN nasa_search_matches AS m USING (source_api, source_id)
            WHERE {SCOPE_SQL}
            GROUP BY r.source_api, r.source_id
        )
        SELECT topic_count, COUNT(*) AS unique_images
        FROM topics_per_image
        GROUP BY topic_count
        ORDER BY topic_count
    """
    return run_query(sql)


METADATA_FIELDS = {
    "title": "Title", "date": "Date", "image_url": "Image URL", "explanation": "Explanation",
    "credit": "Credit", "center": "Center", "location": "Location", "keywords": "Keywords",
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_metadata_completeness():
    """Available values per metadata field as a share of unique images (EDA Insight 4)."""
    sql = f"""
        SELECT COUNT(*) AS total_images,
               COUNT(*) FILTER (WHERE r.title ~ '[^[:space:]]') AS title,
               COUNT(*) FILTER (WHERE r.date IS NOT NULL AND isfinite(r.date)) AS date,
               COUNT(*) FILTER (WHERE r.image_url ~ '[^[:space:]]') AS image_url,
               COUNT(*) FILTER (WHERE r.explanation ~ '[^[:space:]]') AS explanation,
               COUNT(*) FILTER (WHERE r.credit ~ '[^[:space:]]') AS credit,
               COUNT(*) FILTER (WHERE r.center ~ '[^[:space:]]') AS center,
               COUNT(*) FILTER (WHERE r.location ~ '[^[:space:]]') AS location,
               COUNT(*) FILTER (WHERE CASE WHEN jsonb_typeof(r.keywords) = 'array' THEN
                   EXISTS (SELECT 1 FROM jsonb_array_elements(r.keywords) AS keyword(value)
                           WHERE jsonb_typeof(value) = 'string'
                             AND (value #>> '{{}}') ~ '[^[:space:]]')
                   ELSE FALSE END) AS keywords
        FROM nasa_records AS r
        WHERE {SCOPE_SQL}
    """
    counts = run_query(sql).iloc[0]
    total_images = int(counts["total_images"])

    summary = pd.DataFrame([
        {"field": label, "available": int(counts[column])}
        for column, label in METADATA_FIELDS.items()
    ])
    summary["missing"] = total_images - summary["available"]
    summary["completeness"] = summary["available"] / total_images * 100 if total_images else 0.0
    return summary.sort_values("completeness", ascending=False, kind="stable").reset_index(drop=True)
