# Item 1 — Commodity variance risk premium and futures curve state

Series: options-series. Draft 3 of 2026-09-15. Not frozen. Freezes on user sign-off.
Revised only before session 1 runs; after that, deviations are recorded as amendments,
never edited in place.

Each design choice carries a basis tag: [lit] follows a published convention,
[stat] is statistical convention, [judgment] is set by the author with no derivation.

---

## 1. Questions

Q1. Is variance risk in commodity ETF options priced the way it is in the equity index.

Q2. Does the size of the premium depend on the state of the underlying futures curve,
measured both as the sign of the front spread and as its percent slope.

Q3. Is the commonality across commodity variance premia documented in prior art a
curve-state effect, or does it survive conditioning on each commodity's own slope.

All three are asked at the 30-day and the 91-day option maturity.

## 2. Prior art

Trolle and Schwartz (2010, Journal of Derivatives) measure variance risk premia in energy
futures options. Prokopczuk, Symeonidis and Wese Simen (2017, Journal of Banking and
Finance 81, 136–149) construct synthetic variance swaps from commodity futures options
and find significantly negative realized swap payoffs in most markets, commonality across
commodities, and comovement with equity and bond variance swaps. Carr and Wu (2009,
Review of Financial Studies) and Jiang and Tian (2005, Review of Financial Studies) set
the model-free variance construction used here; the CBOE VIX white paper is the
operational reference. Ng and Pirrong (1994, Journal of Business) find metals spot
volatility higher in backwardation, the only published input on the realized-variance
side of Q2.

This item differs on four counts and is labelled as an update and extension in the post.
Instrument is the ETF option chain in OptionMetrics. Sample runs to August 2025. The
premium is conditioned on curve state. Commonality is re-examined after that conditioning.

## 3. Hypotheses

H1 (replication). For each of GLD, SLV, USO, UNG the mean log(IV²/RV) is positive.
One-sided. Tested at both nodes. [lit]

H2 (extension). For each ETF the slope coefficient of log(IV²/RV) on the percent curve
slope is non-zero. Two-sided, sign not registered. Tested at both nodes. The sign split
(contango vs backwardation) is reported as a figure and is nested in H2, so it carries
no separate test. [stat]

Q3 carries no hypothesis and no test. It is answered by two numbers, defined in
section 6.

SPX enters as the equity benchmark for H1 only.

## 4. Data

| Quantity | Source | Notes |
|---|---|---|
| Option quotes | `optionm.opprcdYYYY` | per secid per partition; `best_bid`, `best_offer`, `strike_price`, `exdate`, `cp_flag`, `forward_price`, `am_settlement` |
| ATM implied vol | `optionm.vsurfdYYYY`, `days ∈ {30, 91}`, `delta = ±50` | secondary measure |
| Risk-free rate | `optionm.zerocd` | interpolated to each expiry |
| Underlying return | `optionm.secprdYYYY`, column `return` | same secid; no CRSP join |
| Futures curve | `tr_ds_fut`, continuous first and second nearby series | identified and measured in session 1 |
| VIX (validation only) | `cboe` library on WRDS, if present | session 1 checks presence |

Secids are fixed here and not re-resolved at query time.

| Ticker | secid | Surface start |
|---|---|---|
| SPX | 108105 | 1996-01-04 |
| GLD | 122392 | 2008-06-03 |
| SLV | 126776 | 2008-12-08 |
| USO | 126681 | 2007-05-09 |
| UNG | 129367 | 2007-05-09 |

Underlying futures for the curve state: COMEX gold (GC) for GLD, COMEX silver (SI) for
SLV, NYMEX WTI light sweet crude (CL) for USO, NYMEX Henry Hub natural gas (NG) for UNG.

## 5. Sample

Common window 2008-12-08 to 2025-08-29 for every test and every primary figure.
Per-ETF full spans are reported for the annual-mean figure only.

Observations are daily and overlapping, about 4,200 per ETF before drops. Independent
observations are about 200 at the 30-day node and about 67 at the 91-day node.

Reporting floor. [judgment] A curve state with fewer than 30 non-overlapping windows
for an ETF at a node is reported but not tested. A state with 30 to 63 windows is
tested with a note that a Welch test at alpha 0.05 has 80 percent power only for
differences above half a standard deviation; 64 per state is the power threshold. [stat]

## 6. Measurement

### 6.1 Implied variance, primary: model-free [lit]

For each secid, date t and target maturity d ∈ {30, 91} calendar days.

1. Candidate expiries: all `exdate` on date t with at least 7 calendar days to expiry.
   Select the two that bracket d (nearest below and nearest above). If d falls beyond
   the last expiry or before the first, the date is dropped for that node. [judgment
   on the 7-day floor, following the VIX convention of excluding the final week]
