# Item 3 · Short delta-hedged commodity variance with measured costs

Draft 3, 2026-09-17. Supersedes drafts 1 and 2. Every construction is specified here and
nothing is left to be set after measurement. Session 1 reports chain diagnostics and
computes no gains; its results change no parameter in this spec and can only trigger the
stop rules in section 16. Destination in the repository is
items/item3_short_variance/SPEC.md.

Rulings settled before drafting: two instrument arms (ruling 1), equal premium notional
(ruling 2), block C as one unconditional test plus one predictive slope (ruling 3), holdout
at the 2022 calendar boundary with the primary cost tier anchored to published effective
spreads (ruling 4).

---

## 1. Question

Item 1 found commodity ETF options priced above subsequent realized variance at 0.2048 log
units on the pooled 30-day ATM measure and about 0.36 on the model-free measure, with no
response to futures curve state. Item 3 asks whether a seller of that premium keeps a
positive expected return once the position is hedged daily at the close and a measured share
of the quoted option spread is paid at entry. Two instruments run as parallel arms, a
variance-swap replicating strike strip and an ATM straddle. The cost sweep runs from mid to
the full quoted half-spread. April 2020 is the pre-named stress window.

The item fits no parameter to data. Every cost level, sample boundary, filter and floor is
fixed in this document. The one data-dependent construction is the expanding quantile used
by the gate figure in section 7, which carries no test.

## 2. Data

Every source was probed in the Sep 15 2026 series probe. No new source enters.

| Source | Use |
|---|---|
| optionm_all opprcd, year partitions | Listed contracts, best_bid, best_offer, delta, impl_volatility, strike_price, ss_flag, contract_size |
| optionm_all secprd | ETF close, cfadj for corporate-action adjustment |
| optionm_all vsurfd | 30-day and 91-day standardized nodes for the secondary signal columns and one diagnostic |
| optionm_all zerocd | Zero-coupon rate interpolated to remaining tenor |

Fixed secids are GLD 122392, SLV 126776, USO 126681, UNG 129367. Feed end is 2025-08-29, so
the last cycle entered expires 2025-08-15 and nothing is claimed about 2026.

Options on commodity futures are absent from OptionMetrics IvyDB US and from the WRDS
subscription, so the item trades ETF options throughout. Section 15 records what that
implies for comparison with the published literature.

## 3. Position

**Cycle calendar.** Entry is the first trading day after each standard monthly expiration.
The position expires at the next standard monthly expiration. Weekly and quarterly expiries
are excluded. Cycles are non-overlapping and contiguous, so every trading day between an
ETF's first entry and its last expiration belongs to exactly one cycle. Both arms enter and
exit on the same dates.

**Forward.** Following the CBOE VIX methodology, let K* be the strike at which the absolute
difference between the call mid and the put mid is smallest among strikes where both legs
pass the row filters below, ties broken by the lower strike. Then

  F = K* + e^{rT}(C(K*) − P(K*))

with r the zerocd rate interpolated to T, the calendar time to expiration in years on an
actual/365 basis. K_0 is the highest strike below F among strikes passing the filters. The
forward is computed once, at the entry close, and fixes both arms' strike selection.

**Row filters.** Every traded leg requires ss_flag = '0', contract_size = 100,
best_bid > 0, and best_offer > best_bid, evaluated at the entry close.

**Arm 1, the strike strip.** Short out-of-the-money puts at strikes below K_0 and
out-of-the-money calls at strikes above K_0, plus a short position at K_0 itself using the
average of the call and put. Leg quantities are proportional to

  w_i = ΔK_i / K_i²

where ΔK_i is half the distance between the strikes adjacent to K_i, and for the lowest and
highest traded strikes ΔK equals the distance to the single adjacent strike. The 1/K_i²
weighting alone does not replicate variance on a chain with irregular strike spacing, and
listed commodity ETF chains widen from roughly one dollar near the money to five dollars or
more in the wings, so ΔK_i is carried explicitly.

