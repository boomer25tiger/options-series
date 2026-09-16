"""Fixed parameters for item 1: sample, instruments, construction and inference."""

from pathlib import Path

DATA_DIR = Path("data/item1")
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = Path("output/item1")

# Spec section 4: security identifiers, fixed and never re-resolved at query time.
SECIDS: dict[str, int] = {
    "SPX": 108105,
    "GLD": 122392,
    "SLV": 126776,
    "USO": 126681,
    "UNG": 129367,
}
COMMODITY_ETFS: tuple[str, ...] = ("GLD", "SLV", "USO", "UNG")
BENCHMARK = "SPX"

# Pull spans cover each ETF's listing year so the annual figure shows full spans.
PULL_SPANS: dict[str, tuple[str, str]] = {
    "SPX": ("2008-01-01", "2025-08-29"),
    "GLD": ("2008-01-01", "2025-08-29"),
    "SLV": ("2008-01-01", "2025-08-29"),
    "USO": ("2007-01-01", "2025-08-29"),
    "UNG": ("2007-01-01", "2025-08-29"),
}

# Spec section 5.
COMMON_START = "2008-12-08"
COMMON_END = "2025-08-29"

# Spec sections 6.1 and 6.3: target maturities in calendar days and the matching
# realized-variance windows in trading days.
NODES: tuple[int, ...] = (30, 91)
WINDOW_TRADING_DAYS: dict[int, int] = {30: 21, 91: 63}
TRADING_DAYS_PER_YEAR = 252.0
CALENDAR_DAYS_PER_YEAR = 365.0

# Spec section 6.1.
MIN_DAYS_TO_EXPIRY = 7
MAX_DAYS_TO_EXPIRY = 200
STRIKE_FLOOR = 3
ROBUSTNESS_STRIKE_FLOOR = 2
VIX_MIN_CORRELATION = 0.98
VIX_MAX_MEDIAN_GAP = 1.0

# Spec section 13: standard-settlement contracts only.
STANDARD_SETTLEMENT_FLAG = "0"
STANDARD_CONTRACT_SIZE = 100.0

# Spec section 13: the at-the-money measure takes the headline for an ETF whose
# model-free drop dates differ from its retained dates by more than this much, or
# at this significance.
SELECTION_MAX_DIFFERENCE = 0.10
SELECTION_MAX_P_VALUE = 0.05

# Spec section 7.
ALPHA = 0.05
BOOTSTRAP_SEED = 20260915
BOOTSTRAP_DRAWS = 2000
NORMAL_95_QUANTILE = 1.96

# Spec section 6.7.
APRIL_2020_START = "2020-03-01"
APRIL_2020_END = "2020-04-30"

# Spec section 5: reporting and power floors on non-overlapping windows per state.
STATE_REPORT_FLOOR = 30
STATE_POWER_FLOOR = 64

# Spec sections 6.5 and 13: Datastream futures classes for the curve state.
FUTURES_CLASSES: dict[str, int] = {"GC": 335, "SI": 3607, "CL": 1482, "NG": 1539}
ETF_COMMODITY: dict[str, str] = {"GLD": "GC", "SLV": "SI", "USO": "CL", "UNG": "NG"}
COMMODITY_LABELS: dict[str, str] = {
    "GC": "COMEX gold (GLD)",
    "SI": "COMEX silver (SLV)",
    "CL": "NYMEX WTI light sweet crude (USO)",
    "NG": "NYMEX Henry Hub natural gas (UNG)",
}
CONTINUATION_COMMODITIES: tuple[str, ...] = ("GC", "SI")
CONTINUATION_SPLICE_DATE = "2022-12-28"
CONTINUATION_TOLERANCE = 0.005
CONTINUATION_MATCH_FLOOR = 0.95
CONTINUATION_TICKERS: tuple[str, ...] = (
    "GC",
    "SI",
    "MGC",
    "SIL",
    "QO",
    "QI",
    "SGU",
    "ZG",
    "ZI",
    "YG",
    "YI",
)
CURVE_COVERAGE_FLOOR = 0.80
# Futures settlements are pulled with a margin around the common window; only
# common-window trade dates enter the curve state.
FUTURES_SETTLEMENT_SPAN: tuple[str, str] = ("2008-06-01", "2025-09-30")
SLOPE_WINSOR_QUANTILES: tuple[float, float] = (0.01, 0.99)
# Spec section 6.5: dates dropped from the slope because the front settlement is
# negative.
NEGATIVE_FRONT_EXCLUSIONS: dict[str, tuple[str, ...]] = {"CL": ("2020-04-20",)}
