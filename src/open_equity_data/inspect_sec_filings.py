import argparse
from datetime import date

from open_equity_data.sec import all_filings


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("cik")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument(
        "--forms",
        nargs="*",
        default=["8-K", "8-K/A"],
    )

    args = parser.parse_args()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    for filing in all_filings(args.cik):
        filing_date = date.fromisoformat(filing["filingDate"])

        if start and filing_date < start:
            continue

        if end and filing_date > end:
            continue

        if args.forms and filing["form"] not in args.forms:
            continue

        print(
            filing["filingDate"],
            filing["form"],
            filing["accessionNumber"],
            filing["primaryDocument"],
            filing["primaryDocDescription"],
        )


if __name__ == "__main__":
    main()
