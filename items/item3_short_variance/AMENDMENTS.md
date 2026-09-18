# Item 3 amendments

Amendments to items/item3_short_variance/SPEC.md. No return, gain or cycle realized variance
had been computed at any point in this record. Session 1 (commit e15101c) and session 1b
(commits 15b9c10, e0c94cc, 6e40214, fef5125) produced chain diagnostics and housekeeping only.

Revision 1 was committed 2026-09-18 as 15b9c10. Revision 2 supersedes it, withdraws A1, and
corrects seven others against figures session 1b reported. Both revisions predate any
performance statistic, and A1 is recorded as withdrawn rather than removed so the reasoning
stays auditable.

Destination is items/item3_short_variance/AMENDMENTS.md.

---

## A1. WITHDRAWN. The strip coverage floor stands as pre-registered.

Revision 1 struck stop rule 2 and replaced it with a one-strike computability requirement. That
amendment is withdrawn and rule 2 governs as SPEC.md originally wrote it, with two
clarifications recorded as A11 below.

**What revision 1 argued.** D5 showed rule 2 rejecting 285 of 833 strip cycles, and D10 gave a
listed-to-extrapolated variance strike ratio with a median of 0.9993 and a 5th percentile of
0.972. Reading the ratio's dispersion from that lower tail under a normal assumption gave
σ_ε = 0.0166, and assuming a mean ratio of exactly 1 gave a second-order bias in the mean return
of (RV/K)·σ_ε² = 2.8 × 10⁻⁴. A mean-squared-error comparison then said exclusion pays only if the
per-cycle return standard deviation falls below 0.0110, which no short variance position
satisfies, so the floor appeared to cost 23 percent wider standard errors for nothing.

**Why it fails.** Both inputs were wrong in the same direction. The ratio distribution is
right-skewed, so a lower-tail estimate understates its dispersion; the sample standard deviation
is 0.043. Its mean is 1.0075, so the error is not centered and a first-order term survives that
revision 1 set to zero. Recomputing E[1/r] ≈ (1/μ)(1 + s²/μ²):

| Population | mean ratio | SD | bias in mean return |
|---|---|---|---|
| Revision 1's figure | 1.0000 assumed | 0.0166 | −0.03 pp |
| Full sample | 1.0075 | 0.0430 | +0.56 pp |
| Retained by rule 2 | about 1.000 | about 0.030 | −0.09 pp |
| Rejected by rule 2 | about 1.025 | about 0.129 | +0.89 pp |

Rule 2 separates two populations whose replication bias differs by about one percentage point.
The rejected cycles carry a median ratio of 1.022 against 0.998 for the retained, with roughly
three times the dispersion, so revision 1's claim that they replicate accurately is false.

The MSE criterion no longer decides the question either. With the corrected bias, exclusion
lowers MSE whenever the per-cycle return standard deviation falls below 0.226, or below 0.358
using the rejected-cycle bias, and short variance returns plausibly fall on either side. What
decides it is direction: the artifact runs about 0.9 percentage points in the seller's favour,
three to four percent of a 20 to 30 point premium. A bias that inflates the headline is not a
quantity to trade against sampling variance.

**What session 2 must compute rather than inherit.** Every figure above rests on session 1b's
summary statistics plus a second-order moment expansion, and that expansion is unreliable at a
dispersion of 0.129 where the ratio reaches values near 0.7 and 1/r moves sharply. Session 1b
reported the full-sample bias as −0.006 and the rejected-cycle bias as −0.028, opposite in sign
to the figures above and, for the rejected population, three times the magnitude. The sign
determines whether a coarse strike grid flatters or penalizes the seller, so session 2 computes
E[1/r] directly on each population from the empirical distribution, reports it with the mean,
median, standard deviation and the 5th and 95th percentiles of r, and drops the expansion. The
table above is superseded by that output.

**Reporting.** Rule-2-passing cycles carry the strip arm's primary results. The same statistics
on every computable strip cycle appear as a robustness column with no separate test, beside the
replication diagnostics for both populations.

## A2. Stop rule 1 counts the section 3 row filters only

Rule 1's 80 percent threshold counts cycles passing the section 3 row filters (ss_flag,
contract_size, best_bid > 0, best_offer > best_bid). No other exclusion counts against it,
including rule 2.

D2 showed the sentence being read two ways, giving 93.8 percent under the narrow reading and
22.2 percent for the UNG strip under a reading that folded in rule 2. The spec text says
"passing the section 3 filters" and section 3 holds only the row filters, so the narrow reading
is the literal one. Under it all four ETFs stay in both arms with the cycle counts rule 2 leaves,
and their intervals widen to match.

## A3. Hedge fallback

The first fallback, recomputing delta from Black-Scholes using the leg's own impl_volatility, is
removed. Prior-day implied volatility for that leg becomes the first fallback and the carried
hedge the second. Session 2 emits a per-cycle count of carried-hedge days, reported with no
exclusion.

D4 found delta and impl_volatility null together in all 7,456 cases, so the removed path never
executed and its removal changes no computed value. D4 also found 2,803 leg-days falling through
to a carried hedge without reporting how they concentrate.

## A4. K_0 defined at or below F

K_0 is the highest strike at or below F among strikes passing the row filters.

