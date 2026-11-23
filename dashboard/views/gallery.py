"""Planet Gallery page: curated planet and space imagery for each search topic.

Images are picked by the metadata score explained in data_access.py, so this
page favors planet portraits, surface views, and telescope images over
briefings and events. The full, unfiltered archive stays on Archive Search.
"""

import math

import streamlit as st

import data_access
from styles import hero_banner, page_header
from views.components import format_date, render_image_grid, render_pagination, thumbnail_html

DEFAULT_TOPIC = "mars"
TOPIC_BLURBS = {
    "mercury": "The innermost planet, mapped crater by crater by MESSENGER.",
    "venus": "Cloud-wrapped Venus and its radar-mapped volcanic plains.",
    "earth": "Our home planet seen from orbit, the Moon, and deep space.",
    "mars": "Rover landscapes, orbital surface views, dunes, and polar ice.",
    "jupiter": "Storms, cloud belts, rings, and moons of the largest planet.",
    "saturn": "Rings, moons, and storms, largely from the Cassini mission.",
    "uranus": "The tilted ice giant, from Voyager 2 to modern telescopes.",
    "neptune": "The windswept ice giant and its moon Triton.",
    "galaxy": "Spiral galaxies, clusters, and deep-sky telescope views.",
}


def select_topic(topic):
    st.session_state.gallery_topic = topic
    st.session_state.gallery_page_number = 1


def render_topic_picker(summary):
    """A row of round cover images, one per topic; the button selects that topic."""
    columns = st.columns(len(summary))
    for column, topic in zip(columns, summary.itertuples(index=False)):
        with column:
            is_selected = topic.topic == st.session_state.gallery_topic
            cover_class = "thumb cover active" if is_selected else "thumb cover"
            st.markdown(thumbnail_html(topic.cover_url, topic.cover_title, css_class=cover_class),
                        unsafe_allow_html=True)
            st.button(topic.topic.title(), key=f"topic_{topic.topic}", on_click=select_topic,
                      args=(topic.topic,), type="primary" if is_selected else "secondary",
                      use_container_width=True)


MODE_YEAR = "Explore by Year"
MODE_DATE = "Explore by Date"
ALL_YEARS = "All years"  # a real option; Streamlit shows None as "no selection"
DATE_NOTE = (
    "NASA Image Library records are not available for every planet on every day. Dates refer to "
    "stored NASA metadata and may differ from the actual capture date. If no images match your "
    "selected day, we'll show the closest available date when possible."
)


def clear_date_filter():
    st.session_state.gallery_date = None


def switch_to_year(year):
    """Used by the 'explore the full year' button after an empty date search."""
    st.session_state.gallery_mode = MODE_YEAR
    st.session_state.gallery_year = year


def render_date_controls(topic):
    """Mode switch plus either a year picker or a date picker. Returns (mode, year, date)."""
    st.session_state.setdefault("gallery_mode", MODE_YEAR)
    st.session_state.setdefault("gallery_year", ALL_YEARS)
    st.session_state.setdefault("gallery_date", None)

    # Only years that actually contain curated images for this topic, newest first.
    years = data_access.get_planet_years(topic)
    year_counts = dict(zip(years["year"].astype(int), years["curated_images"].astype(int)))
    if st.session_state.gallery_year not in year_counts:
        st.session_state.gallery_year = ALL_YEARS

    with st.container(border=True, key="panel_gallery_dates"):
        mode_column, picker_column, action_column = st.columns([2, 2, 1], vertical_alignment="bottom")
        mode = mode_column.radio("Explore mode", [MODE_YEAR, MODE_DATE], key="gallery_mode",
                                 horizontal=True)

        if mode == MODE_YEAR:
            picker_column.selectbox(
                "Year",
                options=[ALL_YEARS] + list(year_counts),
                key="gallery_year",
                format_func=lambda year: year if year == ALL_YEARS
                else f"{year} · {year_counts[year]:,} image{'s' if year_counts[year] != 1 else ''}",
            )
        else:
            earliest, _, today = data_access.get_date_bounds()
            picker_column.date_input("Metadata Date", key="gallery_date", min_value=earliest,
                                     max_value=today, format="YYYY-MM-DD")
            action_column.button("Clear date", on_click=clear_date_filter, icon=":material/event_busy:",
                                 use_container_width=True,
                                 disabled=st.session_state.gallery_date is None)
        st.markdown(f'<div class="date-note">{DATE_NOTE}</div>', unsafe_allow_html=True)

    chosen_year = st.session_state.gallery_year
    year = chosen_year if mode == MODE_YEAR and chosen_year != ALL_YEARS else None
    metadata_date = st.session_state.gallery_date if mode == MODE_DATE else None
    return mode, year, metadata_date


def resolve_date_selection(topic, selected_date):
    """Exact date first; otherwise the nearest curated date within the window.

    Returns (date_to_show or None, curated count, message kind). Results are never
    widened beyond the documented window.
    """
    curated, _ = data_access.count_planet_gallery(topic, selected_date)
    if curated:
        return selected_date, curated, "exact"
    nearest = data_access.find_nearest_planet_date(topic, selected_date)
    if nearest is None:
        return None, 0, "none_nearby"
    nearest_date, nearest_count = nearest
    return nearest_date, nearest_count, "fallback"


def render_fallback_notice(selected_date, shown_date, count, topic):
    days = (shown_date - selected_date).days
    direction = "after" if days > 0 else "before"
    st.info(
        f"No curated images were found for your selected date ({format_date(selected_date)}). "
        f"Here are the closest available images.\n\n"
        f"**Closest available date: {format_date(shown_date)} — {abs(days)} day{'s' if abs(days) != 1 else ''} "
        f"{direction} your selection.** Showing {count:,} curated {topic.title()} "
        f"image{'s' if count != 1 else ''} from that date.",
        icon=":material/event_repeat:",
    )


