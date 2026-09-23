import os

import httpx
from dotenv import load_dotenv

load_dotenv(".env")

BASE_URL = "https://eodhd.com/api/eod"


def _token() -> str:
    token = os.environ.get("EODHD_API_TOKEN")
    if not token:
        raise RuntimeError("EODHD_API_TOKEN is not set")
    return token


def get_eod(
    symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    provider_symbol = f"{symbol}.US"

    response = httpx.get(
        f"{BASE_URL}/{provider_symbol}",
        params={
            "from": start_date,
            "to": end_date,
            "api_token": _token(),
            "fmt": "json",
        },
        timeout=30.0,
    )

    response.raise_for_status()

    return response.json()
