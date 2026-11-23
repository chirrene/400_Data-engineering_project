"""Data Insights page: the four EDA analyses as interactive Plotly charts.

The SQL behind each chart matches notebooks/eda.ipynb (see data_access.py).
Findings are computed from the live query results, not typed in by hand.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_access
from styles import page_header

# Light "Starlight Observatory" palette, close to the EDA notebook's navy/blue (presentation only).
TEXT = "#17324D"
MUTED = "#60758A"
BLUE = "#4A93C6"
PEAK = "#17324D"
GOLD = "#D8BA83"
GRID = "#E6EEF5"
CHART_CONFIG = {"displaylogo": False, "scrollZoom": False}


def style_figure(figure, title, subtitle, height):
    """Apply the shared title, font, and background settings."""
    figure.update_layout(
        title=dict(text=f"<b>{title}</b><br><sup>{subtitle}</sup>", x=0, xanchor="left",
                   font=dict(size=18, color=TEXT)),
        font=dict(family="'Source Sans Pro', 'Source Sans 3', sans-serif", size=13, color=MUTED),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=height, showlegend=False,
        margin=dict(l=90, r=70, t=95, b=60),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#BFD9EC", font=dict(size=13, color=TEXT)),
    )
    figure.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    figure.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return figure


def show_chart(figure):
    st.plotly_chart(figure, use_container_width=True, theme=None, config=CHART_CONFIG)


def show_notes(section, key_finding, interpretation):
    """Key finding and interpretation underneath each chart."""
    finding_column, note_column = st.columns(2)
    with finding_column.container(border=True, key=f"finding_{section}"):
        st.markdown(f":material/lightbulb: **Key Finding**  \n{key_finding}")
    with note_column.container(border=True, key=f"note_{section}"):
        st.markdown(f":material/info: **Interpretation & Limitation**  \n{interpretation}")


def section_title(number, title):
    st.markdown(f'<div class="eyebrow">Insight {number}</div>', unsafe_allow_html=True)
    st.subheader(title)


# ---------------------------------------------------------------------------
# Insight 1: Topic distribution
# ---------------------------------------------------------------------------

def render_topic_distribution(topic_counts, total_relationships):
    section_title(1, "Image Distribution by Search Topic")
    topic_counts = topic_counts.assign(
        label=topic_counts["topic"].str.title(),
        share=topic_counts["topic_matches"] / total_relationships * 100,
    )

    figure = go.Figure(go.Bar(
        x=topic_counts["topic_matches"], y=topic_counts["label"], orientation="h",
        marker_color=BLUE, text=topic_counts["topic_matches"], texttemplate="%{x:,}",
        textposition="outside", cliponaxis=False, customdata=topic_counts[["share"]],
        hovertemplate="<b>%{y}</b><br>Matches: %{x:,}<br>Share of all matches: "
                      "%{customdata[0]:.1f}%<extra></extra>",
    ))
    style_figure(figure, "Image–topic matches by search topic",
                 "Keyword-search relationships · one image can match several topics", 480)
    figure.update_yaxes(autorange="reversed", title="Search topic", showgrid=False)
    figure.update_xaxes(title="Image–topic matches", tickformat=",d",
                        range=[0, topic_counts["topic_matches"].max() * 1.18])
    show_chart(figure)

    first, second, last = topic_counts.iloc[0], topic_counts.iloc[1], topic_counts.iloc[-1]
    top_two_share = first["share"] + second["share"]
    show_notes(
        1,
        f"**{first['label']}** has the most topic matches (**{first['topic_matches']:,}**), followed by "
        f"**{second['label']}** (**{second['topic_matches']:,}**). Together they account for "
        f"**{top_two_share:.1f}%** of all {total_relationships:,} topic relationships, while "
        f"**{last['label']}** has the fewest (**{last['topic_matches']:,}**).",
        "The collection is heavily concentrated on two topics, so topic comparisons are uneven. "
        "These counts reflect NASA keyword-search results, not how many photographs NASA took of each "
        "planet, and results can include missions, launches, and spacecraft. Because images can match "
        "several topics, the bars add up to more than the number of unique images.",
    )


# ---------------------------------------------------------------------------
# Insight 2: Historical distribution
# ---------------------------------------------------------------------------

def render_historical_distribution(annual_counts, profile):
    section_title(2, "Historical Image Distribution")
    if annual_counts.empty:
        st.info("No dated images are available for the historical trend.")
        return

    analysis_date = pd.Timestamp(profile["analysis_date"])
    historical_total = int(annual_counts["unique_images"].sum())
    annual_counts = annual_counts.assign(share=annual_counts["unique_images"] / historical_total * 100)
    first_year = int(annual_counts["year"].min())
    last_year = int(annual_counts["year"].max())
    peak = annual_counts.sort_values(["unique_images", "year"], ascending=[False, True]).iloc[0]

    figure = go.Figure(go.Scatter(
        x=annual_counts["year"], y=annual_counts["unique_images"], mode="lines",
        line=dict(color=BLUE, width=2.5), fill="tozeroy", fillcolor="rgba(74,147,198,0.14)",
        customdata=annual_counts[["share"]],
        hovertemplate="<b>%{x}</b><br>Unique images: %{y:,}<br>Share: %{customdata[0]:.1f}%<extra></extra>",
    ))
    figure.add_scatter(x=[peak["year"]], y=[peak["unique_images"]], mode="markers",
                       marker=dict(color=PEAK, size=9, line=dict(color=GOLD, width=2)), hoverinfo="skip")
    figure.add_annotation(x=peak["year"], y=peak["unique_images"],
                          text=f"Peak {int(peak['year'])}: {int(peak['unique_images']):,} images",
                          showarrow=True, arrowhead=0, arrowcolor=BLUE, ax=-60, ay=-30,
                          bgcolor="#FFFFFF", bordercolor=GOLD, font=dict(color=TEXT))
    style_figure(
        figure, "Unique images by metadata year",
        f"Future-dated records excluded · cutoff {analysis_date:%Y-%m-%d} · "
        f"{last_year} is a partial year", 500,
    )

    # Fixed decade ticks plus the latest included year, so the end of the trend is explicit.
    tick_years = [year for year in range(1920, last_year, 20) if year >= first_year and last_year - year >= 5]
    figure.update_xaxes(title="Metadata year", tickmode="array", tickvals=tick_years + [last_year],
                        tickformat="d", range=[first_year - 1, last_year + 1],
                        rangeslider=dict(visible=True, thickness=0.1))
    figure.update_yaxes(title="Unique images", tickformat=",d", rangemode="tozero")
    show_chart(figure)

    recent_share = annual_counts.loc[annual_counts["year"] >= 2000, "unique_images"].sum() / historical_total * 100
    future_dates = int(profile["future_dates"])
    show_notes(
        2,
        f"The trend covers **{historical_total:,} unique images** dated {first_year}–{last_year}. "
        f"The largest year is **{int(peak['year'])}** with **{int(peak['unique_images']):,} images "
        f"({peak['share']:.1f}%)**, and **{recent_share:.1f}%** of records are dated 2000 or later.",
        f"Coverage is much stronger for recent decades. This reflects mission coverage, archiving, and "
        f"our keyword searches, not necessarily how many photos NASA took each year. {last_year} is "
        f"incomplete, and **{future_dates} future-dated records** are excluded from this chart but kept "
        f"unchanged in the database.",
    )


# ---------------------------------------------------------------------------
# Insight 3: Topic overlap
# ---------------------------------------------------------------------------

def build_overlap_matrix(topic_counts, topic_pairs):
    """Symmetric topic-by-topic matrix: totals on the diagonal, shared images elsewhere."""
    topic_order = topic_counts["topic"].tolist()
    matrix = pd.DataFrame(0, index=topic_order, columns=topic_order, dtype="int64")
    for row in topic_counts.itertuples(index=False):
        matrix.loc[row.topic, row.topic] = int(row.topic_matches)
    for row in topic_pairs.itertuples(index=False):
        matrix.loc[row.topic_a, row.topic_b] = int(row.shared_images)
        matrix.loc[row.topic_b, row.topic_a] = int(row.shared_images)
    return matrix


def render_topic_overlap(topic_counts, topic_pairs, topics_per_image, total_images):
    section_title(3, "Topic Overlap")
    matrix = build_overlap_matrix(topic_counts, topic_pairs)
    topics = matrix.index.tolist()
    labels = [topic.title() for topic in topics]

    # Two layers: blue cells for shared images, gray diagonal for each topic's own total.
    shared_values = [[None if a == b else int(matrix.loc[a, b]) for b in topics] for a in topics]
    diagonal_values = [[int(matrix.loc[a, b]) if a == b else None for b in topics] for a in topics]
    max_shared = int(topic_pairs["shared_images"].max()) if not topic_pairs.empty else 1

    figure = go.Figure()
    figure.add_trace(go.Heatmap(
        z=shared_values, x=labels, y=labels, zmin=0, zmax=max(1, max_shared),
        colorscale=[[0, "#F3F7FB"], [0.45, "#A9CBE3"], [1, "#4A93C6"]],
        texttemplate="%{z:,}", textfont=dict(size=11, color=TEXT), xgap=3, ygap=3, hoverongaps=False,
        colorbar=dict(title="Shared images", tickformat=",d", thickness=14, len=0.75),
        hovertemplate="<b>%{y} / %{x}</b><br>Shared unique images: %{z:,}<extra></extra>",
    ))
    figure.add_trace(go.Heatmap(
        z=diagonal_values, x=labels, y=labels, colorscale=[[0, "#E3E8EE"], [1, "#E3E8EE"]],
        showscale=False, texttemplate="%{z:,}", textfont=dict(size=11, color=TEXT),
        xgap=3, ygap=3, hoverongaps=False,
        hovertemplate="<b>%{y}</b><br>Topic total: %{z:,}<extra></extra>",
    ))
    style_figure(figure, "Which search topics share images?",
                 "Gray diagonal = topic totals · blue cells = shared unique images", 600)
    figure.update_xaxes(title="Search topic", showgrid=False)
    figure.update_yaxes(title="Search topic", autorange="reversed", showgrid=False)
    figure.update_layout(margin=dict(l=100, r=110, t=95, b=70))
    show_chart(figure)

    multi_topic_images = int(topics_per_image.loc[topics_per_image["topic_count"] >= 2, "unique_images"].sum())
    multi_topic_share = multi_topic_images / total_images * 100
    if topic_pairs.empty:
        pair_text = "No pair of topics shares an image."
    else:
        top_pair = topic_pairs.iloc[0]
        size_a = int(matrix.loc[top_pair["topic_a"], top_pair["topic_a"]])
        size_b = int(matrix.loc[top_pair["topic_b"], top_pair["topic_b"]])
        shared = int(top_pair["shared_images"])
        smaller_topic = top_pair["topic_a"] if size_a <= size_b else top_pair["topic_b"]
        smaller_share = shared / min(size_a, size_b) * 100
        jaccard = shared / (size_a + size_b - shared) * 100
        pair_text = (
            f"**{top_pair['topic_a'].title()} and {top_pair['topic_b'].title()}** share the most images "
            f"(**{shared:,}**), but that is only **{smaller_share:.1f}%** of {smaller_topic.title()} "
            f"records and a **{jaccard:.1f}% Jaccard** overlap."
        )
    show_notes(
        3,
        f"**{multi_topic_images:,} unique images ({multi_topic_share:.1f}%)** match two or more search "
        f"topics, so most images belong to a single topic. {pair_text}",
        "Overlap comes from NASA keyword search, not the visual content of the image: a shared label "
        "does not mean a photo shows both planets. This is why Archive Search counts each NASA ID "
        "once even when several selected topics match it.",
    )


# ---------------------------------------------------------------------------
# Insight 4: Metadata completeness
# ---------------------------------------------------------------------------

def render_metadata_completeness(completeness, profile):
    section_title(4, "Metadata Completeness")
    figure = go.Figure(go.Bar(
        x=completeness["completeness"], y=completeness["field"], orientation="h",
        marker_color=BLUE, text=completeness["completeness"], texttemplate="%{text:.2f}%",
        textposition="outside", cliponaxis=False,
        customdata=completeness[["available", "missing"]],
        hovertemplate="<b>%{y}</b><br>Available: %{customdata[0]:,}<br>Missing: %{customdata[1]:,}"
                      "<br>Completeness: %{x:.2f}%<extra></extra>",
    ))
    style_figure(figure, "Stored metadata availability",
                 "Non-missing values as a percentage of unique images", 460)
    figure.update_xaxes(title="Completeness (% of unique images)", range=[0, 100],
                        ticksuffix="%", dtick=20)
    figure.update_yaxes(title="Metadata field", autorange="reversed", showgrid=False)
    figure.update_layout(margin=dict(l=110, r=110, t=95, b=60))
    show_chart(figure)

    by_field = completeness.set_index("field")
    full_fields = completeness.loc[completeness["completeness"] >= 100, "field"].tolist()
    lowest = completeness.iloc[-1]
    second_lowest = completeness.iloc[-2]
    if len(full_fields) > 1:
        full_text = f"**{', '.join(full_fields[:-1])}, and {full_fields[-1]}** are **100% complete**. "
    elif full_fields:
        full_text = f"**{full_fields[0]}** is **100% complete**. "
    else:
        full_text = ""
    show_notes(
        4,
        f"{full_text}**{lowest['field']}** is the least complete at **{lowest['completeness']:.2f}%** "
        f"({lowest['available']:,} records), followed by {second_lowest['field']} at "
        f"**{second_lowest['completeness']:.2f}%**. Usable keywords exist for "
        f"**{by_field.loc['Keywords', 'completeness']:.2f}%** of images.",
        f"Core fields are reliable, but optional details are often missing, so the gallery and search pages show "
        f"'Not available' instead of blanks. Complete is not the same as accurate: there are "
        f"**{int(profile['placeholder_titles'])} placeholder titles** and "
        f"**{int(profile['future_dates'])} future-dated records**, and a stored image URL is not "
        f"guaranteed to load.",
    )


def render():
    page_header(
        "Exploratory data analysis",
        "Data Insights",
        "Four analyses from our EDA notebook, recalculated live with read-only SQL. "
        "Unique images (one per NASA ID) and image–topic relationships are counted separately.",
    )

    with st.spinner("Running aggregations in PostgreSQL..."):
        profile = data_access.get_dataset_profile()
        kpis = data_access.get_kpis()
        topic_counts = data_access.get_topic_counts()
        annual_counts = data_access.get_annual_counts()
        topic_pairs = data_access.get_topic_pairs()
        topics_per_image = data_access.get_topics_per_image()
        completeness = data_access.get_metadata_completeness()

    if topic_counts.empty:
        st.info("No topic data is available yet.")
        return

    # Each insight sits in its own panel: chart first, then the finding and its limitation.
    sections = [
        lambda: render_topic_distribution(topic_counts, kpis["total_relationships"]),
        lambda: render_historical_distribution(annual_counts, profile),
        lambda: render_topic_overlap(topic_counts, topic_pairs, topics_per_image, kpis["total_images"]),
        lambda: render_metadata_completeness(completeness, profile),
    ]
    for number, render_section in enumerate(sections, start=1):
        with st.container(border=True, key=f"panel_insight_{number}"):
            render_section()
        st.write("")
