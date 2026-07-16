"""Near real-time telemetry sync from LINKFMS into PostgreSQL."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from linkfms_api_agent import LinkFMSAPIAgent
from sql_agent import SQLAgent


@dataclass
class SyncState:
    running: bool = False
    last_sync_at: Optional[str] = None
    total_inserted: int = 0
    last_error: Optional[str] = None
    current_plate: Optional[str] = None
    active_plates: Optional[list[str]] = None


class DataSyncAgent:
    """Background polling agent to keep local PostgreSQL cache fresh."""

    def __init__(
        self,
        api_agent: LinkFMSAPIAgent,
        sql_agent: SQLAgent,
        poll_seconds: int = 30,
        speed_preset: str = "fastest",
        initial_lookback_days: int = 1,
        plates_provider: Optional[Callable[[], Iterable[str]]] = None,
    ):
        self.api_agent = api_agent
        self.sql_agent = sql_agent
        self.poll_seconds = max(5, int(poll_seconds))
        self.speed_preset = speed_preset
        self.initial_lookback_days = max(1, int(initial_lookback_days))
        self.plates_provider = plates_provider
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.state = SyncState()
        self._plate_watermarks: Dict[str, datetime] = {}
        self._seed_plates: List[str] = []

    def _resolve_plates(self) -> List[str]:
        if self.plates_provider is None:
            return list(self._seed_plates)

        try:
            resolved = [str(plate).strip() for plate in self.plates_provider() if str(plate).strip()]
            if resolved:
                return resolved
        except Exception as exc:
            self.state.last_error = str(exc)

        return list(self._seed_plates)

    def _fetch_incremental(self, plate: str) -> int:
        now = datetime.now(timezone.utc)
        start_dt = self._plate_watermarks.get(plate, now - timedelta(days=self.initial_lookback_days))
        start_date = start_dt.date().isoformat()
        end_date = now.date().isoformat()

        batch = self.api_agent.fetch_by_date_and_vehicle(
            plate_number=plate,
            start_date=start_date,
            end_date=end_date,
            speed_preset=self.speed_preset,
        )
        df = batch.dataframe if batch is not None else pd.DataFrame()
        if df is None or df.empty:
            self._plate_watermarks[plate] = now
            return 0

        timestamp_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
        df = df[df[timestamp_col] >= start_dt]
        if df.empty:
            self._plate_watermarks[plate] = now
            return 0

        inserted = self.sql_agent.upsert_dataframe(df, plate_number=plate, timestamp_col=timestamp_col)
        latest_ts = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True).max()
        if pd.notna(latest_ts):
            self._plate_watermarks[plate] = latest_ts.to_pydatetime()
        else:
            self._plate_watermarks[plate] = now
        return inserted

    def _worker(self) -> None:
        self.state.running = True
        self.state.last_error = None
        while not self._stop_event.is_set():
            try:
                inserted_cycle = 0
                plates = self._resolve_plates()
                self.state.active_plates = list(plates)
                for plate in plates:
                    if self._stop_event.is_set():
                        break
                    if not plate:
                        continue
                    self.state.current_plate = plate
                    inserted_cycle += self._fetch_incremental(plate)

                self.state.total_inserted += inserted_cycle
                self.state.last_sync_at = datetime.now(timezone.utc).isoformat()
                self.state.current_plate = None
            except Exception as exc:
                self.state.last_error = str(exc)

            self._stop_event.wait(self.poll_seconds)

        self.state.running = False
        self.state.current_plate = None

    def start(self, plates: Iterable[str]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._seed_plates = [str(plate).strip() for plate in plates if str(plate).strip()]
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.state.running = False
