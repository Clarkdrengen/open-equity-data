# Data Quality Findings

## Dolt OHLCV and corporate actions

The Dolt source is useful but is not research-ready without validation.

Observed issues include:

- Incorrect split ratios.
- Duplicate split events.
- OHLCV observations on dates when the US equity market was closed.
- Ticker recycling.
- Missing expected trading sessions.
- Current-state symbol metadata that should not be interpreted as historical security metadata.

## Closed-session observations

A material number of Dolt OHLCV rows occur on dates when the XNYS trading calendar was closed.

These include:

- Exact duplicates of adjacent valid sessions.
- Hybrid observations combining fields from neighbouring sessions.
- Other anomalous closed-session observations.

The Silver clean OHLCV layer excludes all observations on non-expected trading sessions while preserving them in Bronze.

## Missing expected sessions

For the three currently validated lineages, 40 expected-session observations were missing from Dolt:

- BCIC_1
- META_1
- VTAK_1

EODHD returned an observation for all 40 dates.

Of these:

- 37 were retrieved using the historically appropriate ticker.
- 3 FB-era observations required lookup under `META.US`.

## EODHD successor-ticker behaviour

EODHD may consolidate historical data under the latest ticker in a security lineage.

This is useful for recovering observations after ticker changes but cannot be treated as semantically identical to historical-ticker data.

Testing RMED versus VTAK showed:

- Raw OHLC values can remain broadly consistent.
- OHLC precision can be reduced under the successor ticker.
- `adjusted_close` may incorporate later reverse splits.
- Volume may also be transformed by later corporate actions.

Therefore successor-ticker data is treated as fallback evidence, not automatically as equivalent raw history.

## FB / META validation

EODHD returned no observation for `FB.US` on 2019-08-23 but returned the corresponding historical observation under `META.US`.

Comparison of surrounding dates showed exact OHLC agreement between:

- Dolt observations stored under historical ticker FB.
- EODHD observations retrieved under META.

Volume differed only by immaterial amounts on overlapping dates.

This supports use of the META lineage fallback for the three missing FB-era observations.

## RMED 2023-01-09

EODHD returned:

- Open: 5.89
- High: 5.89
- Low: 5.89
- Close: 5.89
- Volume: 0

The observation is not a simple previous-close carry-forward, but it also does not represent an ordinary traded OHLC bar.

It is retained in the reconciled data with `research_eligible = false`.

## Same-day split and dividend share-basis ambiguity

A small number of observations contain a cash distribution and a share-count
change on the same effective date.

The dividend amount cannot always be assumed to be quoted on the post-split
share basis.

Two validated examples demonstrate both possibilities:

- FSK 2020-06-16: the $0.60 dividend is quoted on the post-split basis following
  a 1-for-4 reverse split.
- CMCT 2019-09-03: the $14 special distribution is quoted on the pre-split
  basis and is immediately followed by a 1-for-3 reverse split.

Consequently, same-day split/dividend observations are explicitly reviewed and,
where necessary, represented through `silver.corporate_action_override`.

## Composite distributions in provider split feeds

Full-history corporate-action validation showed that a provider "split" record
does not always represent a conventional stock split.

Examples include:

- synthetic share repurchases combining cash repayment and consolidation;
- scrip dividends payable in cash or shares;
- stock distributions;
- composite cash and in-kind distributions.

Such events must not automatically enter the cumulative split multiplier.

Material same-day cases are classified explicitly in
`silver.corporate_action_override` and documented in
`docs/manual-corporate-action-overrides.md`.

In particular:

- PHG 2026-05-13 is treated as a cash-equivalent scrip dividend rather than an
  independent split plus dividend.
- CRESY 2025-11-28 is a composite cash, CRESY-stock and IRSA-security
  distribution and remains outside the generic total-return calculation until
  the in-kind component is valued.


# Extreme-return vendor price validation

The first daily-return audit found 4,948 research-eligible observations with
absolute gross total return above 100%, spread across 3,140 securities.

This is too diffuse for manual security-by-security reconciliation. Before
narrowing the research universe or undertaking further corporate-action
forensics, the project therefore compares the raw Dolt price discontinuities
with an independent vendor series.

## Validation source

EODHD historical end-of-day data are requested directly under the historical
ticker using the `.US` exchange suffix.

For each ticker that has at least one research-eligible observation with
`ABS(gross_total_return) > 1`, one request is made from ten calendar days before
the earliest extreme observation through ten calendar days after the latest
extreme observation.

The response is cached in:

