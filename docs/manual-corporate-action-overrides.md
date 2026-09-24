# Manual Corporate-Action Overrides

## Purpose

This document records all corporate-action observations for which the generic
split/dividend reconciliation rules are insufficient and an explicit,
evidence-backed manual treatment is required.

Manual overrides are part of the audited data pipeline. They are not silent
data corrections.

The machine-readable version of these decisions is stored in:

`silver.corporate_action_override`

and is reproducibly seeded from:

`sql/silver/seed_corporate_action_overrides.sql`

## General rule

When a row exists in `silver.corporate_action_override`, its explicitly
validated corporate-action treatment takes precedence over generic
split/dividend normalization rules.

The raw source observations remain unchanged in Bronze.

---

## FSK — 2020-06-16

**Security ID:** 22362

**Corporate action:** 1-for-4 reverse split plus cash distribution.

**Raw split ratio:** 0.25

**Raw dividend amount:** 0.60

**Dividend share basis:** Post-split.

### Resolution

The $0.60 distribution is quoted per post-split share.

To express the dividend on the preceding pre-split share basis:

`0.60 × 0.25 = 0.15`

The split-adjusted closing price is similarly converted using the 0.25 split
ratio.

### Return treatment

For a preceding close of 4.20 and event-date close of 16.70:

- split-normalized event close = `16.70 × 0.25 = 4.175`
- dividend on preceding share basis = `0.60 × 0.25 = 0.15`

Gross total return:

`(4.175 + 0.15) / 4.20 - 1 ≈ 2.98%`

### Evidence

Issuer primary-source documentation describing the 1-for-4 reverse split and
the post-split $0.60 distribution.

**Status:** Manually validated.

---

## CMCT — 2019-09-03

**Security ID:** 12288

**Corporate action:** $14 special cash distribution immediately followed by a
1-for-3 reverse split.

**Raw split ratio:** 1/3

**Raw dividend amount:** 14.00

**Dividend share basis:** Pre-split.

### Resolution

The $14 special distribution is quoted per pre-split share.

It must therefore NOT be multiplied by the 1/3 reverse-split ratio when
expressing the dividend on the preceding day's share basis.

The event-date stock price is converted to the preceding share basis using the
split ratio.

### Return treatment

For a preceding close of 20.00 and event-date close of 16.42:

- split-normalized event close = `16.42 / 3 ≈ 5.4733`
- dividend on preceding share basis = `14.00`

Gross total return:

`(5.4733 + 14.00) / 20.00 - 1 ≈ -2.63%`

### Evidence

Issuer and exchange corporate-action documentation establishing that the
special cash distribution precedes the reverse split.

**Status:** Manually validated.

---

## QGEN — 2017-01-25

**Security ID:** 49013

**Corporate action:** Synthetic share repurchase consisting of a cash capital
repayment and share consolidation.

**Raw vendor split ratio:** 0.962

**Raw vendor dividend amount:** 1.087

### Resolution

Issuer documentation states that every 27 existing shares were consolidated
into 26 shares and shareholders received USD 1.04 per pre-split share.

Validated split ratio:

`26 / 27 = 0.962962962963...`

Validated cash distribution:

`USD 1.04 per pre-split share`

The primary-source values replace the rounded/vendor-derived economic terms.

**Dividend share basis:** Pre-split.

**Evidence:** QIAGEN issuer announcement dated 2017-01-18.

**Status:** Manually validated.

---

## SLGN — 2017-05-30

**Security ID:** 54326

**Corporate action:** 2-for-1 stock split plus quarterly cash dividend.

**Split ratio:** 2.0

**Dividend amount:** USD 0.09

### Resolution

The issuer explicitly described USD 0.09 as the post-split quarterly cash
dividend.

For return calculations on the preceding share basis, the dividend is therefore
converted using the split ratio together with the event-date price.

**Dividend share basis:** Post-split.

