"""Agent for LINKFMS telemetry fetch optimization strategies."""

from dataclasses import dataclass
from threading import Lock
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth


@dataclass(frozen=True)
class FetchSpeedConfig:
    page_size_telemetry: int
    max_days_per_chunk: int
    inter_request_delay_seconds: float
    cooldown_every_n_requests: int
    cooldown_duration_seconds: float
    page_failure_rounds: int
    max_retries: int
    base_retry_delay_seconds: float


FETCH_SPEED_PRESETS: Dict[str, FetchSpeedConfig] = {
    "super-slow": FetchSpeedConfig(1000, 3, 5.0, 5, 60.0, 4, 5, 5.0),
    "slow": FetchSpeedConfig(3000, 7, 3.0, 10, 30.0, 4, 5, 5.0),
    "normal": FetchSpeedConfig(10000, 14, 2.0, 20, 20.0, 4, 5, 5.0),
    "fast": FetchSpeedConfig(10000, 30, 1.0, 50, 10.0, 4, 5, 5.0),
    "super-fast": FetchSpeedConfig(20000, 60, 0.5, 100, 5.0, 4, 5, 5.0),
    "fastest": FetchSpeedConfig(50000, 90, 0.2, 0, 0.0, 4, 5, 5.0),
}


class RequestCounter:
    """Thread-safe request counter used for global cooldown pacing."""

    def __init__(self):
        self._lock = Lock()
        self._count = 0

    def increment_and_check(self, every_n: int) -> bool:
        if every_n <= 0:
            return False
        with self._lock:
            self._count += 1
            return self._count % every_n == 0


