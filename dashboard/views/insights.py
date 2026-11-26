"""Data Insights page: three analytical stories about the NASA image archive.

1. Behind the 2014 Peak: which documented missions are reflected in the busiest year.
2. Beyond Planet Photos: what kinds of records each NASA center contributes.
3. Missions, Sources & Locations: what the archive's metadata mentions most.

All numbers come from live, read-only SQL in data_access.py (the same SQL as
notebooks/eda.ipynb), so the charts and Key Findings update with the database.
"""

from html import escape

import plotly.graph_objects as go
import streamlit as st

import analysis_rules as rules
import data_access
from styles import page_header
from views.components import card_html, format_date, has_text

# "Starlight Observatory" chart palette: muted blue data, navy and gold highlights.
TEXT = "#17324D"
MUTED = "#60758A"
BLUE = "#4A93C6"
LIGHT_BLUE = "#A9CBE4"
NAVY = "#17324D"
GOLD = "#C9A86A"
GREY = "#C8D3DD"
GRID = "#E6EEF5"
CHART_CONFIG = {"displaylogo": False, "scrollZoom": False}

CONTENT_COLORS = {
    "Operations, people & engineering": NAVY,
    "Earth photography by crews": GOLD,
    "Other descriptive title": LIGHT_BLUE,
    "ID-only title": GREY,
}

# Verified NASA context (official sources); shown separately from database results.
HISTORY_SOURCES = [
    ("TDRS-L launched January 23, 2014 from Cape Canaveral.",
     "https://www.nasa.gov/image-article/tracking-data-relay-satellite-launch-lights-up-night-sky/"),
    ("OCO-2 launched July 2, 2014 from Vandenberg to measure atmospheric carbon dioxide.",
     "https://www.nasa.gov/news-release/nasa-launches-new-carbon-sensing-mission-to-monitor-earths-breathing-2/"),
    ("Project Morpheus flew 13 free flights at Kennedy's Shuttle Landing Facility between "
     "December 2013 and December 2014, six of them with the ALHAT landing system.",
     "https://www.nasa.gov/technology/morpheus-team-completes-alhat-system-tests-on-prototype-lander/"),
    ("Orion's Exploration Flight Test-1 launched December 5, 2014 from Cape Canaveral.",
     "https://www.nasa.gov/mission/exploration-flight-test-1/"),
    ("SMAP launched January 31, 2015, so its 2014 records show prelaunch preparation.",
     "https://www.nasa.gov/reference/lsp-primary-launches-archive/"),
]
BUDGET_SOURCE = "https://www.nasa.gov/wp-content/uploads/2018/02/fy-2014-nasa-operating-plan-june-2014.pdf"
STS135_SOURCE = "https://www.nasa.gov/mission/sts-135/"
ARTEMIS_II_SOURCE = ("https://www.nasa.gov/news-release/"
                     "liftoff-nasa-launches-astronauts-on-historic-artemis-moon-mission/")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def style_figure(figure, title, subtitle, height, legend=False):
    """Apply the shared title, font, and background settings."""
    figure.update_layout(
        title=dict(text=f"<b>{title}</b><br><sup>{subtitle}</sup>", x=0, xanchor="left",
                   font=dict(size=17, color=TEXT)),
        font=dict(family="'Source Sans Pro', 'Source Sans 3', sans-serif", size=13, color=MUTED),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=height, showlegend=legend,
        legend=dict(orientation="h", yanchor="top", y=-0.14, x=0, xanchor="left",
                    font=dict(size=12, color=TEXT), traceorder="normal"),
        margin=dict(l=10, r=30, t=85, b=95 if legend else 50),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#BFD9EC", font=dict(size=13, color=TEXT)),
        bargap=0.25,
    )
    figure.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, automargin=True)
    figure.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, automargin=True)
    return figure


def show_chart(figure):
    st.plotly_chart(figure, use_container_width=True, theme=None, config=CHART_CONFIG)


def section_title(number, title, question):
    st.markdown(f'<div class="eyebrow">Insight {number}</div>', unsafe_allow_html=True)
    st.subheader(title)
    st.markdown(f'<div class="insight-question">{question}</div>', unsafe_allow_html=True)


def key_findings(section, findings):
    """The two or three takeaways for one insight."""
    with st.container(border=True, key=f"finding_{section}"):
        st.markdown(":material/lightbulb: **Key Findings**")
        st.markdown("\n".join(f"- {finding}" for finding in findings))


