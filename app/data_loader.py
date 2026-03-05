"""Data loading and caching logic for speedtest results."""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

try:
    import orjson

    _JSON_LOADS = orjson.loads
    _USE_ORJSON = True
except Exception:
    _JSON_LOADS = json.loads
    _USE_ORJSON = False

# Configure module logger
logger = logging.getLogger(__name__)

# Only configure if no handlers exist (avoid duplicate handlers on Streamlit reruns)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Environment variables
DATA_DIR = os.environ.get("DATA_DIR", "/data")


def _parse_refresh_interval_seconds(default_value: int = 3600) -> int:
    """Parse refresh interval from env with validation and safe fallback."""
    raw_value = os.environ.get("REFRESH_INTERVAL_SECONDS", str(default_value))
    try:
        parsed = int(raw_value)
        if parsed < 1:
            raise ValueError("must be >= 1")
        return parsed
    except (TypeError, ValueError):
        logger.warning(
            "Invalid REFRESH_INTERVAL_SECONDS=%r. Falling back to %d seconds.",
            raw_value,
            default_value,
        )
        return default_value


REFRESH_INTERVAL_SECONDS = _parse_refresh_interval_seconds()
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DEFAULT_METRIC = os.environ.get("DEFAULT_METRIC")

# Apply configured log level
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


def _get_cache_path() -> Path:
    """Get cache file path in system temp directory, unique per DATA_DIR."""
    # Hash DATA_DIR to create unique cache file per data source
    dir_hash = hashlib.md5(DATA_DIR.encode()).hexdigest()[:12]
    cache_path = Path(tempfile.gettempdir()) / f"speedtest_cache_{dir_hash}.parquet"
    logger.debug("Cache path resolved: %s (DATA_DIR=%s)", cache_path, DATA_DIR)
    return cache_path


# Metric definitions with display names, units, and conversion functions
METRICS = {
    "download": {
        "name": "Download",
        "unit": "Mbps",
        "convert": lambda x: x / 1_000_000,
    },
    "upload": {
        "name": "Upload",
        "unit": "Mbps",
        "convert": lambda x: x / 1_000_000,
    },
    "latency": {
        "name": "Latency",
        "unit": "ms",
        "convert": lambda x: x,
    },
    "jitter": {
        "name": "Jitter",
        "unit": "ms",
        "convert": lambda x: x,
    },
    "downLoadedLatency": {
        "name": "Loaded Latency (Down)",
        "unit": "ms",
        "convert": lambda x: x,
    },
    "downLoadedJitter": {
        "name": "Loaded Jitter (Down)",
        "unit": "ms",
        "convert": lambda x: x,
    },
    "upLoadedLatency": {
        "name": "Loaded Latency (Up)",
        "unit": "ms",
        "convert": lambda x: x,
    },
    "upLoadedJitter": {
        "name": "Loaded Jitter (Up)",
        "unit": "ms",
        "convert": lambda x: x,
    },
}


_TIMESTAMP_RE = re.compile(
    r"speedtest-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)\.json"
)


def parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """
    Extract timestamp from filename like 'speedtest-2024-01-15T10-30-00-000Z.json'.

    The timestamp format is ISO 8601 with colons/dots replaced by hyphens.
    """
    match = _TIMESTAMP_RE.match(filename)
    if not match:
        return None

    timestamp_str = match.group(1)
    # Convert back to standard ISO format: replace hyphens with colons in time part
    # 2024-01-15T10-30-00-000Z -> 2024-01-15T10:30:00.000Z
    parts = timestamp_str.split("T")
    if len(parts) != 2:
        return None

    date_part = parts[0]
    time_part = parts[1]

    # Time format: HH-mm-ss-SSSZ -> HH:mm:ss.SSSZ
    time_match = re.match(r"(\d{2})-(\d{2})-(\d{2})-(\d{3})Z", time_part)
    if not time_match:
        return None

    hour, minute, second, ms = time_match.groups()
    iso_str = f"{date_part}T{hour}:{minute}:{second}.{ms}Z"

    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_single_file(filepath: Path) -> Optional[dict]:
    """
    Load and validate a single JSON file.

    Returns None if file is corrupt or missing required fields.
    """
    try:
        if _USE_ORJSON:
            with open(filepath, "rb") as f:
                data = _JSON_LOADS(f.read())
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                data = _JSON_LOADS(f.read())

        # Filter out failed measurements
        if not data.get("success", False):
            logger.debug("Skipping failed measurement: %s", filepath.name)
            return None

        if "result" not in data:
            logger.debug("Skipping file without result field: %s", filepath.name)
            return None

        # Extract timestamp from filename
        timestamp = parse_timestamp_from_filename(filepath.name)
        if timestamp is None:
            logger.warning("Could not parse timestamp from filename: %s", filepath.name)
            return None

        # Build record with converted metrics
        record = {
            "timestamp": timestamp,
            "source_file": filepath.name,  # Track which file this came from
            "source_mtime_ns": filepath.stat().st_mtime_ns,
            "sessionID": data.get("sessionID"),
            "endpoint": data.get("endpoint"),
        }

        for key, config in METRICS.items():
            if key in data["result"]:
                record[key] = config["convert"](data["result"][key])

        return record
    except json.JSONDecodeError as e:
        logger.warning("JSON decode error in %s: %s", filepath.name, e)
        return None
    except (KeyError, TypeError) as e:
        logger.warning("Data extraction error in %s: %s", filepath.name, e)
        return None
    except OSError as e:
        logger.error("File read error for %s: %s", filepath.name, e)
        return None


