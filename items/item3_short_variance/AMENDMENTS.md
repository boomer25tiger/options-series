# Item 3 amendments

Amendments to items/item3_short_variance/SPEC.md.

Revision 1 was committed 2026-09-18 as 15b9c10. Revision 2 superseded it as b5b1a1a, withdrawing
A1 before any return was computed. Revision 3 adds A12 through A22, which record deviations and
ambiguities session 2 resolved while computing returns, together with the figures that replace
revision 2's approximations. Sessions 1 and 1b computed no returns; session 2 (commits 4e39206
and 46f41fe) computed all of them, so every entry below is dated after the results existed and is
recorded as such.

Destination is items/item3_short_variance/AMENDMENTS.md.

---

## A1 through A11

Unchanged from revision 2, with the corrections in A20 below applied to A1's figures.

## A12. Realized and implied variance annualize on different clocks

Section 4 annualizes realized variance by 252/n over trading days while section 3 annualizes K
by 1/T over calendar years on an actual/365 basis. The two clocks disagree by roughly one and a
half percent on a monthly horizon. The mixed convention follows standard practice, since
model-free implied variance is built on calendar time and realized variance is conventionally
annualized on trading days.

No tested quantity moves. Section 5 computes the reported return from marks, settlement, hedge
trades, financing and costs over the entry mid premium, so realized variance never enters a
tested number. O1 carries a level offset that cancels in a slope and in an expanding quantile.

The section 12 replication diagnostic is sensitive to it. Session 2 measured the per-cycle
difference between the realized return and the 1 − RV/K target at −0.048 for rule-2-passing
cycles and −0.057 for the rest, and at −0.001 and −0.003 against a target built on Σr²/T with
both sides on calendar time. The consistent target governs the diagnostic and both figures are
reported. Against it, the strip replicates variance to within a fifth of a percentage point in
both populations, with a Welch p of 0.96 between them.

## A13. The hedge carry operates per leg

Section 3's fallback reads "the prior day's hedge is carried," which does not say whether the
position's net hedge or each leg's delta is carried. Session 2 carried each leg's last delta,
because carrying the whole position's hedge froze USO's March and April 2020 hedges for weeks.
The literal position-level reading is computed alongside and reported in the `*_position_carry`
columns, and the difference between the two is reported per ETF and arm.

## A14. The O1 slope sits outside section 9's Holm family

Section 9 lists the slope among block C's two tests while section 7 states that the slope's
procedure replaces section 9's and the two are never combined. Session 2 followed section 7,
testing block C's mean alone at the five percent level and the slope under its own clustered
procedure. Neither test clears under either reading, so no verdict depends on the resolution.

## A15. Bootstrap block length

Section 9 specifies a stationary block bootstrap without a block length. Session 2 used the
Newey-West lag, 4 for estimation-window tests and 3 for the holdout, which is item 1's
convention.

## A16. RV21 uses 21 returns

Section 7's "trailing 21 daily returns" and section 4's "trailing 21 closes" imply 20 and 21
returns respectively. Session 2 used 21 returns ending at the entry close.

## A17. Secondary column assignment

Section 5 lists gain in variance points and gain normalized by the ETF close without saying
which arm carries which. Session 2 reported variance points on the strip, where K − RV is the
native payoff, and spot normalization on the straddle, where the Bakshi and Kapadia convention
applies.

## A18. Truncated cycles close at last valid marks

Section 16 rule 5 ends a truncated cycle without saying how it closes. Session 2 closed at the
last valid marks with no option execution cost, since no trade occurs. Truncated cycles enter
the daily equity curve up to their truncation date and stay out of every test in section 9.

## A19. A cycle can truncate on its entry date

UNG's cycle entered 2024-01-22 and UNG's cycle entered 2012-02-21 truncated within one and two
trading days, the latter on its entry date. Session 2 entered them and carried the entry cost,
so the cycle entered 2012-02-21 reports a gross return of zero and a primary-cell return of
−0.030 from cost alone. Both stay out of the tests.

## A20. Revision 2's A1 figures corrected

Revision 2's table rested on summary statistics plus a second-order moment expansion, and it
warned that the expansion fails at the dispersions involved. Session 2's empirical figures
replace it. Every sign in revision 2 was right and every magnitude was understated.

| | Passes rule 2 | Fails rule 2 |
|---|---|---|
| Cycles | 546 | 283 |
| Mean r (median) | 0.9947 (0.9978) | 1.0291 (1.0218) |
| SD of r | 0.0192 | 0.0495 |
| 5th to 95th percentile | 0.974 to 1.010 | 0.966 to 1.125 |
| E[1/r] | 1.0058 | 0.9738 |
| Bias in mean cycle return (SE) | −0.0041 (0.0008) | +0.0217 (0.0025) |

Admitting rule-2 failures biases returns 2.17 percentage points per cycle in the seller's
favour. The passing sample carries 0.41 points against the seller, so the primary strip estimates
understate the premium slightly. Mean r falls from 1.098 at one strike per side to between 0.991
and 0.996 at six or more, so the pre-registered six-strike threshold sits where the artifact
disappears. Revision 1's proposal to strike rule 2 would have admitted the artifact, and its
withdrawal stands on these measurements.

## A21. Hedge cost dominates the strip's cost surface

Section 6 sweeps k and c together and section 6 leads its reporting with breakeven k. Session 2
measured strip hedge turnover at 180 to 240 times entry premium, so the pooled breakeven k falls
from 3.72 at c = 0 to 1.31 at c = 10 basis points while moving little across k. Section 6's
disclosure that c carries no measured anchor in the held data therefore governs the strip result,
and the writeup states it before it states any mean return.

## A22. The pre-named stress window was profitable

Section 11 named April 2020 as the stress case. USO's cycle entered 2020-04-20, the day WTI
settled negative, and returned +0.494 gross to its truncation on 2020-04-28, with a residual of
+0.353 that entry Greeks do not capture. The worst single cycle in the sample is the 2013-03-18
entry at −3.02 to −3.28 across cost cells, driven by GLD at −5.29 and SLV at −3.44 in the April
2013 gold decline. The stress section reports both and states that the pre-named window was not
the worst.
