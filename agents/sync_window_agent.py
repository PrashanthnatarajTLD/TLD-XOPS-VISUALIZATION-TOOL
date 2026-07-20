"""Agent for resolving live-sync date windows (from/to timestamps)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple


@dataclass
class SyncWindowConfig:
    initial_lookback_days: int = 1
    fixed_from_date: Optional[date] = None
    fixed_to_date: Optional[date] = None


class SyncWindowAgent:
    """Computes sync window boundaries for background fetches."""

    def __init__(self, config: SyncWindowConfig):
        self.config = config

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        return datetime.strptime(value, "%Y-%m-%d").date()

    @classmethod
    def from_env(cls) -> "SyncWindowAgent":
        # Where to enter your sync date window:
        # Set environment variables before starting Streamlit.
        # Example range requested: 01/07/2025 to 15/07/2025
        # Use this exact env format (YYYY-MM-DD):
        #   LINKFMS_SYNC_FROM_DATE=2025-07-01
        #   LINKFMS_SYNC_TO_DATE=2025-07-15
        # If these are not set, the example range below is used for now.
        lookback_days = int(os.getenv("LINKFMS_SYNC_INITIAL_LOOKBACK_DAYS", "1"))
        fixed_from = cls._parse_date(os.getenv("LINKFMS_SYNC_FROM_DATE", "2025-07-01"))
        fixed_to = cls._parse_date(os.getenv("LINKFMS_SYNC_TO_DATE", "2025-07-15"))
        #fixed_from = cls._parse_date(os.getenv("LINKFMS_SYNC_FROM_DATE"))
        #fixed_to = cls._parse_date(os.getenv("LINKFMS_SYNC_TO_DATE"))
        return cls(
            SyncWindowConfig(
                initial_lookback_days=max(1, lookback_days),
                fixed_from_date=fixed_from,
                fixed_to_date=fixed_to,
            )
        )

    def resolve_window(
        self,
        now_utc: datetime,
        plate_watermark: Optional[datetime],
    ) -> Tuple[datetime, datetime, str, str]:
        if self.config.fixed_from_date and self.config.fixed_to_date:
            from_dt = datetime.combine(self.config.fixed_from_date, time.min, tzinfo=timezone.utc)
            to_dt = datetime.combine(self.config.fixed_to_date, time.max, tzinfo=timezone.utc)
        else:
            from_dt = plate_watermark or (now_utc - timedelta(days=self.config.initial_lookback_days))
            to_dt = now_utc

        return from_dt, to_dt, from_dt.date().isoformat(), to_dt.date().isoformat()