2. Per expiry: forward F from the `forward_price` column where non-null; otherwise from
   put-call parity at the strike with the smallest |C − P| midquote difference, using
   the zero rate r from `zerocd` interpolated to the expiry. K0 is the first strike at
   or below F.
3. Strike set: out-of-the-money options only (puts below K0, calls above K0, the
   average of put and call at K0). Midquote (best_bid + best_offer)/2. Zero-bid
   options are excluded; the strike sweep on each side stops after two consecutive
   zero-bid strikes. [lit, CBOE]
4. Model-free variance for the expiry with time to expiry T in years:
   σ² = (2/T) Σ_i (ΔK_i / K_i²) e^{rT} Q(K_i) − (1/T)(F/K0 − 1)², with ΔK_i the
   half-distance between neighbouring strikes and Q the midquote. [lit, CBOE; Jiang
   and Tian 2005]
5. Interpolate the two expiries linearly in total variance σ²T to d, then divide by
   d/365. [lit, CBOE]
6. A date is dropped for that node if either bracketing expiry has fewer than 3 OTM
   strikes on either side after step 3. Drop counts are reported per secid, node and
   year. [judgment on the floor of 3]

Validation. If the `cboe` library carries a daily VIX close, the SPX 30-day model-free
volatility constructed here is compared to VIX over the overlap: correlation of levels,
mean and median level difference, and the count of dates where the two differ by more
than 2 vol points. A correlation below 0.98 or a median gap above 1 vol point stops
session 1 and is reported as a construction defect. [judgment on thresholds]

### 6.2 Implied variance, secondary: ATM [lit]

Mean of `impl_volatility` at `delta = 50, cp_flag = 'C'` and `delta = -50,
cp_flag = 'P'` on node d in `vsurfd`, squared. Reported next to every primary number
so the skew contribution is visible as the difference between the two.

### 6.3 Realized variance [lit]

Sum of squared log(1 + return) over trading days t+1 to t+h with h = 21 for d = 30 and
h = 63 for d = 91, scaled by 252/h. A window with any missing return is dropped.

### 6.4 Premium [lit, Carr and Wu 2009]

Primary is log(IV²_t / RV_t) with IV² from 6.1. Secondary is IV²_t − RV_t in annualized
variance points, comparable to Bollerslev, Tauchen and Zhou (2009) and Prokopczuk et al.
(2017). Both are also reported with IV² from 6.2.

### 6.5 Curve state

Sign version s_t. Sign of F2_t − F1_t on the Datastream continuous first and second
nearby series for the ETF's underlying, matched on trade date. F2 > F1 is contango,
F2 < F1 is backwardation, equality is dropped. The difference rather than a ratio, so
that the negative WTI settlement of 2020-04-20 is handled without special casing. Used
for figure 2 only. [judgment]

Slope version z_t. (F2_t − F1_t) / F1_t on the same series. The date 2020-04-20 is
dropped from this version for CL because F1 is negative. z_t is winsorized at the 1st
and 99th percentile per commodity, computed once on the common window before any test.
[judgment] This is the H2 regressor.

State is taken on the window's first day for both versions.

Curve-state series are ETF-agnostic: options are written on the ETF, the state is read
from the futures. The ETF-to-futures basis is disclosed and not modelled.

### 6.6 Commonality (Q3) [judgment]

First principal component of the four daily log(IV²/RV) series over the common window;
the share of total variance it explains is number one. Each series is then residualized
on its own z_t by OLS and the PCA is repeated; the share explained by the first
component of the residuals is number two. Pairwise correlations before and after are
reported alongside. Computed at both nodes. No test. With four series the first
component is always a large share, and the post says so.

### 6.7 Exclusions and robustness

April 2020. Included in every primary figure and test with the affected windows
marked. A robustness row excluding windows that start between 2020-03-01 and
2020-04-30 is reported next to every primary number.

Roll drag on USO and UNG affects return levels and not second moments to first order.
No adjustment.

## 7. Inference [stat]

Every H1 and H2 statistic on the overlapping daily series is reported three ways:
Newey-West with lag h, Hansen-Hodrick with lag h, and a stationary block bootstrap
(Politis and Romano 1994) with mean block length h and 2,000 draws. The non-overlapping
grid, anchored on the first common trade date, is a fourth row.

Decision rule, fixed here. A hypothesis is reported as supported only if the Newey-West
and the block-bootstrap p-values both clear the Holm-corrected level within their
block. Disagreement between the two is reported as "not robust to the inference
method", never as supported. At the 91-day node the non-overlapping row is reported
next to the headline in every table because 67 independent observations govern.

