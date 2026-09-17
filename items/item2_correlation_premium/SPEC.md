# Item 2 — Correlation risk premium: the index against its constituents

Series: options-series. Draft 2 of 2026-09-16, frozen on sign-off. One session.
Basis tags as in item 1: [lit] follows a published convention, [stat] is statistical
convention, [judgment] is set by the author with no derivation.

## 1. Questions

Q1. Is the variance premium on the S&P 500 index larger than the average variance
premium on its constituents, and by how much.

Q2. Did the gap change between the post-crisis decade and the post-COVID years.

Q3 (exploratory). How is the single-name premium distributed across the cross-section,
how much of the index-minus-average gap is an implied-correlation premium as opposed
to a difference in how variance is priced on the index against the names, and when
in the sample the gap shifted, if it did.

## 2. Prior art

Driessen, Maenhout and Vilkov (2009, Journal of Finance) show that index options carry
a variance premium that individual equity options largely do not, and attribute the gap
to priced correlation risk. Their sample ends in 2003 and their implied-correlation
construction is the one used here. [lit] Carr and Wu (2009) supply the premium
convention. The delta-grid integration of the implied surface follows the practice of
computing risk-neutral moments from the OptionMetrics surface file (Conrad, Dittmar
and Ghysels 2013, Journal of Finance). [lit]

## 3. Hypotheses

H1. Mean log(IV²/RV) on SPX exceeds the equal-weighted mean of log(IV²/RV) across
current constituents. One-sided. Both nodes. [lit]

H2. The index-minus-average gap over 2021-01-01 to 2025-08-29 differs from the gap over
2010-01-01 to 2019-12-31. Two-sided, sign not registered. Both nodes. [judgment on the
boundaries: the two calm regimes on either side of the 2020 shock; 2008-2009 and 2020
are reported as their own cells and enter no test]

H3. Mean implied correlation exceeds mean realized correlation over the following
window. One-sided. Both nodes. [lit]

Q3 carries no test.

## 4. Data

| Quantity | Source |
|---|---|
| Index membership, point in time | `crsp_q_stock.dsp500list_v2` (permno, mbrstartdt, mbrenddt) |
| permno to secid | `wrdsapps_link_crsp_optionm.opcrsphist`, date-ranged; one secid per permno per date |
| Implied surface, names and SPX | `optionm.vsurfdYYYY`, `days ∈ {30, 91}`, all 34 delta nodes, `impl_volatility` and `impl_strike` |
| Returns | `optionm.secprdYYYY` `return` for every secid; SPX 108105 |
| Market cap for value weights | `crsp_q_stock.dsf_v2`, `dlyprc × shrout`, previous trading day |
| SPX ladder model-free series | item 1, `items/item1_commodity_vrp/data/model_free_variance.parquet`, validation only |

Item 1's realized variance, log ratio, inference and figure code are reused unchanged.

## 5. Sample

1996-01-04 to 2025-08-29, the full vsurfd span. Periods for reporting: 1996-2007,
2008-2009, 2010-2019, 2020, 2021-2025. Observations are daily and overlapping;
inference is item 1's section 7 rule, Newey-West and stationary block bootstrap both
clearing Holm within block, with Hansen-Hodrick and the non-overlapping grid as further
rows.

Two floors, both counts reported by year. [judgment]
- H1 and H2 averages: a date enters when at least 300 constituents carry a valid
  surface-based variance at that maturity.
- H3 correlation: a date enters when at least 450 constituents do, because names
  missing from the cross-product shrink the denominator while the index variance still
  includes them, which biases implied correlation upward.

## 6. Measurement

### 6.1 Implied variance, primary: surface-based model-free [lit]

Per secid, date and maturity d, the 17 call nodes (delta 10 to 90) and 17 put nodes
(delta −10 to −90) carry `impl_volatility` and `impl_strike`. Convert each node to a
Black-Scholes price at its own implied vol and strike, using the forward implied by
the 50-delta pair and the zero rate from `zerocd`. Order the 34 strikes, take
out-of-the-money prices on each side of the forward, and evaluate the item 1 sum
(2/T) Σ ΔK/K² e^{rT} Q(K) − (1/T)(F/K0 − 1)² over the grid with ΔK the half-distance
between neighbouring strikes. A secid-date is dropped at that maturity if any node's
`impl_volatility` is null. The measure truncates the tails beyond 10 delta.