The fair variance strike at entry is

  K = (2 e^{rT}/T) Σ_i w_i Q(K_i) − (1/T)(F/K_0 − 1)²

with Q(K_i) the mid price of the OTM option at K_i and the average of call and put mids at
K_0. This is the construction item 1 validated against VIX on SPX at 0.9989 correlation, and
item 3 calls the same code path, so K and item 1's model-free series are the same object
computed on the same strikes.

K uses listed strikes only, with no extrapolated tail, because the traded portfolio holds
only listed strikes. A flat-tail extrapolated value on a dense grid is computed alongside as
the replication-shortfall diagnostic in section 8.

Quantities are continuous. Integer-contract rounding is not imposed, and section 8 reports
the minimum position size at which rounding every leg to the nearest contract moves K by less
than one percent, so the size at which the construction becomes tradable is measured rather
than assumed.

**Arm 2, the ATM straddle.** Short one call and one put at the strike nearest F among strikes
where both legs pass the filters, ties broken by the lower strike. If no such strike lies
within 5 percent of F in absolute terms, the cycle is excluded for this arm and counted.

**Hedge.** Net position delta is hedged in ETF shares at each daily close, including the
entry close. Delta is the opprcd delta of each leg times its quantity times 100. When a leg's
delta is null, delta is recomputed from Black-Scholes using the leg's mid, the ETF close, the
zerocd rate to remaining tenor, and the leg's own impl_volatility, falling back to the prior
day's implied volatility for that leg when impl_volatility is also null. When both paths fail,
the prior day's hedge is carried and the day is counted in the fallback tally.

**Marking.** Every open leg is marked each day as follows. When best_bid > 0 and
best_offer > best_bid, the mark is the mid. When best_bid = 0 and best_offer > 0, the mark is
best_offer / 2, which overstates the liability of a short leg and is therefore conservative
for this study; the count of such marks enters the per-cycle diagnostics. When both quotes are
absent or zero, the last valid mark is carried and the day is counted. Zero-bid wings are the
expected state of the far strip for much of a cycle, so this rule governs a large share of
strip marks and is not an edge case.

The entry fill is at mid minus k times the leg's half-spread, while the entry-close mark is at
mid, so the option execution cost appears as a day-one mark-to-market loss.

**Expiration.** Legs settle at intrinsic value against the ETF close on the expiration date.
Assigned shares net against the hedge and any residual is closed at that close. Early exercise
before expiration is not modelled, and section 13 states what that omits.

## 4. Realized variance

For a cycle spanning n trading days from the entry close to the expiration close,

  RV = (252 / n) Σ_{t=1}^{n} r_t²,  r_t = ln(P_t / P_{t−1})

with P the secprd close adjusted for corporate actions through cfadj, t = 1 the first close
after the entry close, and t = n the expiration close. No mean is subtracted and the divisor
is n. A return at or below −100 percent is treated as missing, the correction item 2 made to
the shared realized-variance code. A cycle carrying any missing return is flagged and excluded
for both arms, and counted.

RV21, the signal input in section 7, uses the same formula with n = 21 over the trailing 21
closes ending at the entry close.

These conventions match item 1 and item 2 exactly, so realized variance is one object across
the three items.

## 5. Sizing, premium and the cycle return

**Entry mid premium.** For a position with signed leg quantities q_i,

  P_entry = Σ_i |q_i| × 100 × mid_i

with mid_i the entry-close mid of leg i. Quantities enter explicitly, so the strip's wide-wing
legs contribute in proportion to the small quantities the ΔK_i / K_i² weighting assigns them.

**Strip arm.** Variance notional is set to N = 1/K at entry, which sells one unit of entry
premium because the strip's cost per unit of variance notional is K·e^{−rT} to first order.
The theoretical gross short return is 1 − RV/K. The reported return is the realized gain from
marks, settlement, hedge trades, financing and costs, divided by P_entry, and the 1 − RV/K form
serves as the target the realized number is checked against.

