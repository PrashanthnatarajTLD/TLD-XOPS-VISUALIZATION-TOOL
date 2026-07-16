"""PostgreSQL data access agent for telemetry caching and retrieval."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import psycopg2
    from psycopg2.extras import Json, execute_values
except Exception:  # pragma: no cover - handled at runtime if dependency is missing
    psycopg2 = None
    Json = None
    execute_values = None


@dataclass
class SQLConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str = "prefer"


class SQLAgent:
    """Agent for PostgreSQL operations used by telemetry cache and sync."""

    TABLE_NAME = "telemetry_cache"
    STATUS_TABLE_NAME = "telemetry_plate_status"

    def __init__(self, config: SQLConfig):
        if psycopg2 is None:
            raise RuntimeError(
                "psycopg2 is not installed. Add psycopg2-binary to requirements and install dependencies."
            )
        self.config = config
        self._conn = None

    @classmethod
    def from_env(cls) -> "SQLAgent":
        host = os.getenv("PGHOST")
        port = int(os.getenv("PGPORT", "5432"))
        database = os.getenv("PGDATABASE")
        user = os.getenv("PGUSER")
        password = os.getenv("PGPASSWORD")
        sslmode = os.getenv("PGSSLMODE", "prefer")

        missing = [
            name
            for name, value in {
                "PGHOST": host,
                "PGDATABASE": database,
                "PGUSER": user,
                "PGPASSWORD": password,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing PostgreSQL environment variables: {', '.join(missing)}")

        return cls(
            SQLConfig(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                sslmode=sslmode,
            )
        )

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                dbname=self.config.database,
                user=self.config.user,
                password=self.config.password,
                sslmode=self.config.sslmode,
            )
            self._conn.autocommit = False
        return self._conn

    def initialize(self) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    plate_number TEXT NOT NULL,
                    event_ts TIMESTAMPTZ NOT NULL,
                    payload JSONB NOT NULL,
                    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (plate_number, event_ts)
                );
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.STATUS_TABLE_NAME} (
                    plate_number TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    from_ts TIMESTAMPTZ NULL,
                    to_ts TIMESTAMPTZ NULL,
                    total_rows BIGINT NOT NULL DEFAULT 0,
                    last_error TEXT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()

    def mark_plate_status(
        self,
        plate_number: str,
        status: Optional[str],
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        total_rows: Optional[int] = None,
        last_error: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self.STATUS_TABLE_NAME}
                    (plate_number, status, from_ts, to_ts, total_rows, last_error, updated_at)
                VALUES
                    (%s, COALESCE(%s, 'fetching'), %s, %s, COALESCE(%s, 0), %s, NOW())
                ON CONFLICT (plate_number)
                DO UPDATE SET
                    status = COALESCE(EXCLUDED.status, {self.STATUS_TABLE_NAME}.status),
                    from_ts = CASE
                        WHEN EXCLUDED.from_ts IS NULL THEN {self.STATUS_TABLE_NAME}.from_ts
                        WHEN {self.STATUS_TABLE_NAME}.from_ts IS NULL THEN EXCLUDED.from_ts
                        ELSE LEAST({self.STATUS_TABLE_NAME}.from_ts, EXCLUDED.from_ts)
                    END,
                    to_ts = CASE
                        WHEN EXCLUDED.to_ts IS NULL THEN {self.STATUS_TABLE_NAME}.to_ts
                        WHEN {self.STATUS_TABLE_NAME}.to_ts IS NULL THEN EXCLUDED.to_ts
                        ELSE GREATEST({self.STATUS_TABLE_NAME}.to_ts, EXCLUDED.to_ts)
                    END,
                    total_rows = COALESCE(EXCLUDED.total_rows, {self.STATUS_TABLE_NAME}.total_rows),
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
                """,
                (plate_number, status, from_ts, to_ts, total_rows, last_error),
            )
        conn.commit()

    def refresh_plate_status_from_cache(self, plate_number: str, status: Optional[str] = None) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MIN(event_ts), MAX(event_ts), COUNT(*)
                FROM {self.TABLE_NAME}
                WHERE plate_number = %s
                """,
                (plate_number,),
            )
            row = cur.fetchone()

        min_ts, max_ts, total_rows = row if row else (None, None, 0)
        self.mark_plate_status(
            plate_number=plate_number,
            status=status,
            from_ts=min_ts,
            to_ts=max_ts,
            total_rows=int(total_rows or 0),
            last_error=None,
        )

    def _to_json_safe(self, value: Any) -> Any:
        """Convert pandas/python objects into JSON-serializable primitives."""
        if value is None:
            return None

        if isinstance(value, (pd.Timestamp, datetime, date, time)):
            return value.isoformat()

        if isinstance(value, pd.Timedelta):
            return value.total_seconds()

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")

        if isinstance(value, dict):
            return {str(k): self._to_json_safe(v) for k, v in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [self._to_json_safe(v) for v in value]

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        # Handle numpy scalar values if present.
        if hasattr(value, "item"):
            try:
                return self._to_json_safe(value.item())
            except Exception:
                pass

        return value

    def upsert_dataframe(self, df: pd.DataFrame, plate_number: str, timestamp_col: str = "timestamp") -> int:
        if df is None or df.empty or timestamp_col not in df.columns:
            return 0

        conn = self._get_conn()
        rows: List[Any] = []

        for _, row in df.iterrows():
            ts = pd.to_datetime(row.get(timestamp_col), errors="coerce", utc=True)
            if pd.isna(ts):
                continue

            payload = {
                str(key): self._to_json_safe(value)
                for key, value in row.to_dict().items()
            }
            rows.append((plate_number, ts.to_pydatetime(), Json(payload)))

        if not rows:
            return 0

        with conn.cursor() as cur:
            execute_values(
                cur,
                f"""
                INSERT INTO {self.TABLE_NAME} (plate_number, event_ts, payload)
                VALUES %s
                ON CONFLICT (plate_number, event_ts)
                DO UPDATE SET payload = EXCLUDED.payload
                """,
                rows,
                page_size=1000,
            )
        conn.commit()
        return len(rows)

    def fetch_by_range(self, plate_number: str, start_ts: str, end_ts: str) -> pd.DataFrame:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT event_ts, payload
                FROM {self.TABLE_NAME}
                WHERE plate_number = %s
                  AND event_ts >= %s::timestamptz
                  AND event_ts <= %s::timestamptz
                ORDER BY event_ts ASC
                """,
                (plate_number, start_ts, end_ts),
            )
            rows = cur.fetchall()

        if not rows:
            return pd.DataFrame()

        data: List[Dict[str, Any]] = []
        for event_ts, payload in rows:
            payload = payload or {}
            payload["timestamp"] = event_ts
            data.append(payload)

        df = pd.DataFrame(data)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df