def example_cards(examples, chip_column):
    """Real archive images with a link back to each original NASA record."""
    if examples.empty:
        st.caption("No example images are available right now.")
        return
    for column, image in zip(st.columns(len(examples)), examples.itertuples(index=False)):
        meta = [format_date(image.date), f"NASA ID: {image.source_id}"]
        if has_text(image.credit):
            meta.append(f"Credit: {image.credit}")
        column.markdown(card_html(image.image_url, image.title, meta, chip=getattr(image, chip_column)),
                        unsafe_allow_html=True)
        if has_text(image.page_url):
            column.markdown(f'<a class="example-link" href="{escape(image.page_url, quote=True)}" '
                            'target="_blank">View on NASA Image Library ↗</a>', unsafe_allow_html=True)


def pct(part, whole):
    return part / whole * 100 if whole else 0.0


def pct_label(part, whole):
    """One-decimal percentage that never rounds a partial share up to 100%."""
    value = pct(part, whole)
    return ">99.9%" if 99.95 <= value < 100 else f"{value:.1f}%"


# ---------------------------------------------------------------------------
# Insight 1: Behind the 2014 Peak
# ---------------------------------------------------------------------------

def annual_trend_chart(annual, peak_year):
    modern = annual[annual["year"] >= data_access.NASA_FIRST_YEAR]
    colors = [NAVY if year == peak_year else BLUE for year in modern["year"]]
    figure = go.Figure(go.Bar(
        x=modern["year"], y=modern["unique_images"], marker_color=colors,
        hovertemplate="<b>%{x}</b><br>%{y:,} images<extra></extra>",
    ))
    peak_value = int(modern.loc[modern["year"] == peak_year, "unique_images"].iloc[0])
    figure.add_annotation(x=peak_year, y=peak_value, text=f"<b>{peak_year} peak</b><br>{peak_value:,} images",
                          showarrow=True, arrowhead=0, arrowcolor=GOLD, ax=-70, ay=-30,
                          font=dict(color=TEXT, size=13), bgcolor="rgba(255,255,255,0.85)")
    style_figure(figure, "NASA image records per year",
                 f"Unique images by metadata year, {data_access.NASA_FIRST_YEAR}–today", 380)
    figure.update_yaxes(title="Unique images", tickformat=",d")
    figure.update_xaxes(title=None, showgrid=False, dtick=5)
    return figure


def center_change_chart(centers, years):
    first, last = years
    top = centers[centers["center"].isin(["KSC", "JSC", "JPL", "HQ"])]
    top = top.sort_values("change")
    figure = go.Figure(go.Bar(
        x=top["change"], y=top["center"], orientation="h",
        marker_color=[NAVY if value > 0 else GREY for value in top["change"]],
        text=[f"{value:+,}" for value in top["change"]], textposition="outside", cliponaxis=False,
        customdata=top[[first, last]],
        hovertemplate=f"<b>%{{y}}</b><br>{first}: %{{customdata[0]:,}}<br>{last}: "
                      "%{customdata[1]:,}<br>Change: %{x:+,}<extra></extra>",
    ))
    style_figure(figure, f"Who changed from {first} to {last}?",
                 "Change in unique images by NASA center", 330)
    span = max(abs(top["change"]).max(), 1) * 1.35
    figure.update_xaxes(range=[-span, span], tickformat="+,d", title=None)
    figure.update_yaxes(title=None, showgrid=False)
    return figure


def mission_share_chart(breakdown):
    labels = breakdown["year"].astype(str)
    figure = go.Figure()
    figure.add_bar(x=labels, y=breakdown["any_mission"], name="Mentions one of the five missions",
                   marker_color=NAVY, text=breakdown["any_mission"], texttemplate="%{y:,}",
                   textposition="inside", insidetextfont=dict(color="#FFFFFF"),
                   hovertemplate="%{x}: %{y:,} mission-related images<extra></extra>")
    figure.add_bar(x=labels, y=breakdown["other"], name="Other records", marker_color=LIGHT_BLUE,
                   text=breakdown["other"], texttemplate="%{y:,}", textposition="inside",
                   insidetextfont=dict(color=TEXT),
                   hovertemplate="%{x}: %{y:,} other images<extra></extra>")
    for row in breakdown.itertuples(index=False):
        figure.add_annotation(x=str(row.year), y=row.total, text=f"<b>{row.mission_share:.1f}%</b> mission-related",
                              showarrow=False, yshift=14, font=dict(color=TEXT, size=12))
    style_figure(figure, f"KSC Earth-topic records, {' vs. '.join(labels)}",
                 "Five missions: Orion/EFT-1, Morpheus/ALHAT, OCO-2, TDRS, SMAP", 360, legend=True)
    figure.update_layout(barmode="stack", bargap=0.45)
    figure.update_yaxes(title="Unique images", tickformat=",d", range=[0, breakdown["total"].max() * 1.2])
    figure.update_xaxes(title=None, showgrid=False)
    return figure