**Straddle arm.** The cycle gain is divided by that arm's own P_entry.

**Pooled rows.** Equal-weighted average of the ETF returns available on a cycle date, with the
ETF count printed in every pooled row. The pooled series begins at the first cycle where at
least two ETFs are available, the May 2007 entry for USO and UNG, and the count rises to four
from the December 2008 entry onward. No balanced-panel restriction applies anywhere.

**Secondary columns, per ETF.** Gain in variance points, meaning N = 1 with the result in
K − RV units, and gain normalized by the ETF close at entry, the Bakshi and Kapadia (2003)
convention.

**Financing.** Interest accrues daily on the net cash balance, defined as cumulative premium
received net of option costs plus cumulative cash from hedge share trades, at the zerocd rate
interpolated to remaining tenor, refreshed daily, simple accrual on actual/365. Interest is
earned on positive balances and paid on negative balances at the same rate. Short share
positions additionally accrue borrow at zerocd plus 50 basis points annualized on the absolute
market value of the short, reported with sensitivities at 0 and 200 basis points outside the
cost grid. Hedge cost c in section 6 covers share spread and commission only, so borrow is
charged once.

**Costs of premium normalization, carried in the writeup.** Sizing shrinks the position when
implied variance is high, so a volatility-timing effect runs through every cycle, and the block
A and B means and every stress statistic carry it. A mean return can be negative where item 1's
mean log ratio is positive, because 1 − RV/K ≤ log(K/RV) holds cycle by cycle. The relevant item
1 figure for the strip arm is the model-free 0.36 because the strip trades K; 0.2048 is the ATM
figure and bounds the straddle arm.

## 6. Costs

Costs enter as a pre-registered sweep. No single cost figure is admissible as a result.

| Parameter | Grid | Meaning |
|---|---|---|
| k, option execution | 0, 0.25, 0.5, 0.75, 1.0 | Each leg sold at mid minus k times its own half-spread at entry |
| c, hedge cost | 0, 2, 5, 10 bps | Charged on the absolute notional of every share trade, covering share spread and commission |

The option cost at execution fraction k is

  cost_k = k × Σ_i |q_i| × 100 × (best_offer_i − best_bid_i) / 2

so k = 1.0 charges the full quoted half-spread on every leg, which equals half the total quoted
spread. Every headline statistic is reported on all 20 cells, per arm. No option cost is charged
at expiration because settlement is at intrinsic.

**Denominator.** P_entry fixes the denominator in every cell, so position size is constant
across the grid and the sweep isolates cost. Because the alternative convention shares a
numerator, breakeven k and every verdict are invariant to this choice, and the difference is a
level effect growing with k.

**Primary tier, fixed now at k = 0.5 and c = 2 bps, both arms.** Muravyev and Pearson (2020,
RFS 33(11)) measure adjusted effective option spreads at about 54 percent of quoted spreads,
which places the realistic execution fraction of the half-spread near 0.5 and makes k = 0.5 the
nearest grid point. Their sample is US equity options from 2003 to 2006, so transferring 54
percent to commodity ETF options over 2007 to 2025 is an inference and is disclosed as one.
No measurement in session 1 moves this tier.

**Headline result.** Breakeven k, the execution fraction at which the mean return reaches zero,
is reported per ETF, arm and value of c, with a stationary block bootstrap interval. A mean
return already negative at k = 0 reports as negative at mid. A mean return still positive at
k = 1.0 reports as surviving the full quoted half-spread. The reader can substitute any
execution assumption against that number without relying on the primary tier.

## 7. Timing signals

Both signals use only information available at the entry close.

**O1, ex-ante premium.** log(K / RV21), with K the strip's fair variance strike from section 3
and RV21 from section 4. Goyal and Saretto (2009 JFE) is the published anchor and their
close-to-close convention matches section 4. The ATM variant, log(σ²_ATM / RV21), is reported
beside it with no test.

