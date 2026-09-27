"""Audit M15E extension/RIF identity and dated priced-issue overlap."""

from open_equity_data.audit_msci_m15d_name_isin_consistency import build as build_family
from open_equity_data.db import connect


def build(con):
    return build_family(con, family="m15e")


def main():
    with connect() as con:
        statuses, overlap = build(con)
    print("identity_status | MSCI code-dates | normalized-name-agreements | first | last")
    for row in statuses:
        print(*row, sep=" | ")
    print("price_overlap_status | issue-dates | security_ids | multi-security rows")
    for row in overlap:
        print(*row, sep=" | ")
    print("Candidate evidence only; no automatic M15E-to-project identity approval.")


if __name__ == "__main__":
    main()
