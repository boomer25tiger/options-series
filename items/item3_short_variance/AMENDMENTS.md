# Item 3 amendments

Amendments to items/item3_short_variance/SPEC.md. Entries A1 through A11 were recorded before
any return, gain or cycle realized variance existed, during the chain-diagnostic and
housekeeping work. Entries A12 through A23 were recorded after the returns were computed and
say so. A1 is recorded as withdrawn, with its text kept in place, so the reasoning that
produced it and then reversed it stays auditable.

## A1. WITHDRAWN. The strip coverage floor stands as pre-registered.

An earlier entry struck stop rule 2 and replaced it with a one-strike computability
requirement. That amendment is withdrawn and rule 2 governs as SPEC.md wrote it, with the
clarifications in A11.

The withdrawn argument ran as follows. Rule 2 rejects 286 of 833 strip cycles, and the
listed-to-extrapolated variance strike ratio had a median of 0.9993 with a 5th percentile of
0.972. Reading the dispersion from that lower tail under a normal assumption gave a standard
deviation of 0.0166, and assuming a mean ratio of exactly 1 gave a second-order bias in the
mean return of 2.8 × 10⁻⁴. A mean-squared-error comparison then said exclusion pays only if the
per-cycle return standard deviation falls below 0.0110.

Both inputs were wrong in the same direction. The ratio distribution is right-skewed, so a
lower-tail estimate understates its dispersion, and its mean exceeds 1, so a first-order term
survives that the argument set to zero. Measurement replaced the approximation and the answer
reversed.

| | Passes rule 2 | Fails rule 2 |
|---|---|---|
| Cycles | 546 | 283 |
| Mean r | 0.9947 | 1.0291 |
| Median r | 0.9978 | 1.0218 |
| SD of r | 0.0192 | 0.0495 |
| 5th to 95th percentile | 0.974 to 1.010 | 0.966 to 1.124 |
| E[1/r] | 1.0058 | 0.9738 |
| Bias in mean cycle return (SE) | −0.0041 (0.0008) | +0.0217 (0.0025) |

The table counts the 829 computable strip cycles that ran to expiration, and A11 counts all
833, which include the 4 truncated cycles.

Admitting the rule-2 failures moves the sample's replication bias from −0.41 percentage
points against the seller to +0.47 in the seller's favour, a swing of 0.88 points, because
those cycles carry +2.17 points among themselves. Mean r falls from 1.098 at one strike per
side to between 0.991 and 0.996 at six or more, so the pre-registered six-strike threshold
sits where the artifact disappears. The withdrawn amendment would have admitted it.

Rule-2-passing cycles carry the strip arm's primary results. The same statistics on every
computable strip cycle are reported as a robustness column with no separate test.

## A2. Stop rule 1 counts the section 3 row filters only

Rule 1's 80 percent threshold counts cycles passing the section 3 row filters, meaning ss_flag,
contract_size, best_bid > 0 and best_offer > best_bid. No other exclusion counts against it,
including rule 2. The spec text reads "passing the section 3 filters" and section 3 holds only
the row filters, so the narrow reading is the literal one. Under it every fund stays in both
arms, with the lowest share at 0.9375 for the UNG strip.

## A3. Hedge fallback

The first fallback, recomputing delta from Black-Scholes using the leg's own impl_volatility,
is removed. Prior-day implied volatility for that leg becomes the first fallback and the
carried hedge the second. A per-cycle count of carried-hedge days is emitted and reported with
no exclusion. Delta and impl_volatility were null together in all 7,437 cases, so the removed
path never executed and its removal changes no computed value.

## A4. K_0 defined at or below F

K_0 is the highest strike at or below F among strikes passing the row filters. The correction
term −(1/T)(F/K_0 − 1)² is the second-order remainder from expanding ln(F/K_0) and vanishes
when F equals K_0, so a strike sitting at F minimizes it. The per-cycle table found the call
and put mids tying exactly in 13 of 844 cycles, where F lands on K* and the strict wording
pushed K_0 one strike lower.

## A5. T and the expiration date measured to the last trading day

T runs from the entry close to the close of the contract's last trading day on an actual/365
basis, and settlement occurs at that close. That day is the third Friday of the expiration
month except where the Friday is an exchange holiday, in which case it is the preceding
Thursday, which occurs in five months of the sample. Section 3 settles against the ETF close
on the expiration date, and no ETF close exists on the Saturday that pre-February-2015
contracts carried as their exdate. K scales as 2/T, so a one-day difference on the sample's
25-day median cycle gives 26/25 = 1.04, matching the 4 percent by which K ran above item
1's value before 2015. Item 3's series carries no break at February 2015 because this
convention applies throughout. K's ratio to item 1's value falls from 1.042 to 1.018 across
February 2015, so the comparison between the two series carries a break there even though item
3's own series does not.

