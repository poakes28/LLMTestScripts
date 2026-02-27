"""
Shared utilities: config loading, logging, Parquet I/O, path management.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Union

import yaml
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


# ---------------------------------------------------------------------------
# Path Resolution
# ---------------------------------------------------------------------------
def get_project_root() -> Path:
    """Return the project root directory."""
    # Try relative to this file first (src/utils.py -> project root)
    file_based = Path(__file__).resolve().parent.parent
    if (file_based / "config" / "settings.yaml").exists():
        return file_based
    # Fallback: walk up from cwd
    cwd = Path.cwd()
    for p in [cwd] + list(cwd.parents):
        if (p / "config" / "settings.yaml").exists():
            return p
    return file_based


def get_config_dir() -> Path:
    return get_project_root() / "config"


def get_data_dir() -> Path:
    return get_project_root() / "data"


def get_log_dir() -> Path:
    return get_project_root() / "logs"


# ---------------------------------------------------------------------------
# Config Loading
# ---------------------------------------------------------------------------
_config_cache: Dict[str, Any] = {}


def load_config(name: str = "settings") -> Dict[str, Any]:
    """Load a YAML config file, cached after first load."""
    if name in _config_cache:
        return _config_cache[name]
    path = get_config_dir() / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    _config_cache[name] = cfg
    return cfg


def load_credentials() -> Dict[str, Any]:
    """Load credentials config."""
    return load_config("credentials")


def get_fund_config(fund_name: str) -> Dict[str, Any]:
    """Get configuration for a specific fund."""
    cfg = load_config()
    funds = cfg.get("funds", {})
    if fund_name not in funds:
        raise ValueError(f"Unknown fund: {fund_name}. Available: {list(funds.keys())}")
    return funds[fund_name]


def get_all_tickers() -> List[str]:
    """Get combined watchlist of all tickers."""
    cfg = load_config()
    wl = cfg.get("watchlist", {})
    tickers = set()
    for group in wl.values():
        if isinstance(group, list):
            tickers.update(group)
    return sorted(tickers)


def get_sector(ticker: str) -> str:
    """Get sector for a ticker from config."""
    cfg = load_config()
    return cfg.get("sector_map", {}).get(ticker, "Unknown")


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
_log_initialized = False


def setup_logging(module_name: str = "system", level: str = "INFO"):
    """Configure loguru for the given module."""
    global _log_initialized
    if _log_initialized:
        return

    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console handler
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> - {message}",
    )

    # File handler (rotated daily)
    logger.add(
        log_dir / f"{module_name}_{{time:YYYY-MM-DD}}.log",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
    )

    _log_initialized = True
    logger.info(f"Logging initialized for module: {module_name}")


# ---------------------------------------------------------------------------
# Parquet I/O Helpers
# ---------------------------------------------------------------------------
def save_parquet(
    df: pd.DataFrame,
    category: str,
    filename: str,
    partition_cols: Optional[List[str]] = None,
):
    """
    Save DataFrame to Parquet in data/<category>/<filename>.parquet
    Optionally partition by columns.
    """
    data_dir = get_data_dir() / category
    data_dir.mkdir(parents=True, exist_ok=True)

    path = data_dir / f"{filename}.parquet"

    if partition_cols:
        table = pa.Table.from_pandas(df)
        pq.write_to_dataset(
            table,
            root_path=str(data_dir / filename),
            partition_cols=partition_cols,
        )
        logger.debug(f"Saved partitioned parquet: {data_dir / filename}")
    else:
        df.to_parquet(path, engine="pyarrow", index=False)
        logger.debug(f"Saved parquet: {path}")

    return path


def load_parquet(
    category: str,
    filename: str,
    filters: Optional[List] = None,
) -> Optional[pd.DataFrame]:
    """
    Load DataFrame from Parquet. Returns None if not found.
    """
    data_dir = get_data_dir() / category

    # Try partitioned dataset first
    dataset_dir = data_dir / filename
    if dataset_dir.is_dir():
        try:
            dataset = pq.ParquetDataset(str(dataset_dir), filters=filters)
            return dataset.read().to_pandas()
        except Exception as e:
            logger.warning(f"Failed to read partitioned dataset {dataset_dir}: {e}")
            return None

    # Try single file
    path = data_dir / f"{filename}.parquet"
    if path.exists():
        try:
            return pd.read_parquet(path, engine="pyarrow")
        except Exception as e:
            logger.warning(f"Failed to read parquet {path}: {e}")
            return None

    return None


def append_parquet(
    df: pd.DataFrame,
    category: str,
    filename: str,
):
    """Append rows to existing Parquet file, or create new."""
    existing = load_parquet(category, filename)
    if existing is not None:
        combined = pd.concat([existing, df], ignore_index=True)
        # Drop exact duplicates
        combined = combined.drop_duplicates()
    else:
        combined = df
    save_parquet(combined, category, filename)


# ---------------------------------------------------------------------------
# Date Helpers
# ---------------------------------------------------------------------------
def trading_date_str(d: Optional[date] = None) -> str:
    """Return date string in YYYY-MM-DD format."""
    if d is None:
        d = date.today()
    return d.strftime("%Y-%m-%d")


def is_market_open(d: Optional[date] = None) -> bool:
    """Simple check if date is a weekday (not accounting for holidays)."""
    if d is None:
        d = date.today()
    return d.weekday() < 5


# ---------------------------------------------------------------------------
# Financial Formatting
# ---------------------------------------------------------------------------
def fmt_pct(value: float, decimals: int = 2) -> str:
    """Format as percentage string."""
    if pd.isna(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def fmt_currency(value: float, decimals: int = 2) -> str:
    """Format as currency string."""
    if pd.isna(value):
        return "N/A"
    return f"${value:,.{decimals}f}"


def fmt_number(value: float, decimals: int = 2) -> str:
    """Format number with commas."""
    if pd.isna(value):
        return "N/A"
    return f"{value:,.{decimals}f}"
