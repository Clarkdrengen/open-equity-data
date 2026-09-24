import hashlib
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


load_dotenv()


SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
COMPANYFACTS_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
SEC_FILES_BASE_URL = "https://www.sec.gov/files"
ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"


SUBMISSIONS_CACHE_DIR = Path(
    "data/external/sec/submissions"
)

COMPANYFACTS_CACHE_DIR = Path(
    "data/external/sec/companyfacts"
)

FILINGS_CACHE_DIR = Path(
    "data/external/sec/filings"
)

TICKER_CACHE_PATH = Path(
    "data/external/sec/company_tickers.json"
)


def _user_agent() -> str:
    value = os.environ.get("SEC_USER_AGENT")

    if not value:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. "
            "Example: 'OpenEquityData name@example.com'"
        )

    return value


def normalize_cik(cik: str | int) -> str:
    return (
        str(cik)
        .replace("CIK", "")
        .zfill(10)
    )


def _headers() -> dict:
    return {
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }


def _get_json(
    url: str,
) -> dict:
    with httpx.Client(
        headers=_headers(),
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def get_submissions(
    cik: str,
    refresh: bool = False,
) -> dict:
    cik = normalize_cik(cik)

    SUBMISSIONS_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache_path = (
        SUBMISSIONS_CACHE_DIR
        / f"CIK{cik}.json"
    )

    if (
        cache_path.exists()
        and not refresh
    ):
        return json.loads(
            cache_path.read_text()
        )

    url = (
        f"{SUBMISSIONS_BASE_URL}/"
        f"CIK{cik}.json"
    )

    data = _get_json(url)

    cache_path.write_text(
        json.dumps(
            data,
            indent=2,
        )
    )

    return data


def get_company_facts(
    cik: str,
    refresh: bool = False,
) -> dict:
    """
    Return SEC XBRL Company Facts for one issuer.

    Cached locally by normalized CIK.
    """

    cik = normalize_cik(cik)

    COMPANYFACTS_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache_path = (
        COMPANYFACTS_CACHE_DIR
        / f"CIK{cik}.json"
    )

    if (
        cache_path.exists()
        and not refresh
    ):
        return json.loads(
            cache_path.read_text()
        )

    url = (
        f"{COMPANYFACTS_BASE_URL}/"
        f"CIK{cik}.json"
    )

    data = _get_json(url)

    cache_path.write_text(
        json.dumps(
            data,
            indent=2,
        )
    )

    return data


def get_company_tickers(
    refresh: bool = False,
) -> dict:
    """
    SEC current ticker -> CIK reference.
    """

    TICKER_CACHE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if (
        TICKER_CACHE_PATH.exists()
        and not refresh
    ):
        return json.loads(
            TICKER_CACHE_PATH.read_text()
        )

    url = (
        f"{SEC_FILES_BASE_URL}/"
        "company_tickers.json"
    )

    data = _get_json(url)

    TICKER_CACHE_PATH.write_text(
        json.dumps(
            data,
            indent=2,
        )
    )

    return data


def ticker_to_cik_map(
    refresh: bool = False,
) -> dict[str, str]:
    """
    Current SEC ticker -> normalized CIK mapping.
    """

    raw = get_company_tickers(
        refresh=refresh
    )

    result = {}

    for row in raw.values():
        ticker = (
            str(row["ticker"])
            .upper()
            .strip()
        )

        result[ticker] = normalize_cik(
            row["cik_str"]
        )

    return result


def _rows_from_block(
    block: dict,
) -> list[dict]:
    fields = [
        "accessionNumber",
        "filingDate",
        "reportDate",
        "form",
        "primaryDocument",
        "primaryDocDescription",
    ]

    n = len(
        block.get(
            "accessionNumber",
            [],
        )
    )

    return [
        {
            field:
                block.get(
                    field,
                    [None] * n,
                )[i]
            for field in fields
        }
        for i in range(n)
    ]


def all_filings(
    cik: str,
) -> list[dict]:
    data = get_submissions(cik)

    rows = _rows_from_block(
        data["filings"]["recent"]
    )

    for file_info in (
        data["filings"]
        .get(
            "files",
            [],
        )
    ):
        name = file_info["name"]

        url = (
            f"{SUBMISSIONS_BASE_URL}/"
            f"{name}"
        )

        rows.extend(
            _rows_from_block(
                _get_json(url)
            )
        )

    return rows


def get_filing_document(
    cik: str,
    accession_number: str,
    primary_document: str,
    refresh: bool = False,
) -> dict:
    cik_int = str(
        int(
            normalize_cik(cik)
        )
    )

    accession_compact = (
        accession_number
        .replace("-", "")
    )

    cache_path = (
        FILINGS_CACHE_DIR
        / cik_int
        / accession_compact
        / primary_document
    )

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    url = (
        f"{ARCHIVES_BASE_URL}/"
        f"{cik_int}/"
        f"{accession_compact}/"
        f"{primary_document}"
    )

    if (
        not cache_path.exists()
        or refresh
    ):
        with httpx.Client(
            headers=_headers(),
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        cache_path.write_bytes(
            response.content
        )

    content = (
        cache_path.read_bytes()
    )

    return {
        "url":
            url,

        "cache_path":
            str(cache_path),

        "sha256":
            hashlib.sha256(
                content
            ).hexdigest(),

        "content":
            content,
    }


def common_shares_outstanding_facts(
    cik: str,
    refresh: bool = False,
) -> list[dict]:
    """
    Extract SEC DEI common-shares-outstanding observations.

    We retain every SEC fact observation rather than immediately choosing
    one value. Selection / PIT resolution belongs in Silver.
    """

    data = get_company_facts(
        cik,
        refresh=refresh,
    )

    concept = (
        data
        .get("facts", {})
        .get("dei", {})
        .get(
            "EntityCommonStockSharesOutstanding"
        )
    )

    if not concept:
        return []

    rows = []

    for unit, facts in (
        concept
        .get("units", {})
        .items()
    ):
        for fact in facts:
            rows.append(
                {
                    "cik":
                        normalize_cik(cik),

                    "entity_name":
                        data.get(
                            "entityName"
                        ),

                    "unit":
                        unit,

                    "shares_outstanding":
                        fact.get("val"),

                    "shares_as_of_date":
                        fact.get("end"),

                    "filed_date":
                        fact.get("filed"),

                    "form":
                        fact.get("form"),

                    "accession_number":
                        fact.get("accn"),

                    "frame":
                        fact.get("frame"),
                }
            )

    return rows
