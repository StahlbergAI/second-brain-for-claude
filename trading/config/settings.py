import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TRADOVATE_ENV = os.getenv("TRADOVATE_ENV", "demo")  # "demo" or "live" - default to demo on purpose

TRADOVATE_USERNAME = os.getenv("TRADOVATE_USERNAME")
TRADOVATE_PASSWORD = os.getenv("TRADOVATE_PASSWORD")
TRADOVATE_APP_ID = os.getenv("TRADOVATE_APP_ID", "SecondBrainTrader")
TRADOVATE_APP_VERSION = os.getenv("TRADOVATE_APP_VERSION", "1.0")
TRADOVATE_CID = os.getenv("TRADOVATE_CID")
TRADOVATE_SEC = os.getenv("TRADOVATE_SEC")
TRADOVATE_DEVICE_ID = os.getenv("TRADOVATE_DEVICE_ID", "second-brain-trader-1")

REST_BASE_URLS = {
    "demo": "https://demo.tradovateapi.com/v1",
    "live": "https://live.tradovateapi.com/v1",
}


def rest_base_url() -> str:
    return REST_BASE_URLS[TRADOVATE_ENV]


def require_credentials():
    missing = [name for name, val in [
        ("TRADOVATE_USERNAME", TRADOVATE_USERNAME),
        ("TRADOVATE_PASSWORD", TRADOVATE_PASSWORD),
        ("TRADOVATE_CID", TRADOVATE_CID),
        ("TRADOVATE_SEC", TRADOVATE_SEC),
    ] if not val]
    if missing:
        raise RuntimeError(
            f"Missing Tradovate credentials in trading/.env: {', '.join(missing)}. "
            "See trading/.env.example and docs/CONNECT_TRADOVATE.md for how to get these."
        )