### Test family

| Block | Count | Method |
|---|---|---|
| H1 at 30-day, one per ETF | 4 | one-sided test of mean log ratio |
| H1 at 91-day, one per ETF | 4 | one-sided test of mean log ratio |
| H2 at 30-day, one per ETF plus pooled | 5 | OLS of log ratio on z_t; pooled with ETF fixed effects |
| H2 at 91-day, one per ETF plus pooled | 5 | as above |

Eighteen tests. Holm correction within each block. No test is added after results are
seen. The 91-day H2 block is underpowered for effects below half a standard deviation
and is labelled as such in every table.

## 8. Holdout and cost

No holdout. The item fits no predictive model and tunes no parameter on the data; the
window lengths, nodes, strike floors and winsorization points are fixed here before any
query runs.

No cost sweep. The item makes no strategy return claim. The short-variance Sharpe
framing in prior art is not reproduced.

## 9. Session plan

Session 1.
- Check for a VIX series in the `cboe` library and record its span.
- Identify the Datastream continuous first and second nearby series for GC, SI, CL, NG
  in `tr_ds_fut` (`wrds_cseries_info` and `dsfutcalcserval` or equivalents). Record per
  series: code, mnemonic, roll convention from the name and metadata, first and last
  date, number of dates matching OptionMetrics trade dates in the common window.
- Build the model-free implied variance (6.1) for the five secids at both nodes, run
  the VIX validation on SPX, and stop on failure.
- Pull the ATM node (6.2) and returns (6.3); compute both premium measures (6.4), daily
  and on the non-overlapping grid.
- Produce figure 1: annual mean log(IV²/RV), model-free, 30-day node, five series, 2009
  to 2025 with 2008 and 2025 marked partial. The 91-day version is a second panel.
- Kill check at end of session. [judgment] If for any commodity no first-and-second
  series pair matches at least 80 percent of the common window's trade dates, or the
  two series in a pair carry different roll conventions, curve state is dropped for that
  commodity. If it is dropped for all four, the item ships as the unconditional version
  and H2 and Q3 are recorded as not measured.

Session 2.
- Join curve state, build s_t and z_t, run the eighteen tests under section 7, produce
  figure 2 (per-ETF mean log ratio by sign state with CI and window counts, both
  nodes), figure 3 (H2 slope coefficients with CI, both nodes), the Q3 table, and the
  results table with the ATM secondary alongside.
- Write the post.

Budget is two sessions. The model-free construction is the heaviest code in the item
and sits in session 1. A third session needed for any reason drops the item to the back
of the queue with a one-line note on what blocked it.

## 10. Handling rules

Interpreter is `/Users/GualyCr/wrds-env/bin/python`. Column lists come from
`information_schema.columns`. Every OptionMetrics query filters on `secid` and `date`
before any other predicate; `opprcd` is pulled one secid and one year partition at a
time. Results and figures are written under `output/item1/` and not committed; code
under `src/item1/` is committed.

## 11. Outputs

Figure 1 (30-day panel, model-free) is the post figure. Figures 2 and 3 and the Q3
table go in the post's second slide or the repo README. The post opens with the H1
number for the four commodity ETFs pooled at 30 days, states the sample end as August
2025, states the inference rule from section 7 in one line, and labels the item as an
update and extension of Prokopczuk, Symeonidis and Wese Simen (2017).

## 12. Null abstracts

Null A, H1 fails. Across 2008 to 2025 the model-free implied variance of GLD, SLV, USO
and UNG options does not exceed subsequent realized variance on average at either
maturity; the commodity variance premium documented on futures options through the
mid-2010s does not appear in the ETF chain over this window, while SPX retains its
premium.

Null B, H2 fails. The commodity variance premium is present but its size does not vary
with the slope of the futures curve at either maturity; curve state carries no
information about the pricing of variance beyond its effect on realized variance.

Null C, Q3 unchanged. The first principal component of the four premia explains the
same share of variance before and after conditioning on slope; the commonality is not
a curve-state effect.

Null D, data does not support the measurement. Datastream continuous series for one or
more of GC, SI, CL, NG do not cover the common window or carry inconsistent roll
conventions across the first and second nearby; the item is reported as the
unconditional premium only and H2 and Q3 are recorded as unmeasured.

Null E, construction fails validation. The SPX model-free volatility built from
`opprcd` does not track VIX within the section 6.1 thresholds; the item stops at
session 1 and the defect is reported before any commodity number is produced.

## 13. Amendments

Logged after session 1 (2026-09-15) and before any hypothesis test. None changes a hypothesis, a sample window, a node, or the test family.

