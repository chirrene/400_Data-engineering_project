"""Building blocks shared by the gallery-style pages."""

from html import escape

import pandas as pd
import streamlit as st

GALLERY_COLUMNS = 4

# Shown when an image URL is missing or fails to load in the browser.
PREVIEW_UNAVAILABLE = "Image preview unavailable — view the original NASA record."


def has_text(value):
    """True when a value is a non-blank string."""
    return isinstance(value, str) and value.strip() != ""


def format_date(value):
    """Format a date like 'Mar 5, 2019', or return 'Date unavailable'."""
    if value is None or pd.isna(value):
        return "Date unavailable"
    timestamp = pd.Timestamp(value)
    return f"{timestamp:%b} {timestamp.day}, {timestamp.year}"


def thumbnail_html(image_url, title, css_class="thumb"):
    """Image tile with a text fallback that stays visible if the URL fails to load.

    The image sits on top of a 'preview unavailable' label. A broken image with
    an empty alt attribute renders as nothing, so the label shows through.
    The card title below the image already describes it.
    """
    if not has_text(image_url):
        return f'<div class="{css_class}"><span class="thumb-fallback">{PREVIEW_UNAVAILABLE}</span></div>'
    return (
        f'<div class="{css_class}"><span class="thumb-fallback">{PREVIEW_UNAVAILABLE}</span>'
        f'<img src="{escape(image_url, quote=True)}" alt="" title="{escape(title or "", quote=True)}" '
        'loading="lazy" referrerpolicy="no-referrer"></div>'
    )


def card_html(image_url, title, meta_lines, chip=None):
    """Thumbnail, an optional topic chip, a two-line title, and short metadata lines."""
    chip_html = f'<span class="topic-chip">{escape(chip)}</span>' if chip else ""
    meta = "".join(f'<div class="card-meta">{escape(line)}</div>' for line in meta_lines if line)
    return (
        thumbnail_html(image_url, title)
        + chip_html
        + f'<div class="card-title" title="{escape(title or "", quote=True)}">{escape(title or "Untitled")}</div>'
        + meta
    )


def optional(value):
    return value if has_text(value) else "Not available"


@st.dialog("Image details", width="large")
def show_image_details(image):
    """Full metadata for one image, with graceful fallbacks for missing fields."""
    st.markdown(thumbnail_html(image["image_url"], image["title"], css_class="thumb detail"),
                unsafe_allow_html=True)
    st.subheader(image["title"] or "Untitled")

    left, right = st.columns(2)
    left.markdown(f"**NASA ID:** `{image['source_id']}`")
    left.markdown(f"**Date:** {format_date(image['date'])}")
    left.markdown(f"**NASA center:** {optional(image['center'])}")
    right.markdown(f"**Credit:** {optional(image['credit'])}")
    right.markdown(f"**Location:** {optional(image['location'])}")
    # Archive rows carry every matched topic; Planet Gallery rows carry just the one being browsed.
    topics = image.get("topics") or ([image["topic"]] if has_text(image.get("topic")) else [])
    right.markdown(f"**Search topics:** {', '.join(t.title() for t in topics) if topics else 'None'}")

    keywords = [k for k in (image.get("keywords") or []) if has_text(k)]
    if keywords:
        st.markdown("**Keywords:** " + ", ".join(keywords))

    st.markdown("**Description**")
    if has_text(image["explanation"]):
        st.text(image["explanation"])
    else:
        st.caption("No description is available for this image.")

    if has_text(image["page_url"]):
        st.link_button("Open on NASA Image Library", image["page_url"], type="primary",
                       icon=":material/open_in_new:")


def render_image_grid(images, key_prefix, chip_column=None):
    """Show images as a grid of cards, each with a 'View details' button."""
    records = images.to_dict("records")
    for start in range(0, len(records), GALLERY_COLUMNS):
        columns = st.columns(GALLERY_COLUMNS)
        for column, image in zip(columns, records[start:start + GALLERY_COLUMNS]):
            with column.container(border=True, key=f"card_{key_prefix}_{image['source_id']}"):
                meta = [format_date(image["date"])]
                if has_text(image["credit"]):
                    meta.append(f"Credit: {image['credit']}")
                chip = image[chip_column].title() if chip_column else None
                st.markdown(card_html(image["image_url"], image["title"], meta, chip=chip),
                            unsafe_allow_html=True)
                if st.button("View details", key=f"details_{key_prefix}_{image['source_id']}",
                             use_container_width=True):
                    show_image_details(image)


def render_pagination(state_key, page_number, total_pages):
    """Previous / Next buttons that change st.session_state[state_key]."""

    def change_page(step):
        st.session_state[state_key] += step

    previous_column, label_column, next_column = st.columns([1, 2, 1])
    previous_column.button("← Previous", key=f"{state_key}_previous", on_click=change_page, args=(-1,),
                           disabled=page_number <= 1, use_container_width=True)
    label_column.markdown(
        f"<div class='muted' style='text-align:center;padding-top:0.45rem'>"
        f"Page {page_number:,} of {total_pages:,}</div>",
        unsafe_allow_html=True,
    )
    next_column.button("Next →", key=f"{state_key}_next", on_click=change_page, args=(1,), type="primary",
                       disabled=page_number >= total_pages, use_container_width=True)