**O2, implied term structure.** IV30 / IV91 from the vsurfd 50-delta nodes. Johnson (2017 JFQA
52(6)) shows the VIX term-structure slope predicts synthetic variance swap and straddle excess
returns, with an upward-sloping term structure marking the favourable state for a variance
seller; a high IV30 / IV91 ratio is the inverted case, which is the state O2 skips. Exploratory
throughout, because Johnson's evidence is on equity index volatility and no published work
applies a term-structure slope to commodity variance selling.

**Three implied-variance objects, distinguished.** K is the model-free strike from the traded
strike ladder. σ²_ATM is the square of the average of the call and put impl_volatility at the
traded straddle strike, from opprcd. IV30 and IV91 are the averages of the 50-delta call and put
nodes from vsurfd at those tenors. The three differ, and section 12 reports the correlations
among them. The seventeen dates in 2020 carrying null vsurfd implied volatility for every secid
affect only the secondary columns and O2, since K and σ²_ATM come from opprcd.

**Tested form.** O1 enters block C as a predictive slope on stacked ETF-cycle rows over the
holdout, with cycle return as the regressand and the raw log ratio, unstandardized, as the
regressor, and the coefficient reported per log unit. No full-sample moment enters the
construction. The strip arm carries the test.

**Inference for the slope.** OLS with standard errors clustered by cycle date, plus a wild
cluster bootstrap using Rademacher weights, 9,999 replications, seed 20260917. A test is
supported only when the clustered interval and the bootstrap both clear. Forty-three clusters
sits at the low end for cluster-robust inference, which is why the bootstrap governs. This
procedure replaces section 9's mean-test inference for this one test, and the two are never
combined.

**The mechanical channel, disclosed and diagnosed.** The regressand 1 − RV/K rises in K holding
RV fixed, and the regressor log(K / RV21) also rises in K, so a positive slope can arise without
K carrying any forecasting power. No sizing convention removes this, since the variance-points
payoff K − RV rises in K as well. Three regressions are run and only the first is the registered
test.

1. Return on log(K / RV21). Registered, with the inference above.
2. Return on log K and log RV21 as separate regressors. Diagnostic, no p-value.
3. Cycle RV on log K and log RV21. Diagnostic, no p-value. A K with no power to forecast RV
   makes the registered slope mechanical, and this regression says which.

**Implementation figure, no test.** The binary gate trades a cycle when O1 sits at or above the
expanding median of its own history on prior entry dates for that ETF and skips otherwise.
Skipped cycles enter as zero returns over the full cycle count, so the curve reads as a portfolio
return on a fixed schedule. The first 36 cycles of each ETF always trade. O2's gate at the
expanding 90th percentile is reported the same way. The expanding quantile is the only
data-dependent construction in the item.

A slope detects a monotone relationship, so a threshold effect concentrated in the top decile of
O1 would show in the gate figure while the slope underweights it. The registered claim is that
O1 orders returns, and the writeup states it in those terms.

## 8. Diagnostics computed per cycle, no tests

- Strip traded strike count on each side of K_0, the traded moneyness span each side in units of
  σ_ATM √T, and the count of zero-bid marks over the cycle life.
- Replication shortfall, defined as K from listed strikes divided by K computed with Jiang-Tian
  flat-tail extrapolation on a 1,000-point strike grid on the same date. Item 2 measured a
  truncated 34-node surface measure recovering 0.92 of σ² before extrapolation, so the traded
  strip's shortfall is measured rather than assumed away.
- Minimum position size at which rounding every strip leg to the nearest integer contract moves
  K by less than one percent.
- Delta fallback count and the share of cycle days on a carried hedge.

## 9. Hypotheses and test family