The correction term −(1/T)(F/K_0 − 1)² is the second-order remainder from expanding ln(F/K_0)
and vanishes exactly when F equals K_0, so a strike sitting at F minimizes it. Session 1's
per-cycle table found the call and put mids tying exactly in 13 of 844 cycles, where F lands on
K* and the strict wording pushed K_0 one strike lower. A forward strictly between strikes gives
an identical answer either way.

## A5. T and the expiration date measured to the last trading day

T runs from the entry close to the close of the contract's last trading day, on an actual/365
basis. That day is the third Friday of the expiration month except where the Friday is an
exchange holiday, in which case it is the preceding Thursday, which session 1b found in five
months of the sample. Settlement in section 3 occurs at that close.

Section 3 settles legs against the ETF close on the expiration date, and no ETF close exists on
the Saturday that pre-February-2015 contracts carried as their exdate. D9 measured K running 4
percent above item 1's value before 2015, consistent with K scaling as 2/T and a one-day
difference on the sample's 25-day median cycle giving 26/25 = 1.04. Item 3's own series carries
no break at February 2015 because this convention applies throughout.

## A6. Marking rule restated exhaustively

A leg with best_bid > 0 and best_offer > 0 marks at their midpoint, which covers normal, locked
and crossed quotes. A leg with best_bid = 0 and best_offer > 0 marks at best_offer / 2. Anything
else carries the last valid mark and counts. The section 3 entry filter continues to require
best_offer > best_bid strictly, and the two rules differ deliberately because entry requires a
two-sided market and marking does not.

D6 found 732 of 588,023 strip marks, 0.12 percent, carrying locked or crossed quotes, 710 locked
and 22 crossed, which SPEC.md's three branches left unhandled. D6 also found the carry branch
never firing.

## A7. Section 3 sentence on K corrected

The sentence claiming K and item 1's model-free series are the same object computed on the same
strikes is replaced with: K is computed by the same formula as item 1's model-free measure,
applied to the traded expiry, with item 3's own strike selection. Item 1 interpolates two
expiries to a constant 30 days, so the two series differ in level; they correlate at 0.9989 with
a median ratio of 1.028.

D9 measured both figures. The original sentence was false on the object and on the code path.

## A8. Split cycles

Section 11 adds UNG's reverse splits of 2011-03-09, 2012-02-22, 2018-01-05 and 2024-01-24 to the
case studies alongside USO's 2020-04-29 split. D1 lists six corporate actions across the four
secids, of which these five fall inside cycles; SLV's 10-for-1 forward split of 2008-07-24
precedes SLV's first cycle and affects nothing.

Stop rule 5 gains a second clause and a definition. A cycle is truncated when a traded leg's
contract_size leaves 100 or its ss_flag leaves '0' during the cycle life, because the deliverable
the position was entered against no longer exists. Truncation does not require the contract to
become untraceable; D7 shows USO's 21 adjusted legs keeping their contract ID and quoting every
day after the split while losing the standard flag, the 100-share deliverable and delta. A
truncated cycle is excluded from the mean tests in blocks A, B and C, and its count is reported.

Averaging a partial-period return into a mean of full-cycle returns misstates that mean. USO's
legs stayed standard for 7 of the cycle's 20 trading days, so the cycle entered 2020-04-20 ends
on 2020-04-28. The stress section reports what happened to that point and records that the
largest stress event in the sample could not be carried to expiration in this instrument. D4
found two UNG split cycles running on carried hedges for 89 and 84 percent of their days.

## A9. Traded maturity disclosed

Section 13 gains a disclosure that cycle days to expiration at entry run 24 to 32 with a median
of 25, so the traded maturity sits below item 1's constant 30-day node and the section 12
comparison between K and item 1's series carries that mismatch. Section 15's sentence reading
"Item 1 and item 3 use ETF options from OptionMetrics over 2007 to 2025 at 30 and 91 days" is
corrected to attribute the 30 and 91 day measures to item 1 and to state item 3's monthly cycle
with its median maturity. No other text describes item 3 as a 30-day trade.

D2 measured the range and median. Variance carries a term structure, so a 25-day strike and a
30-day measure are different quantities.

## A10. Marking sensitivity on the stress table

Maximum drawdown, recovery time and daily Sharpe in section 11 are reported under three marking
conventions for zero-bid legs, at half the offer as primary, at the full offer, and at zero.

D6 found 28.7 percent of strip marks before expiry sitting at a zero bid, rising to about 96
percent in the far wings by day 22. Cycle returns are unaffected because the position settles at
intrinsic and intermediate marks cancel, so no test in section 9 moves. Every path-dependent
statistic moves.

## A11. Rule 2 clarified

Rule 2's span is measured in log-moneyness and both its strike count and its span are measured
from K_0. SPEC.md left the distance measure unstated and counted strikes from K_0 while
measuring span from F. Session 1b found 548 cycles passing under log distance and 541 under
price distance.

## Reverts to revision 1's SPEC edits

Revision 1 marked section 16 rule 2 as struck and removed strike coverage from section 17's
null abstract N-E. Both edits are reverted, so rule 2 reads as originally written with A11's
clarifications and N-E lists strike coverage among its floors. Revision 1 also named a section 19
checklist edit with no target in SPEC.md, and that instruction is dropped.

## Withdrawn without effect

An amendment adding open_interest and volume to section 2's column list was drafted and
withdrawn in revision 1. Item 3's cached data is deleted when item 3 finishes under the
project's data policy, and item 6 sits three items later in the queue, so item 6 re-pulls either
way.