def render_no_nearby_notice(selected_date, topic):
    year = selected_date.year
    year_available = year in set(data_access.get_planet_years(topic)["year"].astype(int))
    st.warning(
        f"No curated images were found within {data_access.NEAREST_DATE_WINDOW_DAYS} days of your "
        f"selected date ({format_date(selected_date)}). Try exploring the full year instead.",
        icon=":material/event_busy:",
    )
    if year_available:
        st.button(f"Explore {topic.title()} in {year}", on_click=switch_to_year, args=(year,),
                  icon=":material/calendar_month:", type="primary")
    else:
        st.button(f"Explore all years for {topic.title()}", on_click=switch_to_year, args=(ALL_YEARS,),
                  icon=":material/calendar_month:", type="primary")
        st.caption(f"{topic.title()} has no curated images in {year}.")


def render_topic_note(topic, curated):
    """Explain when a topic has few or no strong planet-image matches."""
    if curated == 0:
        st.info(f"No records for {topic.title()} passed the planet-imagery check. "
                "Try **Archive Search** to browse every matching archive record.")
    elif curated < data_access.PAGE_SIZE:
        st.info(f"Only {curated} records for {topic.title()} passed the planet-imagery "
                "check, so they are all shown here. Archive Search has every matching record.")


def render_method_note():
    with st.expander("How are these images chosen?"):
        st.markdown(
            f"""
Each record gets a simple score from metadata already stored in PostgreSQL; records scoring
**{data_access.PLANET_MIN_SCORE} or more** appear here.

| Signal | Points |
|---|---|
| NASA ID starts with `PIA` (Planetary Photojournal science imagery) | +3 |
| Title names the topic, e.g. "Saturn" | +2 |
| Title or keywords use science-imagery words (crater, rings, nebula, rover, Hubble, …) | +2 |
| Title uses people or event words (briefing, ceremony, team, launch, testing, …) | −6 |
| Title suggests an illustration (artist, concept, diagram, …) | −2 |
| Center whose photos are mostly launch processing or events (KSC, HQ, MAF, SSC) | −2 |
| Title is only an ID code, e.g. "KSC-2011-5720" | −3 |

Images are ordered by score, with a stable shuffle among equal scores so one mission does not
fill the page. Records with future-dated metadata are excluded. This is a heuristic on text
metadata, not image recognition, so an occasional off-topic image can still appear.
"""
        )


def render():
    page_header(
        "Curated views",
        "Planet Gallery",
        "Planet portraits, surface views, and telescope imagery for each of our nine search topics, "
        "chosen from the archive with a transparent metadata score.",
    )

    summary = data_access.get_planet_topic_summary()
    if summary.empty:
        st.info("No topic data is available yet.")
        return

    topics = summary["topic"].tolist()
    if st.session_state.get("gallery_topic") not in topics:
        st.session_state.gallery_topic = DEFAULT_TOPIC if DEFAULT_TOPIC in topics else topics[0]
    st.session_state.setdefault("gallery_page_number", 1)

    render_topic_picker(summary)
    st.write("")
    topic = st.session_state.gallery_topic
    selected = summary.set_index("topic").loc[topic].to_dict()
    has_curated_images = int(selected["curated_images"]) > 0

    # Date controls sit right under the topic circles, above the topic banner.
    if has_curated_images:
        mode, year, selected_date = render_date_controls(topic)
    hero_banner(
        topic.title(),
        f"{TOPIC_BLURBS.get(topic, '')}<br>"
        f"<b>{int(selected['curated_images']):,}</b> curated images, selected from "
        f"{int(selected['archive_images']):,} archive matches.",
        image_url=selected["cover_url"] if isinstance(selected["cover_url"], str) else None,
        tag="Planet Gallery",
        compact=True,
    )
    if not has_curated_images:
        render_topic_note(topic, 0)
        render_method_note()
        return

    # Go back to page 1 whenever the topic, mode, year, or date changes.
    signature = (topic, mode, year, selected_date)
    if st.session_state.get("gallery_signature") != signature:
        st.session_state.gallery_signature = signature
        st.session_state.gallery_page_number = 1

    # Work out which images to show. Every path uses the same topic and score rules.
    shown_date = None
    if mode == MODE_DATE and selected_date is not None:
        shown_date, curated, outcome = resolve_date_selection(topic, selected_date)
        if outcome == "none_nearby":
            render_no_nearby_notice(selected_date, topic)
            render_method_note()
            return
        if outcome == "fallback":
            render_fallback_notice(selected_date, shown_date, curated, topic)
        else:
            st.markdown(f"**{curated:,} curated {topic.title()} image{'s' if curated != 1 else ''}** "
                        f"with metadata date {format_date(shown_date)}")
    elif year is not None:
        curated, _ = data_access.count_planet_gallery(topic, year=year)
        st.markdown(f"**{curated:,} curated {topic.title()} image{'s' if curated != 1 else ''}** "
                    f"with metadata dates in {year}")
    else:
        curated, _ = data_access.count_planet_gallery(topic)
        if mode == MODE_DATE:
            st.caption("Pick a date to narrow the gallery. Showing all dates for now.")
        render_topic_note(topic, curated)

    total_pages = math.ceil(curated / data_access.PAGE_SIZE)
    page_number = min(max(st.session_state.gallery_page_number, 1), total_pages)
    st.session_state.gallery_page_number = page_number

    images = data_access.get_planet_gallery(topic, page=page_number, metadata_date=shown_date, year=year)
    render_image_grid(images, key_prefix=f"planet_{topic}")
    if total_pages > 1:
        render_pagination("gallery_page_number", page_number, total_pages)
    render_method_note()