| Block | Test | Window | Arms | Count |
|---|---|---|---|---|
| A | Mean cycle return > 0 at k = 0, c = 0, per ETF and pooled | Estimation | Both | 10 |
| B | Mean cycle return > 0 at k = 0.5, c = 2 bps, per ETF and pooled | Estimation | Both | 10 |
| C | Pooled unconditional mean return > 0 at k = 0.5, c = 2 bps | Holdout | Strip | 1 |
| C | O1 predictive slope ≠ 0 | Holdout | Strip | 1 |

Twenty-two tests. Blocks A and B run on each ETF's own estimation cycles, 163 for GLD, 157 for
SLV, 176 for USO and 176 for UNG, and on 176 pooled estimation cycles. Block C's mean test runs
on 43 pooled holdout cycles and its slope on at most 172 holdout ETF-cycle rows, fewer wherever
an ETF fails a filter or a floor on a given cycle.

**Inference for the twenty mean tests and the block C mean test.** Newey-West standard errors on
cycle returns with lag 4 for estimation-window tests and lag 3 for the holdout test, both from
floor(4(T/100)^{2/9}) at the cycle counts above and frozen here. A stationary block bootstrap on
cycles with seed 20260917, 9,999 replications. Holm correction within each block. A test is
supported only when Newey-West and the bootstrap both clear after correction. The block C slope
uses section 7's procedure and nothing here.

Two properties of this family go in the writeup. Holm assumes nothing about dependence, and the
two arms on one ETF will be strongly correlated, so the correction is conservative; item 1's
convention is kept anyway. Block A also confirms item 1 on a different sample construction, and
its ten tests earn their place by separating null N-A from null N-B.

Because the strip's payoff is quadratic in realized volatility, the left tail is heavy and a few
cycles can set the sign of a mean. Every mean is reported with median, skewness, 5 percent CVaR,
and the share of cumulative loss contributed by the worst 5 percent of cycles. Daily marked
returns give annualized Sharpe with Newey-West errors as a descriptive statistic outside the
family.

## 10. Samples and holdout

| Window | Definition | Cycles |
|---|---|---|
| Estimation, per ETF | Cycles entered from the ETF's first full cycle through 2021-12-31 | GLD 163, SLV 157, USO 176, UNG 176 |
| Estimation, pooled | Cycles entered 2007-05 through 2021-12-31, averaged over available ETFs | 176 |
| Holdout | Cycles entered 2022-01-01 through the last cycle expiring by 2025-08-29 | 43 |

Windows are defined by entry date and they tile without gap or overlap. The last estimation
cycle is entered 2021-12-20 and expires 2022-01-21. The first holdout cycle is entered
2022-01-24 and the last is entered 2025-07-21, expiring 2025-08-15; the cycle entered 2025-08-18
would expire 2025-09-19, past the feed end, so it is excluded. Holdout entries number 12 in each
of 2022, 2023 and 2024 and 7 in 2025.

First entries are GLD 2008-06-23, SLV 2008-12-22, USO 2007-05-21 and UNG 2007-05-21, each the
first trading day after the monthly expiration following that ETF's OptionMetrics start date.
Starting each ETF at its own first cycle rather than at a common December 2008 date adds 6 cycles
for GLD and 19 each for USO and UNG.

**Why this boundary.** The holdout is 20 percent of the pooled sample, a conventional split, at a
calendar-year boundary for reproducibility, and it excludes the April 2020 cycle so the named
stress analysis sits inside the estimation window. An earlier boundary would give more holdout
cycles and more slope power; the earliest boundary still excluding April 2020 falls in May 2020
and would yield about 63 holdout cycles. The trade is deliberate: a holdout containing the
single largest loss in the sample would have its mean and every tail statistic set by one event,
and the item's stress section is a named deliverable that belongs in-sample. This spec takes the
power cost and says so.

Item 1 measured the premium over the full 2008 to 2025 sample, so no unconditional result in
item 3 is out of sample in the strict sense, and the writeup states that.

## 11. Stress analysis

