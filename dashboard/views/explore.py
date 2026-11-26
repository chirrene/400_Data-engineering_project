"""Archive Search page: full metadata search over every stored NASA record.

Unlike the curated Planet Gallery, results here are every record that matched
a search topic in the NASA Image Library, including missions, events, and people.

The main row holds the controls most visitors need: search, year, sort, and
reset. Everything else (topics, centers, a custom date range, and the
historical records dated before 1958) sits in a collapsed "More filters" section.

Only one date filter is ever active:

* Year (default): a dropdown of years (1958 to today) that actually contain
  records matching the other filters, each with its image count.
* Custom date range: exact start and end dates, reaching every stored date,
  including the few records dated before NASA existed. While it is active the
  year dropdown shows "Custom date range", and picking a year switches back.
"""

import datetime as dt
import math
from html import escape

import streamlit as st

import data_access
from styles import page_header
from views.components import render_image_grid, render_pagination

MODE_YEAR = "By year"
MODE_RANGE = "Date range"
ALL_YEARS = "All years (1958–today)"
CUSTOM_RANGE = "Custom date range"

INTRO = ("Explore NASA's full image collection — from space missions and rocket launches to "
         "historic moments.")
DATE_NOTE = ("Dates reflect NASA's archived metadata and may differ from the date an image was "
             "originally captured.")
HISTORICAL_NOTE = ("NASA was established in 1958, but our collection includes some earlier historical "
                   "records. Dates reflect archived metadata and may not represent when a photo was taken.")
NO_RESULTS = "No images match this date range. Try another year or reset your filters."
FILTER_KEYS = ("filter_topics", "filter_centers")


def default_filters():
    """Starting values for every filter.

    The year filter starts at "All years", which covers NASA's first year up to
    today. That hides the few records with future-dated metadata (a known
    data-quality issue from the EDA); the custom date range can reach them.
    """
    _, _, today = data_access.get_date_bounds()
    return {
        "filter_search": "",
        "filter_topics": [],
        "filter_centers": [],
        "filter_date_mode": MODE_YEAR,
        "filter_year": ALL_YEARS,
        "filter_dates": (dt.date(data_access.NASA_FIRST_YEAR, 1, 1), today),
        "filter_sort": "Newest first",
    }


def reset_filters():
    """Put every filter back to its default and return to page 1."""
    for key, value in default_filters().items():
        st.session_state[key] = value
    st.session_state.explore_page_number = 1


def use_year_filter():
    """Picking a year (or All years) makes the year the active date filter."""
    if st.session_state.filter_year != CUSTOM_RANGE:
        st.session_state.filter_date_mode = MODE_YEAR


def use_date_range():
    """Editing the custom dates makes the range the active date filter."""
    st.session_state.filter_date_mode = MODE_RANGE
    st.session_state.filter_year = CUSTOM_RANGE


def show_historical_records():
    """One click: every record dated before 1958, oldest first, with no other filters."""
    earliest, _, _ = data_access.get_date_bounds()
    reset_filters()
    st.session_state.filter_dates = (earliest, dt.date(data_access.NASA_FIRST_YEAR - 1, 12, 31))
    st.session_state.filter_sort = "Oldest first"
    use_date_range()


def show_full_date_range():
    """Every stored date, including future-dated metadata."""
    earliest, latest, _ = data_access.get_date_bounds()
    st.session_state.filter_dates = (earliest, latest)
    use_date_range()


# Kept under its earlier name for callers and tests.
show_pre_nasa_records = show_historical_records


def pre_nasa_count():
    """Number of stored records dated before 1958, and the earliest stored date."""
    earliest, _, _ = data_access.get_date_bounds()
    count = data_access.count_images(start_date=earliest,
                                     end_date=dt.date(data_access.NASA_FIRST_YEAR - 1, 12, 31))
    return count, earliest


def year_label(year, year_sizes):
    if year in (ALL_YEARS, CUSTOM_RANGE):
        return year
    count = year_sizes[year]
    return f"{year} — {count:,} image{'' if count == 1 else 's'}"


def render_year_selector(column, search_text, topics, centers):
    """Year dropdown listing only years with records that match the other filters."""
    years = data_access.get_archive_years(search_text, topics, centers)
    year_sizes = dict(zip(years["year"].astype(int), years["images"].astype(int)))
    options = [ALL_YEARS] + list(year_sizes)
    if st.session_state.filter_date_mode == MODE_RANGE:
        options = [CUSTOM_RANGE] + options
        st.session_state.filter_year = CUSTOM_RANGE
    elif st.session_state.filter_year not in options:
        # A year chosen earlier may have no matches after the search, topic, or center changes.
        st.session_state.filter_year = ALL_YEARS

    column.selectbox(
        "Year",
        options=options,
        format_func=lambda year: year_label(year, year_sizes),
        key="filter_year",
        on_change=use_year_filter,
        help="Only years with matching records are listed, with their image counts. " + DATE_NOTE,
    )


