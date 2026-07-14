"""FastAPI bridge for the React frontend.

This service exposes minimal API endpoints that wrap existing LINKFMS agents.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from requests.auth import HTTPBasicAuth

BASE_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BASE_DIR / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from linkfms_api_agent import LinkFMSAPIAgent
from linkfms_dtc_agent import LinkFMSDTCAgent


class FetchRequest(BaseModel):
    plateNumber: str = Field(..., min_length=1)
    startDate: str = Field(..., min_length=1)
    endDate: str = Field(..., min_length=1)
    timezone: str = "Asia/Kolkata"
    username: Optional[str] = None
    password: Optional[str] = None
    sessionId: Optional[str] = None
    pageSize: int = 100000
    previewRows: int = 500


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    sessionId: str
    user: Dict[str, str]


class LogoutRequest(BaseModel):
    sessionId: str = Field(..., min_length=1)


class DateRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class FetchResponse(BaseModel):
    records: List[Dict[str, Any]]
    totalRows: int
    returnedRows: int
    dateRange: DateRange
    message: Optional[str] = None


SESSION_STORE: Dict[str, Dict[str, Any]] = {}
SESSION_TTL_HOURS = 8


def _is_valid_linkfms_auth(username: str, password: str) -> bool:
    api_url = "https://www.linkfms.com/fms/graphql"
    query = "query q { __typename }"
    try:
        response = requests.post(
            api_url,
            json={"operationName": "q", "query": query, "variables": {}},
            auth=HTTPBasicAuth(username, password),
            timeout=20,
        )
        if response.status_code != 200:
            return False
        data = response.json()
        if isinstance(data, dict) and data.get("errors"):
            return False
        return True
    except Exception:
        return False


def _resolve_credentials(req: FetchRequest) -> tuple[str, str]:
    if req.sessionId:
        session_data = SESSION_STORE.get(req.sessionId)
        if session_data:
            expires_at = session_data.get("expiresAt")
            if isinstance(expires_at, datetime) and expires_at > datetime.now(timezone.utc):
                return session_data.get("username", ""), session_data.get("password", "")
            SESSION_STORE.pop(req.sessionId, None)

    username = (req.username or os.getenv("LINKFMS_USERNAME") or "").strip()
    password = (req.password or os.getenv("LINKFMS_PASSWORD") or "").strip()
    return username, password


def _format_dataframe_for_json(df: pd.DataFrame) -> pd.DataFrame:
    out_df = df.copy()
    dt_cols = out_df.select_dtypes(include=["datetime64[ns, UTC]", "datetime64[ns]"]).columns
    for col in dt_cols:
        out_df[col] = pd.to_datetime(out_df[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    out_df = out_df.where(out_df.notna(), None)
    return out_df


def _convert_time_columns(df: pd.DataFrame, timezone: str) -> pd.DataFrame:
    out_df = df.copy()
    date_cols = [c for c in ["date", "dateReceived", "dateProcessed", "timestamp"] if c in out_df.columns]
    for col in date_cols:
        out_df[col] = (
            pd.to_datetime(out_df[col], errors="coerce", utc=True)
            .dt.tz_convert(timezone)
            .dt.tz_localize(None)
        )
    return out_df


app = FastAPI(title="LINKFMS Telemetry API Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://10.11.192.94:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=LoginResponse)
def auth_login(req: LoginRequest) -> LoginResponse:
    username = req.username.strip()
    password = req.password

    if not _is_valid_linkfms_auth(username, password):
        raise HTTPException(status_code=401, detail="Invalid LINKFMS credentials.")

    session_id = str(uuid4())
    SESSION_STORE[session_id] = {
        "username": username,
        "password": password,
        "expiresAt": datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
    }

    return LoginResponse(
        sessionId=session_id,
        user={
            "userid": username,
            "role": "LINKFMS User",
        },
    )


@app.post("/api/auth/logout")
def auth_logout(req: LogoutRequest) -> Dict[str, str]:
    SESSION_STORE.pop(req.sessionId, None)
    return {"status": "ok"}


@app.post("/api/telemetry/fetch", response_model=FetchResponse)
def fetch_telemetry(req: FetchRequest) -> FetchResponse:
    username, password = _resolve_credentials(req)
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Missing LINKFMS credentials. Provide username/password in request or set LINKFMS_USERNAME/LINKFMS_PASSWORD.",
        )

    agent = LinkFMSAPIAgent(username, password)
    data = agent.fetch_by_date_and_vehicle(
        plate_number=req.plateNumber,
        start_date=req.startDate,
        end_date=req.endDate,
        page_size=req.pageSize,
    )

    if data is None or data.dataframe.empty:
        return FetchResponse(
            records=[],
            totalRows=0,
            returnedRows=0,
            dateRange=DateRange(start=None, end=None),
            message="No telemetry records found.",
        )

    df = _convert_time_columns(data.dataframe, req.timezone)

    # Keep frontend payload small and fast: return preview rows while reporting full count.
    total_rows = len(df)
    preview_rows = max(1, min(req.previewRows, 2000))
    preview_df = _format_dataframe_for_json(df.head(preview_rows))

    date_col = "timestamp" if "timestamp" in df.columns else ("dateProcessed" if "dateProcessed" in df.columns else None)
    start_val = str(df[date_col].min()) if date_col else None
    end_val = str(df[date_col].max()) if date_col else None

    return FetchResponse(
        records=preview_df.to_dict(orient="records"),
        totalRows=total_rows,
        returnedRows=len(preview_df),
        dateRange=DateRange(start=start_val, end=end_val),
        message=(
            "Preview response returned for speed. "
            f"Showing {len(preview_df)} of {total_rows} rows."
        ),
    )


@app.post("/api/dtc/fetch", response_model=FetchResponse)
def fetch_dtc(req: FetchRequest) -> FetchResponse:
    username, password = _resolve_credentials(req)
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Missing LINKFMS credentials. Provide username/password in request or set LINKFMS_USERNAME/LINKFMS_PASSWORD.",
        )

    agent = LinkFMSDTCAgent(username, password)
    dtc_df = agent.fetch(
        plate_number=req.plateNumber,
        start_date=req.startDate,
        end_date=req.endDate,
        page_size=req.pageSize,
    )

    if dtc_df is None or dtc_df.empty:
        return FetchResponse(
            records=[],
            totalRows=0,
            returnedRows=0,
            dateRange=DateRange(start=None, end=None),
            message="No DTC records found.",
        )

    dtc_df = _convert_time_columns(dtc_df, req.timezone)
    total_rows = len(dtc_df)
    preview_rows = max(1, min(req.previewRows, 2000))
    preview_df = _format_dataframe_for_json(dtc_df.head(preview_rows))

    start_val = str(dtc_df["timestamp"].min()) if "timestamp" in dtc_df.columns else None
    end_val = str(dtc_df["timestamp"].max()) if "timestamp" in dtc_df.columns else None

    return FetchResponse(
        records=preview_df.to_dict(orient="records"),
        totalRows=total_rows,
        returnedRows=len(preview_df),
        dateRange=DateRange(start=start_val, end=end_val),
        message=(
            "Preview response returned for speed. "
            f"Showing {len(preview_df)} of {total_rows} rows."
        ),
    )