def mission_detail_chart(breakdown):
    missions = list(rules.PEAK_MISSIONS)
    figure = go.Figure()
    for (_, row), color in zip(breakdown.iterrows(), [LIGHT_BLUE, NAVY]):
        year = int(row["year"])
        values = [int(row[name]) for name in missions]
        figure.add_bar(y=missions, x=values, orientation="h", name=str(year), marker_color=color,
                       text=values, texttemplate="%{x:,}", textposition="outside", cliponaxis=False,
                       hovertemplate=f"<b>%{{y}}</b><br>{year}: %{{x:,}} images<extra></extra>")
    style_figure(figure, "Images mentioning each mission",
                 "KSC Earth-topic records · title or keyword mention · one image can name several missions",
                 400, legend=True)
    figure.update_layout(barmode="group")
    figure.update_yaxes(autorange="reversed", title=None, showgrid=False)
    figure.update_xaxes(title="Unique images", tickformat=",d")
    return figure


def render_peak():
    section_title(1, "Behind the 2014 Peak",
                  "Why does 2014 hold the most image records in our archive, and which NASA "
                  "missions are reflected in that peak?")
    years = rules.PEAK_YEARS
    annual = data_access.get_annual_counts()
    centers = data_access.get_center_year_counts(years)
    breakdown = data_access.get_peak_mission_breakdown()
    if annual.empty or breakdown.empty or len(breakdown) < 2:
        st.info("The data for this insight is not available right now.")
        return

    ranked = annual.sort_values("unique_images", ascending=False).reset_index(drop=True)
    peak_year, peak_images = int(ranked.loc[0, "year"]), int(ranked.loc[0, "unique_images"])
    runner_up = ranked.iloc[1]
    show_chart(annual_trend_chart(annual, peak_year))

    left, right = st.columns(2)
    with left:
        show_chart(center_change_chart(centers, years))
    with right:
        show_chart(mission_share_chart(breakdown))

    first, last = breakdown.iloc[0], breakdown.iloc[-1]
    subset_growth = int(last["total"] - first["total"])
    mission_growth = int(last["any_mission"] - first["any_mission"])
    by_center = centers.set_index("center")
    ksc_peak_row = data_access.get_center_annual_counts(rules.PEAK_CENTER).sort_values(
        "images", ascending=False).iloc[0]
    ksc_last = int(by_center.loc[rules.PEAK_CENTER, years[-1]]) if rules.PEAK_CENTER in by_center.index else 0
    year_total = int(annual.loc[annual["year"] == years[-1], "unique_images"].iloc[0])

    risers = by_center[by_center["change"] > 0].sort_values("change", ascending=False).head(2)
    fallers = by_center[by_center["change"] < 0].sort_values("change").head(2)
    shift = (", ".join(f"**{c}** {int(v):+,}" for c, v in risers["change"].items()) + " while "
             + ", ".join(f"**{c}** {int(v):+,}" for c, v in fallers["change"].items()))

    key_findings(1, [
        f"**{peak_year} is the busiest year** in our collected archive with **{peak_images:,}** images, "
        f"just ahead of {int(runner_up['year'])} ({int(runner_up['unique_images']):,}). Kennedy Space Center "
        f"supplied **{pct(ksc_last, year_total):.1f}%** of {years[-1]}'s records, although KSC's own busiest "
        f"year was {int(ksc_peak_row['year'])} ({int(ksc_peak_row['images']):,}).",
        f"The jump from {years[0]} to {years[-1]} was not shared by every center: {shift}.",
        f"Inside KSC's Earth-topic records ({int(first['total']):,} → {int(last['total']):,}, "
        f"**{pct(subset_growth, first['total']):+.1f}%**), images mentioning Orion/EFT-1, Morpheus/ALHAT, "
        f"OCO-2, TDRS, or SMAP grew from {int(first['any_mission']):,} to {int(last['any_mission']):,}. "
        f"That **+{mission_growth:,}** accounts for about **{pct(mission_growth, subset_growth):.0f}%** of the "
        f"subset's net growth, and their share rose from {first['mission_share']:.1f}% to "
        f"{last['mission_share']:.1f}%.",
    ])

    detail_tab, images_tab, context_tab = st.tabs(
        ["Mission breakdown", f"Images from {years[-1]}", "NASA historical context"])
    with detail_tab:
        show_chart(mission_detail_chart(breakdown))
    with images_tab:
        example_cards(data_access.get_peak_mission_examples(), "mission")
    with context_tab:
        st.markdown("Verified events from NASA's official pages that line up with the missions above:")
        st.markdown("\n".join(f"- {fact} [Source ↗]({url})" for fact, url in HISTORY_SOURCES))
        st.markdown(
            '<div class="context-note"><b>External budget context, not from our database:</b> NASA\'s '
            "FY2014 operating plan funded Earth Science at $1,824.9 million and Planetary Science at "
            f'$1,343.4 million (<a href="{BUDGET_SOURCE}" target="_blank">source ↗</a>). Fiscal-year funding '
            "is a different measure and period from calendar-year image records, so it is context only.</div>",
            unsafe_allow_html=True,
        )

    st.caption("Counts are unique NASA Image Library records by stored metadata date. A mission counts when "
               "its name appears in the title or keywords. The five missions were chosen after exploring the "
               "data, so this describes the archive's composition; it does not show what caused the peak.")


