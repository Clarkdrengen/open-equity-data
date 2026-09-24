INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id,
    ticker,
    event_date,
    corporate_action_type,
    dividend_share_basis,
    original_split_ratio,
    original_dividend_amount,
    override_split_ratio,
    override_dividend_amount,
    resolution_source,
    source_reference,
    resolution_notes
)
VALUES
(
    22362,
    'FSK',
    DATE '2020-06-16',
    'reverse_split',
    'post_split',
    0.25,
    0.60,
    0.25,
    0.60,
    'issuer_primary_source',
    'FS KKR Capital Corp reverse-split and distribution announcement',
    '1-for-4 reverse split. The $0.60 dividend is quoted per post-split share. For return calculations on the preceding share basis, dividend contribution is 0.60 * 0.25 = 0.15.'
),
(
    12288,
    'CMCT',
    DATE '2019-09-03',
    'cash_plus_reverse_split',
    'pre_split',
    0.3333333333333333,
    14.00,
    0.3333333333333333,
    14.00,
    'issuer_and_exchange_primary_source',
    'CIM Commercial Trust / Nasdaq corporate-action documentation',
    'The $14 special cash dividend is quoted per pre-split share and occurs immediately before the 1-for-3 reverse split. Do not multiply the $14 dividend by the split ratio when converting the event to the preceding share basis.'
);

-- QGEN 2017-01-25
-- Synthetic share repurchase: $1.04 per pre-split share plus 27-for-26
-- consolidation. Use primary-source terms rather than vendor-rounded values.
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    49013, 'QGEN', DATE '2017-01-25',
    'cash_plus_share_consolidation', 'pre_split',
    0.962, 1.087,
    26.0 / 27.0, 1.04,
    'issuer_primary_source',
    'QIAGEN synthetic share repurchase announcement, 2017-01-18',
    'Primary source specifies $1.04 cash repayment per pre-split share and consolidation of every 27 existing shares into 26 shares. Vendor dividend and ratio are replaced with primary-source economic terms.'
);

-- SLGN 2017-05-30
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    54326, 'SLGN', DATE '2017-05-30',
    'stock_split_plus_cash_dividend', 'post_split',
    2.0, 0.09,
    2.0, 0.09,
    'issuer_primary_source',
    'Silgan Holdings 2017-05-04 split/dividend announcement',
    'Issuer explicitly describes $0.09 as the post-split quarterly cash dividend following the 2-for-1 split. Dividend must be converted to previous-share basis using the split ratio in the return calculation.'
);

-- TRI 2023-06-23
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    59016, 'TRI', DATE '2023-06-23',
    'cash_plus_share_consolidation', 'pre_split',
    0.963, 4.845,
    0.963957, 4.67,
    'issuer_primary_source',
    'Thomson Reuters return-of-capital transaction, 2023-06-22',
    'Primary source specifies $4.67 cash per pre-consolidation common share and 0.963957 post-consolidation shares for each pre-consolidation share.'
);

-- PHG 2026-05-13
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    46405, 'PHG', DATE '2026-05-13',
    'scrip_or_cash_dividend', 'pre_split',
    1.03712, 1.01303,
    1.0, 1.01303,
    'issuer_primary_source_plus_vendor_cash_amount',
    'Philips 2025 dividend information and 2026 exchange-ratio announcement',
    'This is not a mechanical stock split. Shareholders could elect cash or shares; the later share ratio was calibrated to the cash dividend value. For the canonical cash-equivalent gross-return treatment, retain the USD cash amount and suppress the 1.03712 ratio from the generic split multiplier to avoid double counting.'
);

-- CRESY 2025-11-28
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    13267, 'CRESY', DATE '2025-11-28',
    'composite_cash_and_in_kind_distribution', 'pre_split',
    1.025, 0.62934,
    NULL, 0.629341,
    'issuer_and_exchange_primary_source',
    'Cresud / Nasdaq corporate-action notice for 2025-11-28',
    'Composite event: $0.629341 gross cash per ADS, 0.8459562% CRESY stock distribution, and 0.020271025 IRSA GDS per CRESY ADS. Generic vendor split ratio 1.025 is not accepted. Event remains excluded from generic gross-total-return logic until the in-kind IRSA distribution is valued.'
);

