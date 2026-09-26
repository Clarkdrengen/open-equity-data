from io import BytesIO
from zipfile import ZipFile

import duckdb

from open_equity_data.audit_msci_m15d_name_isin_consistency import build
from open_equity_data.build_msci_m15d_rif_silver import observations
from open_equity_data.load_msci_m15d_rif_bronze import archive


def rif_zip(blank_last_field=False):
    keys = ['calc_date', 'security_name', 'msci_timeseries_code',
            'msci_issuer_code', 'msci_security_code', 'sedol', 'cusip', 'isin']
    if blank_last_field:
        keys.append('RIC')
    definitions = [
        f'# {i:2d} {key.replace("_", " "):<33} {key:<30} '
        f'{"D" if i == 1 else "S" if i in (2, 6, 7, 8) else "N"} {12:3d} {0:2d}'.ljust(78)
        for i, key in enumerate(keys, 1)
    ]
    values = ['20180930', 'ACME CLASS A', '12345', '100', '200', '', '',
              'US0378331005']
    if blank_last_field:
        values.append('')
    payload = ('*\r\n' + '\r\n'.join(definitions) + '\r\n' +
               '|' + '|'.join(values) + ('\r\n' if blank_last_field else '|\r\n')).encode('latin-1')
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        z.writestr('m15d_rif', payload)
    return out.getvalue()


def test_rif_exact_archive_and_name_isin_price_match(tmp_path):
    raw = rif_zip()
    (tmp_path / '2018_m15d_rif.zip').write_bytes(raw)
    con = duckdb.connect()
    assert archive(con, tmp_path) == (1, 1)
    assert archive(con, tmp_path) == (1, 0)
    assert bytes(con.execute('SELECT raw_archive_bytes FROM bronze.msci_m15d_rif_source_archive').fetchone()[0]) == raw
    assert list(observations(raw, 'test'))[0][-1] == 'valid_isin'
    con.execute('CREATE SCHEMA silver')
    con.execute('''
        CREATE TABLE silver.msci_m15d_security_observation AS
        SELECT DATE '2018-09-30' AS observation_date,
               '200' AS msci_security_code, 'ACME CLASS A' AS security_name,
               '100' AS msci_issuer_code, '12345' AS msci_timeseries_code,
               1000000.0 AS shares_today, 1200000.0 AS closing_shares,
               '0.8000' AS scap_fif_raw, '1.0000' AS historical_gimi_fif_raw
    ''')
    con.execute('''
        CREATE TABLE silver.msci_m15d_rif_observation AS
        SELECT DATE '2018-09-30' AS observation_date,
               '200' AS msci_security_code, 'Acme Class A' AS security_name,
               '100' AS msci_issuer_code, '12345' AS msci_timeseries_code,
               'US0378331005' AS isin, 'valid_isin' AS parse_status
    ''')
    con.execute('''
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'AAPL' AS ticker,
               'US0378331005' AS isin, TRUE AS primary_research_eligible_exchange
    ''')
    con.execute('''
        CREATE TABLE silver.security_daily_ohlcv AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'AAPL' AS ticker,
               50.0 AS close
    ''')
    statuses, overlap = build(con)
    assert statuses[0][0:3] == ('candidate_exact_code_name', 1, 1)
    assert overlap[0][0:4] == ('candidate_exact_code_name', 1, 1, 0)
    assert con.execute('''
        SELECT isin, shares_today, closing_shares, price_date
        FROM silver.msci_m15d_price_overlap_candidate
    ''').fetchone() == ('US0378331005', 1000000.0, 1200000.0,
                      __import__('datetime').date(2018, 9, 28))


def test_blank_last_rif_field_is_not_removed():
    rows = list(observations(rif_zip(blank_last_field=True), 'source'))
    assert len(rows) == 1
    assert rows[0][-2:] == ('', 'valid_isin')


def test_name_disagreement_is_reported_without_approving_identity():
    con = duckdb.connect()
    con.execute('CREATE SCHEMA silver')
    con.execute('''
        CREATE TABLE silver.msci_m15d_security_observation AS
        SELECT DATE '2018-09-30' AS observation_date, '200' AS msci_security_code,
               'ACME' AS security_name, '100' AS msci_issuer_code,
               '12345' AS msci_timeseries_code, 100.0 AS shares_today,
               100.0 AS closing_shares, '0.8000' AS scap_fif_raw,
               '1.0000' AS historical_gimi_fif_raw
    ''')
    con.execute('''
        CREATE TABLE silver.msci_m15d_rif_observation AS
        SELECT DATE '2018-09-30' AS observation_date, '200' AS msci_security_code,
               'OTHER' AS security_name, '100' AS msci_issuer_code,
               '12345' AS msci_timeseries_code, 'US0378331005' AS isin,
               'valid_isin' AS parse_status
    ''')
    con.execute('''
        CREATE TABLE silver.research_universe_eligibility AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'AAPL' AS ticker,
               'US0378331005' AS isin, TRUE AS primary_research_eligible_exchange
    ''')
    con.execute('''
        CREATE TABLE silver.security_daily_ohlcv AS
        SELECT 1 AS security_id, DATE '2018-09-28' AS date, 'AAPL' AS ticker,
               50.0 AS close
    ''')
    statuses, _ = build(con)
    assert statuses[0][0:3] == ('name_review', 1, 0)
