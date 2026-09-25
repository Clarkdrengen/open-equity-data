from __future__ import annotations

from bs4 import BeautifulSoup

from open_equity_data.db import connect
from open_equity_data.sec import (
    all_filings,
    get_filing_document,
)
from open_equity_data.sec_shares import (
    extract_context_metadata,
    extract_shares_outstanding_facts_from_html,
)


FORMS = {
    "10-Q",
    "10-K",
    "10-Q/A",
    "10-K/A",
    "20-F",
    "20-F/A",
}


def tag_name(tag) -> str:
    return (
        tag.name.lower()
        if getattr(tag, "name", None)
        else ""
    )


def extract_class_security_metadata(
    html: bytes | str,
) -> list[dict]:

    if isinstance(html, bytes):
        html = html.decode(
            "utf-8",
            errors="ignore",
        )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    contexts = extract_context_metadata(
        soup
    )

    rows = {}

    for tag in soup.find_all():

        name = tag.get("name")

        if name not in {
            "dei:TradingSymbol",
            "dei:Security12bTitle",
        }:
            continue

        if not tag_name(tag).endswith(
            "nonnumeric"
        ):
            continue

        context_id = tag.get(
            "contextref"
        )

        context = contexts.get(
            context_id,
            {},
        )

        class_member = context.get(
            "class_member"
        )

        key = (
            context_id,
            class_member,
        )

        row = rows.setdefault(
            key,
            {
                "context_id":
                    context_id,

                "class_member":
                    class_member,

                "trading_symbol":
                    None,

                "security_title":
                    None,
            },
        )

        value = tag.get_text(
            " ",
            strip=True,
        )

        if name == "dei:TradingSymbol":
            row["trading_symbol"] = value

        elif name == "dei:Security12bTitle":
            row["security_title"] = value

    return list(
        rows.values()
    )


def main() -> None:
    con = connect()

    ciks = [
        row[0]
        for row in con.execute("""
            SELECT DISTINCT cik
            FROM silver.multi_listed_common_equity_candidate
            ORDER BY cik
        """).fetchall()
    ]

    entities = dict(
        con.execute("""
            SELECT cik, entity_name
            FROM bronze.sec_submission_entity
            WHERE cik IN (
                SELECT DISTINCT cik
                FROM silver.multi_listed_common_equity_candidate
            )
        """).fetchall()
    )

    print(
        f"Candidate issuers: {len(ciks)}"
    )

    for i, cik in enumerate(
        ciks,
        start=1,
    ):
        name = entities.get(
            cik,
            "<unknown>",
        )

        print()
        print("=" * 78)
        print(
            f"[{i:02d}/{len(ciks):02d}] "
            f"{cik}  {name}"
        )
        print("=" * 78)

        filings = [
            row
            for row in all_filings(cik)
            if row.get("form") in FORMS
            and row.get("primaryDocument")
        ]

        filings.sort(
            key=lambda x:
                x.get("filingDate") or "",
            reverse=True,
        )

        if not filings:
            print(
                "NO SUPPORTED FILINGS"
            )
            continue

        filing = filings[0]

        print(
            "filing:",
            filing.get("form"),
            filing.get("filingDate"),
            filing.get("accessionNumber"),
            filing.get("primaryDocument"),
        )

        try:
            document = get_filing_document(
                cik=cik,
                accession_number=
                    filing["accessionNumber"],
                primary_document=
                    filing["primaryDocument"],
            )

        except Exception as exc:
            print(
                "FETCH ERROR:",
                repr(exc),
            )
            continue

        security_meta = (
            extract_class_security_metadata(
                document["content"]
            )
        )

        shares = (
            extract_shares_outstanding_facts_from_html(
                html=document["content"],
                cik=cik,
                filing_date=
                    filing["filingDate"],
                accession_number=
                    filing["accessionNumber"],
                form=
                    filing["form"],
                primary_document=
                    filing["primaryDocument"],
            )
        )

        print("\nSECURITY METADATA")

        for row in security_meta:
            print(
                row
            )

        print("\nSHARES FACTS")

        for fact in shares:
            print(
                {
                    "class_member":
                        fact.class_member,

                    "as_of":
                        fact.shares_as_of_date,

                    "shares":
                        fact.shares_outstanding,

                    "concept":
                        f"{fact.taxonomy}:"
                        f"{fact.concept}",
                }
            )

    con.close()


if __name__ == "__main__":
    main()
