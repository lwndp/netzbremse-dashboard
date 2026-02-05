"""Reusable UI components for the dashboard."""

import pandas as pd
import streamlit as st


def render_header():
    """Render the dashboard header."""
    st.markdown("# Netzbremse Speedtest Dashboard")


def render_latest_summary(df: pd.DataFrame, run_size: int = 5):
    """
    Render summary cards for the latest measurement.

    Shows the average of the last complete test run (typically 5 data points).
    """
    if df.empty:
        st.warning("No data available yet.")
        return

    df_sorted = df.sort_values("timestamp")
    run_size = min(max(run_size, 1), len(df_sorted))

    # Average the last complete test run for accurate values
    latest_run = df_sorted.iloc[-run_size:]
    latest = latest_run.mean(numeric_only=True)
    latest_timestamp = latest_run["timestamp"].max()

    # Previous run for percent difference comparison
    previous_run = (
        df_sorted.iloc[-(run_size * 2) : -run_size]
        if len(df_sorted) >= run_size * 2
        else pd.DataFrame()
    )
    previous = (
        previous_run.mean(numeric_only=True) if not previous_run.empty else pd.Series()
    )

    def _percent_diff(metric_key: str) -> str | None:
        if previous.empty:
            return None
        prev_value = previous.get(metric_key)
        latest_value = latest.get(metric_key)
        if pd.isna(prev_value) or pd.isna(latest_value) or prev_value == 0:
            return None
        percent = (latest_value - prev_value) / prev_value * 100
        return f"{percent:+.1f}%"

    st.subheader("Latest Measurement")
    # Format timestamp with timezone name from the timestamp itself
    tz_name = latest_timestamp.strftime("%Z") if latest_timestamp.tzinfo else ""
    st.caption(
        f"Recorded at: {latest_timestamp.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}"
        f" (last of the set)"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Download",
            value=f"{latest.get('download', 0):.2f} Mbps",
            delta=_percent_diff("download"),
        )
    with col2:
        st.metric(
            label="Upload",
            value=f"{latest.get('upload', 0):.2f} Mbps",
            delta=_percent_diff("upload"),
        )
    with col3:
        st.metric(
            label="Latency",
            value=f"{latest.get('latency', 0):.2f} ms",
            delta=_percent_diff("latency"),
        )
    with col4:
        st.metric(
            label="Jitter",
            value=f"{latest.get('jitter', 0):.2f} ms",
            delta=_percent_diff("jitter"),
        )

    st.caption(
        "Values are averaged over the last complete test run, which typically"
        " consists of 5 individual measurements."
        " Percent differences compare against the previous test run when available."
    )

    # Show last 5 measurements in an accordion
    with st.expander("View individual measurements from this test run"):
        last_5_df = latest_run.copy()
        last_5_df["timestamp"] = last_5_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

        # Select all available columns
        all_columns = [
            "timestamp",
            "sessionID",
            "endpoint",
            "download",
            "upload",
            "latency",
            "jitter",
            "downLoadedLatency",
            "downLoadedJitter",
            "upLoadedLatency",
            "upLoadedJitter",
        ]
        available_cols = [col for col in all_columns if col in last_5_df.columns]
        display_df = last_5_df[available_cols].copy()

        column_rename = {
            "timestamp": "Time",
            "sessionID": "Session ID",
            "endpoint": "Endpoint",
            "download": "Download (Mbps)",
            "upload": "Upload (Mbps)",
            "latency": "Latency (ms)",
            "jitter": "Jitter (ms)",
            "downLoadedLatency": "Loaded Latency Down (ms)",
            "downLoadedJitter": "Loaded Jitter Down (ms)",
            "upLoadedLatency": "Loaded Latency Up (ms)",
            "upLoadedJitter": "Loaded Jitter Up (ms)",
        }
        display_df = display_df.rename(columns=column_rename)

        # Format numeric columns
        numeric_cols = [
            col
            for col in display_df.columns
            if col not in ["Time", "Session ID", "Endpoint"]
        ]
        for col in numeric_cols:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}")

        st.dataframe(display_df, width="stretch", hide_index=True)