**Evidence:** Silgan Holdings issuer announcement dated 2017-05-04.

**Status:** Manually validated.

---

## TRI — 2023-06-23

**Security ID:** 59016

**Corporate action:** Return of capital plus share consolidation.

**Raw vendor split ratio:** 0.963

**Raw vendor distribution:** USD 4.845

### Resolution

Thomson Reuters specified:

- USD 4.67 cash per pre-consolidation common share.
- 0.963957 post-consolidation shares for each pre-consolidation share.

The primary-source economic terms replace the vendor-rounded values.

**Dividend share basis:** Pre-split / pre-consolidation.

**Validated split ratio:** 0.963957

**Validated cash distribution:** USD 4.67

**Evidence:** Thomson Reuters return-of-capital announcement dated 2023-06-22.

**Status:** Manually validated.

---

## PHG — 2026-05-13

**Security ID:** 46405

**Corporate action:** Dividend payable in cash or shares at shareholder election.

### Resolution

Philips declared a dividend of EUR 0.85 per existing common share, payable in
cash or shares. The later share entitlement was set at one new share for every
26.9341 existing shares so that the stock-dividend value approximately equaled
the cash dividend.

The resulting share issuance is therefore not treated as an independent stock
split in addition to the dividend.

For the canonical cash-equivalent gross-total-return series:

- retain the provider USD cash-equivalent dividend amount;
- suppress the 1.03712 share factor from the generic split multiplier.

This prevents double counting the same economic distribution as both cash and
additional shares.

**Corporate-action type:** Scrip-or-cash dividend.

**Evidence:** Philips dividend information and exchange-ratio announcement.

**Status:** Manually validated for cash-equivalent gross-return treatment.

---

## CRESY — 2025-11-28

**Security ID:** 13267

**Corporate action:** Composite cash and in-kind distribution.

### Source terms

The distribution comprised:

- USD 0.629341 gross cash per CRESY ADS;
- a 0.8459562% CRESY stock distribution;
- 0.020271025 IRSA GDS per CRESY ADS.

### Resolution

The vendor split ratio of 1.025 is not accepted as a representation of this
composite event.

The event cannot be represented correctly by the generic
`cash dividend + split multiplier` model because part of the shareholder return
is delivered in IRSA securities.

The event therefore remains outside the generic gross-total-return calculation
until the in-kind IRSA distribution is explicitly valued.

**Corporate-action type:** Composite cash and in-kind distribution.

**Evidence:** Cresud issuer notice and Nasdaq corporate-action notice.

**Status:** Manually classified; total-return valuation pending.

---

## QGEN — 2024-01-30

Synthetic share repurchase.

Issuer terms:
- 25 existing shares consolidated into 24.25 shares.
- USD 1.28 repayment per pre-split share.

**Dividend basis:** Pre-split.

**Validated split ratio:** 24.25 / 25 = 0.97.

**Validated cash amount:** USD 1.28.

**Status:** Manually validated from issuer primary source.

---

## QGEN — 2025-01-29

Synthetic share repurchase.

Issuer terms:
- 36 existing shares consolidated into 35 shares.
- USD 1.26 repayment per pre-split share.

**Dividend basis:** Pre-split.

**Validated split ratio:** 35 / 36.

**Validated cash amount:** USD 1.26.

**Status:** Manually validated from issuer primary source.

---

## CASS — 2017-12-04

10% stock dividend plus cash dividend.

Issuer documentation states that the USD 0.24 cash dividend applies to shares
after completion of the stock dividend.

**Dividend basis:** Post-split.

**Validated stock ratio:** 1.10.

**Validated cash amount:** USD 0.24 per post-stock-dividend share.

**Status:** Manually validated from issuer primary source.

---

## CASS — 2018-12-03

20% stock dividend plus cash dividend.

Issuer documentation specifies a USD 0.26 cash dividend applying to shares
after completion of the 20% stock dividend.

