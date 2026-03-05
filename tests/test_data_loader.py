"""Unit tests for app/data_loader.py."""

import json
import os
from datetime import timezone
from pathlib import Path

import pandas as pd
import pytest

# conftest.py stubs streamlit before this import
from app.data_loader import (
    aggregate_to_intervals,
    get_latest_measurements,
    load_single_file,
    parse_timestamp_from_filename,
)

# ---------------------------------------------------------------------------
# parse_timestamp_from_filename
# ---------------------------------------------------------------------------


class TestParseTimestampFromFilename:
    def test_valid_filename_returns_utc_datetime(self):
        ts = parse_timestamp_from_filename("speedtest-2024-01-15T10-30-00-000Z.json")
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15
        assert ts.hour == 10
        assert ts.minute == 30
        assert ts.second == 0
        assert ts.tzinfo == timezone.utc

    def test_milliseconds_preserved(self):
        ts = parse_timestamp_from_filename("speedtest-2024-06-01T23-59-59-123Z.json")
        assert ts is not None
        assert ts.microsecond == 123_000

    def test_non_matching_filename_returns_none(self):
        assert parse_timestamp_from_filename("not-a-speedtest-file.json") is None

    def test_wrong_extension_returns_none(self):
        assert (
            parse_timestamp_from_filename("speedtest-2024-01-15T10-30-00-000Z.txt")
            is None
        )

    def test_empty_string_returns_none(self):
        assert parse_timestamp_from_filename("") is None

    def test_missing_milliseconds_returns_none(self):
        # Time part only has HH-mm-ss without -SSSZ
        assert (
            parse_timestamp_from_filename("speedtest-2024-01-15T10-30-00Z.json") is None
        )


# ---------------------------------------------------------------------------
# _parse_refresh_interval_seconds (tested via env var)
# ---------------------------------------------------------------------------


class TestParseRefreshIntervalSeconds:
    def _call(self, value=None, default=3600):
        # Import private function directly
        from app.data_loader import _parse_refresh_interval_seconds

        old = os.environ.pop("REFRESH_INTERVAL_SECONDS", None)
        try:
            if value is not None:
                os.environ["REFRESH_INTERVAL_SECONDS"] = value
            return _parse_refresh_interval_seconds(default)
        finally:
            if old is not None:
                os.environ["REFRESH_INTERVAL_SECONDS"] = old
            elif "REFRESH_INTERVAL_SECONDS" in os.environ:
                del os.environ["REFRESH_INTERVAL_SECONDS"]

    def test_valid_integer_string(self):
        assert self._call("600") == 600

    def test_uses_default_when_env_not_set(self):
        assert self._call(None, default=1800) == 1800

    def test_zero_falls_back_to_default(self):
        assert self._call("0", default=3600) == 3600

    def test_negative_falls_back_to_default(self):
        assert self._call("-10", default=3600) == 3600

    def test_non_numeric_falls_back_to_default(self):
        assert self._call("not-a-number", default=3600) == 3600

    def test_float_string_falls_back_to_default(self):
        assert self._call("3.14", default=3600) == 3600


# ---------------------------------------------------------------------------
# load_single_file
# ---------------------------------------------------------------------------


def _write_json(tmp_path: Path, filename: str, data: dict) -> Path:
    filepath = tmp_path / filename
    filepath.write_text(json.dumps(data))
    return filepath


VALID_FILENAME = "speedtest-2024-03-10T12-00-00-000Z.json"

VALID_DATA = {
    "success": True,
    "sessionID": "abc-123",
    "endpoint": "https://speedtest.example.com",
    "result": {
        "download": 100_000_000,
        "upload": 50_000_000,
        "latency": 10.5,
        "jitter": 2.3,
    },
}


class TestLoadSingleFile:
    def test_valid_file_returns_record(self, tmp_path):
        fp = _write_json(tmp_path, VALID_FILENAME, VALID_DATA)
        record = load_single_file(fp)
        assert record is not None
        assert record["download"] == pytest.approx(100.0)
        assert record["upload"] == pytest.approx(50.0)
        assert record["latency"] == pytest.approx(10.5)
        assert record["jitter"] == pytest.approx(2.3)

    def test_converts_bps_to_mbps(self, tmp_path):
        fp = _write_json(tmp_path, VALID_FILENAME, VALID_DATA)
        record = load_single_file(fp)
        # download: 100_000_000 bps / 1_000_000 = 100.0 Mbps
        assert record["download"] == pytest.approx(100.0)

    def test_failed_measurement_returns_none(self, tmp_path):
        data = {**VALID_DATA, "success": False}
        fp = _write_json(tmp_path, VALID_FILENAME, data)
        assert load_single_file(fp) is None

    def test_missing_result_field_returns_none(self, tmp_path):
        data = {"success": True, "sessionID": "x"}
        fp = _write_json(tmp_path, VALID_FILENAME, data)
        assert load_single_file(fp) is None

    def test_corrupt_json_returns_none(self, tmp_path):
        fp = tmp_path / VALID_FILENAME
        fp.write_text("{ not valid json }")
        assert load_single_file(fp) is None

    def test_bad_filename_returns_none(self, tmp_path):
        fp = _write_json(tmp_path, "bad-filename.json", VALID_DATA)
        assert load_single_file(fp) is None

    def test_missing_file_returns_none(self, tmp_path):
        fp = tmp_path / VALID_FILENAME
        assert load_single_file(fp) is None

    def test_record_includes_timestamp(self, tmp_path):
        fp = _write_json(tmp_path, VALID_FILENAME, VALID_DATA)
        record = load_single_file(fp)
        assert "timestamp" in record
        assert record["timestamp"].year == 2024
        assert record["timestamp"].month == 3

    def test_record_includes_session_and_endpoint(self, tmp_path):
        fp = _write_json(tmp_path, VALID_FILENAME, VALID_DATA)
        record = load_single_file(fp)
        assert record["sessionID"] == "abc-123"
        assert record["endpoint"] == "https://speedtest.example.com"

    def test_partial_metrics_are_loaded(self, tmp_path):
        data = {
            "success": True,
            "result": {"download": 80_000_000},
        }
        fp = _write_json(tmp_path, VALID_FILENAME, data)
        record = load_single_file(fp)
        assert record is not None
        assert "download" in record
        assert "upload" not in record


