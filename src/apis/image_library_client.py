
import os
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Load environment variables
load_dotenv()

NASA_LIBRARY_API_URL = os.getenv(
    "NASA_LIBRARY_API_URL",
    "https://images-api.nasa.gov"
)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))


def create_retry_session():
    """Create an HTTP session with automatic retries."""

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def fetch_nasa_library(query="Mars", page=1, start_year=2020, end_year=2026):
    """Search NASA Image Library within a specified year range."""

    with create_retry_session() as session:
        response = session.get(
            f"{NASA_LIBRARY_API_URL.rstrip('/')}/search",
            params={
                "q": query,
                "media_type": "image",
                "page": page,
                "year_start": start_year,
                "year_end": end_year,
            },
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()
        return response.json()


def fetch_nasa_library_pages(
    query="Mars",
    max_pages=2,
    start_year=2020,
    end_year=2026,
):
    """Fetch multiple pages of NASA Image Library results."""

    all_items = []

    for page in range(1, max_pages + 1):
        data = fetch_nasa_library(
            query=query,
            page=page,
            start_year=start_year,
            end_year=end_year,
        )

        items = data.get("collection", {}).get("items", [])

        if not items:
            break

        all_items.extend(items)

    return {
        "collection": {
            "items": all_items
        }
    }


if __name__ == "__main__":
    data = fetch_nasa_library("Mars")
    items = data.get("collection", {}).get("items", [])

    print("Records fetched:", len(items))
