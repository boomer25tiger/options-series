# Commodity variance risk premium and the futures curve

Do options on commodity ETFs price variance the way index options do, and does the premium depend on whether the futures curve is in contango or backwardation.

Options on GLD, SLV, USO and UNG from December 2008 to August 2025, with SPX as the equity benchmark. Implied variance is built model-free from the full strike ladder on the CBOE VIX method; on SPX the construction tracks VIX at 0.999 correlation with a median gap of 0.23 vol points. Realized variance is the sum of squared daily log returns over the following 21 or 63 trading days, annualized by 252 over the window length. The curve state for each commodity comes from individual futures settlements, nearest and second-nearest contract by last trading date.

The design was written and committed before any result was computed. Five changes made after the data pull and before any test, covering a data filter, the futures source and two registered diagnostics, are logged in section 13 of the spec. Eighteen tests were registered, eight on the level of the premium and ten on its relation to the curve slope, with Holm correction inside each block. A result counts as supported only when Newey-West and a stationary block bootstrap both clear the corrected level.

![Annual mean log variance ratio, 30-day maturity](items/item1_commodity_vrp/figures/post_fig1.png)

## Results

Across the four commodity ETFs, 30-day implied variance ran 23 percent above the variance that followed, on average. The mean log ratio of implied to realized variance is 0.20 with a 95 percent interval of 0.16 to 0.24 on 4,165 trading days, using the at-the-money measure that covers every date. On the dates where all four chains support the model-free construction the gap is 43 percent. Every commodity carries the premium on its own at both maturities. SPX over the same window runs at 77 percent model-free against 43 percent for the commodities, so the commodity premium is a little over half the index premium in percentage terms and about 0.6 of it in log units.

The premium does not depend on the curve. None of the ten slope tests cleared the pre-set bar. The largest effect of a one-standard-deviation move in the curve slope is 0.08 log units. One cell, silver at 30 days, has intervals that exclude zero under both methods and still fails the Holm-corrected level on the bootstrap, which is the case the two-method rule exists to catch. The common factor across the four premia explains about 47 percent of their variance and moves by less than a point after conditioning on slope.

| node | ETF | series | n | mean log ratio | p Newey-West | p bootstrap | verdict |
|---|---|---|---|---|---|---|---|
| 30 | GLD | ATM | 4,170 | 0.1893 | 9.01e-11 | <0.0005 | supported |
| 30 | SLV | model-free | 3,143 | 0.3928 | 6.95e-30 | <0.0005 | supported |
| 30 | USO | ATM | 4,169 | 0.2225 | 3.29e-12 | <0.0005 | supported |
| 30 | UNG | ATM | 4,166 | 0.2097 | 6.76e-17 | <0.0005 | supported |
| 91 | GLD | ATM | 4,128 | 0.1946 | 0.0002 | 0.0005 | supported |
| 91 | SLV | model-free | 3,694 | 0.3509 | 7.31e-13 | <0.0005 | supported |
| 91 | USO | ATM | 4,127 | 0.1582 | 0.0043 | 0.0095 | supported |
| 91 | UNG | ATM | 4,124 | 0.1509 | 0.0004 | 0.0020 | supported |

| node | ETF | slope per 1 sd of z | Newey-West 95 percent interval | p Newey-West | p bootstrap | verdict |
|---|---|---|---|---|---|---|
| 30 | GLD | -0.0256 | [-0.0706, +0.0194] | 0.2651 | 0.2750 | not supported |
| 30 | SLV | -0.0739 | [-0.1241, -0.0237] | 0.0039 | 0.0120 | not robust to inference method |
| 30 | USO | -0.0055 | [-0.0528, +0.0419] | 0.8212 | 0.8370 | not supported |
| 30 | UNG | +0.0373 | [-0.0070, +0.0815] | 0.0989 | 0.0890 | not supported |
| 30 | POOLED | +0.0158 | [-0.0001, +0.0317] | 0.0509 | 0.1900 | not supported |
| 91 | GLD | -0.0576 | [-0.1281, +0.0128] | 0.1090 | 0.1160 | not supported |
| 91 | SLV | -0.0780 | [-0.1427, -0.0134] | 0.0180 | 0.0610 | not supported |
| 91 | USO | +0.0573 | [-0.0066, +0.1212] | 0.0790 | 0.0430 | not supported |
| 91 | UNG | +0.0335 | [-0.0198, +0.0867] | 0.2178 | 0.2260 | not supported |
| 91 | POOLED | +0.0248 | [+0.0021, +0.0475] | 0.0319 | 0.1040 | not supported |

| node | series | share before | share after | change |
|---|---|---|---|---|
| 30 | model-free | 0.4680 | 0.4691 | +0.0011 |
| 30 | ATM | 0.4783 | 0.4761 | -0.0022 |
| 91 | model-free | 0.5241 | 0.5186 | -0.0055 |
| 91 | ATM | 0.5635 | 0.5556 | -0.0079 |

Three of the four ETFs report the at-the-money measure as headline because a registered check found their model-free drop dates differ from retained dates in premium level; the model-free numbers are larger in every case. Full construction rules, the test family and every judgment call are in items/item1_commodity_vrp/SPEC.md.

## What is not claimed

No strategy return. There is no cost model, no hedging and no trade in this study. The premium is a measurement of how options are priced against what the underlying then does.

## Reproduce

Requires a WRDS account with OptionMetrics, Datastream futures and CBOE index access, and a ~/.pgpass entry.

    pip install -r requirements.txt
    python -m options_series.item1.run

The run pulls quotes for five underlyings and thirteen futures classes (four primary, nine screened for the gold and silver continuation), builds both implied variance measures, runs the tests and writes every figure and table under items/item1_commodity_vrp/output/.

## References

Carr, P. and Wu, L. (2009). Variance risk premiums. Review of Financial Studies 22(3), 1311–1341.
Jiang, G. and Tian, Y. (2005). The model-free implied volatility and its information content. Review of Financial Studies 18(4), 1305–1342.
Prokopczuk, M., Symeonidis, L. and Wese Simen, C. (2017). Variance risk in commodity markets. Journal of Banking and Finance 81, 136–149.
Ng, V. and Pirrong, S. (1994). Fundamentals and volatility: storage, spreads, and the dynamics of metals prices. Journal of Business 67(2), 203–230.
Politis, D. and Romano, J. (1994). The stationary bootstrap. Journal of the American Statistical Association 89(428), 1303–1313.