-- QGEN 2024-01-30
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    49013, 'QGEN', DATE '2024-01-30',
    'cash_plus_share_consolidation', 'pre_split',
    0.97, 1.32,
    24.25 / 25.0, 1.28,
    'issuer_primary_source',
    'QIAGEN synthetic share repurchase announcement, January 2024',
    'Issuer specifies consolidation of every 25 shares into 24.25 shares and $1.28 cash repayment per pre-split share. Vendor cash amount is replaced by issuer terms.'
);

-- QGEN 2025-01-29
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    49013, 'QGEN', DATE '2025-01-29',
    'cash_plus_share_consolidation', 'pre_split',
    0.9722222222222222, 1.26,
    35.0 / 36.0, 1.26,
    'issuer_primary_source',
    'QIAGEN synthetic share repurchase announcement, January 2025',
    'Issuer specifies consolidation of every 36 shares into 35 shares and $1.26 capital repayment per pre-split share.'
);

-- CASS 2017-12-04
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    9785, 'CASS', DATE '2017-12-04',
    'stock_dividend_plus_cash_dividend', 'post_split',
    1.1, 0.24,
    1.1, 0.24,
    'issuer_primary_source',
    'Cass Information Systems 2017 stock/cash dividend announcement',
    'Issuer states the $0.24 cash payout applies to all shares held after completion of the 10% stock dividend. Cash is therefore quoted on the post-stock-dividend basis.'
);

-- CASS 2018-12-03
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    9785, 'CASS', DATE '2018-12-03',
    'stock_dividend_plus_cash_dividend', 'post_split',
    1.2, 0.21666,
    1.2, 0.26,
    'issuer_primary_source',
    'Cass Information Systems 2018 stock/cash dividend announcement',
    'Issuer specifies a 20% stock dividend and $0.26 cash dividend applying to shares after the stock dividend. Vendor-adjusted cash amount is replaced with the issuer-stated $0.26 post-stock-dividend amount.'
);

-- PEBK 2017-12-01
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    45883, 'PEBK', DATE '2017-12-01',
    'cash_dividend_then_stock_dividend', 'pre_split',
    1.1, 0.12,
    1.1, 0.12,
    'issuer_primary_source',
    'Peoples Bancorp 2017 cash and 10% stock dividend announcement',
    'Issuer states the $0.12 cash dividend is paid based on existing shares and the 10% stock dividend is processed following the cash dividend.'
);

-- CBSH 2024-12-03
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    9971, 'CBSH', DATE '2024-12-03',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.05, 0.27,
    1.05, 0.27,
    'issuer_primary_source',
    'Commerce Bancshares 2024 stock and cash dividend announcement',
    'Issuer states the $0.27 cash dividend is not payable on shares issued pursuant to the 5% stock dividend. Cash is therefore on the pre-stock-dividend share basis.'
);

-- CBSH 2025-12-02
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    9971, 'CBSH', DATE '2025-12-02',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.05, 0.275,
    1.05, 0.275,
    'issuer_primary_source',
    'Commerce Bancshares 2025 stock and cash dividend announcement',
    'Issuer states the $0.275 cash dividend is not payable on shares issued pursuant to the 5% stock dividend. Cash is therefore on the pre-stock-dividend share basis.'
);

-- NGG 2024-11-22
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    41530, 'NGG', DATE '2024-11-22',
    'scrip_or_cash_dividend', 'pre_split',
    1.01646, 1.0196,
    1.0, 1.0196,
    'issuer_primary_source_plus_vendor_cash_amount',
    'National Grid scrip dividend scheme',
    'Share issuance is an elective scrip alternative to the cash dividend, not an independent stock split. Canonical gross-return series uses the cash-equivalent amount and suppresses the vendor share-ratio factor.'
);

-- NGG 2025-05-30
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    41530, 'NGG', DATE '2025-05-30',
    'scrip_or_cash_dividend', 'pre_split',
    1.02922, 2.0545,
    1.0, 2.0545,
    'issuer_primary_source_plus_vendor_cash_amount',
    'National Grid scrip dividend scheme',
    'Share issuance is an elective scrip alternative to the cash dividend, not an independent stock split. Canonical gross-return series uses the cash-equivalent amount.'
);

-- NGG 2025-11-21
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    41530, 'NGG', DATE '2025-11-21',
    'scrip_or_cash_dividend', 'pre_split',
    1.01435, 1.0657,
    1.0, 1.0657,
    'issuer_primary_source_plus_vendor_cash_amount',
    'National Grid scrip dividend scheme',
    'Share issuance is an elective scrip alternative to the cash dividend, not an independent stock split. Canonical gross-return series uses the cash-equivalent amount.'
);

