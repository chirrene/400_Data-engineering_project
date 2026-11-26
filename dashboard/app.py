"""NASA Space Explorer dashboard.

Run from the repository root:
    streamlit run dashboard/app.py
"""

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

import data_access
from styles import apply_styles, footer
from views import explore, gallery, home, insights

st.set_page_config(
    page_title="NASA Space Explorer",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="auto",  # expanded on desktop, collapsed on mobile
)
apply_styles()


def show_database_error(error):
    """Explain a database problem without exposing connection details."""
    st.error(
        "**Could not connect to the NASA PostgreSQL database.**\n\n"
        "Check that PostgreSQL is running and that `DATABASE_URL` is set in the "
        f"project's `.env` file. (Error type: `{type(error).__name__}`)"
    )
    st.stop()


# Stop early with a clear message if the database is unavailable.
try:
    data_access.check_connection()
except (data_access.DatabaseConfigError, SQLAlchemyError) as error:
    show_database_error(error)

# Build the pages first so the Home page can link to the others.
gallery_page = st.Page(gallery.render, title="Planet Gallery", icon=":material/public:",
                       url_path="planets")
archive_page = st.Page(lambda: explore.render(gallery_page), title="Archive Search", icon=":material/travel_explore:",
                       url_path="archive")
insights_page = st.Page(lambda: insights.render(archive_page, gallery_page), title="Data Insights",
                        icon=":material/insights:", url_path="insights")
home_page = st.Page(
    lambda: home.render(gallery_page, archive_page, insights_page),
    title="Home", icon=":material/rocket_launch:", url_path="home", default=True,
)

# Vertical sidebar navigation; the section name doubles as the app heading above the links.
current_page = st.navigation(
    {"NASA Space Explorer": [home_page, insights_page, gallery_page, archive_page]},
    position="sidebar",
)

try:
    current_page.run()
except SQLAlchemyError as error:
    show_database_error(error)

footer()
