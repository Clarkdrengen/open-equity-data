"""
Resolve raw SEC XBRL shares-outstanding facts into issuer-level observations.

Resolution philosophy
---------------------
The output represents issuer common-equity shares outstanding as known
point-in-time.

Priority:

1. dei:EntityCommonStockSharesOutstanding
   - normally the filing cover-page observation
   - if multiple stock-class facts share the same as-of date, sum classes

2. us-gaap:CommonStockSharesOutstanding
   - prefer an undimensioned issuer-total observation
   - otherwise sum class-dimensional observations for the same as-of date

Weighted-average shares and shares issued are never substitutes for
point-in-time shares outstanding.

Availability is governed by filing_date, not shares_as_of_date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from open_equity_data.sec_shares import (
    SharesOutstandingFact,
)


@dataclass(frozen=True)
class ResolvedSharesObservation:
    cik: str
    filing_date: date
    accession_number: str
    form: str

    shares_as_of_date: date
    shares_outstanding: float

    resolution_method: str
    component_count: int
    source_concept: str

    def as_dict(self) -> dict:
        return {
            "cik": self.cik,
            "filing_date": self.filing_date,
            "accession_number": self.accession_number,
            "form": self.form,
            "shares_as_of_date": self.shares_as_of_date,
            "shares_outstanding": self.shares_outstanding,
            "resolution_method": self.resolution_method,
            "component_count": self.component_count,
            "source_concept": self.source_concept,
        }


def deduplicate_facts(
    facts: list[SharesOutstandingFact],
) -> list[SharesOutstandingFact]:
    """
    Remove exact semantic duplicates from a filing.
    """

    seen = set()
    result = []

    for fact in facts:
        key = (
            fact.cik,
            fact.filing_date,
            fact.accession_number,
            fact.shares_as_of_date,
            fact.taxonomy,
            fact.concept,
            fact.class_member,
            float(fact.shares_outstanding),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(fact)

    return result


def _same_latest_date(
    facts: list[SharesOutstandingFact],
) -> list[SharesOutstandingFact]:
    usable = [
        fact
        for fact in facts
        if fact.shares_as_of_date is not None
        and fact.shares_outstanding is not None
        and fact.shares_outstanding > 0
    ]

    if not usable:
        return []

    latest = max(
        fact.shares_as_of_date
        for fact in usable
    )

    return [
        fact
        for fact in usable
        if fact.shares_as_of_date == latest
    ]


def resolve_filing_shares(
    facts: list[SharesOutstandingFact],
) -> ResolvedSharesObservation | None:
    """
    Resolve one filing's facts into one issuer-total shares observation.
    """

    facts = deduplicate_facts(facts)

    if not facts:
        return None

    # --------------------------------------------------------
    # 1. DEI cover-page facts
    # --------------------------------------------------------

    dei = [
        fact
        for fact in facts
        if fact.taxonomy == "dei"
        and fact.concept
        == "EntityCommonStockSharesOutstanding"
    ]

    dei = _same_latest_date(dei)

    if dei:
        # If the filing reports several classes on the same date,
        # total issuer common shares are the sum of those classes.
        total = sum(
            float(fact.shares_outstanding)
            for fact in dei
        )

        first = dei[0]

        method = (
            "dei_single"
            if len(dei) == 1
            else "dei_sum_classes"
        )

        return ResolvedSharesObservation(
            cik=first.cik,
            filing_date=first.filing_date,
            accession_number=first.accession_number,
            form=first.form,
            shares_as_of_date=first.shares_as_of_date,
            shares_outstanding=total,
            resolution_method=method,
            component_count=len(dei),
            source_concept=
                "dei:EntityCommonStockSharesOutstanding",
        )

    # --------------------------------------------------------
    # 2. GAAP shares outstanding
    # --------------------------------------------------------

    gaap = [
        fact
        for fact in facts
        if fact.taxonomy == "us-gaap"
        and fact.concept
        == "CommonStockSharesOutstanding"
    ]

    gaap = _same_latest_date(gaap)

    if not gaap:
        return None

    # Prefer an undimensioned issuer-total fact.
    undimensioned = [
        fact
        for fact in gaap
        if fact.class_member is None
    ]

    if undimensioned:
        # Multiple identical observations should already have been
        # deduplicated. If differing values remain, do not guess.
        values = {
            float(fact.shares_outstanding)
            for fact in undimensioned
        }

        if len(values) != 1:
            return None

        first = undimensioned[0]

        return ResolvedSharesObservation(
            cik=first.cik,
            filing_date=first.filing_date,
            accession_number=first.accession_number,
            form=first.form,
            shares_as_of_date=first.shares_as_of_date,
            shares_outstanding=next(iter(values)),
            resolution_method=
                "gaap_undimensioned",
            component_count=1,
            source_concept=
                "us-gaap:CommonStockSharesOutstanding",
        )

    # Otherwise sum the explicitly reported stock classes.
    first = gaap[0]

    return ResolvedSharesObservation(
        cik=first.cik,
        filing_date=first.filing_date,
        accession_number=first.accession_number,
        form=first.form,
        shares_as_of_date=first.shares_as_of_date,
        shares_outstanding=sum(
            float(fact.shares_outstanding)
            for fact in gaap
        ),
        resolution_method=
            "gaap_sum_classes",
        component_count=len(gaap),
        source_concept=
            "us-gaap:CommonStockSharesOutstanding",
    )