Validation, run before any premium is computed. On SPX over the item 1 window, the
surface-based series is compared to item 1's strike-ladder series: correlation of
levels, median and mean level gap in variance points and in log units, and the share
of dates differing by more than 10 percent in variance. The median log gap is the
tail-truncation term and is reported in every table as the amount by which the
surface measure understates the ladder measure on SPX. Stop rule: correlation below
0.98 stops the session and the item ships as ATM-only under section 6.2. [judgment on
the threshold]

### 6.2 Implied variance, secondary: ATM [lit]

Mean of `impl_volatility` at delta ±50, squared, as in item 1. Reported next to every
primary number.

### 6.3 Realized variance [lit]

Item 1's construction: sum of squared daily log returns over the following 21 or 63
trading days, annualized by 252/h.

### 6.4 Premiums [lit, Carr and Wu 2009]

Single-name premium log(IV²_i,t / RV_i,t). Average is equal-weighted across names
present on date t; value-weighted reported alongside. Index premium is the same on
SPX. Gap_t = index premium minus equal-weighted average.

### 6.5 Implied and realized correlation [lit, DMV 2009]

ρ^imp_t = (IV²_index − Σ w_i² IV²_i) / Σ_{i≠j} w_i w_j IV_i IV_j with value weights
from the previous day's market cap renormalized over names present, and IV² the
surface-based measure. Realized correlation is the same formula on realized variances
over the following window.

### 6.6 Decomposition (Q3) [judgment]

Gap_t is split into the log index variance the correlation premium adds at the
observed single-name variances, log(ρ^imp Σ_{i≠j} w_i w_j IV_i IV_j + Σ w_i² IV²_i)
minus the same at ρ^real, and the residual. Reported by period, both nodes.

### 6.7 Cross-section and timing (Q3)

Per year, deciles of the single-name premium at 30 days and the share of names whose
annual premium exceeds the index premium. A single break date in the annual gap series
estimated by least squares (Bai and Perron 1998), reported with no test. The share of
SPX option volume at zero days to expiry by year from `opprcd`, overlaid on the gap in
one figure, no test.

## 7. Test family

| Block | Count |
|---|---|
| H1, one per node | 2 |
| H2, one per node | 2 |
| H3, one per node | 2 |

Six tests, Holm within block. Nothing added after results are seen.

## 8. Holdout and cost

None. No fitted model, no strategy return. Item 5 (dispersion) is the trade.

## 9. Stop rules, in order

1. Link coverage. On the median date, fewer than 90 percent of constituents map to a
   secid with a valid 30-day surface: stop, report coverage by year, no test runs.
2. Surface validation. Correlation with the item 1 SPX ladder series below 0.98:
   continue with ATM as primary and record null E.
3. Pull time. If the vsurfd pulls exceed 120 minutes wall clock, restrict the sample
   to 2005-01-03 onward and record the restriction.
4. Membership span. If dsp500list_v2 does not cover the sample start, the sample
   starts where the table does and the start is reported.

## 10. Outputs

Figure 1 (post): annual mean premium, index against the equal-weighted constituent
average, 30-day node, the five periods shaded.
Figure 2: implied against realized correlation, annual means, both nodes.
Figure 3: yearly decile band of single-name premia with the index premium overlaid.
Figure 4: the gap by year with the 0DTE volume share and the estimated break date.
RESULTS.md under items/item2_correlation_premium/output/; a README section appended
in the repo's format.

## 11. Null abstracts

Null A. The index premium does not exceed the average constituent premium on 1996-2025
data; the gap DMV documented through 2003 has closed.
Null B. The gap over 2021-2025 is indistinguishable from 2010-2019.
Null C. Implied correlation does not exceed realized correlation; the index premium is
a variance-pricing difference and not a correlation premium.
Null D. Link coverage fails rule 9.1 and the item ships as a coverage report.
Null E. The surface-based construction fails validation against the ladder series and
the item ships on the ATM measure with the skew term unmeasured.
