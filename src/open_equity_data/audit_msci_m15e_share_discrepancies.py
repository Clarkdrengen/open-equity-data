"""Compare M15E shares with existing EODHD PIT shares as diagnostics."""

from open_equity_data.audit_msci_m15d_share_discrepancies import build as build_family
from open_equity_data.db import connect


def build(con):
    return build_family(con, family="m15e")


def main():
    with connect() as con:
        rows = build(con)
    print("identity | today_band | closing_band | issue_dates | issues | split_overlap | first | last")
    for row in rows:
        print(*row, sep=" | ")
    print("No automatic share, market-cap or weight correction.")


if __name__ == "__main__":
    main()