def more_filters_label():
    active = len(st.session_state.filter_topics) + len(st.session_state.filter_centers)
    active += st.session_state.filter_date_mode == MODE_RANGE
    return f"More filters ({active} active)" if active else "More filters"


def render_more_filters(topic_sizes, center_sizes):
    """Topics, centers, custom dates, and historical records, collapsed by default."""
    earliest, latest, _ = data_access.get_date_bounds()
    historical_count, _ = pre_nasa_count()
    with st.expander(more_filters_label(), icon=":material/tune:"):
        topic_column, center_column = st.columns(2)
        topic_column.multiselect(
            "Search topics",
            options=list(topic_sizes),
            format_func=lambda topic: f"{topic.title()} ({topic_sizes[topic]:,})",
            key="filter_topics",
            placeholder="All topics",
            help="Records matching any of the selected topics.",
        )
        center_column.multiselect(
            "NASA center",
            options=list(center_sizes),
            format_func=lambda center: f"{center} ({center_sizes[center]:,})",
            key="filter_centers",
            placeholder="All centers",
            help="Records from any of the selected centers.",
        )

        range_active = st.session_state.filter_date_mode == MODE_RANGE
        st.date_input(
            "Custom date range" + (" (active)" if range_active else ""),
            key="filter_dates",
            min_value=earliest,
            max_value=latest,
            format="YYYY-MM-DD",
            on_change=use_date_range,
            help=f"Stored dates run from {earliest:%Y-%m-%d} to {latest:%Y-%m-%d}. " + DATE_NOTE,
        )
        st.caption("In use instead of the year filter. Pick a year above to switch back."
                   if range_active else "Pick start and end dates to use them instead of the year filter.")

        st.markdown(f'<div class="filter-group-label">Historical Records — {historical_count:,} '
                    f'records before {data_access.NASA_FIRST_YEAR}</div>', unsafe_allow_html=True)
        st.caption(HISTORICAL_NOTE)
        left, right = st.columns(2)
        left.button(f"Show the {historical_count:,} records before {data_access.NASA_FIRST_YEAR}",
                    key="show_historical", on_click=show_historical_records,
                    icon=":material/history_edu:", use_container_width=True,
                    help="Clears other filters and lists them oldest first.")
        right.button("Show every stored date", key="show_all_dates", on_click=show_full_date_range,
                     icon=":material/date_range:", use_container_width=True)


def selected_date_range(today):
    """Start and end dates from whichever date filter is active."""
    if st.session_state.filter_date_mode == MODE_RANGE:
        # While the user is still picking a range, the widget holds only one date.
        selected = st.session_state.filter_dates
        start_date = selected[0] if len(selected) > 0 else None
        end_date = selected[1] if len(selected) > 1 else None
        return start_date, end_date
    if st.session_state.filter_year in (ALL_YEARS, CUSTOM_RANGE):
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

    search_text = st.session_state.filter_search.strip()
    selected_topics = tuple(sorted(st.session_state.filter_topics))
    selected_centers = tuple(sorted(st.session_state.filter_centers))

    with st.container(border=True, key="panel_archive_filters"):
        search_column, year_column, sort_column, reset_column = st.columns(
            [3.2, 1.7, 1.2, 0.9], vertical_alignment="bottom")
        search_column.text_input(
            "Search",
            key="filter_search",
            placeholder="Try Orion, Apollo 11, Saturn rings, or a NASA ID",
        )
        render_year_selector(year_column, search_text, selected_topics, selected_centers)
        sort_column.selectbox("Sort by", options=list(data_access.SORT_OPTIONS), key="filter_sort")
        reset_column.button("Reset", on_click=reset_filters, icon=":material/restart_alt:",
                            use_container_width=True, key="reset_filters")
        render_more_filters(topic_sizes, center_sizes)

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


def result_count_html(total, filters, first_shown, last_shown):
    noun = "image" if total == 1 else "images"
    return (f'<div class="result-count"><span class="num">{total:,}</span> matching {noun} '
            f'<span class="range">{escape(describe_range(filters))}</span>'
            f'<span class="showing">Showing {first_shown:,}–{last_shown:,}</span></div>')


def render(gallery_page=None):
    page_header("Full archive", "Archive Search", INTRO)
    if gallery_page is not None:
        st.page_link(gallery_page, label="Planet images? Open the Planet Gallery",
                     icon=":material/public:")

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
    st.markdown(result_count_html(total_matches, filters, first_shown, last_shown), unsafe_allow_html=True)

    images = data_access.search_images(**filters, sort=sort, page=page_number)
    render_image_grid(images, key_prefix="archive")
    render_pagination("explore_page_number", page_number, total_pages)
