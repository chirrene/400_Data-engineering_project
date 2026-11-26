"""Shared visual styling for the dashboard: "Starlight Observatory".

Pearl-white pages and white cards for readability, a deep-navy sidebar and dark
space banners for atmosphere, ice-blue for interaction, and a touch of champagne
gold for small premium details. Base colors live in .streamlit/config.toml; this
file only adds what the theme cannot (banners, cards, KPI tiles, small accents).
"""

import streamlit as st

# Palette shared with the Plotly charts and inline elements.
NAVY = "#17324D"          # primary text
MUTED = "#60758A"         # secondary text
ACCENT = "#5DAFDE"        # decorative ice blue
ACCENT_STRONG = "#2B7CB3" # ice blue dark enough for text and buttons
GOLD = "#D8BA83"          # champagne highlight
GRID = "#E6EEF5"

# A few soft "stars" used only inside dark banners, never across the whole page.
STAR_LAYERS = """
    radial-gradient(1px 1px at 8% 22%, rgba(255,255,255,0.85), transparent 60%),
    radial-gradient(1px 1px at 18% 70%, rgba(255,255,255,0.55), transparent 60%),
    radial-gradient(1.5px 1.5px at 30% 38%, rgba(216,186,131,0.85), transparent 60%),
    radial-gradient(1px 1px at 42% 84%, rgba(255,255,255,0.6), transparent 60%),
    radial-gradient(1px 1px at 52% 16%, rgba(255,255,255,0.7), transparent 60%),
    radial-gradient(1.3px 1.3px at 63% 58%, rgba(200,228,250,0.8), transparent 60%),
    radial-gradient(1px 1px at 76% 30%, rgba(255,255,255,0.55), transparent 60%),
    radial-gradient(1px 1px at 88% 76%, rgba(255,255,255,0.65), transparent 60%)
"""

