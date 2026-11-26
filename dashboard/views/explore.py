"""Archive Search page: full metadata search over every stored NASA record.

Unlike the curated Planet Gallery, results here are every record that matched
a search topic in the NASA Image Library, including missions, events, and people.

Simple Search browses NASA's own era (1958 to today) by year, and the year list
only offers years that actually contain matching records. The Historical
Archive option keeps every stored date reachable, including the few records
dated before NASA existed and the few with future-dated metadata.
"""

import datetime as dt
import math

import streamlit as st

import data_access
from styles import page_header
from views.components import render_image_grid, render_pagination

ALL_YEARS = "All years (1958–today)"

DATE_NOTE = ("Dates reflect NASA's archived metadata and may differ from the date an image was "
             "originally captured.")
HISTORICAL_NOTE = ("NASA was established in 1958, but the archive may include older historical material. "
                   "Some early records may have limited metadata or unavailable image previews.")
NO_RESULTS = "No matching images were found for this date range. Try another year or reset your filters."


def default_filters():
    """Starting values for every filter widget.

    The custom range starts at NASA's first year and stops at today, which hides
    the few records with future-dated metadata (a known data-quality issue from
    the EDA). Users can widen it to see those records.
    """
    _, _, today = data_access.get_date_bounds()
    return {
        "filter_search": "",
        "filter_topics": [],
        "filter_centers": [],
        "filter_year": ALL_YEARS,
        "filter_custom_dates": False,
        "filter_dates": (dt.date(data_access.NASA_FIRST_YEAR, 1, 1), today),
        "filter_sort": "Newest first",
    }


def reset_filters():
    """Put every filter back to its default and return to page 1."""
    for key, value in default_filters().items():
        st.session_state[key] = value
    st.session_state.explore_page_number = 1


def show_pre_nasa_records():
    """Open the historical range: everything dated before 1958."""
    earliest, _, _ = data_access.get_date_bounds()
    st.session_state.filter_custom_dates = True
    st.session_state.filter_dates = (earliest, dt.date(data_access.NASA_FIRST_YEAR - 1, 12, 31))


def show_full_date_range():
    """Every stored date, including future-dated metadata."""
    earliest, latest, _ = data_access.get_date_bounds()
    st.session_state.filter_custom_dates = True
    st.session_state.filter_dates = (earliest, latest)


def year_label(year, year_sizes):
    if year == ALL_YEARS:
        return ALL_YEARS
    return f"{year} ({year_sizes[year]:,} images)"


def render_year_selector(column, search_text, topics, centers):
    """Year dropdown populated only with years that contain matching records."""
    years = data_access.get_archive_years(search_text, topics, centers)
    year_sizes = dict(zip(years["year"].astype(int), years["images"].astype(int)))
    options = [ALL_YEARS] + list(year_sizes)

    # A year chosen earlier may have no matches after the topic or center changes.
    if st.session_state.filter_year not in options:
        st.session_state.filter_year = ALL_YEARS

    column.selectbox(
        "Year",
        options=options,
        format_func=lambda year: year_label(year, year_sizes),
        key="filter_year",
        disabled=st.session_state.filter_custom_dates,
        help="Only years with matching records are listed. Use Historical Archive for exact dates.",
    )


def render_historical_filters():
    """Advanced options: a custom date range that reaches every stored date."""
    earliest, latest, _ = data_access.get_date_bounds()
    with st.expander("Historical Archive & custom dates",
                     expanded=st.session_state.filter_custom_dates, icon=":material/history_edu:"):
        st.markdown(f'<div class="date-note">{HISTORICAL_NOTE}</div>', unsafe_allow_html=True)
        st.toggle("Use a custom date range", key="filter_custom_dates",
                  help="Replaces the Year filter with exact start and end dates.")
        if st.session_state.filter_custom_dates:
            st.date_input(
                "Date range",
                key="filter_dates",
                min_value=earliest,
                max_value=latest,
                format="YYYY-MM-DD",
                help=f"Stored dates run from {earliest:%Y-%m-%d} to {latest:%Y-%m-%d}. A few records "
                     "have future-dated metadata; extend the end date to include them.",
            )
        left, right, _ = st.columns([1, 1, 2])
        left.button(f"Records before {data_access.NASA_FIRST_YEAR}", on_click=show_pre_nasa_records,
                    icon=":material/hourglass_top:", use_container_width=True)
        right.button("Every stored date", on_click=show_full_date_range,
                     icon=":material/date_range:", use_container_width=True)