# ---------------------------------------------------------------------------
# Insight 2: Beyond Planet Photos
# ---------------------------------------------------------------------------

def center_ranking_chart(ranking, highlight):
    colors = [NAVY if center in highlight else LIGHT_BLUE for center in ranking["center"]]
    figure = go.Figure(go.Bar(
        x=ranking["images"], y=ranking["center"], orientation="h", marker_color=colors,
        text=[f"{images:,} · {share:.1f}%" for images, share in zip(ranking["images"], ranking["share"])],
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,} images<extra></extra>",
    ))
    style_figure(figure, "Top 10 NASA centers by image records",
                 "Unique images · share of the whole archive", 420)
    figure.update_yaxes(autorange="reversed", title=None, showgrid=False)
    figure.update_xaxes(title=None, tickformat=",d", range=[0, ranking["images"].max() * 1.32])
    return figure


def content_profile_chart(profile, centers):
    figure = go.Figure()
    for group in rules.CONTENT_GROUPS:
        rows = profile[profile["content_group"] == group].set_index("center").reindex(centers)
        shares = rows["share"].fillna(0)
        figure.add_bar(
            y=centers, x=shares, orientation="h", name=group, marker_color=CONTENT_COLORS[group],
            text=[f"{value:.0f}%" if value >= 6 else "" for value in shares], textposition="inside",
            insidetextfont=dict(color="#FFFFFF" if group in ("Operations, people & engineering",) else TEXT),
            customdata=rows["images"].fillna(0),
            hovertemplate=f"<b>%{{y}}</b> · {group}<br>%{{x:.1f}}% (%{{customdata:,}} images)<extra></extra>",
        )
    style_figure(figure, "What do the titles describe?",
                 "Share of each center's records by title-based content group", 420, legend=True)
    figure.update_layout(barmode="stack", bargap=0.35)
    figure.update_xaxes(range=[0, 100], ticksuffix="%", title=None)
    figure.update_yaxes(autorange="reversed", title=None, showgrid=False)
    return figure


