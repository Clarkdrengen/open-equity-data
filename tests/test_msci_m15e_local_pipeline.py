from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

import duckdb
import pytest

from open_equity_data.build_msci_m15e_rif_silver import build as build_rif
from open_equity_data.build_msci_m15e_silver import build as build_extension
from open_equity_data.audit_msci_m15e_name_isin_consistency import build as audit_identity
from open_equity_data.audit_msci_m15e_share_discrepancies import build as audit_shares
from open_equity_data.load_msci_m15e_bronze import archive as archive_extension
from open_equity_data.load_msci_m15e_rif_bronze import archive as archive_rif
from test_msci_m15d_local_pipeline import fixture_zip
from test_msci_m15d_rif_consistency import rif_zip


def test_m15e_archive_and_silver_are_separate_from_m15d(tmp_path: Path):
    extension = fixture_zip(blank_final_field=True)
    rif = rif_zip(blank_last_field=True)
    (tmp_path / "one_m15e.extension.zip").write_bytes(extension)
    (tmp_path / "one_m15e_rif.zip").write_bytes(rif)
    (tmp_path / "one_m15d.extension.zip").write_bytes(extension)
    (tmp_path / "one_m15d_rif.zip").write_bytes(rif)
    con = duckdb.connect()

    assert archive_extension(con, tmp_path) == (1, 1)
    assert archive_rif(con, tmp_path) == (1, 1)
    assert archive_extension(con, tmp_path) == (1, 0)
    assert bytes(con.execute(
        "SELECT raw_archive_bytes FROM bronze.msci_m15e_source_archive"
    ).fetchone()[0]) == extension
    assert bytes(con.execute(
        "SELECT raw_archive_bytes FROM bronze.msci_m15e_rif_source_archive"
    ).fetchone()[0]) == rif
    assert build_extension(con)["shares_present"] == 1
    assert build_rif(con)["valid_isin"] == 1
    assert con.execute("""
        SELECT closing_shares FROM silver.msci_m15e_security_observation
    """).fetchone()[0] == 1_200_000
    assert con.execute("""
        SELECT isin FROM silver.msci_m15e_rif_observation
    """).fetchone()[0] == "US0378331005"
    assert build_extension(con)["already_built"] == 1
    with pytest.raises(duckdb.CatalogException):
        con.execute("SELECT * FROM silver.msci_m15d_security_observation")


def test_m15e_schema_difference_fails_without_silver_rows(tmp_path: Path):
    # The real M15E dictionary is checked at build time; source bytes remain Bronze.
    with ZipFile(BytesIO(fixture_zip())) as source:
        member = source.namelist()[0]
        payload = source.read(member).replace(
            b"scap_number_of_shares_today", b"alternative_shares_today   "
        )
    out = BytesIO()
    with ZipFile(out, "w") as target:
        target.writestr(member, payload)
    raw = out.getvalue()
    (tmp_path / "one_m15e.extension.zip").write_bytes(raw)
    con = duckdb.connect()
    assert archive_extension(con, tmp_path) == (1, 1)
    with pytest.raises(ValueError, match="Unexpected MSCI extension dictionary"):
        build_extension(con)
    assert con.execute("""
        SELECT COUNT(*) FROM silver.msci_m15e_security_observation
    """).fetchone()[0] == 0


def test_m15e_join_and_share_audit_stay_in_candidate_tables(tmp_path: Path):
    with ZipFile(BytesIO(fixture_zip())) as source:
        member = source.namelist()[0]
        payload = source.read(member).replace(b"20091231", b"20180930")
    out = BytesIO()
    with ZipFile(out, "w") as target:
        target.writestr(member, payload)
    (tmp_path / "one_m15e.extension.zip").write_bytes(out.getvalue())
    (tmp_path / "one_m15e_rif.zip").write_bytes(rif_zip())
    con = duckdb.connect()
    archive_extension(con, tmp_path)
    archive_rif(con, tmp_path)
    build_extension(con)
    build_rif(con)
    con.execute("""
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'ACME' AS ticker,
               'US0378331005' AS isin, TRUE AS primary_research_eligible_exchange
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'ACME' AS ticker,
               50.0 AS close
    """)
    statuses, overlap = audit_identity(con)
    assert statuses[0][:2] == ('candidate_exact_code_name', 1)
    assert overlap[0][:3] == ('candidate_exact_code_name', 1, 1)
    con.execute("""
        CREATE TABLE silver.security_daily_shares_outstanding_pit AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'ACME' AS ticker,
               1000.0 AS shares_outstanding, DATE '2018-09-15' AS shares_period_date,
               DATE '2018-09-20' AS shares_filing_date, 8 AS shares_age_days,
               TRUE AS shares_pit_available, FALSE AS ticker_identity_ambiguous
    """)
    con.execute("""
        CREATE TABLE silver.security_daily_split_factor_reconciled AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date,
               1.0 AS daily_split_ratio WHERE FALSE
    """)
    rows = audit_shares(con)
    assert rows[0][:5] == ('candidate_exact_code_name', 'near_1000x_high',
                            'near_1000x_high', 1, 1)
