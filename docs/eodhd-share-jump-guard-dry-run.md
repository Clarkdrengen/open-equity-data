# Forward-only EODHD share jump dry run

Run after `python -m open_equity_data.build_msci_daily_share_preference`:

```bash
python -m open_equity_data.audit_eodhd_share_jump_guard --limit 20
```

The command builds two **diagnostic** Silver tables:

- `silver.eodhd_share_jump_guard_observation_candidate`: one priced EODHD
  observation per security, filing date, period, provider and raw count.
- `silver.eodhd_share_jump_guard_impact_candidate`: only the selected EODHD
  issue-days that would change, with their original and hypothetical shares
  and caps. A null hypothetical cap means the prior accepted filing is too old
  or an intervening split makes the carry unsafe.

For each security, walk EODHD filings in date order. Ignore observations that
the current Silver source-priority table already deems ineligible or that a
Bronze sourced adjustment has invalidated. If the first priced day of a new
filing has the same reconciled split multiplier as the last accepted filing,
flag an upward share jump of at least 100×. Do not let a flagged filing reset
the accepted baseline; later bad filings are compared with the last accepted
one. Other eligible filings become the next baseline. The threshold is a
**candidate screening rule**, not a correction or a claim that 100× share
issuance cannot happen.

For a flagged source record that currently supplies the market cap, the dry
run carries the last accepted eligible count only up to **365 calendar days
after its own filing** and only if the split multiplier is unchanged. After
that, the hypothetical EODHD share count is null. MSCI and sourced manual
priority remain as they are. The dry run does not edit Bronze, selected shares,
or the selected market-cap table. It never uses a later filing to fill an
earlier date.

This guard cannot identify a bad first observation, a consistently bad early
history, or problems across split boundaries. It relies on the existing
source-priority table's eligibility and basis classification, whose calibration
may have its own retrospective evidence. A separate date-aware review of that
calibration is needed before promoting any guard to selected market caps.
The command reports affected issues and issue-days, carried versus null days,
and the highest cap impact so the policy can be decided from actual data.

## Batch review of every selected case

After the dry-run audit, run:

```bash
python -m open_equity_data.review_eodhd_share_jump_cases
```

This reads the existing candidate tables and prints **all** affected
securities, then writes timestamped issue-level and filing-level CSVs in
`~/Downloads`. The issue file includes the earlier and newly reported share
counts, number of flagged filings, affected date span, actual and hypothetical
caps, 365-day uncovered days, dated MSCI/manual overlap counts, and whether a
later eligible EODHD filing returns near the earlier count on the same split
basis. Source overlaps use the dated daily candidate; the report does not use
a later MSCI or EODHD value to alter an earlier share count.

The issue file also measures each flagged issue's peak share of the **recorded
daily research-eligible aggregate market cap**, in basis points, and its
hypothetical carried-cap difference when available. Console output defaults
to issues reaching at least one basis point (`--min-peak-bps` changes this
display threshold); both CSVs retain the full batch. The denominator includes
the suspected inflated cap, so this is a prioritization measure, not a final
estimate of the corrected market return or index weight.

The printed categories distinguish independent evidence favoring the prior
or new count, a later EODHD return near the prior count, an implausibly tiny
prior cap requiring review, and unresolved cases. A category is evidence for
review, **not** approval to change the selected share series. In particular,
returning to a small prior count can still be an error in the prior count.

## SEC-backed correction preview

`python -m open_equity_data.stage_sec_share_jump_corrections` is a **read-only**
preview for FRST, EVBN and LHC, three high-impact cases with contemporary SEC
filing evidence. It proposes only issue-days already flagged by the dry-run
audit, requires the recorded security name, compares the current EODHD count
to the SEC count, and chooses the latest filing available at that day's close.
The EVBN March 2013 filing was accepted after close on March 4; its first usable
price date is March 5. A November 2, 2012 EVBN 10-Q supplies the flagged
March 4 date without looking forward. The LHC November 12, 2019 filing was also accepted
after close; its 20 million shares are **Class A ordinary shares** corresponding
to NYSE LHC, excluding the separate Class B founder shares. The preview
prints the proposed target dates, exact source documents, and before/after
market-cap peaks. It neither writes to Bronze nor changes Silver selection.

Source documents are the FRST August and November 2021 10-Qs, EVBN November
2012 10-Q and March 2013 10-K, and LHC November 2019 10-Q; accession numbers
and links are kept beside the proposal in the staging script. Once the exact
preview is approved, `--apply` writes those date-level source-backed rows to
`bronze.eodhd_share_manual_adjustment` and rebuilds Silver in one transaction;
the program rolls back on an existing conflicting row, an incomplete preview,
or an unexpected Silver selection. OPFI is withheld here: the November 2021
filing distinguishes publicly listed Class A shares from Class V shares.
