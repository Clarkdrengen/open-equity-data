from io import BytesIO
from zipfile import ZipFile

import duckdb
import pytest

from open_equity_data.audit_msci_rif_share_candidates import build as audit
from open_equity_data.build_msci_rif_share_candidates import build, observations
from open_equity_data.load_msci_m15d_rif_bronze import archive


def fixture_zip(closing="1000000.0000"):
    keys = [
        "calc_date", "security_name", "msci_timeseries_code",
        "msci_issuer_code", "msci_security_code", "isin", "price",
        "price_ISO_currency_symbol", "eod_number_of_shares_today",
        "eod_number_of_shares_next_day", "closing_number_of_shares",
        "unadj_market_cap_today_usdol",
    ]
    definitions = [
        f'# {i:2d} {key.replace("_", " "):<33} {key:<30} '
        f'{"D" if i == 1 else "S" if i in (2, 6, 8) else "N"} {16:3d} {4:2d}'.ljust(78)
        for i, key in enumerate(keys, 1)
    ]
    values = [
        "20180930", "ACME CLASS A", "12345", "100", "200",
        "US0378331005", "50.0000", "USD", "1000000.0000",
        "1000001.0000", closing, "",
    ]
    payload = ("*\r\n" + "\r\n".join(definitions) + "\r\n" +
               "|" + "|".join(values) + "\r\n").encode("latin-1")
    out = BytesIO()
    with ZipFile(out, "w") as z:
        z.writestr("synthetic_rif", payload)
    return out.getvalue()


@pytest.mark.parametrize("family", ["m15d", "m15e"])
def test_rif_shares_source_backed_and_dated_candidate(tmp_path, family):
    raw = fixture_zip()
    (tmp_path / f"one_{family}_rif.zip").write_bytes(raw)
    con = duckdb.connect()
    assert archive(con, tmp_path, family=family) == (1, 1)
    assert bytes(con.execute(f"""
        SELECT raw_archive_bytes FROM bronze.msci_{family}_rif_source_archive
    """).fetchone()[0]) == raw
    counts = build(con, family)
    assert counts["shares_present"] == counts["archives"] == 1
    assert build(con, family)["already_built"] == 1
    assert con.execute(f"""
        SELECT closing_shares, shares_today, price_currency
        FROM silver.msci_{family}_rif_share_observation
    """).fetchone() == (1_000_000.0, 1_000_000.0, "USD")

    con.execute(f"""
        CREATE TABLE silver.msci_{family}_price_overlap_candidate AS
        SELECT DATE '2018-09-30' AS observation_date, '200' AS msci_security_code,
               'US0378331005' AS isin, 1 AS security_id, 'ACME' AS ticker,
               DATE '2018-09-28' AS price_date,
               'candidate_exact_code_name' AS identity_status,
               1 AS project_security_matches
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'ACME' AS ticker,
               1000.0 AS shares_outstanding, DATE '2018-08-01' AS shares_period_date,
               DATE '2018-08-03' AS shares_filing_date, TRUE AS shares_pit_available,
               FALSE AS ticker_identity_ambiguous
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_split_factor_reconciled AS
        SELECT 1 AS security_id, DATE '2018-09-01' AS date,
               1.0 AS daily_split_ratio WHERE FALSE
    """)
    summary = audit(con, family)
    assert summary[:8] == (1, 1, 1, 1, 1, 1, 1, 1)
    assert summary[8:10] == (1, 0)
    assert con.execute(f"""
        SELECT closing_to_eodhd_ratio FROM silver.msci_{family}_rif_share_overlap_audit
    """).fetchone()[0] == 1000.0


def test_invalid_rif_share_number_has_lineage():
    row = list(observations(fixture_zip(closing="not-a-number"), "digest"))[0]
    assert row[0] == "digest"
    assert row[13] == "not-a-number"
    assert row[-1] == "invalid_number"
