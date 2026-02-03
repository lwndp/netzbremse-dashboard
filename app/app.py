"""Netzbremse Speedtest Dashboard - Main Application."""

from dotenv import load_dotenv

load_dotenv()

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from charts import render_24h_section, render_longterm_section
from components import render_header, render_latest_summary
from data_loader import (
    DATA_DIR,
    METRICS,
    REFRESH_INTERVAL_SECONDS,
    aggregate_to_intervals,
    get_latest_measurements,
    load_all_data,
)

# Configure app logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Number of recent measurements to show
RECENT_COUNT = 5

# Default date range: past 3 days
DEFAULT_DATE_RANGE_DAYS = 3

# KPI options for the dropdown
KPI_OPTIONS = {key: f"{info['name']} ({info['unit']})" for key, info in METRICS.items()}

# Page configuration
st.set_page_config(
    page_title="Netzbremse Dashboard",
    page_icon=":hourglass:",
    layout="wide",
    initial_sidebar_state="expanded",
)

logger.info("Dashboard page render started")

# Custom CSS for brand color buttons and reduced spacing
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
    }
    .stTitle {
        margin-top: -1.5rem;
    }
    .stButton > button {
        background-color: #e91e63;
        color: white;
        border: none;
    }
    .stButton > button:hover {
        background-color: #c2185b;
        color: white;
        border: none;
    }
    .stDownloadButton > button {
        background-color: #e91e63;
        color: white;
        border: none;
    }
    .stDownloadButton > button:hover {
        background-color: #c2185b;
        color: white;
        border: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar - Settings
st.sidebar.title("Settings")

# Fixed timezone for all data
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")

# Main content
render_header()

# Load data
with st.spinner("Loading data..."):
    df_utc = load_all_data()


def convert_timezone(df_input):
    """Convert timestamp column to Europe/Berlin timezone."""
    if df_input.empty:
        return df_input
    df_out = df_input.copy()
    # Ensure timestamp is timezone-aware (UTC), then convert to Berlin time
    if df_out["timestamp"].dt.tz is None:
        df_out["timestamp"] = df_out["timestamp"].dt.tz_localize("UTC")
    df_out["timestamp"] = df_out["timestamp"].dt.tz_convert(DISPLAY_TIMEZONE)
    return df_out


# Convert to Europe/Berlin timezone for all data
df = convert_timezone(df_utc)

# Check for stale data (no new measurements in last 2 hours)
if not df.empty:
    latest_measurement = df["timestamp"].max()
    now = datetime.now(DISPLAY_TIMEZONE)
    time_since_last = now - latest_measurement
    if time_since_last > timedelta(hours=2):
        total_hours = time_since_last.total_seconds() / 3600
        if total_hours >= 48:
            time_ago_str = f"{round(total_hours / 24):.0f} days"
        else:
            time_ago_str = f"{round(total_hours, 1):.0f} hours"
        logger.warning(
            "Stale data detected: last measurement was %s ago (at %s)",
            time_ago_str,
            latest_measurement.strftime("%Y-%m-%d %H:%M"),
        )
        st.warning(
            f"⚠️ No new data in the last ~{time_ago_str}. "
            f"Last measurement: {latest_measurement.strftime('%Y-%m-%d %H:%M')}"
        )

# Date range selector - First option in sidebar
if not df.empty:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Chart Controls")

    # Calculate data range bounds
    min_datetime = df["timestamp"].min()
    max_datetime = df["timestamp"].max()

    # Default to past 3 days or data range if less
    default_start = max(
        min_datetime,
        max_datetime - timedelta(days=DEFAULT_DATE_RANGE_DAYS),
    )

    # Initialize session state for applied controls (only on first run)
    if "applied_kpi" not in st.session_state:
        st.session_state.applied_kpi = "download"
        st.session_state.applied_start_date = default_start.date()
        st.session_state.applied_start_time = default_start.time().replace(
            second=0, microsecond=0
        )
        st.session_state.applied_end_date = max_datetime.date()
        st.session_state.applied_end_time = max_datetime.time().replace(
            second=0, microsecond=0
        )

    # KPI Selector
    selected_kpi = st.sidebar.selectbox(
        "Select KPI",
        options=list(KPI_OPTIONS.keys()),
        format_func=lambda x: KPI_OPTIONS[x],
        index=list(KPI_OPTIONS.keys()).index(st.session_state.applied_kpi),
        help="Choose the metric to display in all charts",
        key="input_kpi",
    )

    # Date-time range for charts
    st.sidebar.markdown("##### Date-Time Range")

    # Date-time picker using columns
    col_start, col_end = st.sidebar.columns(2)
    with col_start:
        start_date = st.date_input(
            "Start Date",
            value=st.session_state.applied_start_date,
            min_value=min_datetime.date(),
            max_value=max_datetime.date(),
            key="input_start_date",
        )
        start_time = st.time_input(
            "Start Time",
            value=st.session_state.applied_start_time,
            key="input_start_time",
        )
    with col_end:
        end_date = st.date_input(
            "End Date",
            value=st.session_state.applied_end_date,
            min_value=min_datetime.date(),
            max_value=max_datetime.date(),
            key="input_end_date",
        )
        end_time = st.time_input(
            "End Time",
            value=st.session_state.applied_end_time,
            key="input_end_time",
        )

    # Combine input date and time into datetime objects for validation
    input_start_datetime = datetime.combine(
        start_date, start_time, tzinfo=DISPLAY_TIMEZONE
    )
    input_end_datetime = datetime.combine(end_date, end_time, tzinfo=DISPLAY_TIMEZONE)

    # Clamp datetime values to available data range
    min_dt_tz = min_datetime.replace(tzinfo=DISPLAY_TIMEZONE)
    max_dt_tz = max_datetime.replace(tzinfo=DISPLAY_TIMEZONE)
    clamped_start = max(input_start_datetime, min_dt_tz)
    clamped_end = min(input_end_datetime, max_dt_tz)

    # Validation: only check if start is before end (after clamping)
    validation_error = None
    if clamped_start >= clamped_end:
        validation_error = "Start date/time must be before end date/time."

    # Show validation error if any
    if validation_error:
        st.sidebar.error(f"⚠️ {validation_error}")

    # Apply button
    apply_disabled = validation_error is not None
    if st.sidebar.button(
        "Update Charts",
        type="primary",
        disabled=apply_disabled,
        use_container_width=True,
    ):
        # Store clamped values in session state
        st.session_state.applied_kpi = selected_kpi
        st.session_state.applied_start_date = clamped_start.date()
        st.session_state.applied_start_time = clamped_start.time()
        st.session_state.applied_end_date = clamped_end.date()
        st.session_state.applied_end_time = clamped_end.time()
        st.rerun()

    # Use applied values for charts (not the input values)
    chart_start_datetime = datetime.combine(
        st.session_state.applied_start_date,
        st.session_state.applied_start_time,
        tzinfo=DISPLAY_TIMEZONE,
    )
    chart_end_datetime = datetime.combine(
        st.session_state.applied_end_date,
        st.session_state.applied_end_time,
        tzinfo=DISPLAY_TIMEZONE,
    )
    applied_kpi = st.session_state.applied_kpi

    # Filter data for charts using applied values
    chart_df = df[
        (df["timestamp"] >= chart_start_datetime)
        & (df["timestamp"] <= chart_end_datetime)
    ].copy()

    st.sidebar.caption(
        f"Showing {len(chart_df)} measurements from "
        f"{chart_start_datetime.strftime('%b %d %H:%M')} to "
        f"{chart_end_datetime.strftime('%b %d %H:%M')}"
    )

# Refresh info
st.sidebar.markdown("---")
st.sidebar.subheader("Auto-Refresh")
refresh_note = (
    f"{REFRESH_INTERVAL_SECONDS // 60} minutes"
    if REFRESH_INTERVAL_SECONDS >= 60
    else f"{REFRESH_INTERVAL_SECONDS} seconds"
)

st.sidebar.caption(
    f"The dashboard refreshes data from the linked directory automatically every"
    f" {refresh_note}. You can also manually refresh it any time."
)

if st.sidebar.button("Manual Refresh", width="stretch"):
    logger.info("Manual refresh triggered by user")
    st.cache_data.clear()
    st.rerun()

# Show data count in sidebar after loading
if not df.empty:
    from_date = df["timestamp"].min().strftime("%Y-%m-%d %H:%M")
    to_date = df["timestamp"].max().strftime("%Y-%m-%d %H:%M")

    # CSV Download button at bottom of sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("Export Data")
    import io

    # Prepare export data with clear timezone in column name
    export_df = df.copy()
    export_df = export_df.rename(columns={"timestamp": "timestamp_Europe_Berlin"})
    # Format timestamp as ISO 8601 with timezone offset for clarity
    export_df["timestamp_Europe_Berlin"] = export_df[
        "timestamp_Europe_Berlin"
    ].dt.strftime("%Y-%m-%dT%H:%M:%S%z")

    csv_buffer = io.StringIO()
    export_df.to_csv(csv_buffer, index=False)
    csv_data = csv_buffer.getvalue()

    st.sidebar.download_button(
        label="📥 Download as CSV",
        data=csv_data,
        file_name="speedtest_data.csv",
        mime="text/csv",
        help="Download data as CSV (timestamps in Europe/Berlin timezone)",
        width="stretch",
    )
    st.sidebar.caption(f"Loaded {len(df)} measurements\n({from_date} to {to_date})")

if df.empty:
    logger.warning("No speedtest data found in DATA_DIR=%s", DATA_DIR)
    st.warning(f"No speedtest data found in `{DATA_DIR}`")
    st.info(
        "Make sure speedtest files are being saved to the configured directory. "
        "Check that the `DATA_DIR` environment variable is set correctly."
    )
    st.stop()

# Get latest measurements for summary (raw data, most recent first)
latest_df = get_latest_measurements(df, RECENT_COUNT)

# Prepare chart data (always aggregated by measurement run)
aggregated_chart_df = aggregate_to_intervals(chart_df, interval_minutes=10)

# Summary section
st.markdown("---")
render_latest_summary(latest_df)

# Get metric info for applied KPI
metric_info = METRICS[applied_kpi]
metric_name = metric_info["name"]
metric_unit = metric_info["unit"]

# Section 1: Long-term Performance Overview
st.markdown("---")
st.subheader(f"📈 Long-term Performance: {metric_name}")
st.caption(
    f"Showing data from {chart_start_datetime.strftime('%b %d, %Y %H:%M')} to "
    f"{chart_end_datetime.strftime('%b %d, %Y %H:%M')}"
)

if aggregated_chart_df.empty:
    st.warning("No data available for the selected date range.")
else:
    # Render long-term section charts
    longterm_median_chart, longterm_endpoint_chart = render_longterm_section(
        df=aggregated_chart_df,
        metric_key=applied_kpi,
        metric_name=metric_name,
        metric_unit=metric_unit,
    )

    # Display in two columns
    col1, col2 = st.columns(2)
    with col1:
        st.altair_chart(longterm_median_chart, use_container_width=True)
    with col2:
        st.altair_chart(longterm_endpoint_chart, use_container_width=True)

# Section 2: 24-Hour Summary
st.markdown("---")
st.subheader(f"🕐 24-Hour Performance Pattern: {metric_name}")
st.caption(
    "Aggregated by hour of day across the selected date range to show "
    "typical performance patterns throughout the day."
)

if aggregated_chart_df.empty:
    st.warning("No data available for the selected date range.")
else:
    # Render 24h section charts
    h24_median_chart, h24_endpoint_chart, missing_hours = render_24h_section(
        df=aggregated_chart_df,
        metric_key=applied_kpi,
        metric_name=metric_name,
        metric_unit=metric_unit,
    )

    # Display in two columns
    col1, col2 = st.columns(2)
    with col1:
        st.altair_chart(h24_median_chart, use_container_width=True)
    with col2:
        st.altair_chart(h24_endpoint_chart, use_container_width=True)

    # Show warning if not all 24 hours have data
    if missing_hours > 0:
        hours_with_data = 24 - missing_hours
        st.warning(
            "⚠️ Not enough data available. "
            "Select a wider date range or wait for more"
            "data to achieve complete 24-hour coverage."
        )

st.markdown("---")
st.caption("All timestamps are displayed in Europe/Berlin timezone (CET/CEST).")
