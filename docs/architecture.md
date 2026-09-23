# Architecture

## Overview

The project separates raw source data from interpreted and research-ready data.

### Bronze

Bronze preserves raw observations and source-specific metadata.

Current examples include:

- Raw Dolt OHLCV
- Raw Dolt corporate actions
- External ticker-reference data
- SEC filing evidence
- EODHD external price requests and observations

External provider data never overwrites Dolt Bronze data.

### Silver

Silver contains interpreted, validated and reconciled data.

Key layers include:

- Trading calendar
- Clean OHLCV
- Ticker episodes
- Ticker-transition evidence
- Validated ticker transitions
- Stable ticker lineages
- Missing-price diagnostics
- External-price reconciliation
- Reconciled OHLCV

## Reconciled OHLCV

`silver.reconciled_ohlcv` is the principal reconciled daily market-data table.

Each observation retains provenance through:

- `source`
- `source_symbol`
- `source_lookup_method`
- `reconciliation_status`
- `observation_type`
- `research_eligible`

Native Dolt observations retain precedence when present.

External observations are used only for missing Dolt sessions and are never allowed to overwrite Bronze source data.

## Identity model

A ticker is not treated as a permanent security identifier.

Observed ticker histories are first segmented into ticker episodes. Validated same-security ticker transitions are then used to construct persistent security lineages.

This allows a lineage to span ticker changes while preserving the ticker that was historically in force on each date.

## External price reconciliation

Missing expected-session observations are identified from the trading calendar and lineage histories.

External data is queried using:

1. The historically appropriate ticker.
2. The latest ticker in the validated lineage only when the historical ticker does not return an observation.

Provider provenance is retained explicitly rather than normalised away.
