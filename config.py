import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return val


# OPML file exported from Feedly
OPML_PATH: str = os.getenv(
    "OPML_PATH",
    os.path.join(os.path.dirname(__file__), "feedly-opml-2726bff4-1040-4aba-abfd-cf18781586ac-2026-03-15.opml"),
)

# Categories to monitor — comma-separated display names, e.g. "News,Android"
# Leave empty to monitor ALL categories.
CATEGORIES_FILTER: list[str] = [
    c.strip() for c in os.getenv("CATEGORIES", "").split(",") if c.strip()
]

# Claude
CLAUDE_API_KEY: str = _require("CLAUDE_API_KEY")
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Gmail
GMAIL_USER: str = _require("GMAIL_USER")
GMAIL_APP_PASSWORD: str = _require("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL: str = os.getenv("RECIPIENT_EMAIL", "") or GMAIL_USER

# How many hours back to fetch articles
LOOKBACK_HOURS: int = int(os.getenv("LOOKBACK_HOURS", "24"))

# Minimum articles in a cluster to trigger AI summarization
MIN_CLUSTER_SIZE_FOR_SUMMARY: int = 2