def _load_json_files_parallel(filepaths: list[Path]) -> list[dict]:
    """Load multiple JSON files in parallel using thread pool."""
    if not filepaths:
        logger.debug("No files to load")
        return []

    start_time = time.perf_counter()
    num_workers = min(32, len(filepaths))
    logger.info(
        "Loading %d JSON files in parallel (workers=%d)", len(filepaths), num_workers
    )

    records = []
    failed_count = 0
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_path = {executor.submit(load_single_file, fp): fp for fp in filepaths}
        for future in as_completed(future_to_path):
            record = future.result()
            if record:
                records.append(record)
            else:
                failed_count += 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Parallel load complete: %d successful, %d skipped/failed (%.1f ms)",
        len(records),
        failed_count,
        elapsed_ms,
    )
    return records


def _load_cache(cache_path: Path) -> Optional[pd.DataFrame]:
    """Load data from Parquet cache file if it exists."""
    if not cache_path.exists():
        logger.info("Cache miss: file does not exist (%s)", cache_path)
        return None
    try:
        start_time = time.perf_counter()
        df = pd.read_parquet(cache_path)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        cache_size_kb = cache_path.stat().st_size / 1024
        logger.info(
            "Cache hit: loaded %d records (%.1f KB) in %.1f ms",
            len(df),
            cache_size_kb,
            elapsed_ms,
        )
        return df
    except Exception as e:
        logger.warning("Cache corrupted, will rebuild: %s", e)
        return None


def _save_cache(df: pd.DataFrame, cache_path: Path) -> None:
    """Save DataFrame to Parquet cache file."""
    try:
        start_time = time.perf_counter()
        df.to_parquet(cache_path, index=False)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        cache_size_kb = cache_path.stat().st_size / 1024
        logger.info(
            "Cache saved: %d records (%.1f KB) in %.1f ms",
            len(df),
            cache_size_kb,
            elapsed_ms,
        )
    except Exception as e:
        logger.error("Cache save failed (non-fatal): %s", e)