APP_CSS = f"""
<style>
/* Pearl background with a faint ice-blue glow at the top. */
[data-testid="stApp"] {{
    background:
        radial-gradient(ellipse 70% 40% at 80% -8%, rgba(93,175,222,0.13), transparent 70%),
        #F5F8FC;
}}
[data-testid="stHeader"] {{ background: rgba(245,248,252,0.85); backdrop-filter: blur(6px); }}
.block-container {{ padding-top: 3rem; padding-bottom: 3rem; max-width: 1280px; }}
h1, h2, h3 {{ color: {NAVY}; letter-spacing: -0.015em; }}
.muted {{ color: {MUTED}; }}

/* Sidebar navigation: deep navy, readable labels, a clear active page. */
[data-testid="stSidebar"] {{ border-right: 1px solid #1F4063; }}
[data-testid="stNavSectionHeader"] {{ margin-bottom: 0.6rem; padding-bottom: 0.75rem;
                                      border-bottom: 1px solid rgba(216,186,131,0.35); }}
[data-testid="stNavSectionHeader"] p {{ color: #FFFFFF; font-size: 1.12rem; font-weight: 700;
                                        letter-spacing: 0.01em; text-transform: none; }}
a[data-testid="stSidebarNavLink"] {{ padding: 0.55rem 0.75rem; margin: 0.15rem 0; border-radius: 8px;
                                    border-left: 3px solid transparent; }}
a[data-testid="stSidebarNavLink"] p {{ font-size: 1rem; color: #C9D8E7; }}
a[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {{ font-size: 1.25rem; }}
a[data-testid="stSidebarNavLink"]:hover {{ background: rgba(93,175,222,0.10); }}
a[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(93,175,222,0.22); border-left-color: {ACCENT};
}}
a[data-testid="stSidebarNavLink"][aria-current="page"] p {{ color: #FFFFFF; font-weight: 600; }}
a[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {{ color: {ACCENT} !important; }}

/* Page heading: a small gold label, the title, and a one-line description. */
.eyebrow {{ color: #A98547; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.16em;
            text-transform: uppercase; margin-bottom: 0.1rem; }}
.page-intro {{ color: {MUTED}; font-size: 1.04rem; max-width: 820px; margin: -0.4rem 0 1.4rem 0; }}

/* Dark space banner: navy gradient, a few stars, and a real NASA image on the right. */
.hero {{
    position: relative; border-radius: 20px; overflow: hidden; margin-bottom: 1.8rem;
    padding: 3.4rem 3rem; border: 1px solid rgba(216,186,131,0.35);
    background-color: #0E2540; background-size: cover; background-repeat: no-repeat;
    background-position: center right;
    box-shadow: 0 18px 40px rgba(16,41,65,0.18);
}}
.hero::before {{ content: ""; position: absolute; inset: 0; pointer-events: none;
                 background-image: {STAR_LAYERS}; }}
.hero > * {{ position: relative; }}
.hero.compact {{ padding: 2.2rem 2.5rem; }}
.hero [data-testid="stHeaderActionElements"] {{ display: none; }}
.hero h1 {{ color: #FFFFFF; font-size: 2.8rem; margin: 0 0 0.5rem 0; padding: 0; }}
.hero.compact h1 {{ font-size: 2.15rem; }}
.hero p {{ color: #D5E2EF; font-size: 1.08rem; margin: 0; max-width: 640px; line-height: 1.6; }}
.hero b {{ color: #FFFFFF; }}
.hero .hero-tag {{ display: inline-block; color: {GOLD}; border: 1px solid rgba(216,186,131,0.55);
                   border-radius: 999px; padding: 0.15rem 0.8rem; font-size: 0.76rem;
                   letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.9rem; }}

/* KPI tiles: white, with a thin champagne line on top. */
.kpi-card {{
    background: #FFFFFF; border: 1px solid #D9E5EE; border-top: 3px solid {GOLD};
    border-radius: 14px; padding: 1.2rem 1.4rem; height: 100%; min-height: 8.6rem;
    box-shadow: 0 6px 18px rgba(23,50,77,0.06);
}}
.kpi-label {{ color: {ACCENT_STRONG}; font-size: 0.76rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.1em; }}
.kpi-value {{ color: {NAVY}; font-size: 2.4rem; font-weight: 700; line-height: 1.25; }}
.kpi-note {{ color: {MUTED}; font-size: 0.83rem; }}

/* Gallery image tile. The 'preview unavailable' label shows through if the URL fails. */
.thumb {{
    position: relative; width: 100%; aspect-ratio: 4 / 3; border-radius: 10px; overflow: hidden;
    background: #E6EEF6; display: flex; align-items: center; justify-content: center;
    color: #9AAABB; font-size: 0.8rem;
}}
.thumb-fallback {{ padding: 0 1rem; text-align: center; line-height: 1.35; }}
.thumb.cover .thumb-fallback {{ font-size: 0.6rem; padding: 0 0.6rem; }}
.thumb img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
.thumb.detail {{ aspect-ratio: auto; height: 400px; background: #0E2540; }}
.thumb.detail img {{ object-fit: contain; }}
.thumb.cover {{ aspect-ratio: 1 / 1; border-radius: 50%; max-width: 120px; margin: 0 auto 0.5rem auto;
                border: 3px solid #FFFFFF; box-shadow: 0 4px 14px rgba(23,50,77,0.18);
                transition: box-shadow 0.2s ease, transform 0.2s ease; }}
.thumb.cover:hover {{ transform: translateY(-2px); }}
.thumb.cover.active {{ border-color: {GOLD}; box-shadow: 0 0 0 3px rgba(93,175,222,0.45),
                                                       0 6px 18px rgba(23,50,77,0.22); }}
.card-title {{
    font-weight: 600; font-size: 0.96rem; line-height: 1.35; margin-top: 0.65rem; color: {NAVY};
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    min-height: 2.6em;
}}
.card-meta {{ color: {MUTED}; font-size: 0.8rem; margin-top: 0.2rem;
              white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.topic-chip {{ display: inline-block; color: #1F5F8B; background: #DCECF7;
               border-radius: 999px; padding: 0.08rem 0.6rem; font-size: 0.72rem; font-weight: 700;
               margin-top: 0.6rem; }}

/* Bordered containers keyed card_* or panel_* become white cards with soft shadows. */
[class*="st-key-card_"], [class*="st-key-panel_"] {{
    background: #FFFFFF; border-color: #D9E5EE !important;
    box-shadow: 0 4px 16px rgba(23,50,77,0.05);
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}}
[class*="st-key-card_"]:hover {{
    border-color: rgba(93,175,222,0.7) !important; transform: translateY(-2px);
    box-shadow: 0 12px 26px rgba(23,50,77,0.12);
}}

/* Small secondary note under the Planet Gallery date controls. */
.date-note {{ color: {MUTED}; font-size: 0.82rem; line-height: 1.5; margin-top: 0.2rem; }}

/* Key Findings box and the small example cards on the Insights page. */
[class*="st-key-finding_"] {{ background: #EEF6FC; border-left: 3px solid {ACCENT} !important; }}
[class*="st-key-finding_"] li {{ margin-bottom: 0.35rem; }}
.insight-question {{ color: {MUTED}; font-size: 1.05rem; font-style: italic; margin: -0.3rem 0 0.8rem 0; }}
.example-link {{ font-size: 0.82rem; }}
.context-note {{ color: {MUTED}; font-size: 0.85rem; border-top: 1px solid #E6EEF5; padding-top: 0.6rem;
                 margin-top: 0.4rem; }}

/* Data-pipeline steps on the Home page. */
.pipeline {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.55rem; margin: 0.3rem 0 1rem 0; }}
.pipeline .step {{ background: #DCECF7; color: {NAVY}; border: 1px solid #BFD9EC;
                   border-radius: 999px; padding: 0.4rem 1rem; font-weight: 600; font-size: 0.9rem; }}
.pipeline .arrow {{ color: {GOLD}; font-weight: 700; }}

.footer {{ color: {MUTED}; font-size: 0.8rem; text-align: center; margin-top: 3rem;
           padding-top: 1.2rem; border-top: 1px solid #D9E5EE; }}
</style>
"""


