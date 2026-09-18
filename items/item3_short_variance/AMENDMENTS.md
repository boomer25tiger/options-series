# Item 3 amendments

Amendments to items/item3_short_variance/SPEC.md, committed 2026-09-18 before any return,
gain or cycle realized variance was computed. Session 1 (commit e15101c) produced chain
diagnostics only. Every amendment below cites the diagnostic that prompted it.

Destination is items/item3_short_variance/AMENDMENTS.md.

---

## A1. Strip coverage floor struck

**Change.** Stop rule 2 is struck. A strip cycle requires at least one out-of-the-money
strike passing the section 3 row filters on each side of K_0, which is what the ΔK_i / K_i²
construction needs in order to compute. No strike-count or moneyness-span threshold applies.
The rule numbering in section 16 is unchanged and rule 2 reads as struck, so cross-references
elsewhere in the spec stay valid.

**Why.** The struck floor required 6 strikes and a 1.5 σ√T span on each side, and D5 shows it
rejecting 285 of 833 strip cycles with the strike count failing far more often than the span.
The floor stood in for replication quality, and D10 measured that quality directly at a median
listed-to-extrapolated K ratio of 0.9993, a 5th percentile of 0.972, and a ratio above 1 in 46
percent of cycles. The rejected cycles replicate accurately.

**The decision as an inequality.** Write the traded strike as K̂ = K(1 + ε) with E[ε] = 0 and
Var(ε) = σ_ε². Because 1/K̂ is convex, a second-order expansion gives E[1/K̂] ≈ (1/K)(1 + σ_ε²),
so the mean of 1 − RV/K̂ carries a downward bias of (RV/K)·σ_ε². D10's quantiles imply
σ_ε = 0.0166 and σ_ε² = 2.76 × 10⁻⁴, and a 20-million-draw simulation returns a bias of
−2.75 × 10⁻⁴ against the analytic −2.76 × 10⁻⁴ at RV/K = 1.

Comparing mean squared error, keeping every cycle gives (σ_ε²)² + s²/833 and excluding gives
s²/548, with s the per-cycle return standard deviation. Exclusion lowers MSE only when

    s < σ_ε² / sqrt(1/548 − 1/833) = 0.0110

so only if cycle returns have a standard deviation below 1.10 percent of entry premium. D3
measured the entry half-spread alone at 4.6 percent of premium for the strip, and a short
variance return standard deviation runs well above that, so inclusion wins at any plausible s.
Excluding would widen standard errors by 23.3 percent to remove a bias three orders of
magnitude below the effect size.

**What replaces it.** Section 5 already requires the realized return to be checked against the
1 − RV/K target. That difference, written η, is the additive replication error, including the
dollar-gamma variation a coarse strike grid produces. It enters the mean return at first order
through E[η], where the strike error enters at second order through σ_ε², so an E[η] of 10⁻³
is 3.6 times the entire ratio bias and 10⁻² is 36 times it. Session 2 emits η per cycle,
reports its mean and standard error per ETF and arm as the estimate of the replication bias,
and reports it against strike count and against the D10 ratio. The inequality above is
recomputed with the measured s and σ_ε and printed in the results.

**Cross-references updated.** Section 17 null abstract N-E drops strike coverage from its list
of floors. Section 19 checklist item 4 drops the strike coverage floor. Section 8's strike-count
and span diagnostics are retained with no gating role.

## A2. Stop rule 1 counts the section 3 row filters only

**Change.** Rule 1's 80 percent threshold counts cycles passing the section 3 row filters
(ss_flag, contract_size, best_bid > 0, best_offer > best_bid). No other exclusion counts against
it.

**Why.** The spec text already reads "passing the section 3 filters," and D2 showed the sentence
being read two ways, giving 93.8 percent under the narrow reading and 22.2 percent for the UNG
strip under a reading that folded in the now-struck rule 2. An ETF clearing rule 1 with few
usable cycles reports its cycle count, and the Newey-West and bootstrap intervals widen to match.

## A3. Hedge fallback

**Change.** The first fallback, recomputing delta from Black-Scholes using the leg's own
impl_volatility, is removed. Prior-day implied volatility for that leg becomes the first
fallback and the carried hedge the second. Session 2 emits a per-cycle count of carried-hedge
days, reported with no exclusion.

**Why.** D4 found delta and impl_volatility null together in all 7,456 cases, so the removed
path never executed and its removal changes no computed value. D4 also found 2,803 leg-days
falling through to a carried hedge without reporting how they concentrate, and a cycle carrying
its hedge across a large share of its days is not a daily-hedged position.

