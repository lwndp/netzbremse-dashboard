"""Unit tests for app/charts.py."""

import pandas as pd

# conftest.py stubs streamlit before this import
from app.charts import (
    ENDPOINT_PALETTE,
    _build_endpoint_label_map,
    _get_endpoint_color_scale,
    _shorten_endpoint,
    create_endpoint_lines_chart,
    create_median_band_chart,
)

# ---------------------------------------------------------------------------
# _shorten_endpoint
# ---------------------------------------------------------------------------


class TestShortenEndpoint:
    def test_extracts_subdomain(self):
        assert (
            _shorten_endpoint("https://custom-t0.speed.cloudflare.com") == "custom-t0"
        )

    def test_simple_hostname(self):
        assert _shorten_endpoint("https://speedtest.example.com") == "speedtest"

    def test_no_scheme_returns_first_part(self):
        # urlparse without scheme puts the whole string in path, not netloc
        # The function falls back gracefully
        result = _shorten_endpoint("speedtest.example.com")
        # Should not raise; returns some non-empty string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string_returns_empty(self):
        result = _shorten_endpoint("")
        assert isinstance(result, str)

    def test_plain_label_unchanged(self):
        # A URL with only one hostname part → returns that part
        assert _shorten_endpoint("https://myhost") == "myhost"


# ---------------------------------------------------------------------------
# _build_endpoint_label_map
# ---------------------------------------------------------------------------


class TestBuildEndpointLabelMap:
    def test_unique_short_names_use_subdomain(self):
        endpoints = [
            "https://alpha.speed.example.com",
            "https://beta.speed.example.com",
        ]
        label_map = _build_endpoint_label_map(endpoints)
        assert label_map["https://alpha.speed.example.com"] == "alpha"
        assert label_map["https://beta.speed.example.com"] == "beta"

    def test_colliding_short_names_get_index_suffix(self):
        # Both shorten to the same subdomain "node"
        endpoints = [
            "https://node.a.example.com",
            "https://node.b.example.com",
        ]
        label_map = _build_endpoint_label_map(endpoints)
        labels = set(label_map.values())
        # Each label should be unique and contain the index
        assert len(labels) == 2
        assert all("node" in label for label in labels)
        assert any("(1)" in label for label in labels)
        assert any("(2)" in label for label in labels)

    def test_single_endpoint(self):
        endpoints = ["https://test.example.com"]
        label_map = _build_endpoint_label_map(endpoints)
        assert label_map["https://test.example.com"] == "test"

    def test_empty_list_returns_empty_dict(self):
        assert _build_endpoint_label_map([]) == {}

    def test_duplicate_entries_resolved_consistently(self):
        # Same URL twice: only one distinct full endpoint so one label
        endpoints = ["https://alpha.x.com", "https://alpha.x.com"]
        label_map = _build_endpoint_label_map(endpoints)
        assert label_map["https://alpha.x.com"] == "alpha"


# ---------------------------------------------------------------------------
# _get_endpoint_color_scale
# ---------------------------------------------------------------------------


class TestGetEndpointColorScale:
    def test_single_endpoint_uses_first_palette_color(self):
        scale = _get_endpoint_color_scale(["ep-a"])
        assert scale.range == [ENDPOINT_PALETTE[0]]

    def test_colors_match_palette_order(self):
        endpoints = ["ep-a", "ep-b", "ep-c"]
        scale = _get_endpoint_color_scale(endpoints)
        assert scale.range == ENDPOINT_PALETTE[: len(endpoints)]

    def test_more_endpoints_than_palette_cycles(self):
        n = len(ENDPOINT_PALETTE) + 2
        endpoints = [f"ep-{i}" for i in range(n)]
        scale = _get_endpoint_color_scale(endpoints)
        assert len(scale.range) == n
        # First color of the overflow should match the first palette entry
        assert scale.range[len(ENDPOINT_PALETTE)] == ENDPOINT_PALETTE[0]

    def test_domain_matches_endpoints(self):
        endpoints = ["ep-x", "ep-y"]
        scale = _get_endpoint_color_scale(endpoints)
        assert scale.domain == endpoints


# ---------------------------------------------------------------------------
# create_median_band_chart
# ---------------------------------------------------------------------------


def _make_chart_df(n: int = 10) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "download": [50.0 + i for i in range(n)],
        }
    )


class TestCreateMedianBandChart:
    def test_returns_chart_for_valid_data(self):
        import altair as alt

        df = _make_chart_df()
        chart = create_median_band_chart(df, "download", "Download", "Mbps")
        assert isinstance(chart, alt.LayerChart)

    def test_returns_text_mark_for_empty_df(self):
        import altair as alt

        chart = create_median_band_chart(pd.DataFrame(), "download", "Download", "Mbps")
        assert isinstance(chart, alt.Chart)


# ---------------------------------------------------------------------------
# create_endpoint_lines_chart
# ---------------------------------------------------------------------------


def _make_endpoint_df(n: int = 6) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "download": [50.0 + i for i in range(n)],
            "endpoint": ["https://ep-a.example.com", "https://ep-b.example.com"]
            * (n // 2),
        }
    )


class TestCreateEndpointLinesChart:
    def test_returns_chart_for_valid_data(self):
        import altair as alt

        df = _make_endpoint_df()
        chart = create_endpoint_lines_chart(df, "download", "Download", "Mbps")
        assert isinstance(chart, alt.Chart)

    def test_returns_text_mark_for_empty_df(self):
        import altair as alt

        chart = create_endpoint_lines_chart(
            pd.DataFrame(), "download", "Download", "Mbps"
        )
        assert isinstance(chart, alt.Chart)

    def test_returns_text_mark_when_no_endpoint_column(self):
        import altair as alt

        df = _make_chart_df()  # no endpoint column
        chart = create_endpoint_lines_chart(df, "download", "Download", "Mbps")
        assert isinstance(chart, alt.Chart)
