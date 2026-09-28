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