**Dividend basis:** Post-split.

**Validated stock ratio:** 1.20.

**Validated cash amount:** USD 0.26 per post-stock-dividend share.

The vendor value 0.21666 is not used as the authoritative economic amount.

**Status:** Manually validated from issuer primary source.

---

## PEBK — 2017-12-01

Cash dividend followed by a 10% stock dividend.

Issuer documentation states that the USD 0.12 cash dividend is based on the
existing shareholding and that the stock dividend is processed following the
cash distribution.

**Dividend basis:** Pre-split.

**Validated stock ratio:** 1.10.

**Validated cash amount:** USD 0.12.

**Status:** Manually validated from issuer primary source.

---

## CBSH — 2024-12-03

Quarterly cash dividend plus 5% stock dividend.

The issuer explicitly states that the cash dividend is not payable on shares
issued pursuant to the stock dividend.

**Dividend basis:** Pre-split.

**Validated stock ratio:** 1.05.

**Validated cash amount:** USD 0.27.

**Status:** Manually validated from issuer primary source.

---

## CBSH — 2025-12-02

Quarterly cash dividend plus 5% stock dividend.

The issuer explicitly states that the cash dividend is not payable on shares
issued pursuant to the stock dividend.

**Dividend basis:** Pre-split.

**Validated stock ratio:** 1.05.

**Validated cash amount:** USD 0.275.

**Status:** Manually validated from issuer primary source.

---

## NGG — 2024-11-22, 2025-05-30 and 2025-11-21

National Grid operates a scrip dividend scheme under which shareholders may
elect to receive additional shares instead of the cash dividend.

The resulting provider share-ratio observations are therefore not treated as
independent stock splits.

For the canonical gross-total-return series:

- retain the cash-equivalent dividend amount;
- set the generic split ratio to 1.0 for these events;
- do not count both the cash dividend and the scrip shares.

**Corporate-action type:** Scrip-or-cash dividend.

**Dividend basis:** Pre-split / cash-equivalent.

**Status:** Manually classified from issuer documentation.


# Final same-day corporate-action overrides

These entries are intended to be merged into `docs/manual-corporate-action-overrides.md`.

## AIV — 2019-02-21
Composite special cash/stock distribution plus offsetting reverse split. The raw USD 0.39 observation does not represent the complete economic distribution. Suppress the generic split factor and exclude the event from generic gross-total-return calculations until the complete special distribution is valued.

## CZFS — 2025-06-13
USD 0.495 cash dividend plus 1% stock dividend. Dividend basis: pre-stock-dividend. Validated stock ratio: 1.01.

## METCB — 2024-12-02
Pure stock dividend. The quoted USD 0.2364 amount only determined the number of additional Class B shares distributed. No cash dividend is added; the economic return is represented by the stock-dividend factor only.

## TR — 2025-03-05
USD 0.09 cash dividend plus separate 3% stock dividend. Dividend basis: pre-stock-dividend. Validated stock ratio: 1.03.

## TR — 2026-03-05
USD 0.09 cash dividend plus separate 3% stock dividend. Dividend basis: pre-stock-dividend. Validated stock ratio: 1.03.

## TRI — 2026-05-04
Return of capital plus share consolidation. Validated cash amount: USD 1.435518 per pre-consolidation share. Validated consolidation ratio: 0.984560.

## PRTK — 2014 special dividend

Raw dividend date 2014-10-22 was not the effective ex-dividend date.

Issuer/exchange evidence supports:
- cash amount: approximately USD 8.01 per share
- effective ex-dividend date: 2014-10-31

Treatment: ordinary cash dividend moved to the correct effective ex-date.

## VISN — 2026 special distribution

Issuer evidence supports:
- cash amount: USD 5.00 per share
- effective ex-dividend date: 2026-08-28

The raw 2026-08-17 date is retained for provenance but is not used as the
economic ex-dividend date.
