
## Manual corporate-action overrides

Some same-day cash distributions and share-count changes cannot be represented
correctly by a generic split-adjustment rule.

Examples include:

- cash distributions immediately followed by reverse splits;
- dividends quoted on a post-split rather than pre-split share basis;
- stock distributions;
- scrip dividends;
- composite capital-return transactions.

Such events are recorded in `silver.corporate_action_override`.

A manual override must include:

- the original source values;
- the validated treatment;
- the dividend share basis;
- the corporate-action type;
- the evidence source;
- explanatory notes.

Manual overrides take precedence over generic corporate-action normalization,
but never alter the original Bronze records.

The corresponding human-readable audit trail is maintained in
`docs/manual-corporate-action-overrides.md`.


# Reconciliation rules addendum — historical dividends

## EODHD dividend fields
When reconciling EODHD dividends against historical raw prices, use `unadjustedValue` as the historical per-share distribution amount. EODHD `value` may reflect retrospective split adjustment and must not be mixed directly with raw historical prices.

Issuer-primary-source overrides take precedence over provider values when the economic terms of a corporate action are explicitly documented.

## Pure stock dividends
When an override classifies an event as `stock_dividend`, the cash component used in gross total return is zero. The economic effect is represented through the validated share-count multiplier only.

## Composite distributions
Composite cash-and-in-kind events are not forced into the generic `cash dividend + split multiplier` model. They remain non-research-eligible until the full economic distribution is explicitly valued.


## Canonical daily return construction

# Return-engine construction

## Canonical daily return basis

The return engine operates on `security_id × trading_date`, not ticker alone.

`silver.security_daily_return_basis` combines:
- reconciled daily OHLCV;
- source provenance;
- authoritative cumulative split multipliers;
- split-normalized close.

The split-normalized close is:

`split_normalized_close = raw_close × cumulative_split_multiplier`

## Gross total return

`silver.security_daily_return` computes returns only when the current observation
and the immediately preceding expected trading-session observation are both
research eligible.

Cash distributions are joined on `effective_dividend_ex_date`.

The dividend amount stored in `security_dividend_event` is already expressed on
the previous-session share basis. It is converted to the cumulative normalized
share basis by multiplying it by the previous session's cumulative split
multiplier.

For eligible observations:

`price_return = normalized_close_t / normalized_close_(t-1) - 1`

`gross_total_return = (normalized_close_t + normalized_dividend_t)
                      / normalized_close_(t-1) - 1`

No return is calculated across an observational gap.

## Quarantined distributions

A positive distribution that is not research eligible causes the daily return
to be marked `unresolved_positive_distribution` rather than silently ignored.

This currently protects composite distributions such as AIV 2019-02-21 and
CRESY 2025-11-28.

## Provenance

The return table retains the selected market-data source fields from
`security_daily_ohlcv` so externally reconciled price observations remain
identifiable downstream.

## Final research-return eligibility

The canonical return engine is intentionally broader than the final research
sample.

`silver.security_daily_return_research` applies the final observation-level
research quarantine.

An observation is excluded when:

- the underlying canonical return is already not research eligible;
- gross total return is null or implies a non-positive wealth factor;
- absolute gross total return exceeds 100% and the extreme move is not
  independently confirmed by the EODHD adjusted-price series.

Extreme observations remain eligible only when classified as:

`vendor_confirms_extreme_after_adjustment`

This is intentionally a validation rule rather than winsorisation or
return-magnitude filtering. A genuinely extreme return can remain in the
research sample when independently confirmed.

Residual unresolved price discrepancies, corporate-action candidates,
dividend/distribution anomalies, and provider-unavailable extreme observations
remain stored with explicit diagnostic provenance but are quarantined from the
research sample.

This rule closes the extreme-return remediation process. Residual quarantined
observations are not a standing manual-cleanup queue.

## Cumulative gross total return

`silver.security_gtr_index` compounds final research-eligible gross total
returns within uninterrupted research segments.

Quarantined observations break the cumulative series into separate segments.
The index is therefore not allowed to bridge a return observation that was
excluded for data-quality reasons.
