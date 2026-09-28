import duckdb

from open_equity_data.populate_glspt_manual_shares import stage


def test_glspt_stages_each_priced_date_with_redemption_boundary():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("""
        CREATE TABLE silver.security_daily_ohlcv_reconciled AS
        SELECT 99 AS security_id, 'GLSPT' AS ticker,
               d::DATE AS date
        FROM UNNEST(['2021-05-10', '2022-04-14', '2022-04-15',
                     '2022-07-13']) t(d)
    """)
    con.execute("""
        CREATE TABLE silver.security_ticker_reference_resolution AS
        SELECT 99 AS security_id, 'GLSPT' AS ticker,
               'Global SPAC Partners Co Subunit' AS bronze_security_name
    """)
    con.execute("""
        CREATE TABLE silver.security_shares_outstanding_effective AS
        SELECT 'GLSPT' AS ticker, 'GLSPT.US' AS provider_symbol,
               DATE '2022-03-31' AS period_date,
               DATE '2022-05-10' AS filing_date,
               16750000000000.0 AS shares_outstanding
    """)
    summary, last = stage(con)
    assert [row[2] for row in summary] == [2, 2]
    assert last[0][2:4] == (12948213.0, 16750000000000.0)
    assert con.execute("""
        SELECT price_date, sourced_shares, target_shares
        FROM glspt_manual_stage ORDER BY price_date
    """).fetchall() == [
        (duckdb.sql("SELECT DATE '2021-05-10'").fetchone()[0],
         16750000.0, None),
        (duckdb.sql("SELECT DATE '2022-04-14'").fetchone()[0],
         16750000.0, None),
        (duckdb.sql("SELECT DATE '2022-04-15'").fetchone()[0],
         12948213.0, None),
        (duckdb.sql("SELECT DATE '2022-07-13'").fetchone()[0],
         12948213.0, 16750000000000.0),
    ]
