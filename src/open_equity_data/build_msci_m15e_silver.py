"""Parse local M15E extension Bronze archives into separate Silver evidence."""

import argparse

from open_equity_data.build_msci_m15d_silver import build as build_family
from open_equity_data.db import connect


def build(con, rebuild=False):
    return build_family(con, rebuild, family="m15e")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        result = build(con, args.rebuild)
        coverage = con.execute("""
            SELECT MIN(observation_date), MAX(observation_date),
                   COUNT(DISTINCT msci_security_code),
                   COUNT(*) FILTER (WHERE parse_status = 'shares_present')
            FROM silver.msci_m15e_security_observation
        """).fetchone()
    print("M15E extension parse counts:", dict(result))
    print("first, last, MSCI codes, share rows:", coverage)
    print("MSCI codes require the separate RIF ISIN join; no canonical shares changed.")


if __name__ == "__main__":
    main()
