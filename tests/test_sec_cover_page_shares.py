from datetime import date

from open_equity_data.sec_cover_page_shares import extract_cover_shares


def test_two_column_cover_table_preserves_asof_and_class():
    html = b"""
    <p>Indicated below is the number of shares outstanding of each class,
       as of May 6, 2019.</p>
    <table>
      <tr><th>Class</th><th>Number of Shares Outstanding</th></tr>
      <tr><td>Class A Common Stock, $.01 Par Value</td><td>28,212,301</td></tr>
      <tr><td>Class B Common Stock, $.01 Par Value</td><td>8,448,669</td></tr>
    </table>
    """
    rows = extract_cover_shares(html)
    assert [(r.class_label, r.shares_outstanding, r.as_of_date) for r in rows] == [
        ("Class A Common Stock, $.01 Par Value", 28212301, date(2019, 5, 6)),
        ("Class B Common Stock, $.01 Par Value", 8448669, date(2019, 5, 6)),
    ]


def test_cover_matrix_does_not_combine_two_class_a_series():
    html = b"""
    <p>The number of outstanding ordinary shares of Liberty Global plc
       as of May 4, 2016 was:</p>
    <table>
      <tr><th></th><th>Class A</th><th>Class B</th><th>Class C</th></tr>
      <tr><td>Liberty Global ordinary shares</td>
          <td>253,233,390</td><td>10,805,850</td><td>577,324,169</td></tr>
      <tr><td>LiLAC ordinary shares</td>
          <td>12,657,509</td><td>540,089</td><td>30,795,947</td></tr>
    </table>
    """
    rows = extract_cover_shares(html)
    assert len(rows) == 6
    assert {(r.series_label, r.class_label, r.shares_outstanding) for r in rows} >= {
        ("Liberty Global ordinary shares", "Class A", 253233390),
        ("LiLAC ordinary shares", "Class A", 12657509),
    }
    assert all(r.as_of_date == date(2016, 5, 4) for r in rows)


def test_no_date_or_weighted_average_is_not_a_cover_candidate():
    html = b"""
    <table><tr><th>Shares outstanding</th></tr>
      <tr><td>Weighted average common stock</td><td>9,000,000</td></tr>
      <tr><td>Class A common stock</td><td>1,234,567</td></tr>
    </table>
    """
    assert extract_cover_shares(html) == []


def test_central_style_class_b_stock_is_retained_as_reported():
    html = b"""
    <table>
      <tr><th>Common Stock Outstanding as of April 29, 2019</th>
          <td>12,145,135</td></tr>
      <tr><th>Class A Common Stock Outstanding as of April 29, 2019</th>
          <td>44,476,424</td></tr>
      <tr><th>Class B Stock Outstanding as of April 29, 2019</th>
          <td>1,652,262</td></tr>
    </table>
    """
    rows = extract_cover_shares(html)
    assert [r.shares_outstanding for r in rows] == [12145135, 44476424, 1652262]
