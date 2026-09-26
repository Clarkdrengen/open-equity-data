from io import BytesIO
from zipfile import ZipFile

import duckdb

from open_equity_data.build_msci_m15d_silver import build, observations
from open_equity_data.load_msci_m15d_bronze import archive


FIELDS = [
    'calc_date', 'security_name', 'msci_timeseries_code', 'msci_issuer_code',
    'msci_security_code', 'msci_old_industry_code', 'historical_GIMI_FIF',
    'historical_GIMI_DIF', 'family_prov_std_flag', 'family_prov_scap_flag',
    'EURO_series_flag', 'family_prov_std_dom_flag',
    'family_prov_scap_dom_flag', 'scap_foreign_inclusion_factor',
    'scap_number_of_shares_today', 'scap_closing_number_of_shares',
    'free_family_std_flag',
]


def fixture_zip(blank_final_field=False):
    definitions = [
        f'# {i:2d} {key.replace("_", " "):<33} {key:<30} '
        f'{"D" if i == 1 else "S" if i == 2 else "N"} {16:3d} {4:2d}'.ljust(78)
        for i, key in enumerate(FIELDS, 1)
    ]
    values = ['20091231', 'ACME CLASS A', '12345', '100', '200', '1',
              '1.0000', '1.0000', '0', '1', '0', '0', '0', '0.8000',
              '1000000.0000', '1200000.0000', '0']
    if blank_final_field:
        values[-1] = ''
    data = ('*\r\n' + '\r\n'.join(definitions) + '\r\n' +
            '|' + '|'.join(values) + ('\r\n' if blank_final_field else '|\r\n')).encode('latin-1')
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        z.writestr('sample_m15d.extension', data)
    return out.getvalue()


def test_exact_zip_in_bronze_and_security_shares_derived_in_silver(tmp_path):
    raw = fixture_zip()
    (tmp_path / '2009_m15d.extension.zip').write_bytes(raw)
    (tmp_path / '2009_m15d_rif.zip').write_bytes(raw)
    con = duckdb.connect()
    assert archive(con, tmp_path) == (1, 1)
    assert archive(con, tmp_path) == (1, 0)
    assert bytes(con.execute('SELECT raw_archive_bytes FROM bronze.msci_m15d_source_archive').fetchone()[0]) == raw
    derived = list(observations(raw, 'source'))
    assert len(derived) == 1
    assert derived[0][-3:] == (1_000_000.0, 1_200_000.0, 'shares_present')
    result = build(con)
    assert result['archives'] == result['shares_present'] == 1
    assert con.execute('''
        SELECT msci_security_code, shares_today, closing_shares
        FROM silver.msci_m15d_security_observation
    ''').fetchone() == ('200', 1_000_000.0, 1_200_000.0)


def test_blank_last_m15d_field_is_not_removed():
    rows = list(observations(fixture_zip(blank_final_field=True), 'source'))
    assert len(rows) == 1
    assert rows[0][-3:] == (1_000_000.0, 1_200_000.0, 'shares_present')
