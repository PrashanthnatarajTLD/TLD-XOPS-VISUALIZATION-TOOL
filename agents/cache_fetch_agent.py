"""DB-first telemetry fetch agent with LINKFMS fallback."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from linkfms_api_agent import LinkFMSAPIAgent
from sql_agent import SQLAgent


@dataclass
class CacheFetchResult:
    dataframe: pd.DataFrame
    source: str
    cached_rows: int
    fetched_rows: int


class CacheFetchAgent:
    """Read telemetry from PostgreSQL first, fallback to LINKFMS GraphQL if needed."""

    def __init__(self, sql_agent: SQLAgent, api_agent: LinkFMSAPIAgent):
        self.sql_agent = sql_agent
        self.api_agent = api_agent

    def fetch_db_first(
        self,
        plate_number: str,
        start_date: str,
        end_date: str,
        speed_preset: str = "normal",
    ) -> CacheFetchResult:
        self.sql_agent.mark_plate_status(plate_number=plate_number, status="fetching")
        try:
            cached_df = self.sql_agent.fetch_by_range(plate_number=plate_number, start_ts=start_date, end_ts=end_date)
            if cached_df is not None and not cached_df.empty:
                self.sql_agent.refresh_plate_status_from_cache(plate_number=plate_number, status="completed")
                return CacheFetchResult(
                    dataframe=cached_df,
                    source="postgres",
                    cached_rows=len(cached_df),
                    fetched_rows=0,
                )

            batch = self.api_agent.fetch_by_date_and_vehicle(
                plate_number=plate_number,
                start_date=start_date,
                end_date=end_date,
                speed_preset=speed_preset,
            )
            fetched_df = batch.dataframe if batch is not None else pd.DataFrame()

            inserted = 0
            if fetched_df is not None and not fetched_df.empty:
                inserted = self.sql_agent.upsert_dataframe(
                    fetched_df,
                    plate_number=plate_number,
                    timestamp_col="timestamp" if "timestamp" in fetched_df.columns else fetched_df.columns[0],
                )

            self.sql_agent.refresh_plate_status_from_cache(plate_number=plate_number, status="completed")
            return CacheFetchResult(
                dataframe=fetched_df,
                source="linkfms_graphql",
                cached_rows=0,
                fetched_rows=inserted,
            )
        except Exception as exc:
            self.sql_agent.mark_plate_status(
                plate_number=plate_number,
                status="not_completed",
                last_error=str(exc),
            )
            raise
