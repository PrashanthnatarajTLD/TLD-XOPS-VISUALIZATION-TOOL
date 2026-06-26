"""Shared numeric cleaning helpers.

Telemetry values often come like:
- "95" or "95.0"
- "0.02"
- sometimes with trailing unit tokens ("95%", "12 V", "35 °C", "10A")

These helpers coerce to float and strip common unit characters.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd


_UNIT_STRIP_RE = re.compile(r"[^0-9eE+\-\.]+")


def _coerce_series_to_float(s: pd.Series) -> pd.Series:
    """Convert a Series with messy numeric values into float (NaN on failure)."""
    # Ensure string processing, but preserve NaNs
    def to_float(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return float("nan")
        if isinstance(x, (int, float)):
            return float(x)
        x_str = str(x).strip()
        if x_str == "" or x_str.lower() in {"nan", "none", "null"}:
            return float("nan")

        # Strip non-numeric tokens (keep signs/dot/exponent)
        cleaned = _UNIT_STRIP_RE.sub("", x_str)
        if cleaned in {"", "+", "-"}:
            return float("nan")

        try:
            return float(cleaned)
        except ValueError:
            return float("nan")

    return s.apply(to_float)


def clean_float_like(
    series: pd.Series,
    *,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    clamp: bool = False,
) -> pd.Series:
    """Clean numeric-ish telemetry into float values.

    Args:
        series: Input pandas Series
        min_val: Optional min bound
        max_val: Optional max bound
        clamp: If True, clamp to [min_val, max_val] instead of nulling outliers.

    Returns:
        Cleaned float Series.
    """

    cleaned = _coerce_series_to_float(series)

    if min_val is not None:
        if clamp:
            cleaned = cleaned.clip(lower=min_val)
        else:
            cleaned = cleaned.where(cleaned >= min_val)

    if max_val is not None:
        if clamp:
            cleaned = cleaned.clip(upper=max_val)
        else:
            cleaned = cleaned.where(cleaned <= max_val)

    return cleaned

