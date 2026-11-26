"""Home / Overview page."""

import streamlit as st

import data_access
from styles import hero_banner
from views.components import card_html, format_date

PIPELINE_STEPS = [
    ("NASA API", "Search the NASA Image and Video Library API for nine planet and space topics."),
    ("Processing", "Flatten API responses and normalize titles, dates, descriptions, and keywords."),
    ("Data Quality", "Validate required fields and dates, detect duplicate NASA IDs, and report issues."),
    ("PostgreSQL", "Load unique images and image–topic relationships into two related tables."),
    ("Streamlit", "Query PostgreSQL directly to power the gallery, search, and charts."),
]


def render_kpi(column, label, value, note):
    column.markdown(
        f"""<div class="kpi-card">
              <div class="kpi-label">{label}</div>
              <div class="kpi-value">{value:,}</div>
              <div class="kpi-note">{note}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def render_destination(column, page, title, text, key):
    """A card that describes one page and links to it."""
    with column.container(border=True, key=f"panel_{key}"):
        st.markdown(f"#### {title}")
        st.markdown(f"<span class='muted'>{text}</span>", unsafe_allow_html=True)
        st.page_link(page, label=f"Open {title}", icon=":material/arrow_forward:")


def render(gallery_page, archive_page, insights_page):
    featured = data_access.get_featured_images(limit=6)

    # The hero uses a real image from the database (the Galaxy cover when available).
    hero_image = None
    if not featured.empty:
        galaxy = featured.loc[featured["topic"] == "galaxy", "image_url"]
        hero_image = galaxy.iloc[0] if not galaxy.empty else featured["image_url"].iloc[0]
    hero_banner(
        "NASA Space Explorer",
        "Browse tens of thousands of images from the NASA Image and Video Library, collected, "
        "cleaned, and validated by our data pipeline and served live from PostgreSQL.",
        image_url=hero_image,
        tag="Northwestern MLDS 400 · Data Engineering",
        animated=True,
    )

    # KPI counts come straight from PostgreSQL.
    kpis = data_access.get_kpis()
    kpi_columns = st.columns(3)
    render_kpi(kpi_columns[0], "Unique Images", kpis["total_images"], "One row per NASA ID in nasa_records")
    render_kpi(kpi_columns[1], "Topic Relationships", kpis["total_relationships"],
               "Image–topic links; one image can match several topics")
    render_kpi(kpi_columns[2], "Search Topics", kpis["total_topics"], "Keywords used to search the NASA API")

    st.write("")
    st.markdown('<div class="eyebrow">Start exploring</div>', unsafe_allow_html=True)
    destination_columns = st.columns(3)
    render_destination(destination_columns[0], gallery_page, "Planet Gallery",
                       "Curated planet portraits, surface views, and telescope images for each topic.",
                       "dest_gallery")
    render_destination(destination_columns[1], archive_page, "Archive Search",
                       "Search every stored record by text, topic, NASA center, and date.",
                       "dest_archive")
    render_destination(destination_columns[2], insights_page, "Data Insights",
                       "Three findings: the 2014 peak, what NASA centers document, and the most documented missions.",
                       "dest_insights")

    # A few highlights from the Planet Gallery.
    st.write("")
    st.markdown('<div class="eyebrow">Featured</div>', unsafe_allow_html=True)
    st.subheader("Highlights from the Planet Gallery")
    if featured.empty:
        st.info("No images are available to feature right now.")
    else:
        gallery_columns = st.columns(len(featured))
        for column, image in zip(gallery_columns, featured.itertuples(index=False)):
            column.markdown(
                card_html(image.image_url, image.title, [format_date(image.date)], chip=image.topic.title()),
                unsafe_allow_html=True,
            )

    # How the data got here.
    st.write("")
    st.markdown('<div class="eyebrow">Under the hood</div>', unsafe_allow_html=True)
    st.subheader("Our Data Engineering Pipeline")
    arrow = '<span class="arrow">→</span>'
    st.markdown(
        '<div class="pipeline">'
        + arrow.join(f'<span class="step">{step}</span>' for step, _ in PIPELINE_STEPS)
        + "</div>",
        unsafe_allow_html=True,
    )
    for column, (step, description) in zip(st.columns(len(PIPELINE_STEPS)), PIPELINE_STEPS):
        column.markdown(f"**{step}**  \n<span class='muted'>{description}</span>",
                        unsafe_allow_html=True)
