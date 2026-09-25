"""
Parse class-specific shares-outstanding facts from SEC Inline XBRL filings.

The objective is to recover machine-readable observations such as:

    dei:EntityCommonStockSharesOutstanding

together with the XBRL context that identifies the relevant stock class.

This module deliberately does not yet resolve XBRL class members to our
security_id. It only extracts filing facts faithfully.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from bs4 import BeautifulSoup

from open_equity_data.sec import (
    get_filing_document,
    normalize_cik,
)


OUTSTANDING_CONCEPTS = {
    "dei:EntityCommonStockSharesOutstanding",
    "us-gaap:CommonStockSharesOutstanding",
}


@dataclass(frozen=True)
class SharesOutstandingFact:
    cik: str
    filing_date: date
    accession_number: str
    form: str
    primary_document: str

    shares_as_of_date: date | None
    shares_outstanding: int | float

    taxonomy: str
    concept: str

    context_id: str | None
    class_axis: str | None
    class_member: str | None

    source: str = "filing_inline_xbrl"

    def as_dict(self) -> dict:
        return {
            "cik": self.cik,
            "filing_date": self.filing_date,
            "accession_number": self.accession_number,
            "form": self.form,
            "primary_document": self.primary_document,
            "shares_as_of_date": self.shares_as_of_date,
            "shares_outstanding": self.shares_outstanding,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "context_id": self.context_id,
            "class_axis": self.class_axis,
            "class_member": self.class_member,
            "source": self.source,
        }


def _tag_name(tag) -> str:
    return (
        tag.name.lower()
        if getattr(tag, "name", None)
        else ""
    )


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(
            value.strip()
        )
    except ValueError:
        return None


def _parse_numeric_fact(tag) -> int | float:
    """
    Parse an Inline XBRL numeric fact.

    Handles:
      - commas
      - scale
      - sign
    """

    raw = tag.get_text(
        "",
        strip=True,
    )

    raw = (
        raw.replace(",", "")
        .replace("\xa0", "")
        .strip()
    )

    if raw in {"", "-", "—"}:
        raise ValueError(
            "Empty/non-numeric XBRL fact"
        )

    value = float(raw)

    scale = int(
        tag.get("scale", "0")
    )

    value *= 10 ** scale

    if tag.get("sign") == "-":
        value *= -1

    if value.is_integer():
        return int(value)

    return value


def extract_context_metadata(
    soup: BeautifulSoup,
) -> dict[str, dict]:
    """
    Parse XBRL contexts keyed by context id.

    Captures:
      - instant date
      - StatementClassOfStockAxis member where present
    """

    result: dict[str, dict] = {}

    for tag in soup.find_all():
        if not _tag_name(tag).endswith(
            "context"
        ):
            continue

        context_id = tag.get("id")

        if not context_id:
            continue

        instant = None
        class_axis = None
        class_member = None

        for child in tag.find_all():
            name = _tag_name(child)

            if name.endswith("instant"):
                instant = _parse_iso_date(
                    child.get_text(
                        " ",
                        strip=True,
                    )
                )

            if name.endswith(
                "explicitmember"
            ):
                dimension = child.get(
                    "dimension"
                )

                member = child.get_text(
                    " ",
                    strip=True,
                )

                if (
                    dimension
                    and dimension.endswith(
                        "StatementClassOfStockAxis"
                    )
                ):
                    class_axis = dimension
                    class_member = member

        result[context_id] = {
            "shares_as_of_date":
                instant,

            "class_axis":
                class_axis,

            "class_member":
                class_member,
        }

    return result


def extract_shares_outstanding_facts_from_html(
    *,
    html: bytes | str,
    cik: str,
    filing_date: str | date,
    accession_number: str,
    form: str,
    primary_document: str,
) -> list[SharesOutstandingFact]:
    """
    Extract supported shares-outstanding facts from one filing document.
    """

    if isinstance(html, bytes):
        html = html.decode(
            "utf-8",
            errors="ignore",
        )

    if isinstance(
        filing_date,
        str,
    ):
        filing_date = date.fromisoformat(
            filing_date
        )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    contexts = extract_context_metadata(
        soup
    )

    rows: list[
        SharesOutstandingFact
    ] = []

    for tag in soup.find_all():
        name = tag.get("name")

        if name not in OUTSTANDING_CONCEPTS:
            continue

        tag_name = _tag_name(tag)

        # Shares-outstanding concepts are numeric facts.
        # Do not attempt to interpret ix:nonNumeric facts that
        # happen to carry the same concept name.
        if not tag_name.endswith(
            "nonfraction"
        ):
            continue

        # Explicitly nil XBRL facts carry no usable numeric value.
        nil_value = (
            tag.get("xsi:nil")
            or tag.get("nil")
        )

        if (
            nil_value is not None
            and str(nil_value).lower()
            in {"true", "1"}
        ):
            continue

        context_id = tag.get(
            "contextref"
        )

        context = contexts.get(
            context_id,
            {},
        )

        try:
            shares = _parse_numeric_fact(
                tag
            )
        except (TypeError, ValueError):
            # Preserve the filing as source evidence; simply do
            # not promote an unparseable fact into the structured
            # shares-outstanding interpretation.
            continue

        taxonomy, concept = (
            name.split(
                ":",
                1,
            )
        )

        rows.append(
            SharesOutstandingFact(
                cik=normalize_cik(cik),
                filing_date=filing_date,
                accession_number=accession_number,
                form=form,
                primary_document=primary_document,
                shares_as_of_date=context.get(
                    "shares_as_of_date"
                ),
                shares_outstanding=shares,
                taxonomy=taxonomy,
                concept=concept,
                context_id=context_id,
                class_axis=context.get(
                    "class_axis"
                ),
                class_member=context.get(
                    "class_member"
                ),
            )
        )

    return rows


def extract_shares_outstanding_facts_from_filing(
    *,
    cik: str,
    filing_date: str | date,
    accession_number: str,
    form: str,
    primary_document: str,
    refresh: bool = False,
) -> list[SharesOutstandingFact]:
    """
    Download/cache and parse one SEC filing.
    """

    document = get_filing_document(
        cik=cik,
        accession_number=accession_number,
        primary_document=primary_document,
        refresh=refresh,
    )

    return (
        extract_shares_outstanding_facts_from_html(
            html=document["content"],
            cik=cik,
            filing_date=filing_date,
            accession_number=accession_number,
            form=form,
            primary_document=primary_document,
        )
    )


def facts_to_dicts(
    facts: Iterable[
        SharesOutstandingFact
    ],
) -> list[dict]:
    return [
        fact.as_dict()
        for fact in facts
    ]