A1. Standard-settlement filter. Section 6.1 step 3 is amended: only standard-settlement contracts enter the strike set. Operationally, rows are kept only where ss_flag marks standard settlement and contract_size equals 100; the exact ss_flag encoding is read from the data and recorded. Reason: session 1 found split-adjusted chains sharing an exdate with the standard chain on 27 percent of UNG dates, 10 percent of USO and 16 percent of GLD, and the duplicate-collapse rule spliced them into one ladder (REPORT_s1 section 3.7). The filter is the standard OptionMetrics treatment of adjusted contracts. Primary results use the filter; the unfiltered series is retained and reported alongside so the effect of the amendment is visible. [lit]

A2. Datastream series identification. Session 1's selection rule required a "2ND" name marker and relied on the positionfwdcode and rollmethodcode columns of wrds_cseries_info. For mnemonics of the form XXXX.NN (Datastream's carriage of Reuters continuation records TRc1 to TRc12) those coded columns are the mnemonic suffix parsed as a CS-format code and are not reliable. Section 4's requirement, continuous first and second nearby series, is unchanged. Identification is verified against individual-contract data in tr_ds_fut by the procedure in session 1b, and the kill check of section 9 re-runs on the verified pair. [judgment on the verification thresholds, stated in session 1b]

A3. Two registered diagnostics, run before any test and counted outside the test family. (a) Selection check on the 3-strike floor: per secid and node, the mean ATM log ratio on dates retained by the model-free construction against dates dropped by it, with the difference and a Welch p-value. If the difference exceeds 0.10 log units or p is below 0.05, the model-free H1 result for that ETF is labelled as computed on a selected subsample and the ATM secondary carries the headline for it. (b) A floor-of-2 robustness series for every secid and node, reported as a robustness row next to every primary H1 number. [judgment on the 0.10 and 0.05 thresholds]

A4. Construction choices adopted. The implementation choices listed in REPORT_s1's closing section are adopted as part of the section 6.1 definition: expiry identity is (exdate, am_settlement); Q(K0) uses the single usable leg when one is missing; a usable quote requires best_bid > 0 and best_offer >= best_bid; the two-consecutive-zero-bid stop is counted along quoted rows; strike counts for the floor exclude K0; the zero rate falls back to the nearest earlier zerocd date. The open-interest duplicate collapse is superseded by A1 and is retained only as the fallback if duplicates survive the filter, with any such survivor counted and reported.

A5. Curve state from contract-level settlements. Logged 2026-09-15 after session 1b, before any hypothesis test. Section 6.5 is amended: F1_t and F2_t are the settlement prices of the nearest and second-nearest contracts whose last trading date is on or after t (session 1b's convention X), taken from tr_ds_fut.dsfutcontrval with contract identity and last trading date from tr_ds_fut.dsfutcontr, for classes 335 (gold), 3607 (silver), 1482 (light crude) and 1539 (natural gas). The Datastream continuous series named in section 4 are no longer an input; they served as verification, and the construction is verified where they exist: crude on both legs at 1.0000 within 0.5 percent, natural gas on the front leg at 1.0000, gold and silver on the second leg at 0.97 and 0.96 exact through 2013 (REPORT_s1b sections 1.4 to 1.6). A date is dropped for a commodity when either rank's settlement is null. Gold and silver contract values in these classes end 2022-12-28; their curve state covers 2008-12-08 to that date unless a continuing class is found under the rule below, and their H2 tests run on that subsample, disclosed in every table. The sign version s_t and slope version z_t, the winsorization, and the 2020-04-20 crude exclusion from z_t are unchanged. Reason: session 1b established that the pre-built continuous series are absent or unverifiable for three of the four contracts, while the contract-level table covers all four under one explicit roll rule. [judgment on the choice of convention X; verified on crude]

A5 continuation rule for gold and silver, fixed here. Session 2 searches for any other class in tr_ds_fut carrying COMEX or NYMEX gold or silver futures with contract values after 2022-12-28. A candidate class is accepted only if, on the overlap 2008-12-08 to 2022-12-28, its F1 and F2 match the class 335 or 3607 construction within 0.5 percent on at least 95 percent of dates. If accepted, the series are spliced at 2022-12-28 and the splice date is reported; if not, coverage stays at the class 335 and 3607 span. [judgment on the thresholds]

Q3 under A5. Section 6.6 runs on the window where all four z_t exist. The unconditioned first-component share is also reported on the full common window for reference. Correlation matrices are computed pairwise-complete because model-free retention differs by ETF; the ATM version is reported alongside as robustness. [judgment]
