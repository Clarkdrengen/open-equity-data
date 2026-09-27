# MSCI-preferred daily share sensitivity (candidate)

Nick approved preferring MSCI RIF security shares where both MSCI and EODHD
have an eligible count for the same priced issue. The two source facts remain
separate; no source bytes or row-level outputs are uploaded. This candidate
does not replace the established EODHD PIT table or existing return weights.

Run after the RIF share extraction and both family overlap audits:

```bash
python -m open_equity_data.build_msci_daily_share_preference
```

`silver.msci_preferred_share_snapshot_candidate` combines exact
date/code/ISIN single-issue matches from the distinct M15D and M15E families.
It excludes duplicate issue/snapshot rows and conflicting positive Closing
share values. The three daily Silver tables
`silver.msci_daily_share_preference_lag{1,5,22}_candidate` use the first,
fifth or twenty-second **research session after** the MSCI month-end date as
alternative earliest-use assumptions. The source's actual release timestamp
is not available, so none of these is asserted to be historical truth.

Each lag keeps the previous available snapshot until the replacement becomes
eligible, subject to a 45-calendar-day snapshot age limit. Where the same
issue also has a valid EODHD PIT share record, the candidate selects MSCI
Closing shares. To compare with a later daily closing price, it adjusts for
the project's reconciled split factors from the MSCI price anchor to the
current date; missing factors block selection. Rows with only MSCI are marked
pending rather than automatically filling an EODHD gap. EODHD issuer-total
shares are not an acceptable fallback for flagged simultaneously listed
common-equity issues when MSCI is unavailable.

The command prints issue-day status counts, priced MSCI candidate counts and
the maximum MSCI-based security market-cap candidate for all three lag
assumptions. It does not calculate a full-universe market cap or alter any
benchmark. Before adopting a lag or market-cap weight, review
coverage, giant-cap outliers, share-class/ADR basis and the release-timing
assumption with Nick. Month-end shares cannot be used on earlier daily dates.
