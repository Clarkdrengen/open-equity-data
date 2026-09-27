"""Archive local M15E RIF ZIP bytes in their own Bronze table."""

import argparse
from pathlib import Path

from open_equity_data.db import connect
from open_equity_data.load_msci_m15d_rif_bronze import archive as archive_family


def archive(con, root: Path, pilot: bool = False):
    return archive_family(con, root, pilot, family="m15e")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    with connect() as con:
        found, added = archive(con, args.directory, args.pilot)
    print(f"M15E RIF ZIPs found={found} newly archived={added}")


if __name__ == "__main__":
    main()
