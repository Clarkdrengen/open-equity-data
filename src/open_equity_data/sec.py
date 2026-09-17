import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://data.sec.gov/submissions"
CACHE_DIR = Path("data/external/sec/submissions")


def _user_agent() -> str:
    value = os.environ.get("SEC_USER_AGENT")
    if not value:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. "
            "Example: 'OpenEquityData name@example.com'"
        )
    return value


def normalize_cik(cik: str) -> str:
    return str(cik).replace("CIK", "").zfill(10)


def _headers() -> dict:
    return {
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }


def get_submissions(cik: str, refresh: bool = False) -> dict:
    cik = normalize_cik(cik)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"CIK{cik}.json"

    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())

    url = f"{BASE_URL}/CIK{cik}.json"

    with httpx.Client(
        headers=_headers(),
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()

    data = response.json()
    cache_path.write_text(json.dumps(data, indent=2))

    return data


def _rows_from_block(block: dict) -> list[dict]:
    fields = [
        "accessionNumber",
        "filingDate",
        "reportDate",
        "form",
        "primaryDocument",
        "primaryDocDescription",
    ]

    n = len(block.get("accessionNumber", []))

    return [
        {
            field: block.get(field, [None] * n)[i]
            for field in fields
        }
        for i in range(n)
    ]


def all_filings(cik: str) -> list[dict]:
    data = get_submissions(cik)

    rows = _rows_from_block(data["filings"]["recent"])

    with httpx.Client(
        headers=_headers(),
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for file_info in data["filings"].get("files", []):
            name = file_info["name"]
            url = f"{BASE_URL}/{name}"

            response = client.get(url)
            response.raise_for_status()

            rows.extend(_rows_from_block(response.json()))

    return rows


FILINGS_CACHE_DIR = Path("data/external/sec/filings")


def get_filing_document(
    cik: str,
    accession_number: str,
    primary_document: str,
    refresh: bool = False,
) -> dict:
    cik_int = str(int(normalize_cik(cik)))
    accession_compact = accession_number.replace("-", "")

    FILINGS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_path = (
        FILINGS_CACHE_DIR
        / cik_int
        / accession_compact
        / primary_document
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    url = (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_int}/{accession_compact}/{primary_document}"
    )

    if not cache_path.exists() or refresh:
        with httpx.Client(
            headers=_headers(),
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        cache_path.write_bytes(response.content)

    content = cache_path.read_bytes()

    import hashlib

    return {
        "url": url,
        "cache_path": str(cache_path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "content": content,
    }
