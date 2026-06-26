"""Agent: LinkFMS Combined Fetch (DTC + Raw Telemetry linked by timestamp).

Provides a single entrypoint that:
1) Fetches DTC records for a vehicle and time range.
2) Fetches raw telemetry records for the same vehicle and time range.
3) Normalizes/aligns both datasets onto the telemetry timestamp timeline
   and appends DTC fields aligned to the closest/nearest timestamp.

Important notes
- This module is designed to be called from the Streamlit UI.
- It does not import streamlit.
- It uses only pandas for merging.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd

from linkfms_api_agent import LinkFMSAPIAgent
from linkfms_dtc_agent import LinkFMSDTCAgent


@dataclass
class CombinedFetchContext:
    plate_number: str
    start_date: date
    end_date: date
    timezone_label: str  # only for display; actual TZ handling is done in caller
    tz_api_label: str = "Asia/Calcutta"


def _ensure_datetime_utc(series: pd.Series) -> pd.Series:
    """Convert series to UTC datetime.
    
    API returns data in UTC, so we just ensure it's in UTC format.
    Conversion to display timezone happens in the UI layer.
    """
    s = pd.to_datetime(series, errors="coerce")
    
    # If timezone-naive, assume it's already UTC from the API
    if s.dt.tz is None:
        s = s.dt.tz_localize("UTC")
    else:
        # If it has timezone info, convert to UTC
        s = s.dt.tz_convert("UTC")
    
    return s


def _suffix_columns(df: pd.DataFrame, suffix: str, exclude: set[str]) -> pd.DataFrame:
    df2 = df.copy()
    rename_map = {}
    for c in df2.columns:
        if c in exclude:
            continue
        rename_map[c] = f"{c}{suffix}"
    return df2.rename(columns=rename_map)


def fetch_dtc_and_telemetry_linked_by_timestamp(
    *,
    plate_number: str,
    start_date: date,
    end_date: date,
    username: str,
    password: str,
    telemetry_alignment: str = "nearest",
    telemetry_timestamp_col: str = "date",
    dtc_timestamp_col: str = "timestamp",
    dtc_max_rows_per_telemetry_tick: int = 10,
) -> Dict[str, pd.DataFrame]:
    """Fetch DTC + Raw Telemetry and link them by timestamp.

    New Logic Flow:
    1. Fetch DTC data first for the given date range
    2. Extract unique dates from DTC timestamps
    3. Fetch raw telemetry using DTC timestamp dates as filters
    4. Combine DTC and telemetry data by matching exact timestamps
    5. For each DTC record at timestamp X, find telemetry records at X and merge

    Returns a dict with:
      - 'telemetry_df': normalized telemetry dataframe (filtered by DTC dates)
      - 'dtc_df': normalized dtc dataframe
      - 'combined_df': merged DTC + telemetry records with all fields
    """

    dtc_agent = LinkFMSDTCAgent(username, password)
    tele_agent = LinkFMSAPIAgent(username, password)

    # STEP 1: Fetch DTC data first
    print(f"[Step 1] Fetching DTC data for {plate_number} from {start_date} to {end_date}...")
    dtc_df = dtc_agent.fetch(
        plate_number=plate_number,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    if dtc_df is None or dtc_df.empty:
        dtc_df = pd.DataFrame(columns=[dtc_timestamp_col])
        print("[Step 1] No DTC data found. Returning empty combined dataset.")
        return {
            "telemetry_df": pd.DataFrame(columns=[telemetry_timestamp_col]),
            "dtc_df": dtc_df,
            "combined_df": pd.DataFrame(),
        }

    # Normalize DTC timestamps to UTC (API returns in UTC)
    if dtc_timestamp_col in dtc_df.columns:
        dtc_df[dtc_timestamp_col] = _ensure_datetime_utc(dtc_df[dtc_timestamp_col])
    dtc_df = dtc_df.dropna(subset=[dtc_timestamp_col]).sort_values(dtc_timestamp_col).reset_index(drop=True)
    print(f"[Step 1] Found {len(dtc_df)} DTC records")

    # STEP 2: Extract unique dates from DTC timestamps
    print(f"[Step 2] Extracting unique dates from DTC timestamps...")
    dtc_df["date_only"] = dtc_df[dtc_timestamp_col].dt.date
    unique_dtc_dates = dtc_df["date_only"].unique()
    print(f"[Step 2] Found {len(unique_dtc_dates)} unique DTC dates: {unique_dtc_dates}")

    # STEP 3: Fetch telemetry data filtered by DTC dates
    print(f"[Step 3] Fetching telemetry data filtered by DTC dates...")
    telemetry_df = pd.DataFrame(columns=[telemetry_timestamp_col])
    
    for dtc_date in unique_dtc_dates:
        print(f"  - Fetching telemetry for {dtc_date}...")
        telemetry_data = tele_agent.fetch_by_date_and_vehicle(
            plate_number=plate_number,
            start_date=dtc_date.isoformat(),
            end_date=dtc_date.isoformat(),
            filter_diagnostic=True,  # Only fetch Diagnostic records for linked flow
        )
        if telemetry_data is not None and telemetry_data.dataframe is not None and not telemetry_data.dataframe.empty:
            temp_df = telemetry_data.dataframe
            telemetry_df = pd.concat([telemetry_df, temp_df], ignore_index=True)
    
    if telemetry_df.empty:
        print("[Step 3] No telemetry data found for DTC dates.")
        return {
            "telemetry_df": pd.DataFrame(columns=[telemetry_timestamp_col]),
            "dtc_df": dtc_df,
            "combined_df": pd.DataFrame(),
        }

    # Normalize telemetry timestamps to UTC (API returns in UTC)
    if telemetry_timestamp_col in telemetry_df.columns:
        telemetry_df[telemetry_timestamp_col] = _ensure_datetime_utc(telemetry_df[telemetry_timestamp_col])
    telemetry_df = telemetry_df.dropna(subset=[telemetry_timestamp_col]).sort_values(telemetry_timestamp_col).reset_index(drop=True)
    print(f"[Step 3] Found {len(telemetry_df)} Diagnostic telemetry records (filtered at API level)")

    # STEP 4 & 5: Combine DTC and telemetry by matching exact timestamps
    print(f"[Step 4] Combining DTC and telemetry data by exact timestamp match...")
    
    # Prepare DTC data for merge: keep relevant columns
    dtc_columns_to_keep = [dtc_timestamp_col]
    dtc_fields = [c for c in ["code", "severity", "description", "source", "name"] if c in dtc_df.columns]
    dtc_columns_to_keep.extend(dtc_fields)
    dtc_simple = dtc_df[dtc_columns_to_keep].copy()

    print(f"[Step 4a] DTC records: {len(dtc_simple)}")
    print(f"[Step 4a] Telemetry records: {len(telemetry_df)}")
    
    # Debug: Show timestamp types and sample values
    print(f"[Step 4b] DTC timestamp dtype: {dtc_simple[dtc_timestamp_col].dtype}")
    print(f"[Step 4b] Telemetry timestamp dtype: {telemetry_df[telemetry_timestamp_col].dtype}")
    print(f"[Step 4b] Sample DTC timestamps:\n{dtc_simple[dtc_timestamp_col].head(3).tolist()}")
    print(f"[Step 4b] Sample Telemetry timestamps:\n{telemetry_df[telemetry_timestamp_col].head(3).tolist()}")

    # Merge on exact timestamp match (left join)
    # Keep ALL DTC records as baseline, match telemetry if available
    # Each DTC row at timestamp X tries to join to telemetry row at timestamp X
    # Result: if 3 DTC codes at 12:00 and 1 telemetry record at 12:00 → 3 combined rows
    #         if 2 DTC codes at 11:00 and NO telemetry at 11:00 → 2 combined rows with NaN telemetry
    combined_df = pd.merge(
        dtc_simple,
        telemetry_df,
        left_on=dtc_timestamp_col,
        right_on=telemetry_timestamp_col,
        how="left",
    )

    # Rename DTC columns with dtc_ prefix
    for col in dtc_fields:
        if col in combined_df.columns:
            combined_df.rename(columns={col: f"dtc_{col}"}, inplace=True)

    # Remove duplicate timestamp column if present
    if dtc_timestamp_col != telemetry_timestamp_col and dtc_timestamp_col in combined_df.columns:
        combined_df = combined_df.drop(columns=[dtc_timestamp_col], errors="ignore")

    # Remove temporary date_only column
    if "date_only" in combined_df.columns:
        combined_df = combined_df.drop(columns=["date_only"])
    if "date_only" in dtc_df.columns:
        dtc_df = dtc_df.drop(columns=["date_only"])

    print(f"[Step 4] Created combined dataset with {len(combined_df)} matched records")
    if combined_df.empty:
        print(f"[Step 4] ⚠️ No exact timestamp matches found between DTC and telemetry!")
    else:
        print(f"[Step 4] ✓ Successfully linked DTC codes to telemetry records")

    return {"telemetry_df": telemetry_df, "dtc_df": dtc_df, "combined_df": combined_df}