-- FER 2026-05-18
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    20272, 'FER', DATE '2026-05-19',
    'scrip_or_cash_dividend', 'pre_split',
    1.0096541310992386, 0.5578,
    1.0, 0.6472,
    DATE '2026-05-18', NULL,
    'issuer_primary_source_plus_provider_fx_conversion',
    'Ferrovial 2026 dividend schedule',
    'Issuer identifies 2026-05-18 as ex-date and 2026-05-19 as record date. Dividend is elective cash-or-scrip; suppress generic share-ratio adjustment. Use EODHD USD cash-equivalent amount for US-listed return series.'
);

-- METC 2024-12-02
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    38557, 'METC', DATE '2024-12-02',
    'in_kind_dividend_other_share_class', 'pre_split',
    1.01, 0.1375,
    1.0, 0.1375,
    DATE '2024-12-02', NULL,
    'issuer_primary_source',
    'Ramaco Resources 2024 stock-dividend announcement',
    'Class A dividend was paid in Class B shares. Treat declared dollar value as cash-equivalent in-kind distribution; suppress vendor split factor because the distributed security is a different share class.'
);

-- METC 2025-02-28
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    38557, 'METC', DATE '2025-02-28',
    'in_kind_dividend_other_share_class', 'pre_split',
    1.014, 0.1375,
    1.0, 0.1375,
    DATE '2025-02-28', NULL,
    'issuer_primary_source',
    'Ramaco Resources 2025 Class A stock-dividend announcement',
    'Class A holders received Class B shares. Treat declared $0.1375 value as cash-equivalent distribution and suppress vendor split factor.'
);

-- METCB 2024-12-02
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    38558, 'METCB', DATE '2024-12-02',
    'stock_dividend', 'not_applicable',
    1.023, 0.2364,
    1.0237349397590362, 0.0,
    DATE '2024-12-02', DATE '2024-12-02',
    'issuer_primary_source',
    'Ramaco Resources 2024 Class B stock-dividend announcement',
    'Class B dividend was paid in additional Class B shares. Economic return is captured through the stock-dividend factor only; do not also add cash.'
);

-- SBS 2025-12-29
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52628, 'SBS', DATE '2025-12-29',
    'gross_cash_plus_stock_dividend', 'pre_split',
    1.02964, 0.4772,
    1.029646975, 0.4772,
    DATE '2025-12-29', DATE '2025-12-29',
    'issuer_primary_source_plus_gross_vendor_conversion',
    'Sabesp December 2025 JCP and capital-increase notice',
    'Issuer specifies gross JCP of R$2.55 per share plus 0.029646975 free shares per share. Retain gross USD-converted Dolt amount for gross-return series and use exact stock ratio.'
);

-- SCCO 2024-11-06
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2024-11-06',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.0062, 0.70,
    1.0062, 0.70,
    DATE '2024-11-06', DATE '2024-11-06',
    'issuer_primary_source',
    'Southern Copper 2024 Q3 filing',
    'Issuer separately declares $0.70 cash and 0.0062 shares per existing share.'
);

-- SCCO 2025-02-11
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2025-02-11',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.0073, 0.70,
    1.0073, 0.70,
    DATE '2025-02-11', DATE '2025-02-11',
    'issuer_primary_source',
    'Southern Copper January 2025 dividend declaration',
    'Issuer separately declares $0.70 cash and 0.0073 shares per existing share.'
);

-- SCCO 2025-05-02
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2025-05-02',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.0099, 0.70,
    1.0099, 0.70,
    DATE '2025-05-02', DATE '2025-05-02',
    'issuer_primary_source',
    'Southern Copper April 2025 dividend declaration',
    'Issuer separately declares $0.70 cash and 0.0099 shares per existing share.'
);

-- SCCO 2025-08-15
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2025-08-15',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.0101, 0.80,
    1.0101, 0.80,
    DATE '2025-08-15', DATE '2025-08-15',
    'issuer_primary_source',
    'Southern Copper July 2025 dividend declaration',
    'Issuer separately declares $0.80 cash and 0.0101 shares per existing share.'
);

-- SCCO 2025-11-12
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2025-11-12',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.0085, 0.90,
    1.0085, 0.90,
    DATE '2025-11-12', DATE '2025-11-12',
    'issuer_primary_source',
    'Southern Copper October 2025 dividend declaration',
    'Issuer separately declares $0.90 cash and 0.0085 shares per existing share.'
);

