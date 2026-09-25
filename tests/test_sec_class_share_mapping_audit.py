from datetime import date

from open_equity_data.audit_sec_class_share_mapping import (
    Candidate,
    classify_unmapped,
)


def candidate(member, when, symbol=None, cik="1"):
    return Candidate(
        cik=cik,
        entity_name="Example",
        class_member=member,
        filing_date=date.fromisoformat(when),
        accession_number=when,
        shares_as_of_date=date.fromisoformat(when),
        trading_symbol=symbol,
        symbol_mapping_status=(
            "mapped_unique_symbol" if symbol else "no_trading_symbol"
        ),
    )


def test_audit_preserves_temporal_and_issuer_boundaries():
    rows = [
        candidate("A", "2020-01-01", "AAA"),
        candidate("A", "2021-01-01"),
        candidate("A", "2022-01-01", "AAA"),
        candidate("A", "2019-01-01"),
        candidate("A", "2023-01-01"),
        candidate("B", "2021-01-01"),
        candidate("A", "2021-01-01", cik="2"),
    ]
    result = classify_unmapped(rows)
    assert [(status, symbol) for _, status, symbol in result] == [
        ("bracketed_same_symbol", "AAA"),
        ("later_evidence_only", "AAA"),
        ("earlier_evidence_only", "AAA"),
        ("no_symbol_evidence", None),
        ("no_symbol_evidence", None),
    ]


def test_changed_symbol_is_not_carried_across_history():
    rows = [
        candidate("A", "2020-01-01", "OLD"),
        candidate("A", "2021-01-01"),
        candidate("A", "2022-01-01", "NEW"),
    ]
    assert classify_unmapped(rows)[0][1:] == (
        "multiple_historical_symbols", None
    )