@st.cache_data(ttl=max(REFRESH_INTERVAL_SECONDS - 5, 5))
def load_all_data() -> pd.DataFrame:
    """
    Load speedtest data with Parquet caching for fast startup.

    On first run, loads all JSON files and creates a cache.
    On subsequent runs, loads from cache and only parses new JSON files.
    Returns a DataFrame sorted by timestamp (oldest first).
    """
    overall_start = time.perf_counter()
    logger.info("Starting data load (DATA_DIR=%s)", DATA_DIR)

    data_path = Path(DATA_DIR)
    if not data_path.exists():
        logger.warning("Data directory does not exist: %s", DATA_DIR)
        return pd.DataFrame()

    cache_path = _get_cache_path()

    # Get all JSON files in directory
    all_json_files = {fp.name: fp for fp in data_path.glob("speedtest-*.json")}
    if not all_json_files:
        logger.warning("No speedtest JSON files found in %s", DATA_DIR)
        return pd.DataFrame()

    logger.info("Found %d JSON files in data directory", len(all_json_files))

    # Try to load existing cache
    cached_df = _load_cache(cache_path)

    if (
        cached_df is not None
        and not cached_df.empty
        and "source_file" in cached_df.columns
    ):
        # Find files not yet in cache
        cached_files = set(cached_df["source_file"].unique())
        current_files = set(all_json_files.keys())

        deleted_files = cached_files - current_files
        new_files = [
            fp for name, fp in all_json_files.items() if name not in cached_files
        ]

        changed_files = []
        if "source_mtime_ns" in cached_df.columns:
            cached_mtime = (
                cached_df.groupby("source_file")["source_mtime_ns"].max().to_dict()
            )
            for name in cached_files & current_files:
                filepath = all_json_files[name]
                try:
                    current_mtime = filepath.stat().st_mtime_ns
                except OSError:
                    changed_files.append(filepath)
                    continue

                cached_mtime_ns = cached_mtime.get(name)
                if cached_mtime_ns is None or int(cached_mtime_ns) != current_mtime:
                    changed_files.append(filepath)
        else:
            logger.info(
                "Cache does not include source mtime metadata; "
                "forcing one-time refresh."
            )
            changed_files = [
                all_json_files[name] for name in (cached_files & current_files)
            ]

        if not new_files and not changed_files and not deleted_files:
            # Cache is up to date
            elapsed_ms = (time.perf_counter() - overall_start) * 1000
            logger.info(
                "Cache is current, no new files to load (total: %.1f ms)", elapsed_ms
            )
            return cached_df.drop(columns=["source_file"], errors="ignore").sort_values(
                "timestamp", ascending=True
            )

        logger.info(
            "Cache delta: %d new, %d changed, %d deleted (%d cached)",
            len(new_files),
            len(changed_files),
            len(deleted_files),
            len(cached_files),
        )

        files_to_reload = {fp.name for fp in [*new_files, *changed_files]}
        if deleted_files or files_to_reload:
            kept_df = cached_df[
                ~cached_df["source_file"].isin(deleted_files | files_to_reload)
            ]
        else:
            kept_df = cached_df

        # Load only new/changed files
        delta_records = _load_json_files_parallel([*new_files, *changed_files])

        if delta_records:
            delta_df = pd.DataFrame(delta_records)
            df = pd.concat([kept_df, delta_df], ignore_index=True)
            logger.info(
                "Merged %d refreshed records with %d cached records",
                len(delta_records),
                len(kept_df),
            )
        else:
            df = kept_df
    else:
        if cached_df is not None and not cached_df.empty:
            logger.warning(
                "Cache schema mismatch: missing 'source_file' column. Rebuilding cache."
            )
        # No cache, load all files
        logger.info("Building cache from scratch (cold start)")
        all_filepaths = list(all_json_files.values())
        records = _load_json_files_parallel(all_filepaths)

        if not records:
            logger.warning("No valid records found in any JSON files")
            return pd.DataFrame()

        df = pd.DataFrame(records)

    # Sort and save updated cache
    df = df.sort_values("timestamp", ascending=True)
    _save_cache(df, cache_path)

    elapsed_ms = (time.perf_counter() - overall_start) * 1000
    logger.info(
        "Data load complete: %d total records (%.1f ms total)", len(df), elapsed_ms
    )

    # Return without source_file column (internal tracking only)
    return df.drop(columns=["source_file"], errors="ignore")


def get_latest_measurements(df: pd.DataFrame, count: int = 5) -> pd.DataFrame:
    """Return the most recent N measurements (most recent first)."""
    if df.empty:
        return df
    return df.tail(count).iloc[::-1]


def aggregate_to_intervals(
    df: pd.DataFrame, interval_minutes: int = 10
) -> pd.DataFrame:
    """
    Aggregate measurements into time intervals, preserving endpoint information.

    Each measurement run produces ~5 data points. This function groups them
    by the specified interval and endpoint, calculating the mean for each metric.
    """
    if df.empty:
        logger.debug("Aggregation skipped: empty DataFrame")
        return df

    start_time = time.perf_counter()
    df = df.assign(interval=df["timestamp"].dt.floor(f"{interval_minutes}min"))

    metric_cols = [col for col in df.columns if col in METRICS]

    # Check if endpoint column exists
    if "endpoint" in df.columns:
        # Group by both interval and endpoint to preserve endpoint info
        agg_dict = {col: "mean" for col in metric_cols}
        agg_df = df.groupby(["interval", "endpoint"]).agg(agg_dict).reset_index()
        agg_df = agg_df.rename(columns={"interval": "timestamp"})
    else:
        # Fallback: group only by interval
        agg_dict = {col: "mean" for col in metric_cols}
        agg_df = df.groupby("interval").agg(agg_dict).reset_index()
        agg_df = agg_df.rename(columns={"interval": "timestamp"})

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.debug(
        "Aggregated %d records into %d intervals (%d-min buckets, %.1f ms)",
        len(df),
        len(agg_df),
        interval_minutes,
        elapsed_ms,
    )

    return agg_df.sort_values("timestamp", ascending=True)
