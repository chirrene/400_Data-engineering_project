
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


def fetch_nasa_library(
    query,
    page=1,
    start_year=None,
    end_year=None,
):
    """Search NASA Image Library with optional year filters."""

    params = {
        "q": query,
        "media_type": "image",
        "page": page,
    }

    if start_year is not None:
        params["year_start"] = start_year

    if end_year is not None:
        params["year_end"] = end_year

    with create_retry_session() as session:
        response = session.get(
            f"{NASA_LIBRARY_API_URL.rstrip('/')}/search",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()
        return response.json()


def fetch_nasa_library_pages(
    query,
    max_pages=100,
    start_year=None,
    end_year=None,
):
    """Fetch up to max_pages of NASA Image Library results."""

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
            print(f"[{query}] No more results at page {page}.")
            break

        all_items.extend(items)

        print(
            f"[{query}] Page {page}/{max_pages}: "
            f"{len(items)} records fetched."
        )

    print(f"[{query}] Total records fetched: {len(all_items)}")

    return {
        "collection": {
            "items": all_items
        }
    }


if __name__ == "__main__":
    data = fetch_nasa_library("Mars")
    items = data.get("collection", {}).get("items", [])

    print("Records fetched:", len(items))
