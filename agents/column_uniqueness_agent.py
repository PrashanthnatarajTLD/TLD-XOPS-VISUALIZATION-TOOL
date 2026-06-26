"""Agent for normalizing and de-duplicating DataFrame column names.

Motivation:
- When telemetry is imported, column names can repeat semantically (e.g., "State of Charge" appearing twice)
  due to different raw sources/sheets or extraction steps.
- For display and downstream processing, we want a stable set of unique column names.

This agent keeps the *first* occurrence for each normalized name and optionally renames duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd


def _normalize_name(name: str) -> str:
    # Lowercase and collapse spaces; keep punctuation minimal.
    # Example: "EV Battery State of Charge" -> "ev_battery_state_of_charge"
    n = str(name).strip().lower()
    n = n.replace("°", "deg")
    n = n.replace("%", "pct")
    # Convert any non-alnum to underscore
    out = []
    for ch in n:
        if ch.isalnum():
            out.append(ch)
        else:
            out.append('_')
    # collapse multiple underscores
    norm = ''.join(out)
    while '__' in norm:
        norm = norm.replace('__', '_')
    return norm.strip('_')


@dataclass
class ColumnUniquenessResult:
    dataframe: pd.DataFrame
    original_to_unique: Dict[str, str]
    kept_columns: List[str]


class ColumnUniquenessAgent:
    """Ensure DataFrame column names are unique and stable."""

    def __init__(self, *, rename_duplicates: bool = True):
        # If rename_duplicates=False: drop later duplicates.
        # If True: rename later duplicates with suffix _2, _3...
        self.rename_duplicates = rename_duplicates

    def make_unique(self, telemetry_df: pd.DataFrame) -> ColumnUniquenessResult:
        df = telemetry_df.copy()
        cols = list(df.columns)

        normalized_seen: Dict[str, str] = {}  # normalized -> kept original name
        original_to_unique: Dict[str, str] = {}
        kept_columns: List[str] = []

        # Track counts for final unique names when rename_duplicates=True
        name_counts: Dict[str, int] = {}

        new_cols: List[str] = []
        for col in cols:
            norm = _normalize_name(col)
            if norm not in normalized_seen:
                normalized_seen[norm] = col
                unique_col = col
                kept_columns.append(col)
                original_to_unique[col] = unique_col
                new_cols.append(unique_col)
            else:
                # Duplicate by normalized semantic name
                if self.rename_duplicates:
                    base = normalized_seen[norm]  # use first occurrence as base
                    idx = name_counts.get(base, 1) + 1
                    name_counts[base] = idx
                    unique_col = f"{base}_{idx}"
                    original_to_unique[col] = unique_col
                    new_cols.append(unique_col)
                else:
                    # drop duplicate columns by not adding to new_cols
                    original_to_unique[col] = normalized_seen[norm]
                    # Mark as placeholder; we'll remove after loop
                    new_cols.append(None)

        df.columns = new_cols

        return ColumnUniquenessResult(
            dataframe=df,
            original_to_unique=original_to_unique,
            kept_columns=kept_columns,
        )

