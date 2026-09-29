# Two missing Dolt price sessions in 2019

The original DoltHub `post-no-preference/stocks` `ohlcv` table has 3,133
records for 2019-08-23 and 3,136 for 2019-09-17, matching local
`bronze.ohlcv`. Adjacent sessions have about 7,910 records. Both dates were
normal US market sessions. On those dates AAPL and AMZN are absent from the
current DoltHub source. This is a source-level gap, not a share-count failure.

The user downloaded EODHD US bulk EOD JSON for each date into
`bronze.eodhd_bulk_eod_response` with original response bytes, SHA-256 digest,
request date, endpoint, and retrieval time. The local report found 4,348 of
4,770 bracketed missing Dolt ticker observations on August 23, and 4,364 of
4,769 on September 17 in EODHD. Those counts represent source availability,
not yet a canonical security mapping.

`python -m open_equity_data.recover_eodhd_bulk_price_gaps` derives
`silver.eodhd_bulk_missing_price_candidate` from the retained Bronze bytes.
It requires one EODHD code per date, the same `security_id` and ticker on
both adjacent research-eligible sessions, and no native Dolt row on the
missing date. Existing non-bulk external prices also take precedence. An
invalid OHLCV bar or a close more than twice or less than half either adjacent
close is reported as a review case. Only `candidate_usable` rows enter the
canonical Silver security price table. The candidate includes the Bronze
response digest for provenance. There are no additions to `bronze.ohlcv`.

`python -m open_equity_data.recover_eodhd_bulk_price_gaps --apply` rebuilds
the dependent Silver price, split-factor, return, research, and market-cap
tables. Review the printed date/status counts first. The EODHD date field is
checked for every source row before deriving anything, because its bulk API
may return a different trading date for an invalid or closed request date.
The 0.5–2 adjacent-close guard is a conservative selection boundary, not a
claim that all excluded prices are wrong. No missing rows are interpolated.
