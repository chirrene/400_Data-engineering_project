"""Archive Search page: full metadata search over every stored NASA record.

Unlike the curated Planet Gallery, results here are every record that matched
a search topic in the NASA Image Library, including missions, events, and people.
"""

import math

import streamlit as st

import data_access
from styles import page_header
from views.components import render_image_grid, render_pagination


def default_filters():
    """Starting values for every filter widget.

    The default date range stops at today, which hides the few records with
    future-dated metadata (a known data-quality issue from the EDA). Users can
    still extend the range to see them.
    """
    earliest, latest, today = data_access.get_date_bounds()
    return {
        "filter_search": "",
        "filter_topics": [],
        "filter_centers": [],
        "filter_dates": (earliest, min(latest, today)),
        "filter_sort": "Newest first",
    }


def reset_filters():
    """Put every filter back to its default and return to page 1."""
    for key, value in default_filters().items():
        st.session_state[key] = value
    st.session_state.explore_page_number = 1


def render_filters():
    """Draw the filter controls and return the selected values."""
    for key, value in default_filters().items():
        st.session_state.setdefault(key, value)

    topics = data_access.get_topics()
    topic_sizes = dict(zip(topics["topic"], topics["images"]))
    centers = data_access.get_centers()
    center_sizes = dict(zip(centers["center"], centers["images"]))
    earliest, latest, _ = data_access.get_date_bounds()

    with st.container(border=True, key="panel_archive_filters"):
        st.text_input(
            "Search",
            key="filter_search",
            placeholder="Search by title, description, or NASA ID (e.g. Curiosity, Saturn rings, PIA21000)",
        )
        topic_column, center_column, date_column, sort_column = st.columns([3, 3, 3, 2])
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
        date_column.date_input(
            "Date range",
            key="filter_dates",
            min_value=earliest,
            max_value=latest,
            format="YYYY-MM-DD",
            help="Defaults to today. A few records have future-dated metadata; "
                 "extend the end date to include them.",
        )
        sort_column.selectbox("Sort by", options=list(data_access.SORT_OPTIONS), key="filter_sort")
        st.button("Reset filters", on_click=reset_filters, icon=":material/restart_alt:")

    # While the user is still picking a range, the widget holds only one date.
    selected_dates = st.session_state.filter_dates
    start_date = selected_dates[0] if len(selected_dates) > 0 else None
    end_date = selected_dates[1] if len(selected_dates) > 1 else None

    return {
        "search_text": st.session_state.filter_search.strip(),
        "topics": tuple(sorted(st.session_state.filter_topics)),
        "centers": tuple(sorted(st.session_state.filter_centers)),
        "start_date": start_date,
        "end_date": end_date,
    }


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
        st.info("No images match these filters. Try a broader search or click **Reset filters**.")
        return

    total_pages = math.ceil(total_matches / data_access.PAGE_SIZE)
    page_number = min(max(st.session_state.get("explore_page_number", 1), 1), total_pages)
    st.session_state.explore_page_number = page_number

    first_shown = (page_number - 1) * data_access.PAGE_SIZE + 1
    last_shown = min(page_number * data_access.PAGE_SIZE, total_matches)
    st.markdown(f"**{total_matches:,} matching images** · showing {first_shown:,}–{last_shown:,}")
    st.caption("Multiple topics or centers match any of the selections; different filters must all match. "
               "Records with future-dated metadata are hidden unless you extend the date range.")

    images = data_access.search_images(**filters, sort=sort, page=page_number)
    render_image_grid(images, key_prefix="archive")
    render_pagination("explore_page_number", page_number, total_pages)
