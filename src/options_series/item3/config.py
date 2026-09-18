"""Fixed parameters for item 3, covering instruments, the cycle calendar, row filters,
floors and the session 1 diagnostics."""

from pathlib import Path

# Paths resolve from this file's location, so the working directory does not matter.
REPO_ROOT = Path(__file__).resolve().parents[3]
ITEM_DIR = REPO_ROOT / "items" / "item3_short_variance"
DATA_DIR = ITEM_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CYCLE_QUOTES_DIR = RAW_DIR / "cycle_quotes"
OUTPUT_DIR = ITEM_DIR / "output"
FIGURES_DIR = ITEM_DIR / "figures"

# Item 3 reads four item 1 files and never writes them, namely the zero curve, the 30- and
# 91-day at-the-money surface nodes, the strike-ladder quote cache and the model-free
# series.
ITEM1_DIR = REPO_ROOT / "items" / "item1_commodity_vrp"
ITEM1_RAW_DIR = ITEM1_DIR / "data" / "raw"
ITEM1_OPTION_QUOTES_DIR = ITEM1_RAW_DIR / "option_quotes"
ITEM1_ZERO_CURVE_PATH = ITEM1_RAW_DIR / "zero_curve.parquet"
ITEM1_ATM_SURFACE_PATH = ITEM1_RAW_DIR / "atm_surface.parquet"
ITEM1_MODEL_FREE_PATH = ITEM1_DIR / "data" / "model_free_variance.parquet"

# Spec section 2 fixes the security identifiers, and no query re-resolves them.
SECIDS: dict[str, int] = {
    "GLD": 122392,
    "SLV": 126776,
    "USO": 126681,
    "UNG": 129367,
}
ETFS: tuple[str, ...] = tuple(SECIDS)
FEED_END = "2025-08-29"
# The secprd pull reaches back to the earliest fund launch, GLD in November 2004, for the
# corporate-action record. Each fund's first option date comes from a scan of the opprcd
# years below.
SECPRD_YEARS = range(2004, 2026)
OPTION_START_SCAN_YEARS = range(2004, 2010)
OPTION_YEARS = range(2007, 2026)

# Spec section 3.
STANDARD_SETTLEMENT_FLAG = "0"
STANDARD_CONTRACT_SIZE = 100.0
STRADDLE_MAX_DISTANCE = 0.05
CALENDAR_DAYS_PER_YEAR = 365.0

# Spec section 6.
EXECUTION_FRACTIONS: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
PRIMARY_EXECUTION_FRACTION = 0.5

# Spec section 8 sets the extrapolated strike grid and the integer-rounding tolerance.
# Sizes run in entry premium dollars on a geometric grid of ROUNDING_GRID_POINTS points.
SHORTFALL_GRID_POINTS = 1_000
ROUNDING_TOLERANCE = 0.01
ROUNDING_SIZE_RANGE: tuple[float, float] = (1e2, 1e9)
ROUNDING_GRID_POINTS = 1_401

# Spec section 10.
ESTIMATION_END = "2021-12-31"
HOLDOUT_START = "2022-01-01"
EXPECTED_ESTIMATION_CYCLES: dict[str, int] = {
    "GLD": 163,
    "SLV": 157,
    "USO": 176,
    "UNG": 176,
}
EXPECTED_POOLED_ESTIMATION_CYCLES = 176
EXPECTED_HOLDOUT_CYCLES = 43
EXPECTED_FIRST_ENTRY: dict[str, str] = {
    "GLD": "2008-06-23",
    "SLV": "2008-12-22",
    "USO": "2007-05-21",
    "UNG": "2007-05-21",
}
EXPECTED_LAST_ESTIMATION_ENTRY = "2021-12-20"
EXPECTED_FIRST_HOLDOUT_ENTRY = "2022-01-24"
EXPECTED_LAST_HOLDOUT_ENTRY = "2025-07-21"
EXPECTED_LAST_HOLDOUT_EXPIRATION = "2025-08-15"

# Spec section 16, rules 1 and 2.
FILTER_SHARE_FLOOR = 0.80
STRIP_MIN_STRIKES = 6
STRIP_MIN_SPAN = 1.5

# Diagnostic 6 buckets leg moneyness at entry, in units of sigma_ATM sqrt(T), at these
# edges.
MONEYNESS_EDGES: tuple[float, ...] = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)

# Diagnostic 7.
CONTINUITY_ETFS: tuple[str, ...] = ("USO", "UNG")
CONTINUITY_START = "2020-03-01"
CONTINUITY_END = "2020-06-30"

# Every distribution reports these percentiles.
PERCENTILES: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