## A4. K_0 defined at or below F

**Change.** K_0 is the highest strike at or below F among strikes passing the row filters.

**Why.** The correction term −(1/T)(F/K_0 − 1)² is the second-order remainder from expanding
ln(F/K_0), and it vanishes exactly when F equals K_0, so a strike sitting exactly at F is the
choice that minimizes the remainder. D9 found the call and put mids tying exactly in 13 of 844
cycles, where F lands on K* and the strict wording pushed K_0 one strike lower. A forward
strictly between strikes gives an identical answer either way.

## A5. T and the expiration date measured to the last trading day

**Change.** T runs from the entry close to the close of the last trading day of the contract,
the third Friday, on an actual/365 basis. Settlement in section 3 occurs at that close.

**Why.** Section 3 settles legs against the ETF close on the expiration date, and no ETF close
exists on the Saturday that pre-February-2015 contracts carried as their exdate. D9 measured K
running 4 percent above item 1's value before 2015, consistent with K scaling as 2/T and a
one-day difference on a thirty-day cycle giving 30/29. Item 3's own series carries no break at
February 2015 because the Friday convention applies throughout.

## A6. Marking rule restated exhaustively

**Change.** A leg with best_bid > 0 and best_offer > 0 marks at their midpoint, which covers
normal, locked and crossed quotes. A leg with best_bid = 0 and best_offer > 0 marks at
best_offer / 2. Anything else carries the last valid mark and counts. The section 3 entry filter
continues to require best_offer > best_bid strictly, and the two rules differ deliberately
because entry requires a two-sided market while marking does not.

**Why.** D6 found 0.13 percent of strip marks locked or crossed, which draft 3's three branches
left unhandled. D6 also found the carry branch never firing.

## A7. Section 3 sentence on K corrected

**Change.** The sentence claiming K and item 1's model-free series are the same object computed
on the same strikes is replaced with: K is computed by the same formula and the same code path
as item 1's model-free measure, applied to the traded expiry. Item 1 interpolates two expiries
to a constant 30 days, so the two series differ in level; they correlate at 0.9989 with a median
ratio of 1.028.

**Why.** D9 measured both figures. The original sentence was false.

## A8. Split cycles

**Change.** Section 11 adds UNG's reverse splits of 2011-03-09, 2012-02-22, 2018-01-05 and
2024-01-24 to the case studies alongside USO's 2020-04-29 split. Stop rule 5 gains a second
clause: a cycle truncated by a corporate action is excluded from the mean tests in blocks A, B
and C, and its count is reported.

**Why.** D1 lists the five splits and D4 shows two UNG cycles running on carried hedges for 89
and 84 percent of their days. D7 shows all 21 USO strip legs held across the 2020-04-29 split
switching to ss_flag '1' at contract size 12 with delta going null, and none surviving the
filter, so the cycle entered 2020-04-20 terminates nine days into nineteen. Averaging a
nine-day return into a mean of full-cycle returns misstates that mean. The stress section
reports what happened up to truncation and records that the largest stress event in the sample
could not be carried to expiration in this instrument.

## A9. Traded maturity disclosed

**Change.** Section 13 gains a disclosure that cycle days to expiration at entry run 24 to 32
with a median of 25, so the traded maturity sits below item 1's constant 30-day node and the
section 12 comparison between K and item 1's series carries that mismatch. No text in the spec
describes item 3 as a 30-day trade.

**Why.** D2 measured the range and median. Variance carries a term structure, so a 25-day
strike and a 30-day measure are different quantities.

## A10. Marking sensitivity on the stress table

**Change.** Maximum drawdown, recovery time and daily Sharpe in section 11 are reported under
three marking conventions for zero-bid legs, at half the offer as primary, at the full offer,
and at zero.

**Why.** D6 found 28.7 percent of strip marks before expiry sitting at a zero bid, rising to
about 96 percent in the far wings by day 22. Cycle returns are unaffected because the position
settles at intrinsic and intermediate marks cancel, so no test in section 9 moves. Every
path-dependent statistic moves.

## Withdrawn

An amendment adding open_interest and volume to section 2's column list was drafted and
withdrawn. Item 3's cached data is deleted when item 3 finishes under the project's data policy,
and item 6 sits three items later in the queue, so item 6 re-pulls either way. The columns would
have bought nothing and cost the re-pull that D11 says session 2 currently avoids.
