"""Data Insights page: three findings, each told with one chart and one paragraph.

1. The 2014 surge: a yearly overview, then Kennedy's Earth-topic records, 2013 vs. 2014.
2. Where the records come from: the top NASA centers and what each one covers.
3. Which missions appear most often in the records.

The full analysis (method, tables, manual review, sources) lives in
notebooks/eda.ipynb. Every number here comes from live, read-only SQL in
data_access.py that uses the same definitions (dashboard/analysis_rules.py).
"""

import plotly.graph_objects as go
import streamlit as st

import analysis_rules as rules
import data_access
from styles import page_header

# "Starlight Observatory" chart palette: navy highlight, muted blue data, gold accent.
TEXT = "#17324D"
MUTED = "#60758A"
NAVY = "#17324D"
BLUE = "#4A93C6"
LIGHT_BLUE = "#BFD8EA"
GOLD = "#C9A86A"
GRID = "#E6EEF5"
FONT = "'Source Sans Pro', 'Source Sans 3', sans-serif"
# No Plotly toolbar: the charts should read cleanly on a projector.
CHART_CONFIG = {"displayModeBar": False, "scrollZoom": False, "responsive": True}

# Short labels keep the chart readable on small screens; hover shows the full name.
CENTER_SHORT = {"KSC": "Kennedy (KSC)", "JPL": "JPL", "JSC": "Johnson (JSC)", "HQ": "Headquarters (HQ)",
                "GSFC": "Goddard (GSFC)", "MSFC": "Marshall (MSFC)"}
CENTER_NAMES = {
    "KSC": "Kennedy Space Center",
    "JPL": "Jet Propulsion Laboratory",
    "JSC": "Johnson Space Center",
    "HQ": "NASA Headquarters",
    "GSFC": "Goddard Space Flight Center",
    "MSFC": "Marshall Space Flight Center",
    "MAF": "Michoud Assembly Facility",
    "ARC": "Ames Research Center",
}

# Shorter display names for the mission chart (the alias rules stay unchanged).
MISSION_LABELS = {
    "Artemis program (incl. EM-1)": "Artemis",
    "Orion spacecraft (incl. EFT-1)": "Orion spacecraft",
    "Space Launch System (SLS)": "Space Launch System",
    "Curiosity / Mars Science Laboratory": "Curiosity (MSL)",
    "Perseverance / Mars 2020": "Perseverance (Mars 2020)",
}


# ---------------------------------------------------------------------------
# Shared layout helpers
# ---------------------------------------------------------------------------

def base_layout(figure, height, left_margin=10):
    """Shared fonts, spacing, and hover style. Titles live in the page, not the chart."""
    figure.update_layout(
        font=dict(family=FONT, size=15, color=TEXT),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=height, margin=dict(l=left_margin, r=20, t=20, b=40),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#BFD9EC", font=dict(size=14, color=TEXT)),
        showlegend=False,
    )
    figure.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, automargin=True,
                        tickfont=dict(size=14, color=MUTED))
    figure.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, automargin=True,
                        tickfont=dict(size=15, color=TEXT))
    return figure


def show_chart(figure, key):
    st.plotly_chart(figure, use_container_width=True, theme=None, config=CHART_CONFIG, key=key)


def step_label(text):
    """Small label that tells the viewer what each chart in a panel shows."""
    st.markdown(f'<div class="chart-step">{text}</div>', unsafe_allow_html=True)