def render_centers():
    section_title(2, "Beyond Planet Photos: NASA Centers & Image Content",
                  "Do different NASA centers contribute different kinds of image records?")
    focus = ["KSC", "JSC", "JPL"]
    ranking = data_access.get_center_ranking(10)
    profile = data_access.get_center_content_profile(tuple(focus))
    if ranking.empty or profile.empty:
        st.info("The data for this insight is not available right now.")
        return

    left, right = st.columns([1, 1.15])
    with left:
        show_chart(center_ranking_chart(ranking, focus))
    with right:
        show_chart(content_profile_chart(profile, focus))

    def share(center, group):
        rows = profile[(profile["center"] == center) & (profile["content_group"] == group)]
        return float(rows["share"].sum())

    def count(center, column="images", group=None):
        rows = profile[profile["center"] == center]
        if group:
            rows = rows[rows["content_group"] == group]
        return int(rows[column].sum())

    operations, earth, _, id_only = rules.CONTENT_GROUPS
    top_three = ranking[ranking["center"].isin(focus)]
    ksc_descriptive = count("KSC") - count("KSC", group=id_only)
    jpl_total = count("JPL")

    key_findings(2, [
        f"**KSC, JPL, and JSC supply {top_three['share'].sum():.1f}%** of all records, but they document "
        "very different things.",
        f"**{pct(count('KSC', group=operations), ksc_descriptive):.0f}%** of KSC's descriptive titles mention "
        f"launches, processing, crews, tests, or events. At JSC, **{share('JSC', earth):.0f}%** of records are "
        f"titled as crew Earth observations. At JPL, only **{share('JPL', operations):.1f}%** of titles use these words, "
        f"and **{pct_label(count('JPL', 'photojournal_ids'), jpl_total)}** of its records are Photojournal "
        "(PIA) releases.",
        f"**{share('KSC', id_only):.0f}%** of KSC records have a title that is only an archive ID, so title "
        "rules undercount KSC. That mix is why we built two views: **Planet Gallery** for curated discovery "
        "and **Archive Search** for comprehensive retrieval.",
    ])

    examples_tab, method_tab = st.tabs(["Example records", "How titles were classified"])
    with examples_tab:
        example_cards(data_access.get_content_examples(), "label")
    with method_tab:
        rows = []
        for center in focus:
            total = count(center)
            rows.append({
                "Center": center,
                "Records": total,
                "First keyword list": pct(count(center, "first_rule_matches"), total),
                "Refined rule": share(center, operations),
                "Crew Earth photography": share(center, earth),
                "ID-only titles": share(center, id_only),
            })
        st.dataframe(
            rows, hide_index=True, use_container_width=True,
            column_config={
                "Records": st.column_config.NumberColumn(format="%d"),
                **{name: st.column_config.NumberColumn(format="%.1f%%") for name in
                   ["First keyword list", "Refined rule", "Crew Earth photography", "ID-only titles"]},
            },
        )
        st.markdown(
            "The first keyword list counted titles such as *Earth Observations taken by the Expedition 38 crew* "
            "as crew activity. The refined rule checks ID-only titles and crew Earth photography first, then "
            "looks for whole words about launches, processing, people, testing, and events. A title without "
            "these words is not proof of a science image; the notebook reviews a fixed sample by hand."
        )

    st.caption("Groups are based on title metadata only, using explicit word rules (dashboard/analysis_rules.py). "
               "They describe titles, not validated image content.")


# ---------------------------------------------------------------------------
# Insight 3: Missions, Sources & Locations
# ---------------------------------------------------------------------------

def mission_ranking_chart(missions):
    top = missions.head(10)
    figure = go.Figure(go.Bar(
        x=top["images"], y=top["mission"], orientation="h",
        marker_color=[NAVY if index == 0 else BLUE for index in range(len(top))],
        text=[f"{images:,}  ·  peak {year}" for images, year in zip(top["images"], top["peak_year"])],
        textposition="outside", cliponaxis=False,
        customdata=top[["peak_year", "peak_year_images"]],
        hovertemplate="<b>%{y}</b><br>%{x:,} images<br>Busiest year: %{customdata[0]} "
                      "(%{customdata[1]:,})<extra></extra>",
    ))
    style_figure(figure, "Most documented NASA missions and programs",
                 "Unique images whose title or keywords name the mission · busiest year shown", 470)
    figure.update_yaxes(autorange="reversed", title=None, showgrid=False)
    figure.update_xaxes(title=None, tickformat=",d", range=[0, top["images"].max() * 1.35])
    return figure


def simple_bar_chart(frame, label_column, title, subtitle, highlight_first=True):
    figure = go.Figure(go.Bar(
        x=frame["images"], y=frame[label_column], orientation="h",
        marker_color=[NAVY if highlight_first and index == 0 else LIGHT_BLUE for index in range(len(frame))],
        text=frame["images"], texttemplate="%{x:,}", textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,} images<extra></extra>",
    ))
    style_figure(figure, title, subtitle, 300)
    figure.update_yaxes(autorange="reversed", title=None, showgrid=False)
    figure.update_xaxes(title=None, tickformat=",d", range=[0, frame["images"].max() * 1.3])
    return figure


