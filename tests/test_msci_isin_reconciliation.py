import duckdb

from open_equity_data.audit_msci_isin_reconciliation import (
    read_panel, references, valid_isin,
)
from open_equity_data.load_msci_usa_bronze import archive
from open_equity_data.build_msci_usa_silver import build


def test_unquoted_name_comma_and_duplicate_conflict_are_visible(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text(
        ",Date,ISIN,CompanyName,MktCap\n"
        "1,2018-08-31,US0758871091,BECTON, DICKINSON,100.5\n"
        "2,2018-09-30,US0758871091,BECTON DICKINSON,120.0\n"
        "3,2018-09-30,US0758871091,BECTON DICKINSON,125.0\n"
        "4,2018-09-30,NA,NA,NA\n"
        "5,2018-09-30,,MISSING,30\n"
    )
    raw = source.read_bytes()
    con = duckdb.connect()
    digest = archive(con, source)
    assert bytes(con.execute("SELECT raw_file_bytes FROM bronze.msci_usa_source_file").fetchone()[0]) == raw
    assert archive(con, source) == digest
    assert con.execute("SELECT COUNT(*) FROM bronze.msci_usa_source_file").fetchone()[0] == 1
    assert build(con) == (digest, 5)
    assert build(con) == (digest, 5)
    assert con.execute("SELECT COUNT(*) FROM silver.msci_usa_observation").fetchone()[0] == 5
    assert con.execute("""
        SELECT raw_company_name FROM silver.msci_usa_observation WHERE source_row_number = 2
    """).fetchone()[0] == 'BECTON, DICKINSON'
    history, counts, invalid, duplicates = read_panel(con, digest)
    assert valid_isin("US0758871091")
    assert not valid_isin("06181104W")
    assert counts["unquoted_name_commas"] == 1
    assert counts["na_padding_rows"] == 1
    assert counts["blank_isin_rows"] == 1
    assert counts["duplicate_date_isin_rows"] == 1
    assert history["US0758871091"].names == {"BECTON, DICKINSON", "BECTON DICKINSON"}
    assert history["US0758871091"].conflicting_duplicate
    assert len(duplicates) == 1
    assert not invalid


def test_reference_join_is_exact_isin_and_retains_multiple_security_ids():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA bronze")
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE bronze.eodhd_symbol_reference AS
        SELECT * FROM (VALUES
          ('US0378331005', 'Apple Inc', 'AAPL'),
          ('US0378331005', 'Apple Computer', 'AAPL_OLD'),
          ('US67066G1040', 'NVIDIA Corporation', 'NVDA')
        ) v(isin, name, code)
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT * FROM (VALUES
          ('US0378331005', 1, 'AAPL'),
          ('US0378331005', 2, 'AAPL'),
          ('US67066G1040', 3, 'NVDA')
        ) v(resolved_isin, security_id, ticker)
    """)
    names, tickers, ids = references(con)
    assert names['US0378331005'] == {'Apple Inc', 'Apple Computer'}
    assert tickers['US0378331005'] == {'AAPL', 'AAPL_OLD'}
    assert ids['US0378331005'] == {'1', '2'}