- `bronze.external_price_validation_request`
- `bronze.external_price_validation_observation`

Requests are resumable. Successful requests and 404 responses for the same
ticker/date window are not repeated.

## Comparison layer

`silver.extreme_return_price_comparison` compares the Dolt return event with:

- EODHD raw close on the previous expected trading session;
- EODHD raw close on the event date;
- EODHD adjusted close on both dates;
- provider raw and adjusted returns;
- provider/Dolt price-level ratios before and after the event.

`comparison_status` is deliberately descriptive rather than a final data-quality
judgment:

- `provider_raw_also_extreme`
- `provider_raw_not_extreme`
- `provider_price_pair_missing`
- `provider_symbol_not_found`
- `provider_request_failed`
- `no_provider_request`

The purpose is to size the remaining problem. A Dolt-only extreme event is
evidence for a Dolt price/corporate-action issue; an extreme event present in
both raw series requires further interpretation rather than automatic removal.


## Extreme-return corporate-action candidate validation

# Extreme-return corporate-action candidate validation

After comparing the extreme Dolt return tail with EODHD prices, 577 extreme
observations across 430 securities were classified as corporate-action
candidates because:

- EODHD raw prices also showed an extreme move; but
- EODHD adjusted prices did not.

This strongly suggests an omitted or mis-specified corporate action rather than
a bad raw price observation.

For each affected ticker, the pipeline requests the full EODHD split history and
stores it in dedicated Bronze validation tables.

The comparison layer matches the nearest provider split within +/-45 calendar
days of each candidate return date and classifies the relationship as:

- exact date / exact ratio already present;
- exact date / ratio conflict;
- nearby date / exact ratio;
- nearby date / ratio conflict;
- no provider split within 45 days;
- provider unavailable.

This is a diagnostic layer only. It does not yet modify the authoritative split
event table or canonical returns.


## Automatic split backfill from vendor-confirmed extreme returns

# Automatic split backfill from vendor-confirmed extreme returns

The extreme-return reconciliation identified 542 exact-date split-ratio
conflicts where the current split factor was 1.0 but EODHD reported a split on
the same date.

A mechanical validation was then applied:

`counterfactual_return = (1 + provider_raw_return) * provider_split_ratio - 1`

An event is automatically backfilled only when:

- the current daily split ratio is exactly 1.0;
- EODHD reports a split on the exact same date;
- the counterfactual return matches EODHD adjusted return within `1e-6`.

422 events satisfy this strict rule.

These 422 events are stored in `silver.automatic_split_backfill`. They are not
inserted into the manual override table.

`silver.security_daily_split_factor_reconciled` overlays the validated automatic
backfills onto the existing authoritative split-factor series. The original
factor columns are retained for auditability.

The remaining exact-date conflicts that fail the strict mechanical validation
are left unchanged for separate investigation.

## Automatic high-confidence price corrections

Extreme-return reconciliation against EODHD identified a subset of Dolt price
observations where one side of a consecutive-session return interval agrees
with EODHD within 1%, while the other differs by more than 10%.

These one-sided discrepancies are treated as high-confidence Dolt price errors.

The correction layer is stored in:

`silver.automatic_price_correction`

The original Dolt observations remain unchanged.

A reconciled price layer:

`silver.security_daily_ohlcv_reconciled`

uses the EODHD raw OHLCV bar only for validated security-date corrections and
otherwise retains the existing `silver.security_daily_ohlcv` observation.

The automatic rule requires:

- one side of the interval to agree with EODHD within 1%;
- the other side to differ from EODHD by more than 10%;
- an exact EODHD raw historical observation on the correction date.

The correction is therefore based on cross-provider price consistency rather
than on the magnitude of the return itself.

## Automatic high-confidence price corrections

Extreme-return reconciliation against EODHD identified a subset of Dolt price
observations where one side of a consecutive-session return interval agrees
with EODHD within 1%, while the other differs by more than 10%.

These one-sided discrepancies are treated as high-confidence Dolt price errors.

The correction layer is stored in:

`silver.automatic_price_correction`

The original Dolt observations remain unchanged.

A reconciled price layer:

`silver.security_daily_ohlcv_reconciled`

uses the EODHD raw OHLCV bar only for validated security-date corrections and
otherwise retains the existing `silver.security_daily_ohlcv` observation.

The automatic rule requires:

- one side of the interval to agree with EODHD within 1%;
- the other side to differ from EODHD by more than 10%;
- an exact EODHD raw historical observation on the correction date.

The correction is therefore based on cross-provider price consistency rather
than on the magnitude of the return itself.