class LinkFMSFetchOptimizationAgent:
    """Optimization helper for pagination, chunking, cooldown and retries."""

    def __init__(self):
        self.request_counter = RequestCounter()
        self.last_response: Optional[Dict[str, Any]] = None

    def resolve_speed_config(
        self,
        *,
        speed_preset: str,
        page_size: int,
        max_days_per_chunk: Optional[int],
        inter_request_delay_seconds: Optional[float],
        cooldown_every_n_requests: Optional[int],
        cooldown_duration_seconds: Optional[float],
        page_failure_rounds: Optional[int],
        max_retries: Optional[int],
        base_retry_delay_seconds: Optional[float],
    ) -> Tuple[str, FetchSpeedConfig]:
        preset_name = speed_preset if speed_preset in FETCH_SPEED_PRESETS else "normal"
        preset = FETCH_SPEED_PRESETS[preset_name]

        config = FetchSpeedConfig(
            page_size_telemetry=page_size if page_size and page_size != 1000000 else preset.page_size_telemetry,
            max_days_per_chunk=max_days_per_chunk or preset.max_days_per_chunk,
            inter_request_delay_seconds=(
                preset.inter_request_delay_seconds if inter_request_delay_seconds is None else inter_request_delay_seconds
            ),
            cooldown_every_n_requests=(
                preset.cooldown_every_n_requests if cooldown_every_n_requests is None else cooldown_every_n_requests
            ),
            cooldown_duration_seconds=(
                preset.cooldown_duration_seconds if cooldown_duration_seconds is None else cooldown_duration_seconds
            ),
            page_failure_rounds=(preset.page_failure_rounds if page_failure_rounds is None else page_failure_rounds),
            max_retries=(preset.max_retries if max_retries is None else max_retries),
            base_retry_delay_seconds=(
                preset.base_retry_delay_seconds if base_retry_delay_seconds is None else base_retry_delay_seconds
            ),
        )

        return preset_name, config

    def _robust_post(
        self,
        *,
        session: requests.Session,
        api_url: str,
        position_query: str,
        username: str,
        password: str,
        variables: Dict[str, Any],
        timeout_seconds: int,
        config: FetchSpeedConfig,
    ) -> Optional[Dict[str, Any]]:
        last_error: Optional[str] = None

        for attempt in range(1, config.max_retries + 1):
            try:
                response = session.post(
                    api_url,
                    json={
                        "operationName": "q",
                        "query": position_query,
                        "variables": variables,
                    },
                    auth=HTTPBasicAuth(username, password),
                    timeout=timeout_seconds,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("errors"):
                        last_error = f"GraphQL Error: {data['errors']}"
                    else:
                        self.last_response = data
                        if config.inter_request_delay_seconds > 0:
                            time.sleep(config.inter_request_delay_seconds)
                        if self.request_counter.increment_and_check(config.cooldown_every_n_requests):
                            print(
                                f"⏸ Cooldown after {config.cooldown_every_n_requests} requests for {config.cooldown_duration_seconds:.1f}s"
                            )
                            time.sleep(config.cooldown_duration_seconds)
                        return data
                elif response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"Retryable HTTP {response.status_code}: {response.text}"
                elif 400 <= response.status_code < 500:
                    print(f"❌ Non-retryable API Error {response.status_code}: {response.text}")
                    return None
                else:
                    last_error = f"Unexpected HTTP {response.status_code}: {response.text}"
            except requests.exceptions.Timeout:
                last_error = "Request timed out. API is taking too long to respond."
            except requests.exceptions.ConnectionError:
                last_error = "Connection error. Unable to reach LINKFMS API."
            except ValueError as exc:
                last_error = f"Invalid JSON response: {exc}"
            except Exception as exc:
                last_error = f"Unexpected request error: {exc}"

            wait_seconds = config.base_retry_delay_seconds * (2 ** (attempt - 1))
            print(f"⚠️ Attempt {attempt}/{config.max_retries} failed: {last_error}")
            if attempt < config.max_retries:
                print(f"🔁 Retrying in {wait_seconds:.1f}s...")
                time.sleep(wait_seconds)

        print(f"❌ Exhausted HTTP retries. Last error: {last_error}")
        return None

    def _fetch_page_with_failure_rounds(
        self,
        *,
        session: requests.Session,
        api_url: str,
        position_query: str,
        username: str,
        password: str,
        variables: Dict[str, Any],
        timeout_seconds: int,
        config: FetchSpeedConfig,
    ) -> Optional[Dict[str, Any]]:
        for failure_round in range(config.page_failure_rounds + 1):
            response_data = self._robust_post(
                session=session,
                api_url=api_url,
                position_query=position_query,
                username=username,
                password=password,
                variables=variables,
                timeout_seconds=timeout_seconds,
                config=config,
            )
            if response_data is not None:
                return response_data

            if failure_round < config.page_failure_rounds:
                cooldown = 60.0 * (failure_round + 1)
                print(f"⏸ Page failure round {failure_round + 1}. Cooling down for {cooldown:.0f}s before retrying same page...")
                time.sleep(cooldown)

        return None

    def fetch_paginated_by_chunks(
        self,
        *,
        session: requests.Session,
        api_url: str,
        position_query: str,
        username: str,
        password: str,
        plate_number: str,
        start_date: str,
        end_date: str,
        filter_diagnostic: bool,
        timeout_seconds: int,
        config: FetchSpeedConfig,
        build_filter: Callable[..., Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        all_results: List[Dict[str, Any]] = []

        chunk_start = start_dt
        while chunk_start <= end_dt:
            chunk_end = min(chunk_start + pd.Timedelta(days=config.max_days_per_chunk - 1), end_dt)
            chunk_start_iso = chunk_start.isoformat()
            chunk_end_iso = chunk_end.isoformat()
            print(f"📦 Chunk: {chunk_start.date()} to {chunk_end.date()}")

            start_index = 0
            chunk_total = 0
            while True:
                variables = {
                    "params": {
                        "startIndex": start_index,
                        "pageSize": config.page_size_telemetry,
                        "filter": build_filter(
                            plate_number=plate_number,
                            start_date=chunk_start_iso,
                            end_date=chunk_end_iso,
                            filter_diagnostic=filter_diagnostic,
                        ),
                        "sorts": [
                            {
                                "field": "date",
                                "direction": "DESC",
                            }
                        ],
                    }
                }

                response_data = self._fetch_page_with_failure_rounds(
                    session=session,
                    api_url=api_url,
                    position_query=position_query,
                    username=username,
                    password=password,
                    variables=variables,
                    timeout_seconds=timeout_seconds,
                    config=config,
                )
                if response_data is None:
                    print(f"❌ Abandoning chunk {chunk_start.date()} to {chunk_end.date()} after repeated failures")
                    break

                results = response_data["data"]["positionService_findByFilter"]["results"]
                total_count = response_data["data"]["positionService_findByFilter"]["totalCount"]
                page_rows = len(results)
                print(
                    f"📄 Page startIndex={start_index} fetched {page_rows} rows (chunk total so far {chunk_total + page_rows}, server total {total_count})"
                )

                if not results:
                    break

                all_results.extend(results)
                chunk_total += page_rows

                if page_rows < config.page_size_telemetry:
                    break

                start_index += config.page_size_telemetry

            chunk_start = chunk_end + pd.Timedelta(days=1)

        return all_results