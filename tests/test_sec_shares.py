from datetime import date

from open_equity_data.sec_shares import (
    extract_context_metadata,
    extract_shares_outstanding_facts_from_html,
)

from bs4 import BeautifulSoup


META_HTML = b"""
<html>
<body>

<xbrli:context id="c-2">
  <xbrli:entity>
    <xbrli:identifier scheme="http://www.sec.gov/CIK">
      0001326801
    </xbrli:identifier>
    <xbrli:segment>
      <xbrldi:explicitMember
        dimension="us-gaap:StatementClassOfStockAxis">
        us-gaap:CommonClassAMember
      </xbrldi:explicitMember>
    </xbrli:segment>
  </xbrli:entity>
  <xbrli:period>
    <xbrli:instant>2026-07-24</xbrli:instant>
  </xbrli:period>
</xbrli:context>

<xbrli:context id="c-3">
  <xbrli:entity>
    <xbrli:identifier scheme="http://www.sec.gov/CIK">
      0001326801
    </xbrli:identifier>
    <xbrli:segment>
      <xbrldi:explicitMember
        dimension="us-gaap:StatementClassOfStockAxis">
        us-gaap:CommonClassBMember
      </xbrldi:explicitMember>
    </xbrli:segment>
  </xbrli:entity>
  <xbrli:period>
    <xbrli:instant>2026-07-24</xbrli:instant>
  </xbrli:period>
</xbrli:context>

<ix:nonFraction
  unitRef="shares"
  contextRef="c-2"
  decimals="INF"
  name="dei:EntityCommonStockSharesOutstanding"
  scale="0">
  2,205,128,509
</ix:nonFraction>

<ix:nonFraction
  unitRef="shares"
  contextRef="c-3"
  decimals="INF"
  name="dei:EntityCommonStockSharesOutstanding"
  scale="0">
  342,377,716
</ix:nonFraction>

</body>
</html>
"""


FORD_HTML = b"""
<html>
<body>

<xbrli:context id="c-6">
  <xbrli:entity>
    <xbrli:segment>
      <xbrldi:explicitMember
        dimension="us-gaap:StatementClassOfStockAxis">
        us-gaap:CommonStockMember
      </xbrldi:explicitMember>
    </xbrli:segment>
  </xbrli:entity>
  <xbrli:period>
    <xbrli:instant>2026-07-24</xbrli:instant>
  </xbrli:period>
</xbrli:context>

<xbrli:context id="c-7">
  <xbrli:entity>
    <xbrli:segment>
      <xbrldi:explicitMember
        dimension="us-gaap:StatementClassOfStockAxis">
        us-gaap:CommonClassBMember
      </xbrldi:explicitMember>
    </xbrli:segment>
  </xbrli:entity>
  <xbrli:period>
    <xbrli:instant>2026-07-24</xbrli:instant>
  </xbrli:period>
</xbrli:context>

<ix:nonFraction
  unitRef="shares"
  contextRef="c-6"
  name="dei:EntityCommonStockSharesOutstanding"
  scale="0">
  3,916,743,591
</ix:nonFraction>

<ix:nonFraction
  unitRef="shares"
  contextRef="c-7"
  name="dei:EntityCommonStockSharesOutstanding"
  scale="0">
  70,852,076
</ix:nonFraction>

</body>
</html>
"""


def test_context_metadata_extracts_stock_class():
    soup = BeautifulSoup(
        META_HTML,
        "html.parser",
    )

    contexts = extract_context_metadata(
        soup
    )

    assert (
        contexts["c-2"][
            "class_member"
        ]
        == "us-gaap:CommonClassAMember"
    )

    assert (
        contexts["c-3"][
            "class_member"
        ]
        == "us-gaap:CommonClassBMember"
    )

    assert (
        contexts["c-2"][
            "shares_as_of_date"
        ]
        == date(2026, 7, 24)
    )


def test_meta_extracts_both_classes():
    facts = (
        extract_shares_outstanding_facts_from_html(
            html=META_HTML,
            cik="1326801",
            filing_date="2026-07-30",
            accession_number=
                "0001628280-26-050705",
            form="10-Q",
            primary_document=
                "meta-20260630.htm",
        )
    )

    assert len(facts) == 2

    lookup = {
        fact.class_member:
            fact.shares_outstanding
        for fact in facts
    }

    assert (
        lookup[
            "us-gaap:CommonClassAMember"
        ]
        == 2_205_128_509
    )

    assert (
        lookup[
            "us-gaap:CommonClassBMember"
        ]
        == 342_377_716
    )


def test_ford_extracts_common_and_class_b():
    facts = (
        extract_shares_outstanding_facts_from_html(
            html=FORD_HTML,
            cik="37996",
            filing_date="2026-07-29",
            accession_number=
                "0000037996-26-000156",
            form="10-Q",
            primary_document=
                "f-20260630.htm",
        )
    )

    lookup = {
        fact.class_member:
            fact.shares_outstanding
        for fact in facts
    }

    assert (
        lookup[
            "us-gaap:CommonStockMember"
        ]
        == 3_916_743_591
    )

    assert (
        lookup[
            "us-gaap:CommonClassBMember"
        ]
        == 70_852_076
    )


def test_fact_metadata_is_preserved():
    fact = (
        extract_shares_outstanding_facts_from_html(
            html=META_HTML,
            cik="1326801",
            filing_date="2026-07-30",
            accession_number=
                "0001628280-26-050705",
            form="10-Q",
            primary_document=
                "meta-20260630.htm",
        )[0]
    )

    assert fact.cik == "0001326801"
    assert (
        fact.filing_date
        == date(2026, 7, 30)
    )
    assert (
        fact.shares_as_of_date
        == date(2026, 7, 24)
    )
    assert (
        fact.taxonomy
        == "dei"
    )
    assert (
        fact.concept
        == "EntityCommonStockSharesOutstanding"
    )
    assert (
        fact.source
        == "filing_inline_xbrl"
    )


def test_non_numeric_shares_fact_is_ignored():
    html = b"""
    <html>
    <body>
    <xbrli:context id="c1">
      <xbrli:period>
        <xbrli:instant>2026-06-30</xbrli:instant>
      </xbrli:period>
    </xbrli:context>

    <ix:nonNumeric
      contextRef="c1"
      name="dei:EntityCommonStockSharesOutstanding">
      no
    </ix:nonNumeric>

    <ix:nonFraction
      contextRef="c1"
      name="dei:EntityCommonStockSharesOutstanding"
      scale="0">
      123456789
    </ix:nonFraction>
    </body>
    </html>
    """

    facts = extract_shares_outstanding_facts_from_html(
        html=html,
        cik="1234",
        filing_date="2026-08-07",
        accession_number="test",
        form="10-K",
        primary_document="test.htm",
    )

    assert len(facts) == 1
    assert facts[0].shares_outstanding == 123_456_789


def test_nil_numeric_shares_fact_is_ignored():
    html = b"""
    <html>
    <body>
    <xbrli:context id="c1">
      <xbrli:period>
        <xbrli:instant>2026-06-30</xbrli:instant>
      </xbrli:period>
    </xbrli:context>

    <ix:nonFraction
      contextRef="c1"
      name="dei:EntityCommonStockSharesOutstanding"
      xsi:nil="true">
    </ix:nonFraction>
    </body>
    </html>
    """

    facts = extract_shares_outstanding_facts_from_html(
        html=html,
        cik="1234",
        filing_date="2026-08-07",
        accession_number="test",
        form="10-K",
        primary_document="test.htm",
    )

    assert facts == []