- **April 2020.** The cycle containing 2020-04-20 for each ETF and arm, with daily marked equity,
  hedge trades, and the loss split into realized-gamma and implied-volatility components using
  entry Greeks. USO changed its futures roll methodology during April 2020 and executed a reverse
  split at the end of the month, so the USO cycle is a case study and any contract that cannot be
  tracked through the split is shown as a gap with no imputation. The jump term separating
  log-contract variance from summed squared returns is reported for this cycle, along with the
  simple-versus-log return gap in the hedge accrual.
- **Worst windows.** Worst single cycle, worst rolling three-cycle window, maximum drawdown on
  daily marked equity, and recovery time in trading days to the prior peak, for each of the 20
  cost cells and each arm. A drawdown unrecovered by 2025-08-29 reports as unrecovered.
- **Other named windows.** Autumn 2008 for GLD and the energy ETFs, March 2020 for all four, and
  2022 for UNG.
- **Cost drift.** Breakeven k by calendar year, arm and c, and entry quoted half-spread as a share
  of P_entry by year.

## 12. Exploratory series, no p-values

**Convexity series.** The per-cycle difference between the strip and straddle returns. Write
u = σ_RV / σ_ATM and g = K / σ²_ATM. The strip returns 1 − RV/K = 1 − u²/g and the straddle
returns approximately 1 − u, so the difference is

  u − u²/g

At g = 1, a flat surface, this reduces to u(1 − u), which vanishes at u = 1. At g > 1, the case in
commodity chains, the difference at u = 1 is 1 − 1/g, which is 0.144 at g = exp(0.36 − 0.2048) =
1.168, the value implied by item 1's own model-free and ATM figures. Drafts 1 and 2 stated the u(1 − u) form alone, which silently sets
g = 1 and therefore assumes away the quantity this series exists to measure. Because u − u²/g is
non-monotone in u, the series is reported against u and g jointly rather than as a scalar.

**Ex-ante wing gap.** log(K / σ²_ATM), which is log g, measured at entry on every cycle. It is
item 4's quantity measured one cycle at a time, and it is reported beside the convexity series so
item 4 has something to read against.

**Link to item 1 and internal consistency.** Correlation of entry K with item 1's model-free
series on matching dates, of σ²_ATM with IV30², and of IV30 with the vsurfd node item 1 used.

## 13. Disclosures

- Early exercise of American ETF options is not modelled. Deep in-the-money short legs can be
  assigned early, which bears more on the strip arm because the ΔK_i / K_i² weighting puts the
  largest quantities on low-strike puts.
- Zero-bid legs are marked at half the offer, which overstates a short leg's liability. The
  direction is conservative for this study and the count of such marks is reported per cycle.
- Hedge cost c falls harder on the strip arm, whose flatter dollar gamma forces more share
  turnover than the straddle's, which decays as spot leaves the strike. The same c in basis points
  therefore charges the strip more.
- Integer-contract rounding is not imposed. Section 8 measures the size at which it stops
  mattering, and below that size a trader would lose the far wings and hold something closer to a
  strangle.
- Margin is not modelled. Returns are per unit of entry premium and say nothing about return on
  posted margin.
- Interest is earned on positive cash balances at the same rate paid on negative ones, which
  overstates what a retail account would earn.
- Borrow is charged at zerocd plus 50 basis points on short share positions, a fixed assumption
  with no series in the held data; sensitivities at 0 and 200 basis points are reported.
- The k = 0.5 primary tier rests on Muravyev and Pearson's 54 percent effective-to-quoted ratio
  measured on US equity options from 2003 to 2006. No trade prints for commodity ETF options are
  in the purchase, so the transfer is an inference and breakeven k is the result that does not
  depend on it.
- OptionMetrics quotes are end-of-day best bid and offer, and executing at those quotes at the
  close is an assumption.
- O1 inherits estimation noise. Under constant volatility, 21 close-to-close returns give a
  relative standard error near √(2/21), about 31 percent.