# ---------------------------------------------------------------------------
# get_latest_measurements
# ---------------------------------------------------------------------------


def _make_df(n: int) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({"timestamp": timestamps, "download": range(n)})


class TestGetLatestMeasurements:
    def test_returns_most_recent_n(self):
        df = _make_df(10)
        result = get_latest_measurements(df, count=3)
        assert len(result) == 3
        # Most recent first
        assert list(result["download"]) == [9, 8, 7]

    def test_empty_df_returns_empty(self):
        result = get_latest_measurements(pd.DataFrame())
        assert result.empty

    def test_count_larger_than_df(self):
        df = _make_df(3)
        result = get_latest_measurements(df, count=10)
        assert len(result) == 3

    def test_default_count_is_five(self):
        df = _make_df(10)
        result = get_latest_measurements(df)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# aggregate_to_intervals
# ---------------------------------------------------------------------------


def _make_metrics_df(
    timestamps, downloads, uploads=None, endpoint=None
) -> pd.DataFrame:
    data = {
        "timestamp": pd.to_datetime(timestamps),
        "download": downloads,
    }
    if uploads is not None:
        data["upload"] = uploads
    if endpoint is not None:
        data["endpoint"] = endpoint
    return pd.DataFrame(data)


class TestAggregateToIntervals:
    def test_empty_df_returns_empty(self):
        result = aggregate_to_intervals(pd.DataFrame())
        assert result.empty

    def test_groups_into_10min_buckets(self):
        timestamps = [
            "2024-01-01 10:01",
            "2024-01-01 10:05",
            "2024-01-01 10:11",
        ]
        downloads = [100.0, 200.0, 50.0]
        df = _make_metrics_df(timestamps, downloads)
        result = aggregate_to_intervals(df, interval_minutes=10)
        # 10:01 and 10:05 → 10:00 bucket; 10:11 → 10:10 bucket
        assert len(result) == 2

    def test_calculates_mean_within_bucket(self):
        timestamps = ["2024-01-01 10:01", "2024-01-01 10:05"]
        downloads = [100.0, 200.0]
        df = _make_metrics_df(timestamps, downloads)
        result = aggregate_to_intervals(df, interval_minutes=10)
        assert result["download"].iloc[0] == pytest.approx(150.0)

    def test_output_sorted_ascending(self):
        timestamps = [
            "2024-01-01 10:11",
            "2024-01-01 10:01",
        ]
        downloads = [1.0, 2.0]
        df = _make_metrics_df(timestamps, downloads)
        result = aggregate_to_intervals(df, interval_minutes=10)
        assert result["timestamp"].is_monotonic_increasing

    def test_groups_by_endpoint_when_present(self):
        timestamps = ["2024-01-01 10:01", "2024-01-01 10:02"]
        downloads = [100.0, 200.0]
        endpoints = ["ep-a", "ep-b"]
        df = _make_metrics_df(timestamps, downloads, endpoint=endpoints)
        result = aggregate_to_intervals(df, interval_minutes=10)
        # Same 10-min bucket, but two distinct endpoints → two rows
        assert len(result) == 2
        assert set(result["endpoint"]) == {"ep-a", "ep-b"}

    def test_only_known_metric_columns_aggregated(self):
        timestamps = ["2024-01-01 10:01"]
        df = _make_metrics_df(timestamps, [100.0], uploads=[50.0])
        result = aggregate_to_intervals(df, interval_minutes=10)
        assert "download" in result.columns
        assert "upload" in result.columns

    def test_custom_interval_minutes(self):
        timestamps = [
            "2024-01-01 10:00",
            "2024-01-01 10:30",
            "2024-01-01 11:00",
        ]
        df = _make_metrics_df(timestamps, [1.0, 2.0, 3.0])
        result = aggregate_to_intervals(df, interval_minutes=60)
        # 10:00 and 10:30 → same 60-min bucket; 11:00 → next bucket
        assert len(result) == 2
