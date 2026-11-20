import os
import requests
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# NASA APOD API endpoint
APOD_API_URL = os.getenv(
    "APOD_API_URL",
    "https://science.nasa.gov/wp-json/wp/v2/apod-basic"
)

# Request timeout in seconds
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))


def fetch_apod():
    """Fetch the latest APOD record from NASA."""

    response = requests.get(
        APOD_API_URL,
        params={
            "per_page": 1,
            "page": 1
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    return response.json()


if __name__ == "__main__":
    data = fetch_apod()

    print("Response type:", type(data))

    if isinstance(data, list) and data:
        print("Number of records:", len(data))
        print("Available fields:", list(data[0].keys()))
        print("First record:", data[0])
    else:
        print("Response:", data)