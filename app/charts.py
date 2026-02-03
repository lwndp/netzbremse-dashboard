"""Chart generation functions using Altair."""

from urllib.parse import urlparse

import altair as alt
import pandas as pd

# Brand color matching netzbremse.de
BRAND_COLOR = "#e91e63"

# Magenta color palette for endpoints (nuances from light to dark)
MAGENTA_PALETTE = [
    "#f8bbd9",  # Light pink
    "#f48fb1",  # Pink
    "#f06292",  # Medium pink
    "#ec407a",  # Magenta pink
    "#e91e63",  # Brand magenta
    "#d81b60",  # Dark magenta
    "#c2185b",  # Darker magenta
    "#ad1457",  # Deep magenta
    "#880e4f",  # Very dark magenta
    "#6a1b4d",  # Darkest
]


def _shorten_endpoint(url: str) -> str:
    """
    Extract short form from endpoint URL.

    Example: https://custom-t0.speed.cloudflare.com --> custom-t0
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.netloc or url
        # Get the first part of the hostname (subdomain)
        first_part = hostname.split(".")[0]
        return first_part if first_part else url
    except Exception:
        return url


def _get_endpoint_color_scale(endpoints: list[str]) -> alt.Scale:
    """Create a color scale for endpoints using magenta nuances."""
    n_endpoints = len(endpoints)
    if n_endpoints <= len(MAGENTA_PALETTE):
        colors = MAGENTA_PALETTE[:n_endpoints]
    else:
        # Cycle through palette if more endpoints than colors
        colors = [MAGENTA_PALETTE[i % len(MAGENTA_PALETTE)] for i in range(n_endpoints)]
    return alt.Scale(domain=endpoints, range=colors)


def create_median_band_chart(
    df: pd.DataFrame,
    metric_key: str,
    metric_name: str,
    metric_unit: str,
    height: int = 300,
    time_format: str = "%Y-%m-%d %H:%M",
    x_title: str = "Time",
) -> alt.Chart:
    """
    Create a line chart showing median with percentile bands.

    Groups data by timestamp and shows:
    - Median line (50th percentile)
    - Band from 25th to 75th percentile
    """
    if df.empty:
        return (
            alt.Chart(pd.DataFrame())
            .mark_text()
            .encode(text=alt.value("No data available"))
        )

    # Group by timestamp and calculate statistics
    stats_df = (
        df.groupby("timestamp")
        .agg(
            median=(metric_key, "median"),
            q25=(metric_key, lambda x: x.quantile(0.25)),
            q75=(metric_key, lambda x: x.quantile(0.75)),
        )
        .reset_index()
    )

    # Create band (25th to 75th percentile)
    band = (
        alt.Chart(stats_df)
        .mark_area(
            opacity=0.3,
            color=BRAND_COLOR,
        )
        .encode(
            x=alt.X(
                "timestamp:T",
                title=x_title,
                axis=alt.Axis(format=time_format, labelAngle=-45),
            ),
            y=alt.Y("q25:Q", title=f"{metric_name} ({metric_unit})"),
            y2=alt.Y2("q75:Q"),
            tooltip=[
                alt.Tooltip("timestamp:T", title="Time", format=time_format),
                alt.Tooltip("q25:Q", title="25th Percentile", format=".2f"),
                alt.Tooltip("q75:Q", title="75th Percentile", format=".2f"),
            ],
        )
    )

    # Create median line
    line = (
        alt.Chart(stats_df)
        .mark_line(
            color=BRAND_COLOR,
            strokeWidth=2.5,
        )
        .encode(
            x=alt.X("timestamp:T", title=x_title),
            y=alt.Y("median:Q"),
            tooltip=[
                alt.Tooltip("timestamp:T", title="Time", format=time_format),
                alt.Tooltip("median:Q", title="Median", format=".2f"),
            ],
        )
    )

    # Add points
    points = (
        alt.Chart(stats_df)
        .mark_circle(
            color=BRAND_COLOR,
            size=30,
        )
        .encode(
            x=alt.X("timestamp:T"),
            y=alt.Y("median:Q"),
        )
    )

    return (band + line + points).properties(
        height=height,
        title=f"{metric_name} - Median with IQR Band",
    )


def create_endpoint_lines_chart(
    df: pd.DataFrame,
    metric_key: str,
    metric_name: str,
    metric_unit: str,
    height: int = 300,
    time_format: str = "%Y-%m-%d %H:%M",
    x_title: str = "Time",
) -> alt.Chart:
    """
    Create a line chart with separate lines for each endpoint.

    Each endpoint is colored in a different magenta nuance.
    """
    if df.empty or "endpoint" not in df.columns:
        return (
            alt.Chart(pd.DataFrame())
            .mark_text()
            .encode(text=alt.value("No data available"))
        )

    # Group by timestamp and endpoint, then shorten endpoint names
    grouped_df = df.groupby(["timestamp", "endpoint"])[metric_key].mean().reset_index()
    grouped_df["endpoint"] = grouped_df["endpoint"].apply(_shorten_endpoint)

    endpoints = sorted(grouped_df["endpoint"].unique().tolist())
    color_scale = _get_endpoint_color_scale(endpoints)

    # Create lines for each endpoint
    lines = (
        alt.Chart(grouped_df)
        .mark_line(
            strokeWidth=2,
        )
        .encode(
            x=alt.X(
                "timestamp:T",
                title=x_title,
                axis=alt.Axis(format=time_format, labelAngle=-45),
            ),
            y=alt.Y(
                f"{metric_key}:Q",
                title=f"{metric_name} ({metric_unit})",
            ),
            color=alt.Color(
                "endpoint:N",
                scale=color_scale,
                legend=alt.Legend(title="Endpoint", orient="top"),
            ),
            tooltip=[
                alt.Tooltip("timestamp:T", title="Time", format=time_format),
                alt.Tooltip("endpoint:N", title="Endpoint"),
                alt.Tooltip(f"{metric_key}:Q", title=metric_name, format=".2f"),
            ],
        )
    )

    # Add points
    points = (
        alt.Chart(grouped_df)
        .mark_circle(
            size=25,
        )
        .encode(
            x=alt.X("timestamp:T"),
            y=alt.Y(f"{metric_key}:Q"),
            color=alt.Color("endpoint:N", scale=color_scale, legend=None),
        )
    )

    return (lines + points).properties(
        height=height,
        title=f"{metric_name} by Endpoint",
    )


def create_24h_median_band_chart(
    df: pd.DataFrame,
    metric_key: str,
    metric_name: str,
    metric_unit: str,
    height: int = 300,
) -> alt.Chart:
    """
    Create a 24-hour summary chart showing median with percentile bands.

    Aggregates data by hour of day (0-23) across all days in the dataset.
    """
    if df.empty:
        return (
            alt.Chart(pd.DataFrame())
            .mark_text()
            .encode(text=alt.value("No data available"))
        )

    # Extract hour of day
    df = df.copy()
    df["hour"] = df["timestamp"].dt.hour

    # Group by hour and calculate statistics
    stats_df = (
        df.groupby("hour")
        .agg(
            median=(metric_key, "median"),
            q25=(metric_key, lambda x: x.quantile(0.25)),
            q75=(metric_key, lambda x: x.quantile(0.75)),
            count=(metric_key, "count"),
        )
        .reset_index()
    )

    # Create band (25th to 75th percentile)
    band = (
        alt.Chart(stats_df)
        .mark_area(
            opacity=0.3,
            color=BRAND_COLOR,
        )
        .encode(
            x=alt.X(
                "hour:O",
                title="Hour of Day",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("q25:Q", title=f"{metric_name} ({metric_unit})"),
            y2=alt.Y2("q75:Q"),
            tooltip=[
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("q25:Q", title="25th Percentile", format=".2f"),
                alt.Tooltip("q75:Q", title="75th Percentile", format=".2f"),
                alt.Tooltip("count:Q", title="Sample Count"),
            ],
        )
    )

    # Create median line
    line = (
        alt.Chart(stats_df)
        .mark_line(
            color=BRAND_COLOR,
            strokeWidth=2.5,
        )
        .encode(
            x=alt.X("hour:O", title="Hour of Day"),
            y=alt.Y("median:Q"),
            tooltip=[
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("median:Q", title="Median", format=".2f"),
            ],
        )
    )

    # Add points
    points = (
        alt.Chart(stats_df)
        .mark_circle(
            color=BRAND_COLOR,
            size=40,
        )
        .encode(
            x=alt.X("hour:O"),
            y=alt.Y("median:Q"),
        )
    )

    return (band + line + points).properties(
        height=height,
        title=f"{metric_name} - 24h Median with IQR Band",
    )


def create_24h_endpoint_lines_chart(
    df: pd.DataFrame,
    metric_key: str,
    metric_name: str,
    metric_unit: str,
    height: int = 300,
) -> alt.Chart:
    """
    Create a 24-hour summary chart with lines for each endpoint.

    Aggregates data by hour of day (0-23) across all days, per endpoint.
    """
    if df.empty or "endpoint" not in df.columns:
        return (
            alt.Chart(pd.DataFrame())
            .mark_text()
            .encode(text=alt.value("No data available"))
        )

    # Extract hour of day
    df = df.copy()
    df["hour"] = df["timestamp"].dt.hour

    # Group by hour and endpoint, then shorten endpoint names
    grouped_df = df.groupby(["hour", "endpoint"])[metric_key].mean().reset_index()
    grouped_df["endpoint"] = grouped_df["endpoint"].apply(_shorten_endpoint)

    endpoints = sorted(grouped_df["endpoint"].unique().tolist())
    color_scale = _get_endpoint_color_scale(endpoints)

    # Create lines for each endpoint
    lines = (
        alt.Chart(grouped_df)
        .mark_line(
            strokeWidth=2,
        )
        .encode(
            x=alt.X(
                "hour:O",
                title="Hour of Day",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                f"{metric_key}:Q",
                title=f"{metric_name} ({metric_unit})",
            ),
            color=alt.Color(
                "endpoint:N",
                scale=color_scale,
                legend=alt.Legend(title="Endpoint", orient="top"),
            ),
            tooltip=[
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("endpoint:N", title="Endpoint"),
                alt.Tooltip(f"{metric_key}:Q", title=metric_name, format=".2f"),
            ],
        )
    )

    # Add points
    points = (
        alt.Chart(grouped_df)
        .mark_circle(
            size=35,
        )
        .encode(
            x=alt.X("hour:O"),
            y=alt.Y(f"{metric_key}:Q"),
            color=alt.Color("endpoint:N", scale=color_scale, legend=None),
        )
    )

    return (lines + points).properties(
        height=height,
        title=f"{metric_name} by Endpoint - 24h Summary",
    )


def render_longterm_section(
    df: pd.DataFrame,
    metric_key: str,
    metric_name: str,
    metric_unit: str,
) -> tuple[alt.Chart, alt.Chart]:
    """
    Render the long-term performance section charts.

    Returns:
        Tuple of (median_band_chart, endpoint_lines_chart)
    """
    median_chart = create_median_band_chart(
        df=df,
        metric_key=metric_key,
        metric_name=metric_name,
        metric_unit=metric_unit,
        height=350,
        time_format="%b %d %H:%M",
    )

    endpoint_chart = create_endpoint_lines_chart(
        df=df,
        metric_key=metric_key,
        metric_name=metric_name,
        metric_unit=metric_unit,
        height=350,
        time_format="%b %d %H:%M",
    )

    return median_chart, endpoint_chart


def render_24h_section(
    df: pd.DataFrame,
    metric_key: str,
    metric_name: str,
    metric_unit: str,
) -> tuple[alt.Chart, alt.Chart, int]:
    """
    Render the 24-hour summary section charts.

    Returns:
        Tuple of (median_band_chart, endpoint_lines_chart, missing_hours_count)
    """
    # Calculate missing hours
    if df.empty:
        missing_hours = 24
    else:
        df_copy = df.copy()
        df_copy["hour"] = df_copy["timestamp"].dt.hour
        present_hours = set(df_copy["hour"].unique())
        missing_hours = 24 - len(present_hours)

    median_chart = create_24h_median_band_chart(
        df=df,
        metric_key=metric_key,
        metric_name=metric_name,
        metric_unit=metric_unit,
        height=350,
    )

    endpoint_chart = create_24h_endpoint_lines_chart(
        df=df,
        metric_key=metric_key,
        metric_name=metric_name,
        metric_unit=metric_unit,
        height=350,
    )

    return median_chart, endpoint_chart, missing_hours