def section_header(number, title, subtitle):
    st.markdown(f'<div class="insight-number">Insight {number:02d}</div>', unsafe_allow_html=True)
    st.markdown(f'<h2 class="insight-title">{title}</h2>', unsafe_allow_html=True)
    st.markdown(f'<div class="insight-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def key_finding(section, text):
    """The single takeaway paragraph under each chart."""
    with st.container(border=True, key=f"finding_{section}"):
        st.markdown(f"**Key Finding.** {text}")


def method_note(text):
    st.markdown(f'<div class="method-note">{text}</div>', unsafe_allow_html=True)


def pct(part, whole):
    return part / whole * 100 if whole else 0.0


# ---------------------------------------------------------------------------
# Insight 1: The 2014 surge
# ---------------------------------------------------------------------------

def annual_overview_chart(annual, peak_year):
    """Compact bar chart of records per year that makes the peak year obvious."""
    years = annual["year"].astype(int).tolist()
    counts = annual["unique_images"].astype(int).tolist()
    peak_images = counts[years.index(peak_year)]
    figure = go.Figure(go.Bar(
        x=years, y=counts,
        marker_color=[GOLD if year == peak_year else LIGHT_BLUE for year in years],
        hovertemplate="%{x}: %{y:,} image records<extra></extra>",
    ))
    figure.add_annotation(x=peak_year, y=peak_images, yshift=6, showarrow=False, yanchor="bottom",
                          text=f"<b>{peak_year}: {peak_images:,}</b>", font=dict(size=14, color=TEXT))
    base_layout(figure, 230)
    figure.update_layout(bargap=0.15, margin=dict(l=10, r=20, t=30, b=30))
    figure.update_xaxes(showgrid=False, tickformat="d", dtick=10, tickfont=dict(size=13, color=MUTED))
    figure.update_yaxes(tickformat=",d", nticks=4, range=[0, peak_images * 1.18],
                        tickfont=dict(size=13, color=MUTED))
    return figure


def peak_chart(breakdown):
    years = [str(int(year)) for year in breakdown["year"]]
    figure = go.Figure()
    figure.add_bar(
        x=years, y=breakdown["any_mission"], name="Mission-linked records (Orion, Morpheus, OCO-2, TDRS, SMAP)",
        marker_color=NAVY, width=0.5,
        text=[f"<b>{count:,}</b><br>{share:.0f}%" for count, share
              in zip(breakdown["any_mission"], breakdown["mission_share"])],
        texttemplate="%{text}", textposition="inside", insidetextanchor="middle",
        insidetextfont=dict(color="#FFFFFF", size=16), customdata=breakdown["mission_share"],
        hovertemplate="%{x}: %{y:,} records linked to the five missions "
                      "(%{customdata:.1f}% of the year)<extra></extra>",
    )
    figure.add_bar(
        x=years, y=breakdown["other"], name="All other records", marker_color=LIGHT_BLUE, width=0.5,
        text=breakdown["other"], texttemplate="%{y:,}", textposition="inside", insidetextanchor="middle",
        insidetextfont=dict(color=TEXT, size=16),
        hovertemplate="%{x}: %{y:,} other records<extra></extra>",
    )
    # Total above each bar; the mission-related share sits inside the navy segment.
    # Position labels by category index: numeric-looking strings such as "2014" would
    # otherwise be read as x = 2014 and stretch the axis until the bars disappear.
    for index, (total, share) in enumerate(zip(breakdown["total"], breakdown["mission_share"])):
        figure.add_annotation(x=index, y=total, yshift=14, showarrow=False,
                              text=f"<b>{int(total):,}</b> total", font=dict(size=15, color=TEXT))
    base_layout(figure, 400)
    figure.update_layout(
        barmode="stack", showlegend=True,
        legend=dict(orientation="h", x=0, y=-0.12, xanchor="left", yanchor="top", font=dict(size=14),
                    traceorder="normal"),
        margin=dict(l=10, r=20, t=30, b=80),
    )
    # Years are categories, never numbers, so the bars always render.
    figure.update_xaxes(type="category", categoryorder="array", categoryarray=years, showgrid=False,
                        range=[-0.5, len(years) - 0.5], tickfont=dict(size=17, color=TEXT))
    figure.update_yaxes(title=dict(text="Image records", font=dict(size=14, color=MUTED)),
                        tickformat=",d", range=[0, breakdown["total"].max() * 1.15],
                        tickfont=dict(size=14, color=MUTED))
    return figure


def go_to_archive_year(archive_page, year):
    """Open Archive Search already filtered to one year."""
    from views import explore

    explore.reset_filters()
    st.session_state.filter_year = int(year)
    st.switch_page(archive_page)


def render_peak(archive_page=None):
    breakdown = data_access.get_peak_mission_breakdown()
    annual = data_access.get_annual_counts()
    centers = data_access.get_center_year_counts(rules.PEAK_YEARS)
    if breakdown.empty or len(breakdown) < 2 or annual.empty:
        st.info("The data for this insight is not available right now.")
        return

    ranked = annual.sort_values("unique_images", ascending=False).reset_index(drop=True)
    peak_year, peak_images = int(ranked.loc[0, "year"]), int(ranked.loc[0, "unique_images"])
    first, last = breakdown.iloc[0], breakdown.iloc[-1]
    subset_growth = int(last["total"] - first["total"])
    mission_growth = int(last["any_mission"] - first["any_mission"])
    by_center = centers.set_index("center")
    last_year = rules.PEAK_YEARS[-1]
    ksc_share = pct(by_center.loc["KSC", last_year],
                    annual.loc[annual["year"] == last_year, "unique_images"].sum())

    overview = annual[(annual["year"] >= data_access.NASA_FIRST_YEAR) & (annual["unique_images"] > 0)]
    before, after = int(first["year"]), int(last["year"])
    section_header(1, f"What drove the {peak_year} surge in NASA image records?",
                   f"{peak_year} has more image records than any other year in our dataset. "
                   "Kennedy Space Center's mission work explains much of the jump.")
    step_label(f"① Image records per year: {peak_year} is the highest")
    show_chart(annual_overview_chart(overview, peak_year), "chart_insight_1_overview")
    step_label(f"② Where the jump came from: Kennedy Space Center's Earth-topic records, {before} vs. {after}")
    show_chart(peak_chart(breakdown), "chart_insight_1")
    key_finding(1, (
        f"**{peak_year} is the busiest year in our dataset**, with {peak_images:,} image records, and "
        f"Kennedy Space Center contributed nearly half of them ({ksc_share:.1f}%). Kennedy's Earth-topic "
        f"records grew {pct(subset_growth, first['total']):.0f}% from {before} to {after}, and records linked "
        f"to five missions (Orion, OCO-2, Morpheus, TDRS, and SMAP) added {mission_growth:,} of them: "
        f"**about {pct(mission_growth, subset_growth):.0f}% of that increase**. {after} was a busy year of "
        "mission testing and launches, and the archive shows it."
    ))
    method_note("A record is mission-linked when a mission name appears in its title or keywords; each "
                "record counts once. Yearly counts exclude missing and future dates.")
    if archive_page is not None:
        if st.button(f"See all {peak_year} records in Archive Search", icon=":material/arrow_forward:",
                     key="insight_to_archive", type="tertiary"):
            go_to_archive_year(archive_page, peak_year)


# ---------------------------------------------------------------------------
# Insight 2: Where the records come from
# ---------------------------------------------------------------------------

def center_chart(ranking):
    labels = ranking["center"].tolist()
    full_names = [CENTER_NAMES.get(center, center) for center in labels]
    figure = go.Figure(go.Bar(
        x=ranking["images"], y=[CENTER_SHORT.get(code, code) for code in labels],
        orientation="h",
        marker_color=[NAVY if index < 3 else LIGHT_BLUE for index in range(len(ranking))],
        text=[f"<b>{images:,}</b>" if index < 3 else f"{images:,}"
              for index, images in enumerate(ranking["images"])],
        textposition="outside", cliponaxis=False, textfont=dict(size=15, color=TEXT),
        customdata=list(zip(full_names, labels, ranking["share"])),
        hovertemplate="<b>%{customdata[0]} (%{customdata[1]})</b><br>%{x:,} images · "
                      "%{customdata[2]:.1f}% of the archive<extra></extra>",
    ))
    base_layout(figure, 400)
    figure.update_yaxes(autorange="reversed", showgrid=False)
    figure.update_xaxes(tickformat=",d", range=[0, ranking["images"].max() * 1.3],
                        nticks=5, title=dict(text="Image records", font=dict(size=14, color=MUTED)))
    return figure


# What each of the three largest centers mostly covers (from the EDA content profile).
CENTER_FOCUS = {
    "KSC": ("Kennedy (KSC)", "Launches, rockets, and spacecraft processing"),
    "JSC": ("Johnson (JSC)", "Astronauts, crews, and Earth seen from orbit"),
    "JPL": ("JPL", "Science releases from planetary missions"),
}


def center_focus_html(codes):
    items = "".join(
        f'<div class="center-focus"><span class="name">{CENTER_FOCUS[code][0]}</span>'
        f'<span class="what">{CENTER_FOCUS[code][1]}</span></div>'
        for code in codes if code in CENTER_FOCUS
    )
    return f'<div class="center-focus-row">{items}</div>'


def render_centers(gallery_page=None, archive_page=None):
    ranking = data_access.get_center_ranking(6)
    profile = data_access.get_center_content_profile(("KSC", "JPL", "JSC"))
    if ranking.empty or profile.empty:
        st.info("The data for this insight is not available right now.")
        return

    top_three_share = ranking.head(3)["share"].sum()
    jpl = profile[profile["center"] == "JPL"]
    jpl_photojournal = pct(jpl["photojournal_ids"].sum(), jpl["images"].sum())

    top_codes = ranking.head(3)["center"].tolist()
    section_header(2, "Where do most of our NASA image records come from?",
                   "The six NASA centers with the most image records. The three largest each cover "
                   "a different side of NASA.")
    show_chart(center_chart(ranking), "chart_insight_2")
    st.markdown(center_focus_html(top_codes), unsafe_allow_html=True)
    jpl_text = "nearly all" if jpl_photojournal >= 95 else f"{jpl_photojournal:.0f}%"
    key_finding(2, (
        f"**Three centers, Kennedy, JPL, and Johnson, contribute about {top_three_share:.0f}% of our "
        "records**, but each covers a different side of NASA. Kennedy is mostly launches and spacecraft "
        f"processing, Johnson is astronauts, crews, and Earth seen from orbit, and {jpl_text} of JPL's "
        "records are science releases. That is why the dashboard has two views: a curated **Planet "
        "Gallery** for clean space imagery, and **Archive Search** for everything else, including launches, "
        "astronauts, engineering, and events."
    ))
    method_note("Each center's focus comes from title and ID patterns plus a hand-checked sample in the "
                "EDA notebook.")
    if gallery_page is not None and archive_page is not None:
        left, right = st.columns(2)
        left.page_link(gallery_page, label="Open Planet Gallery", icon=":material/public:")
        right.page_link(archive_page, label="Open Archive Search", icon=":material/travel_explore:")


# ---------------------------------------------------------------------------
# Insight 3: Missions that appear most often
# ---------------------------------------------------------------------------

def mission_chart(missions):
    top = missions.head(8)
    labels = [MISSION_LABELS.get(name, name) for name in top["mission"]]
    figure = go.Figure(go.Bar(
        x=top["images"], y=labels, orientation="h",
        marker_color=[NAVY if index < 2 else BLUE for index in range(len(top))],
        text=[f"<b>{images:,}</b>" for images in top["images"]],
        textposition="outside", cliponaxis=False, textfont=dict(size=15, color=TEXT),
        customdata=top[["mission", "peak_year", "peak_year_images"]],
        hovertemplate="<b>%{customdata[0]}</b><br>%{x:,} image records<br>"
                      "Busiest year: %{customdata[1]} (%{customdata[2]:,})<extra></extra>",
    ))
    base_layout(figure, 430)
    figure.update_yaxes(autorange="reversed", showgrid=False)
    figure.update_xaxes(tickformat=",d", range=[0, top["images"].max() * 1.3],
                        nticks=5, title=dict(text="Image records", font=dict(size=14, color=MUTED)))
    return figure


def render_missions():
    missions = data_access.get_mission_mentions()
    if missions.empty:
        st.info("The data for this insight is not available right now.")
        return

    by_mission = missions.set_index("mission")
    leader = missions.iloc[0]
    leader_name = MISSION_LABELS.get(leader["mission"], leader["mission"])
    section_header(3, "Which NASA missions appear most often in our records?",
                   "The eight mission and program names found in the most image records")
    show_chart(mission_chart(missions), "chart_insight_3")

    text = f"**{leader_name} ranks first**, appearing in {int(leader['images']):,} image records. "
    if "2001 Mars Odyssey" in by_mission.index:
        odyssey = by_mission.loc["2001 Mars Odyssey"]
        text += (f"**2001 Mars Odyssey** is the leading science mission ({int(odyssey['images']):,}). ")
    others = [MISSION_LABELS.get(name, name) for name in missions.head(5)["mission"]
              if name not in (leader["mission"], "2001 Mars Odyssey")]
    if others:
        listed = ", ".join(others[:-1]) + (", and " if len(others) > 2 else " and ") + others[-1] \
            if len(others) > 1 else others[0]
        text += f"{listed} also appear often. "
    text += ("These counts show how often a mission name appears in titles and keywords. They don't "
             "mean every image shows the spacecraft, and they don't measure NASA's priorities or budget.")
    key_finding(3, text)
    method_note("Each record counts once per mission. Known alternate names count toward the same mission; "
                "for example, EM-1 counts toward Artemis.")


def render(archive_page=None, gallery_page=None):
    page_header(
        "Exploratory data analysis",
        "Data Insights",
        "Three questions about our NASA image records, each answered with one chart and one key "
        "finding. Every number is computed live from our PostgreSQL database.",
    )
    sections = [
        lambda: render_peak(archive_page),
        lambda: render_centers(gallery_page, archive_page),
        render_missions,
    ]
    for number, section in enumerate(sections, start=1):
        with st.container(border=True, key=f"panel_insight_{number}"):
            section()
        st.write("")