def render_missions():
    section_title(3, "Missions, Sources & Locations",
                  "Which NASA missions, credit sources, and places appear most often in the archive's metadata?")
    missions = data_access.get_mission_mentions()
    locations = data_access.get_location_groups()
    formats = data_access.get_credit_formats()
    completeness = data_access.get_metadata_completeness().set_index("field")
    if missions.empty:
        st.info("The data for this insight is not available right now.")
        return

    show_chart(mission_ranking_chart(missions))

    left, right = st.columns(2)
    with left:
        show_chart(simple_bar_chart(locations, "location_group", "Where the Location field points",
                                    f"Records with a Location value ({completeness.loc['Location', 'completeness']:.0f}% "
                                    "of the archive), grouped"))
    with right:
        show_chart(simple_bar_chart(formats, "credit_format", "How images are credited",
                                    f"Records with a Credit value ({completeness.loc['Credit', 'completeness']:.0f}% "
                                    "of the archive)"))

    by_mission = missions.set_index("mission")
    leader = missions.iloc[0]
    odyssey = by_mission.loc["2001 Mars Odyssey"] if "2001 Mars Odyssey" in by_mission.index else None
    shuttle = by_mission.loc["Space Shuttle"] if "Space Shuttle" in by_mission.index else None
    first_finding = (f"**{leader['mission']}** is the most documented name, in **{int(leader['images']):,}** "
                     f"images, busiest in {int(leader['peak_year'])}.")
    if leader["mission"].startswith("Artemis") and int(leader["peak_year"]) == 2026:
        first_finding += (f" That is the year Artemis II launched (April 1, 2026, "
                          f"[NASA ↗]({ARTEMIS_II_SOURCE})).")
    if odyssey is not None:
        first_finding += (f" The most documented science mission is **2001 Mars Odyssey** "
                          f"({int(odyssey['images']):,} images, "
                          f"{pct_label(odyssey['photojournal_images'], odyssey['images'])} of them Photojournal "
                          "releases).")
    findings = [first_finding]
    if shuttle is not None:
        shuttle_text = (f"**Space Shuttle** mentions ({int(shuttle['images']):,} images) peak in "
                        f"**{int(shuttle['peak_year'])}** ({int(shuttle['peak_year_images']):,})")
        if int(shuttle["peak_year"]) == 2011:
            shuttle_text += f", the year of the final shuttle flight, STS-135 ([NASA ↗]({STS135_SOURCE}))"
            annual = data_access.get_annual_counts().sort_values("unique_images", ascending=False)
            if len(annual) > 1 and int(annual.iloc[1]["year"]) == 2011:
                shuttle_text += ". 2011 is also the archive's second-busiest year"
        findings.append(shuttle_text + ".")

    located = int(locations["images"].sum())
    launch_sites = locations.loc[locations["location_group"] == "Launch sites & launch processing", "images"].sum()
    credited = int(formats["images"].sum())
    named = formats.loc[formats["credit_format"] == "NASA / named individual", "images"].sum()
    findings.append(
        f"**{pct(launch_sites, located):.0f}%** of records with a location point to launch sites or launch "
        f"processing facilities, so Location usually tells us where a mission was prepared, not where a planet "
        f"was photographed. Among credited records, **{pct(named, credited):.0f}%** name an individual "
        "alongside NASA (for example *NASA/Bill Ingalls*)."
    )
    key_findings(3, findings)

    with st.expander("Top 10 Credit and Location values"):
        credit_column, location_column = st.columns(2)
        credit_column.dataframe(
            data_access.get_credit_sources(10).rename(columns={
                "credit": "Credit (normalized)", "images": "Images", "credit_format": "Format"}),
            hide_index=True, use_container_width=True)
        location_column.dataframe(
            data_access.get_top_locations(10).rename(columns={
                "location": "Location", "images": "Images", "location_group": "Group"}),
            hide_index=True, use_container_width=True)

    st.caption(f"Mission names use an explicit alias list (for example EM-1 is counted with Artemis); each image "
               f"counts once per mission. Keywords exist on {completeness.loc['Keywords', 'completeness']:.0f}% "
               "of records. Credit and Location rankings describe only records that have those fields.")


def render():
    page_header(
        "Exploratory data analysis",
        "Data Insights",
        "Three stories from our NASA image archive: what drove the 2014 peak, how NASA centers differ, "
        "and which missions, sources, and places the metadata mentions most. Every chart is computed "
        "live from PostgreSQL.",
    )
    for number, section in enumerate([render_peak, render_centers, render_missions], start=1):
        with st.container(border=True, key=f"panel_insight_{number}"):
            section()
        st.write("")