-- SCCO 2026-05-13
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2026-05-13',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.01, 1.00,
    1.01, 1.00,
    DATE '2026-05-13', DATE '2026-05-13',
    'issuer_primary_source',
    'Southern Copper April 2026 dividend declaration',
    'Issuer separately declares $1.00 cash and 0.0100 shares per existing share.'
);

-- SCCO 2026-08-11
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    52802, 'SCCO', DATE '2026-08-11',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.012, 1.10,
    1.012, 1.10,
    DATE '2026-08-11', DATE '2026-08-11',
    'issuer_primary_source',
    'Southern Copper July 2026 dividend declaration',
    'Issuer separately declares $1.10 cash and 0.0120 shares per existing share.'
);

-- AIV 2019-02-21
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    2178, 'AIV', DATE '2019-02-21',
    'composite_cash_and_in_kind_distribution', 'unresolved',
    1.03125, 0.39,
    1.0, NULL,
    DATE '2019-02-21', NULL,
    'issuer_primary_source',
    'Aimco 2018 10-K and February 2019 special-distribution documentation',
    'Special dividend contained cash and Aimco shares, with shareholder election and proration. The $0.39 raw dividend represents only the regular quarterly dividend embedded in the larger special distribution. The associated reverse split was designed to neutralize the stock issued in the special dividend so aggregate shares outstanding were unchanged. Suppress generic split factor and exclude event from generic gross-total-return treatment until the full special distribution is valued.'
);

-- CZFS 2025-06-13
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    14275, 'CZFS', DATE '2025-06-13',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.01, 0.495,
    1.01, 0.495,
    DATE '2025-06-13', DATE '2025-06-13',
    'issuer_primary_source',
    'Citizens Financial Services June 3 2025 cash and 1% stock dividend announcement',
    'Issuer declared $0.495 cash per existing share plus a 1% stock dividend to shareholders of record June 13, 2025. Treat cash as pre-stock-dividend basis and retain the 1.01 stock factor.'
);

-- METCB 2024-12-02
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    38558, 'METCB', DATE '2024-12-02',
    'stock_dividend', 'not_applicable',
    1.0237349397590363, 0.2364,
    1.0237349397590362, 0.0,
    DATE '2024-12-02', DATE '2024-12-02',
    'issuer_primary_source',
    'Ramaco Resources December 2024 Class B stock-dividend announcement',
    'The $0.2364 amount was used only to determine the number of Class B shares distributed. Each Class B holder received 0.023735 additional Class B shares per share. Economic return is represented by the stock factor only; no cash dividend is added.'
);

-- TR 2025-03-05
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    58932, 'TR', DATE '2025-03-05',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.03, 0.09,
    1.03, 0.09,
    DATE '2025-03-05', DATE '2025-03-05',
    'issuer_primary_source',
    'Tootsie Roll 2025 SEC filings',
    'The $0.09 cash dividend is reported separately from the annual 3% stock dividend. Treat cash as pre-stock-dividend basis and retain the 1.03 stock factor.'
);

-- TR 2026-03-05
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    58932, 'TR', DATE '2026-03-05',
    'cash_dividend_plus_stock_dividend', 'pre_split',
    1.03, 0.09,
    1.03, 0.09,
    DATE '2026-03-05', DATE '2026-03-05',
    'issuer_primary_source',
    'Tootsie Roll 2026 SEC filings',
    'The $0.09 cash dividend is separate from the 3% stock dividend to shareholders of record March 5, 2026. Treat cash as pre-stock-dividend basis and retain the 1.03 stock factor.'
);

-- TRI 2026-05-04
INSERT OR REPLACE INTO silver.corporate_action_override (
    security_id, ticker, event_date,
    corporate_action_type, dividend_share_basis,
    original_split_ratio, original_dividend_amount,
    override_split_ratio, override_dividend_amount,
    override_dividend_ex_date, override_split_effective_date,
    resolution_source, source_reference, resolution_notes
)
VALUES (
    59016, 'TRI', DATE '2026-05-04',
    'cash_plus_share_consolidation', 'pre_split',
    0.9845620667926906, 1.43551,
    0.984560, 1.435518,
    DATE '2026-05-04', DATE '2026-05-04',
    'issuer_primary_source',
    'Thomson Reuters May 1 2026 return-of-capital announcement',
    'Issuer specifies US$1.435518 cash per pre-consolidation share and 0.984560 post-consolidation shares for each pre-consolidation share.'
);