- Seventeen dates from 2020-07-27 to 2020-08-18 carry null vsurfd implied volatility for every
  secid, found in item 2. They affect O2 and the secondary signal column only.

## 14. Session 1 diagnostics, no gains computed

Session 1 changes no parameter in this spec. Its output is descriptive and can only trigger a
stop rule in section 16.

1. Corporate actions on all four secids from secprd cfadj and opprcd ss_flag, with dates.
2. Cycle inventory per ETF per year, with calendar days to expiration at entry and the count of
   cycles meeting the section 3 filters for each arm.
3. Entry quoted half-spread as a share of P_entry, per arm, ETF and year, with percentiles, and
   the realized cost at each of the five k values. Reported for the full sample and separately for
   the estimation window, with the k = 0.5 tier held fixed either way.
4. Delta null rate and null run lengths over each cycle's life, and the success rate of each
   fallback path.
5. Strip strike coverage per cycle, meaning strike counts each side of K_0 and the traded span in
   units of σ_ATM √T, by ETF and year, with the count of cycles passing the section 16 floor.
6. Zero-bid mark frequency by leg moneyness and cycle day, for the strip.
7. USO and UNG chain continuity from 2020-03-01 to 2020-06-30, including whether contracts held
   across a split survive the ss_flag filter.
8. Estimation and holdout cycle counts per ETF against the section 10 table.
9. Correlation of entry K with item 1's model-free series, and of σ²_ATM, IV30² and K with each
   other.
10. Replication shortfall distribution and the integer-rounding size threshold from section 8.

## 15. Prior art and how this item sits against it

Checked before freeze, Sep 17 2026.

**Prokopczuk, Symeonidis and Wese Simen (2017, JBF 81, 136-149).** Their sample is American
options on commodity futures from the Commodity Research Bureau, January 1984 to July 2011, 21
commodities, 60-day synthetic variance swaps held to expiry with no delta hedge, and costs entered
as assumed haircuts. Item 1 and item 3 use ETF options from OptionMetrics over 2007 to 2025 at 30
and 91 days with daily delta hedging and a quoted-spread sweep. The instrument, vendor, sample
period, horizon, hedging protocol and cost method all differ, and the samples do not overlap after
2011. Neither item is an update or a replication of that paper, and both state the instrument
difference explicitly. The difference is asset-dependent, since GLD and SLV track spot bullion
closely while USO and UNG hold rolling futures and carry roll drag and reverse splits, so ETF
variance and front-futures variance diverge more for the energy pair.

**Trolle and Schwartz (2010, Journal of Derivatives 17(3), 15).** NYMEX crude and natural gas
futures options, 1996 to 2006, synthetic variance swaps by Carr-Madan. Short-variance annualized
Sharpe of 0.59 for crude and 0.35 for natural gas against 1.02 for S&P 500 variance. Energy
premia are a third to a half of the equity index premium before costs, which is the prior
expectation item 3's cost sweep runs against.

**Jia, Ruan and Zhang (2023, Journal of Commodity Markets 31, 100334).** Risk-neutral variance and
covariance rates on USO ETF options, used to predict USO excess returns. The closest existing work
to item 3's instrument. No variance selling, no delta hedge, no cost treatment.

**Muravyev and Pearson (2020, RFS 33(11), 4973-5014).** Adjusted effective option spreads at about
54 percent of quoted, on US equity options 2003 to 2006. The anchor for the k = 0.5 primary tier.

**Johnson (2017, JFQA 52(6), 2461-2490).** The VIX term-structure slope predicts synthetic S&P 500
variance swap, VIX futures and straddle excess returns. The anchor for O2's direction, on equity
index volatility.

**Gap.** No published cost-adjusted backtest of short variance or short delta-hedged positions on
commodity ETF options was found, and no published use of an implied term-structure slope as a
timing filter for commodity variance selling. The search covered ScienceDirect, RePEc, SSRN and
open working-paper copies. Absence from that search is weaker than a systematic database sweep and
the writeup says so.