## A6. Marking rule restated exhaustively

A leg with best_bid > 0 and best_offer > 0 marks at their midpoint, which covers normal, locked
and crossed quotes. A leg with best_bid = 0 and best_offer > 0 marks at best_offer / 2.
Anything else carries the last valid mark and counts. The section 3 entry filter continues to
require best_offer > best_bid strictly, and the two rules differ deliberately because entry
requires a two-sided market and marking does not. Locked or crossed quotes appear on 732 of
588,023 strip marks, 0.12 percent, 710 locked and 22 crossed. The carry branch never
fired.

## A7. Section 3 sentence on K corrected

The sentence claiming K and item 1's model-free series are the same object computed on the same
strikes is replaced with the following. K is computed by the same formula as item 1's
model-free measure, applied to the traded expiry, with item 3's own strike selection. Item 1
interpolates two expiries to a constant 30 days, so the two series differ in level; they
correlate at 0.9989 with a median ratio of 1.028.

## A8. Split cycles

Section 11 adds UNG's reverse splits of 2011-03-09, 2012-02-22, 2018-01-05 and 2024-01-24 to
the case studies alongside USO's 2020-04-29 split. The corporate-action record holds six
actions across the four secids, of which these five fall inside cycles; SLV's forward split of
2008-07-24 precedes SLV's first cycle and affects nothing.

Stop rule 5 gains a second clause and a definition. A cycle is truncated when a traded leg's
contract_size leaves 100 or its ss_flag leaves '0' during the cycle life, because the
deliverable the position was entered against no longer exists. Truncation does not require the
contract to become untraceable, since USO's 21 adjusted legs kept their contract ID and
quoted every day after the split while losing the standard flag, the 100-share deliverable and
delta. A truncated cycle is excluded from the mean tests in blocks A, B and C, and its count is
reported. Averaging a partial-period return into a mean of full-cycle returns misstates that
mean.

## A9. Traded maturity disclosed

Section 13 gains a disclosure that cycle days to expiration at entry run 24 to 32 with a
median of 25, so the traded maturity sits below item 1's constant 30-day node and any
comparison between K and item 1's series carries that mismatch. Section 15's sentence
attributing 30 and 91 day measures to both items is corrected to attribute them to item 1 and
to state item 3's monthly cycle with its median maturity.

## A10. Marking sensitivity on the stress table

Maximum drawdown, recovery time and daily Sharpe are reported under three marking conventions
for zero-bid legs, at half the offer as primary, at the full offer, and at zero. Zero-bid marks
cover 28.7 percent of strip marks before expiry, rising to about 96 percent in the far
wings by day 22. Cycle returns are unaffected because the position settles at intrinsic and
intermediate marks cancel, so no test moves. Every path-dependent statistic moves.

## A11. Rule 2 clarified

Rule 2's span is measured in log-moneyness and both its strike count and its span are measured
from K_0. SPEC.md left the distance measure unstated and counted strikes from K_0 while
measuring span from F. Log distance passes 547 cycles and price distance 538.

---

Entries below were recorded after the returns existed.

## A12. Realized and implied variance annualize on different clocks

Section 4 annualizes realized variance by 252/n over trading days while section 3 annualizes K
by 1/T over calendar years on an actual/365 basis. Because a cycle runs Monday to Friday,
calendar-time realized variance averages 6.0 percent above the trading-day figure, with a
median of 4.3 percent. The mixed convention follows standard practice, since model-free
implied variance is built on calendar time and realized variance is conventionally annualized
on trading days.

No tested quantity moves. Section 5 computes the reported return from marks, settlement, hedge
trades, financing and costs over the entry mid premium, so realized variance never enters a
tested number. O1 carries a level offset that cancels in a slope and in an expanding quantile.
The offset varies with each RV21 window's calendar span, which runs 31 to 35 days, so it
cancels only approximately in the slope and adds noise to the regressor that attenuates the
estimate toward zero. Its standard deviation of 0.026 against O1's 0.40 keeps that attenuation
small.

The section 5 replication target is sensitive to it. The per-cycle difference between the
realized return and the 1 − RV/K target measures −0.048 for rule-2-passing cycles and
−0.057 for the rest. Against a target built on Σr²/T with both sides on calendar time it
measures −0.001 and −0.0031. The second figure carries a standard error of 5.1 percentage
points, so the failing population's replication error is not measured with useful precision.
The consistent target governs the diagnostic and both figures are reported.

