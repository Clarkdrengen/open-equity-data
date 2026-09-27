"""Parse local M15E RIF Bronze archives into separate Silver ISIN evidence."""

import argparse

from open_equity_data.build_msci_m15d_rif_silver import build as build_family
from open_equity_data.db import connect


def build(con, rebuild=False):
    return build_family(con, rebuild, family="m15e")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        result = build(con, args.rebuild)
    print("M15E RIF parse counts:", dict(result))


if __name__ == "__main__":
    main()
