from datetime import date

from open_equity_data.sec_shares import (
    SharesOutstandingFact,
)
from open_equity_data.sec_shares_resolver import (
    deduplicate_facts,
    resolve_filing_shares,
)


def fact(
    *,
    taxonomy,
    concept,
    shares,
    as_of,
    member=None,
):
    return SharesOutstandingFact(
        cik="0001326801",
        filing_date=date(2026, 7, 30),
        accession_number="test-accession",
        form="10-Q",
        primary_document="test.htm",
        shares_as_of_date=as_of,
        shares_outstanding=shares,
        taxonomy=taxonomy,
        concept=concept,
        context_id="ctx",
        class_axis=(
            "us-gaap:StatementClassOfStockAxis"
            if member
            else None
        ),
        class_member=member,
    )


def test_meta_style_dei_classes_are_summed():
    facts = [
        fact(
            taxonomy="dei",
            concept=
                "EntityCommonStockSharesOutstanding",
            shares=2_205_128_509,
            as_of=date(2026, 7, 24),
            member=
                "us-gaap:CommonClassAMember",
        ),
        fact(
            taxonomy="dei",
            concept=
                "EntityCommonStockSharesOutstanding",
            shares=342_377_716,
            as_of=date(2026, 7, 24),
            member=
                "us-gaap:CommonClassBMember",
        ),
    ]

    result = resolve_filing_shares(facts)

    assert result is not None

    assert (
        result.shares_outstanding
        == 2_547_506_225
    )

    assert (
        result.resolution_method
        == "dei_sum_classes"
    )

    assert result.component_count == 2


def test_dei_has_priority_over_gaap():
    facts = [
        fact(
            taxonomy="dei",
            concept=
                "EntityCommonStockSharesOutstanding",
            shares=100,
            as_of=date(2026, 7, 24),
        ),
        fact(
            taxonomy="us-gaap",
            concept=
                "CommonStockSharesOutstanding",
            shares=999,
            as_of=date(2026, 6, 30),
        ),
    ]

    result = resolve_filing_shares(facts)

    assert result is not None
    assert result.shares_outstanding == 100
    assert result.resolution_method == "dei_single"


def test_gaap_undimensioned_is_preferred():
    facts = [
        fact(
            taxonomy="us-gaap",
            concept=
                "CommonStockSharesOutstanding",
            shares=1_000,
            as_of=date(2026, 6, 30),
        ),
        fact(
            taxonomy="us-gaap",
            concept=
                "CommonStockSharesOutstanding",
            shares=700,
            as_of=date(2026, 6, 30),
            member=
                "us-gaap:CommonClassAMember",
        ),
        fact(
            taxonomy="us-gaap",
            concept=
                "CommonStockSharesOutstanding",
            shares=300,
            as_of=date(2026, 6, 30),
            member=
                "us-gaap:CommonClassBMember",
        ),
    ]

    result = resolve_filing_shares(facts)

    assert result is not None
    assert result.shares_outstanding == 1_000
    assert (
        result.resolution_method
        == "gaap_undimensioned"
    )


def test_gaap_classes_are_summed_without_total():
    facts = [
        fact(
            taxonomy="us-gaap",
            concept=
                "CommonStockSharesOutstanding",
            shares=700,
            as_of=date(2026, 6, 30),
            member=
                "us-gaap:CommonClassAMember",
        ),
        fact(
            taxonomy="us-gaap",
            concept=
                "CommonStockSharesOutstanding",
            shares=300,
            as_of=date(2026, 6, 30),
            member=
                "us-gaap:CommonClassBMember",
        ),
    ]

    result = resolve_filing_shares(facts)

    assert result is not None
    assert result.shares_outstanding == 1_000
    assert (
        result.resolution_method
        == "gaap_sum_classes"
    )


def test_exact_duplicates_are_removed():
    x = fact(
        taxonomy="us-gaap",
        concept=
            "CommonStockSharesOutstanding",
        shares=1_000,
        as_of=date(2026, 6, 30),
    )

    result = deduplicate_facts(
        [x, x]
    )

    assert len(result) == 1
