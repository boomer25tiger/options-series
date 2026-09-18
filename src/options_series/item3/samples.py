"""Samples of section 16 as amended: the exclusions each arm-cycle meets, the cycles
entering each block of section 9, and the pooled series of section 5.

Choices the spec and its amendments leave open, fixed before any return was computed.
- Exclusions are tallied in the order section 3 filters, rule 2 or rule 3, rule 4,
  rule 5 with its A8 clause, so each excluded cycle counts once under the first rule it
  fails.
- The strip's primary sample holds rule-2-passing cycles (A1 as withdrawn). Its
  robustness sample holds every computable strip cycle with the other exclusions applied.
- A pooled row averages the returns of the funds entering on a cycle date. The pooled
  series starts at the first date with at least two funds and keeps later dates with one
  or more.
- The pooled equity path adds each cycle's pooled return to the running total and marks
  the cycle in progress daily. A truncated cycle enters this path up to its last valid
  mark and stays flat after it, although A8 keeps it out of the mean tests.
"""

from __future__ import annotations

import pandas as pd

from options_series.item3.config import FILTER_SHARE_FLOOR
from options_series.item3.construction import OK

ARMS: tuple[str, ...] = ("strip", "straddle")
RULES: tuple[str, ...] = (
    "section 3 filters",
    "rule 2 floor",
    "rule 3 straddle distance",
    "rule 4 missing return",
    "rule 5 truncated",
)


def exclusions(entries: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """One row per fund, cycle and arm with the first rule the cycle fails, empty when
    it enters its block, and whether it enters the strip's robustness sample."""
    rows = []
    returned = returns.set_index(["ticker", "cycle", "arm"])
    for entry in entries.itertuples():
        for arm in ARMS:
            status = entry.strip_status if arm == "strip" else entry.straddle_status
            key = (entry.ticker, entry.cycle, arm)
            truncated = (
                bool(returned.loc[key, "truncated"]) if key in returned.index else False
            )
            if arm == "straddle" and status == "FAR_FROM_FORWARD":
                first = "rule 3 straddle distance"
            elif status != OK:
                first = "section 3 filters"
            elif arm == "strip" and entry.floor_pass is not True:
                first = "rule 2 floor"
            elif entry.missing_returns > 0:
                first = "rule 4 missing return"
            elif truncated:
                first = "rule 5 truncated"
            else:
                first = ""
            robust = (
                arm == "strip"
                and status == OK
                and entry.missing_returns == 0
                and not truncated
            )
            rows.append(
                {
                    "ticker": entry.ticker,
                    "cycle": entry.cycle,
                    "arm": arm,
                    "entry": entry.entry,
                    "window": entry.window,
                    "block": ""
                    if first
                    else ("A and B" if entry.window == "estimation" else "C"),
                    "excluded_by": first,
                    "primary": first == "",
                    "robustness": robust,
                    "truncated": truncated,
                }
            )
    return pd.DataFrame(rows)


def exclusion_table(sample: pd.DataFrame) -> pd.DataFrame:
    """Per fund, arm and window, the cycles, the count excluded by each rule, and the
    cycles entering the block."""
    rows = []
    for (ticker, arm, window), group in sample.groupby(["ticker", "arm", "window"]):
        row = {"ticker": ticker, "arm": arm, "window": window, "cycles": len(group)}
        for rule in RULES:
            row[rule] = int((group.excluded_by == rule).sum())
        row["entering"] = int(group.primary.sum())
        row["robustness_sample"] = int(group.robustness.sum())
        rows.append(row)
    return pd.DataFrame(rows)


def rule_one(sample: pd.DataFrame) -> pd.DataFrame:
    """Rule 1 under A2: each fund's share of estimation cycles passing the section 3
    filters per arm, against the 80 percent floor."""
    estimation = sample[sample.window == "estimation"]
    rows = []
    for (ticker, arm), group in estimation.groupby(["ticker", "arm"]):
        passing = group.excluded_by != "section 3 filters"
        share = passing.mean()
        rows.append(
            {
                "ticker": ticker,
                "arm": arm,
                "estimation_cycles": len(group),
                "passing_section3": int(passing.sum()),
                "share": share,
                "stays_in_family": bool(share >= FILTER_SHARE_FLOOR),
            }
        )
    return pd.DataFrame(rows)


def pooled_returns(panel: pd.DataFrame, column: str) -> pd.DataFrame:
    """Pooled rows of section 5 from one row per fund-cycle carrying the entry date and
    a return column: the equal-weighted mean per date and the fund count, starting at
    the first date with at least two funds."""
    pooled = (
        panel.dropna(subset=[column])
        .groupby("entry")[column]
        .agg(["mean", "count"])
        .rename(columns={"mean": column, "count": "funds"})
        .reset_index()
        .sort_values("entry")
    )
    first = pooled.loc[pooled.funds >= 2, "entry"].min()
    return pooled[pooled.entry >= first].reset_index(drop=True)


def pooled_equity(equity: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """Daily pooled marked equity per unit of entry premium. equity holds daily paths of
    one arm at one marking and cost cell; members lists the fund-cycles entering it with
    their entry date."""
    paths = equity.merge(members[["ticker", "cycle", "entry"]], on=["ticker", "cycle"])
    daily = (
        paths.groupby(["entry", "date"])
        .agg(path=("equity", "mean"), funds=("ticker", "nunique"))
        .reset_index()
    )
    counts = members.groupby("entry").ticker.nunique()
    daily = daily[daily.entry >= counts[counts >= 2].index.min()]
    final = daily.sort_values("date").groupby("entry").path.last()
    offset = final.cumsum().shift(fill_value=0.0)
    daily["equity"] = daily.path + daily.entry.map(offset)
    return daily[["date", "entry", "funds", "path", "equity"]].sort_values("date")