**Also cited for construction.** Carr and Madan (1998), Demeterfi, Derman, Kamal and Zou (1999),
Britten-Jones and Neuberger (2000), Jiang and Tian (2005), Carr and Wu (2009), Bakshi and Kapadia
(2003), Goyal and Saretto (2009), Politis and Romano (1994), Cameron, Gelbach and Miller (2008) for
the wild cluster bootstrap.

## 16. Stop rules

1. An ETF with fewer than 80 percent of its estimation cycles passing the section 3 filters drops
   from that arm's family, the drop is recorded, and the test count falls accordingly. Floors apply
   per arm, so an ETF may remain in one arm and drop from the other.
2. Struck by amendment A1. ~~A strip cycle requires at least 6 strikes with two-sided quotes on each
   side of K_0 and a traded span of at least 1.5 σ_ATM √T on each side of F. A cycle failing either
   condition is excluded for the strip arm and counted. The floor is a viability bar; the section 8
   replication shortfall, not the floor, governs how a passing cycle is interpreted.~~
3. A straddle cycle with no filter-passing strike within 5 percent of F is excluded for that arm
   and counted.
4. A cycle carrying a missing return under section 4 is excluded for both arms and counted.
5. A contract that cannot be tracked through a corporate action ends its cycle at the last valid
   mark, and the cycle is flagged with no imputation.
6. Session 2 is the first session that computes returns. If it ends without producing at least one
   of the section 18 figures, the item moves to the back of the series queue with a one-line note
   on what blocked it, and item 4 opens the same day.

## 17. Null abstracts

**N-A, premium absent at mid.** One or both instruments fail to earn a positive mean return before
costs on one or more ETFs, which would place item 1's measured premium inside the path dependence
of discrete daily hedging and inside the gap between listed-strike replication and the extrapolated
model-free measure. Mixed outcomes across ETFs and arms are reported cell by cell.

**N-B, premium consumed by costs.** Returns are positive at mid and fail at k = 0.5 with c = 2 bps,
with breakeven k reported per ETF, arm and c as the measured quantity a trader would need to beat.
The strip and the straddle may fail at different k, and that difference locates the cost in the
wings.

**N-C, estimation result does not survive the holdout.** The pooled mean return clears in the
estimation window and fails on the 43 holdout cycles, which would say the premium net of costs is
period-specific. Forty-three cycles cannot resolve a small effect, so the estimate and its interval
are reported before any verdict language.

**N-D, the signal does not order returns.** The O1 slope is indistinguishable from zero, consistent
with item 1's finding that the premium behaves like a flat tax. If diagnostic regression 3 in
section 7 shows K carries no power to forecast cycle RV, a nonzero slope is reported as mechanical
rather than predictive. Power against a modest monotone effect is low at this sample size and the
writeup says so before reporting the estimate.

**N-E, data does not support the trade.** Entry quotes, straddle strike availability or return
completeness fail the section 16 floors for one or more ETFs or one arm entirely, and the item
reports the chain properties that block the measurement.

## 18. Figures

1. Panel A, pooled daily marked equity at k = 0.5 and c = 2 bps for both arms, with the named
   stress windows shaded. Panel B, the same series as a fan over the five k values at c = 2 bps.
2. Mean cycle return over the k by c grid, one panel per arm.

## 19. Checklist

A line reads yes before freeze.

1. Every quantity is measurable from section 2 and every formula is written out.
2. Realized variance, the forward, the strip weights, the premium denominator, the marking rule and
   financing are each defined once and used everywhere.
3. No parameter is set after measurement. Session 1 changes nothing.
4. Sample windows tile by entry date with no orphan cycle, and every cycle count is stated.
5. Inference is specified per test, with lags, replications and seed frozen.
6. The O1 slope's mechanical channel is disclosed with its diagnostic.
7. Null abstracts cover every outcome the section 9 family can produce, including holdout failure.
8. The instrument difference against the published commodity variance literature is stated.
