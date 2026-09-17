"""Fixed parameters for item 2: sample, sources, construction, floors, periods and
inference."""

from pathlib import Path

# Paths resolve from this file's location, so the working directory does not matter.
REPO_ROOT = Path(__file__).resolve().parents[3]
ITEM_DIR = REPO_ROOT / "items" / "item2_correlation_premium"
DATA_DIR = ITEM_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SURFACE_DIR = RAW_DIR / "surface"
OUTPUT_DIR = ITEM_DIR / "output"
FIGURES_DIR = ITEM_DIR / "figures"
# Spec section 4: item 1's SPX strike-ladder series, used for validation only.
ITEM1_LADDER_PATH = (
    REPO_ROOT / "items" / "item1_commodity_vrp" / "data" / "model_free_variance.parquet"
)

# Spec section 4. The membership table sits in crsp_q_indexes, the index library of the
# same quarterly CRSP release as crsp_q_stock; crsp_q_stock carries no dsp500list_v2.
MEMBERSHIP_TABLE = "crsp_q_indexes.dsp500list_v2"
LINK_TABLE = "wrdsapps_link_crsp_optionm.opcrsphist"
STOCK_DAILY_TABLE = "crsp_q_stock.dsf_v2"
SPX_SECID = 108105

# Spec section 5.
SAMPLE_START = "1996-01-04"
SAMPLE_END = "2025-08-29"
PERIODS: dict[str, tuple[str, str]] = {
    "1996-2007": ("1996-01-01", "2007-12-31"),
    "2008-2009": ("2008-01-01", "2009-12-31"),
    "2010-2019": ("2010-01-01", "2019-12-31"),
    "2020": ("2020-01-01", "2020-12-31"),
    "2021-2025": ("2021-01-01", "2025-12-31"),
}
AVERAGE_FLOOR = 300
CORRELATION_FLOOR = 450

# Spec section 3, H2: the two calm regimes compared.
H2_BEFORE: tuple[str, str] = ("2010-01-01", "2019-12-31")
H2_AFTER: tuple[str, str] = ("2021-01-01", "2025-08-29")

# Spec sections 6.1 and 6.3: maturities in calendar days, the matching realized-variance
# windows in trading days, and the 34 delta nodes of the surface.
NODES: tuple[int, ...] = (30, 91)
WINDOW_TRADING_DAYS: dict[int, int] = {30: 21, 91: 63}
CALENDAR_DAYS_PER_YEAR = 365.0
CALL_DELTAS: tuple[int, ...] = tuple(range(10, 91, 5))
PUT_DELTAS: tuple[int, ...] = tuple(-delta for delta in CALL_DELTAS)
ATM_DELTA = 50
# Spec section 13, amendment A1: strikes on the dense grid, its reach into each tail in
# standard deviations at the edge volatility, and the out-of-the-money price, as a share
# of the forward, below which it stops.
SURFACE_GRID_POINTS = 1_000
TAIL_STANDARD_DEVIATIONS = 10.0
TAIL_PRICE_FLOOR = 1e-10
# Session checks on the construction: a flat surface must return its volatility squared,
# and a surface whose volatility runs linearly in delta between the two values below at
# the 10-delta put and call must match the same integrand on a reference grid of this
# many strikes, each within the relative tolerance at both maturities.
SYNTHETIC_TOLERANCE = 0.005
SKEW_PUT_VOLATILITY = 0.30
SKEW_CALL_VOLATILITY = 0.15
SKEW_REFERENCE_POINTS = 100_000

# Spec section 6.1 validation and stop rule 9.2.
VALIDATION_MIN_CORRELATION = 0.98
VALIDATION_GAP_THRESHOLD = 0.10

# Spec section 7.
ALPHA = 0.05
BOOTSTRAP_SEED = 20260915
BOOTSTRAP_DRAWS = 2000

# Spec section 9.
LINK_COVERAGE_FLOOR = 0.90
PULL_TIME_LIMIT_MINUTES = 120.0
RESTRICTED_START = "2005-01-03"

# Session budget for the constituent construction: past the first limit the build runs
# across cores, past the second the sample starts at RESTRICTED_START.
CONSTRUCTION_SERIAL_LIMIT_MINUTES = 60.0
CONSTRUCTION_RESTRICT_LIMIT_MINUTES = 120.0
# Worker processes for a parallel construction; each holds one year of the surface, and
# four fit in this machine's 8 GB.
CONSTRUCTION_WORKERS = 4

# Spec section 6.7: the least-squares break keeps each regime to at least this share of
# the annual observations.
BREAK_TRIM = 0.15