def selected_date_range(today):
    """Start and end dates from either the custom range or the Year filter."""
    if st.session_state.filter_custom_dates:
        # While the user is still picking a range, the widget holds only one date.
        selected = st.session_state.filter_dates
        start_date = selected[0] if len(selected) > 0 else None
        end_date = selected[1] if len(selected) > 1 else None
        return start_date, end_date
    if st.session_state.filter_year == ALL_YEARS:
        return dt.date(data_access.NASA_FIRST_YEAR, 1, 1), today
    return data_access.year_bounds(st.session_state.filter_year, today)


def render_filters():
    """Draw the filter controls and return the selected values."""
    for key, value in default_filters().items():
        st.session_state.setdefault(key, value)

    topics = data_access.get_topics()
    topic_sizes = dict(zip(topics["topic"], topics["images"]))
    centers = data_access.get_centers()
    center_sizes = dict(zip(centers["center"], centers["images"]))
    _, _, today = data_access.get_date_bounds()

    with st.container(border=True, key="panel_archive_filters"):
        st.text_input(
            "Search",
            key="filter_search",
            placeholder="Search by title, description, or NASA ID (e.g. Curiosity, Saturn rings, PIA21000)",
        )
        topic_column, center_column, year_column, sort_column = st.columns([3, 3, 2.4, 2])
        topic_column.multiselect(
            "Search topics",
            options=list(topic_sizes),
            format_func=lambda topic: f"{topic.title()} ({topic_sizes[topic]:,})",
            key="filter_topics",
            placeholder="All topics",
        )
        center_column.multiselect(
            "NASA center",
            options=list(center_sizes),
            format_func=lambda center: f"{center} ({center_sizes[center]:,})",
            key="filter_centers",
            placeholder="All centers",
        )
        search_text = st.session_state.filter_search.strip()
        selected_topics = tuple(sorted(st.session_state.filter_topics))
        selected_centers = tuple(sorted(st.session_state.filter_centers))
        render_year_selector(year_column, search_text, selected_topics, selected_centers)
        sort_column.selectbox("Sort by", options=list(data_access.SORT_OPTIONS), key="filter_sort")

        render_historical_filters()
        st.button("Reset filters", on_click=reset_filters, icon=":material/restart_alt:")
        st.markdown(f'<div class="date-note">{DATE_NOTE}</div>', unsafe_allow_html=True)

    start_date, end_date = selected_date_range(today)
    return {
        "search_text": search_text,
        "topics": selected_topics,
        "centers": selected_centers,
        "start_date": start_date,
        "end_date": end_date,
    }


def describe_range(filters):
    start, end = filters["start_date"], filters["end_date"]
    if start and end:
        if start.year == end.year and start == dt.date(start.year, 1, 1):
            return f"in {start.year}"
        return f"from {start:%b %-d, %Y} to {end:%b %-d, %Y}"
    if start:
        return f"from {start:%b %-d, %Y}"
    return ""


def render():
    page_header(
        "Full archive",
        "Archive Search",
        "Search every stored NASA Image Library record by text, topic, center, and date. "
        "Results are based on NASA Image Library search-topic matches and may include missions, "
        "events, spacecraft, and related archival material. For curated planet imagery, use the "
        "Planet Gallery.",
    )

    filters = render_filters()
    sort = st.session_state.filter_sort

    # Go back to page 1 whenever the filters or sort order change.
    signature = (filters, sort)
    if st.session_state.get("explore_signature") != signature:
        st.session_state.explore_signature = signature
        st.session_state.explore_page_number = 1

    total_matches = data_access.count_images(**filters)
    if total_matches == 0:
        st.info(NO_RESULTS, icon=":material/search_off:")
        st.button("Reset filters", on_click=reset_filters, icon=":material/restart_alt:",
                  key="reset_after_empty")
        return

    total_pages = math.ceil(total_matches / data_access.PAGE_SIZE)
    page_number = min(max(st.session_state.get("explore_page_number", 1), 1), total_pages)
    st.session_state.explore_page_number = page_number

    first_shown = (page_number - 1) * data_access.PAGE_SIZE + 1
    last_shown = min(page_number * data_access.PAGE_SIZE, total_matches)
    noun = "image" if total_matches == 1 else "images"
    st.markdown(f"**{total_matches:,} matching {noun}** {describe_range(filters)} · "
                f"showing {first_shown:,}–{last_shown:,}")
    st.caption("Multiple topics or centers match any of the selections; different filters must all match.")

    images = data_access.search_images(**filters, sort=sort, page=page_number)
    render_image_grid(images, key_prefix="archive")
    render_pagination("explore_page_number", page_number, total_pages)