def apply_styles():
    """Inject the shared CSS once per page run."""
    st.markdown(APP_CSS, unsafe_allow_html=True)


def page_header(eyebrow, title, intro):
    """Consistent page heading: small label, title, and one-line description."""
    st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="page-intro">{intro}</div>', unsafe_allow_html=True)


def hero_banner(title, text, image_url=None, tag=None, compact=False):
    """Dark space banner with an optional NASA image faded in on the right side."""
    gradient = ("linear-gradient(90deg, rgba(12,33,56,0.97) 0%, rgba(12,33,56,0.88) 42%, "
                "rgba(12,33,56,0.38) 75%, rgba(12,33,56,0.12) 100%)")
    background = gradient
    # Only use simple https URLs inside CSS, so a stray quote can never break the style.
    if image_url and image_url.startswith("https://") and not any(c in image_url for c in "'\"()<> "):
        background += f", url('{image_url}')"
    tag_html = f'<div class="hero-tag">{tag}</div>' if tag else ""
    css_class = "hero compact" if compact else "hero"
    st.markdown(
        f'<div class="{css_class}" style="background-image: {background};">'
        f"{tag_html}<h1>{title}</h1><p>{text}</p></div>",
        unsafe_allow_html=True,
    )


def footer():
    st.markdown(
        '<div class="footer">NASA Space Explorer · Northwestern MLDS 400 Data Engineering · '
        "Images and metadata from the NASA Image and Video Library, served from our PostgreSQL database.</div>",
        unsafe_allow_html=True,
    )