## A13. The hedge carry operates per leg

Section 3's fallback reads "the prior day's hedge is carried" without saying whether the
position's net hedge or each leg's delta is carried. Each leg's last delta is carried, because
carrying the whole position's hedge froze USO's March and April 2020 hedges for weeks. The
literal position-level reading is computed alongside and reported in returns_position_carry.csv.
At k = 0 and c = 0 strip fund means move by GLD −1.03, SLV +0.91, UNG −1.24, USO +1.12
percentage points, and at the primary cell by GLD −1.01, SLV +0.94, UNG −1.20, USO +1.15.
Straddle means move by 0.02 points or less in both cells. No block A or B verdict changes under either
reading, and that check is emitted to carry_verdict_invariance.csv.

## A14. The O1 slope sits outside section 9's Holm family

Section 9 lists the slope among block C's two tests while section 7 states that the slope's
procedure replaces section 9's and the two are never combined. Section 7 governs, so block C's
mean was tested alone at the five percent level and the slope under its own clustered
procedure. Neither test clears under either reading.

## A15. Bootstrap block length

Section 9 specifies a stationary block bootstrap without a block length. The Newey-West lag
serves as the block length, 4 for estimation-window tests and 3 for the holdout, which is item
1's convention.

## A16. RV21 uses 21 returns

Section 4 contradicts itself, giving both "n = 21" and "the trailing 21 closes". Twenty-one
closes yield 20 returns while n = 21 calls for 21. RV21 uses 21 returns ending at the entry
close. SPEC.md is left as written so the pre-registration record stands.

## A17. Secondary column assignment

Section 5 lists gain in variance points and gain normalized by the ETF close without saying
which arm carries which. Variance points are reported on the strip, where K − RV is the native
payoff, and spot normalization on the straddle, where the Bakshi and Kapadia convention
applies.

## A18. Truncated cycles close at last valid marks

Section 16 rule 5 ends a truncated cycle without saying how it closes. Truncated cycles close
at the last valid marks with no option execution cost, since no trade occurs. They enter the
daily equity curve up to their truncation date and stay out of every test in section 9.

## A19. A cycle can truncate on its entry date

UNG's cycle entered 2012-02-21 truncated after 1 trading day and its cycle entered 2024-01-22
after 2. Both were entered and carry the entry cost, so the first reports a gross return of
0.000 and a primary-cell return of −0.030 from cost alone. Both stay out of the tests.

## A20. Withdrawn-amendment figures corrected

The withdrawn argument in A1 rested on summary statistics plus a second-order moment expansion
that fails at the dispersions involved. Its signs were right and its magnitudes were wrong in
both directions, four overstated and two understated. Its three standard deviations of 0.030, 0.129 and 0.043 all exceed the
measured 0.0192, 0.0495 and 0.0367, and its full-sample bias of +0.56 percentage points
exceeds the measured +0.47. Its two subsample biases of −0.09 and +0.89 points understate the
measured −0.41 and +2.17. A1's table above carries the measured values throughout.

## A21. Hedge cost shapes the strip's result more than option cost

Section 6 sweeps k and c together and leads its reporting with breakeven k. Strip hedge trades
move shares worth 92 times entry premium on average, from 47 on UNG to 136 on GLD, with a
single-cycle maximum of 376, against 52 for the straddle. Raising c from 0 to 10 basis
points lowers the pooled strip mean by 0.107 at k = 0, 2.4 times the 0.044 that raising k
from 0 to 1 costs at c = 0. Section 6's disclosure that c carries no measured anchor in the
held data therefore governs the strip result, and the writeup states it before it states any
mean return.

## A22. The pre-named stress window was profitable

Section 11 named April 2020 as the stress case. USO's cycle entered 2020-04-20, the day WTI
settled below zero, and returned +0.494 gross to its truncation on 2020-04-28, with a
residual of +0.353 that entry Greeks do not capture. The worst single cycle in the sample is
the 2013-03-18 entry, losing 3.09 units pooled at the primary cell as GLD lost 5.29 and SLV
3.44 in the April 2013 gold decline, and it stays the worst strip cycle in all twenty cost
cells. The stress section reports both and states that the pre-named window was not the worst.

## A23. Gate details section 7 left open

Section 7 defines the O1 and O2 gates without fixing four details, and the implementation
resolved each one. O1's history uses every cycle where O1 can be computed, including cycles
the strip did not trade. A cycle with a missing signal trades, so a gate skips only on an
observed state. "First 36 cycles" means the fund's own cycles 1 to 36. The O2 gate skips when
O2 sits above the 90th percentile of the fund's prior values, the inverted term structure
section 7 names as the state to avoid.
