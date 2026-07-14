"""Agent for TMX-style advanced KPI insights and visualizations."""

import re
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class TMXKPIAgent:
    """Build TMX-style advanced KPI datasets and charts from telemetry data."""

    MAX_POINTS_DEFAULT = 3000

    def _downsample_df(self, df: pd.DataFrame, max_points: int | None = None) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        limit = max_points or self.MAX_POINTS_DEFAULT
        if len(df) <= limit:
            return df
        idx = np.linspace(0, len(df) - 1, num=limit, dtype=int)
        return df.iloc[idx].reset_index(drop=True)

    def _find_column(self, df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
        col_map = {str(c).strip().lower(): c for c in df.columns}
        for alias in aliases:
            alias_low = alias.strip().lower()
            if alias_low in col_map:
                return col_map[alias_low]
        for alias in aliases:
            alias_low = alias.strip().lower()
            for key, col in col_map.items():
                if alias_low in key:
                    return col
        return None

    def _parse_telemetry_value(self, value: Any, key: str) -> Any:
        if pd.isna(value):
            return np.nan
        text = str(value)
        patterns = [
            re.escape(key) + r"\s*:\s*([^,]+)",
            re.escape(key) + r"\s*=\s*([^,]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                out = match.group(1).strip()
                try:
                    return float(out)
                except ValueError:
                    return out
        return np.nan

    def _normalize_connection_value(self, value: Any) -> Any:
        if pd.isna(value):
            return np.nan
        txt = str(value).strip().lower()
        if txt in {"connected", "connect", "1", "true", "yes", "on"}:
            return "Connected"
        if txt in {"disconnected", "disconnect", "0", "false", "no", "off"}:
            return "Disconnected"
        if "connected" in txt and "dis" not in txt:
            return "Connected"
        if "disconnected" in txt:
            return "Disconnected"
        return str(value).strip()

    def _parse_soc_value(self, raw: Any) -> Any:
        if pd.isna(raw):
            return np.nan
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
        match = re.search(r":\s*(-?[\d.]+)\s*$", str(raw).strip())
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return np.nan
        return np.nan

    def build_advanced_kpi_bundle(self, df: pd.DataFrame, timestamp_col: str = "dateProcessed") -> Dict[str, Any]:
        work = df.copy()
        work[timestamp_col] = pd.to_datetime(work[timestamp_col], errors="coerce", utc=True)
        work = work.dropna(subset=[timestamp_col]).sort_values(timestamp_col).reset_index(drop=True)

        work["date"] = work[timestamp_col]
        work["day"] = work["date"].dt.tz_convert("UTC").dt.date
        work["week"] = work["date"].dt.tz_convert("UTC").dt.to_period("W").apply(lambda p: p.end_time.date())

        telemetry_col = self._find_column(work, ["telemetry", "telemetry_raw", "telmetry"])

        charger_col = self._find_column(work, ["EV Charger Connection", "charger_connection"])
        if charger_col is not None:
            work["charger_connection"] = work[charger_col].apply(self._normalize_connection_value)
        elif telemetry_col is not None:
            work["charger_connection"] = work[telemetry_col].apply(
                lambda x: self._normalize_connection_value(self._parse_telemetry_value(x, "EV Charger Connection"))
            )
        else:
            work["charger_connection"] = np.nan

        cycle_detail = work[["date", "day", "week", "charger_connection"]].dropna(subset=["charger_connection"]).copy()
        cycle_detail["prev_connection"] = cycle_detail["charger_connection"].shift(1)
        cycle_detail["cycle_completed"] = (
            (cycle_detail["prev_connection"] == "Connected")
            & (cycle_detail["charger_connection"] == "Disconnected")
        ).astype(int)
        cycle_day = cycle_detail.groupby("day", as_index=False).agg(charge_cycles_day=("cycle_completed", "sum"))
        cycle_week = cycle_detail.groupby("week", as_index=False).agg(charge_cycles_week=("cycle_completed", "sum"))

        state_col = self._find_column(work, ["engineState", "engine state"])
        if state_col is not None:
            state_tmp = work[["date", "day", "week", state_col]].copy().sort_values("date").reset_index(drop=True)
            state_tmp["next_date"] = state_tmp["date"].shift(-1)
            state_tmp = state_tmp.dropna(subset=["next_date"]).copy()
            state_tmp["state_bucket"] = state_tmp[state_col].astype(str).str.strip().str.lower().map(
                lambda s: "Running" if s == "running" else ("Idle" if s == "idle" else "Off")
            )

            segments = []
            for _, row in state_tmp.iterrows():
                seg_start = row["date"]
                seg_end = row["next_date"]
                state = row["state_bucket"]
                week = row["week"]
                cur = seg_start
                while cur < seg_end:
                    next_midnight = (cur + pd.Timedelta(days=1)).normalize()
                    chunk_end = min(seg_end, next_midnight)
                    duration_h = (chunk_end - cur).total_seconds() / 3600.0
                    day_utc = cur.tz_convert("UTC").date()
                    segments.append({"day": day_utc, "week": week, "state_bucket": state, "duration_h": duration_h})
                    cur = chunk_end
            segs = pd.DataFrame(segments)
        else:
            segs = pd.DataFrame(columns=["day", "week", "state_bucket", "duration_h"])

        def _pivot_pct(group_col: str) -> pd.DataFrame:
            if segs.empty:
                return pd.DataFrame(columns=[group_col, "running_pct", "idle_pct", "off_pct"])
            pivot = (
                segs.groupby([group_col, "state_bucket"], as_index=False)["duration_h"]
                .sum()
                .pivot(index=group_col, columns="state_bucket", values="duration_h")
                .fillna(0)
                .reset_index()
            )
            for col in ["Running", "Idle", "Off"]:
                if col not in pivot.columns:
                    pivot[col] = 0.0
            pivot["total"] = pivot["Running"] + pivot["Idle"] + pivot["Off"]
            pivot["running_pct"] = (pivot["Running"] / pivot["total"] * 100).round(1)
            pivot["idle_pct"] = (pivot["Idle"] / pivot["total"] * 100).round(1)
            pivot["off_pct"] = (pivot["Off"] / pivot["total"] * 100).round(1)
            return pivot

        state_day = _pivot_pct("day")
        state_week = _pivot_pct("week")

        soc_col = self._find_column(work, ["SOC", "EV Battery State of Charge"])
        soc_df = pd.DataFrame(columns=["date", "soc"])
        if soc_col is not None:
            soc_df = pd.DataFrame({
                "date": work["date"],
                "soc": work[soc_col].apply(self._parse_soc_value),
            }).dropna(subset=["date", "soc"]).sort_values("date").reset_index(drop=True)

        current_col = self._find_column(work, ["EV Battery Current", "battery current"])
        cur_df = pd.DataFrame(columns=["date", "battery_current"])
        if current_col is not None:
            cur_df = pd.DataFrame({
                "date": work["date"],
                "battery_current": pd.to_numeric(work[current_col], errors="coerce"),
            }).dropna(subset=["date", "battery_current"]).sort_values("date").reset_index(drop=True)
        elif telemetry_col is not None:
            cur_df = pd.DataFrame({
                "date": work["date"],
                "battery_current": pd.to_numeric(
                    work[telemetry_col].apply(lambda x: self._parse_telemetry_value(x, "EV Battery Current")),
                    errors="coerce",
                ),
            }).dropna(subset=["date", "battery_current"]).sort_values("date").reset_index(drop=True)

        deadman_col = self._find_column(work, ["Veh Deadman Switch", "deadman switch"])
        deadman_df = pd.DataFrame(columns=["date", "deadman_state"])
        if deadman_col is not None:
            deadman_df = pd.DataFrame({"date": work["date"], "deadman_state": work[deadman_col]})
        elif telemetry_col is not None:
            deadman_df = pd.DataFrame({
                "date": work["date"],
                "deadman_state": work[telemetry_col].apply(lambda x: self._parse_telemetry_value(x, "Veh Deadman Switch")),
            })
        deadman_df = deadman_df.dropna(subset=["date", "deadman_state"]).sort_values("date").reset_index(drop=True)

        max_cell_col = self._find_column(work, ["EV Battery Max Cell Voltage", "max cell voltage"])
        min_cell_col = self._find_column(work, ["EV Battery Min Cell Voltage", "min cell voltage"])
        cell_voltage_df = pd.DataFrame(columns=["date", "cell_volt_max", "cell_volt_min", "cell_volt_delta"])
        if max_cell_col is not None and min_cell_col is not None:
            cell_voltage_df = pd.DataFrame({
                "date": work["date"],
                "cell_volt_max": pd.to_numeric(work[max_cell_col], errors="coerce"),
                "cell_volt_min": pd.to_numeric(work[min_cell_col], errors="coerce"),
            }).dropna(subset=["date", "cell_volt_max", "cell_volt_min"]).sort_values("date").reset_index(drop=True)
        elif telemetry_col is not None:
            cell_voltage_df = pd.DataFrame({
                "date": work["date"],
                "cell_volt_max": pd.to_numeric(
                    work[telemetry_col].apply(lambda x: self._parse_telemetry_value(x, "EV Battery Max Cell Voltage")),
                    errors="coerce",
                ),
                "cell_volt_min": pd.to_numeric(
                    work[telemetry_col].apply(lambda x: self._parse_telemetry_value(x, "EV Battery Min Cell Voltage")),
                    errors="coerce",
                ),
            }).dropna(subset=["date", "cell_volt_max", "cell_volt_min"]).sort_values("date").reset_index(drop=True)
        if not cell_voltage_df.empty:
            cell_voltage_df["cell_volt_delta"] = cell_voltage_df["cell_volt_max"] - cell_voltage_df["cell_volt_min"]

        battery_voltage_col = self._find_column(work, ["EV Battery Voltage", "battery voltage"])
        battery_voltage_df = pd.DataFrame(columns=["date", "battery_voltage"])
        if battery_voltage_col is not None:
            battery_voltage_df = pd.DataFrame({
                "date": work["date"],
                "battery_voltage": pd.to_numeric(work[battery_voltage_col], errors="coerce"),
            }).dropna(subset=["date", "battery_voltage"]).sort_values("date").reset_index(drop=True)
        elif telemetry_col is not None:
            battery_voltage_df = pd.DataFrame({
                "date": work["date"],
                "battery_voltage": pd.to_numeric(
                    work[telemetry_col].apply(lambda x: self._parse_telemetry_value(x, "EV Battery Voltage")),
                    errors="coerce",
                ),
            }).dropna(subset=["date", "battery_voltage"]).sort_values("date").reset_index(drop=True)

        raw_motor_col = self._find_column(work, ["motorHour", "motor hour"])
        raw_odo_col = self._find_column(work, ["odometer", "odo"])
        raw_speed_col = self._find_column(work, ["speed", "vehicle speed"])
        raw_df = pd.DataFrame({"date": work["date"]})
        raw_df["motorHour"] = pd.to_numeric(work[raw_motor_col], errors="coerce") if raw_motor_col else np.nan
        raw_df["odometer"] = pd.to_numeric(work[raw_odo_col], errors="coerce") if raw_odo_col else np.nan
        raw_df["speed"] = pd.to_numeric(work[raw_speed_col], errors="coerce") if raw_speed_col else np.nan

        metric_df = raw_df.copy()
        metric_df["day"] = work["day"]
        metric_df["week"] = work["week"]
        metric_df["next_date"] = metric_df["date"].shift(-1)
        metric_df["dt_hours"] = (metric_df["next_date"] - metric_df["date"]).dt.total_seconds() / 3600.0
        median_dt = metric_df["dt_hours"].dropna().median() if len(metric_df) > 1 else (5 / 3600)
        fallback_dt = median_dt if pd.notna(median_dt) and median_dt > 0 else (5 / 3600)
        metric_df["dt_hours"] = metric_df["dt_hours"].fillna(fallback_dt)
        metric_df.loc[metric_df["dt_hours"] <= 0, "dt_hours"] = fallback_dt
        metric_df.loc[metric_df["dt_hours"] > 1, "dt_hours"] = fallback_dt

        metric_df["motor_delta"] = metric_df["motorHour"].diff().clip(lower=0).fillna(0)
        metric_df["odo_delta"] = metric_df["odometer"].diff().clip(lower=0).fillna(0)

        if state_col is not None:
            state_norm = work[state_col].astype(str).str.strip().str.lower()
            metric_df["idle_hours"] = np.where(state_norm == "idle", metric_df["dt_hours"], 0.0)
        else:
            metric_df["idle_hours"] = 0.0

        day_rollup = metric_df.groupby("day", as_index=False).agg(
            odometer_day_km=("odo_delta", "sum"),
            motor_hour_day=("motor_delta", "sum"),
            avg_speed_day=("speed", "mean"),
            idle_hours_day=("idle_hours", "sum"),
        )
        week_rollup = metric_df.groupby("week", as_index=False).agg(
            odometer_week_km=("odo_delta", "sum"),
            motor_hour_week=("motor_delta", "sum"),
            avg_speed_week=("speed", "mean"),
            idle_hours_week=("idle_hours", "sum"),
        )

        kpis = {
            "avg_charge_cycles_day": float(cycle_day["charge_cycles_day"].mean()) if not cycle_day.empty else 0.0,
            "avg_charge_cycles_week": float(cycle_week["charge_cycles_week"].mean()) if not cycle_week.empty else 0.0,
            "avg_running_pct_day": float(state_day["running_pct"].mean()) if not state_day.empty else 0.0,
            "avg_idle_pct_day": float(state_day["idle_pct"].mean()) if not state_day.empty else 0.0,
            "avg_off_pct_day": float(state_day["off_pct"].mean()) if not state_day.empty else 0.0,
            "avg_odometer_day_km": float(day_rollup["odometer_day_km"].mean()) if not day_rollup.empty else 0.0,
            "avg_odometer_week_km": float(week_rollup["odometer_week_km"].mean()) if not week_rollup.empty else 0.0,
            "avg_motor_hour_day": float(day_rollup["motor_hour_day"].mean()) if not day_rollup.empty else 0.0,
            "avg_motor_hour_week": float(week_rollup["motor_hour_week"].mean()) if not week_rollup.empty else 0.0,
            "avg_speed_day": float(day_rollup["avg_speed_day"].mean()) if not day_rollup.empty else 0.0,
            "avg_speed_week": float(week_rollup["avg_speed_week"].mean()) if not week_rollup.empty else 0.0,
            "avg_idle_hours_day": float(day_rollup["idle_hours_day"].mean()) if not day_rollup.empty else 0.0,
            "avg_idle_hours_week": float(week_rollup["idle_hours_week"].mean()) if not week_rollup.empty else 0.0,
        }

        return {
            "state_day": state_day,
            "state_week": state_week,
            "day_rollup": day_rollup,
            "week_rollup": week_rollup,
            "cycle_day": cycle_day,
            "cycle_week": cycle_week,
            "cycle_detail": cycle_detail,
            "soc_df": soc_df,
            "battery_current_df": cur_df,
            "deadman_df": deadman_df,
            "cell_voltage_df": cell_voltage_df,
            "battery_voltage_df": battery_voltage_df,
            "raw_df": raw_df,
            "kpis": kpis,
        }

    def create_engine_state_pct_chart(self, state_day: pd.DataFrame, state_week: pd.DataFrame) -> go.Figure:
        fig = make_subplots(rows=2, cols=1, subplot_titles=("Engine State % per Day", "Engine State % per Week"), vertical_spacing=0.18)
        colors = {"Running": "#2ca02c", "Idle": "#f0e442", "Off": "#d62728"}
        for state, col in [("Running", "running_pct"), ("Idle", "idle_pct"), ("Off", "off_pct")]:
            if not state_day.empty and col in state_day.columns:
                fig.add_trace(go.Bar(x=state_day["day"].astype(str), y=state_day[col], name=state, marker_color=colors[state]), row=1, col=1)
            if not state_week.empty and col in state_week.columns:
                fig.add_trace(go.Bar(x=state_week["week"].astype(str), y=state_week[col], name=state, marker_color=colors[state], showlegend=False), row=2, col=1)
        fig.update_layout(
            template="plotly_white",
            barmode="stack",
            height=760,
            title="Rate of Operational Status (Running / Idle / Off)",
            yaxis=dict(title="%", range=[0, 100]),
            yaxis2=dict(title="%", range=[0, 100]),
        )
        return fig

    def create_charge_cycles_chart(self, cycle_detail: pd.DataFrame, cycle_day: pd.DataFrame, cycle_week: pd.DataFrame) -> go.Figure:
        fig = make_subplots(rows=2, cols=1, subplot_titles=("EV Charger Connection over Time", "Charge Cycle Count"), vertical_spacing=0.18)
        if not cycle_detail.empty:
            detail = self._downsample_df(cycle_detail, max_points=4000)
            y_map = detail["charger_connection"].map({"Disconnected": 0, "Connected": 1})
            mode = "lines" if len(detail) > 1200 else "lines+markers"
            fig.add_trace(
                go.Scattergl(x=detail["date"], y=y_map, mode=mode, line=dict(color="#a13544", width=2), marker=dict(size=5), text=detail["charger_connection"], hovertemplate="Time: %{x}<br>Connection: %{text}<extra></extra>"),
                row=1,
                col=1,
            )
            fig.update_yaxes(tickmode="array", tickvals=[0, 1], ticktext=["Disconnected", "Connected"], row=1, col=1)
        if not cycle_day.empty:
            fig.add_trace(go.Bar(x=cycle_day["day"].astype(str), y=cycle_day["charge_cycles_day"], name="Cycles/day", marker_color="#437a22"), row=2, col=1)
        if not cycle_week.empty:
            fig.add_trace(go.Bar(x=cycle_week["week"].astype(str), y=cycle_week["charge_cycles_week"], name="Cycles/week", marker_color="#964219"), row=2, col=1)
        fig.update_layout(template="plotly_white", height=780, title="Charging Cycle Count using EV Charger Connection")
        return fig

    def create_usage_hours_bar_chart(self, day_rollup: pd.DataFrame, week_rollup: pd.DataFrame) -> go.Figure:
        fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("Usage Hours per Day", "Usage Hours per Week"),
            vertical_spacing=0.18,
        )
        if day_rollup is not None and not day_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=day_rollup["day"].astype(str),
                    y=day_rollup["motor_hour_day"],
                    marker_color="#01696f",
                    name="Usage/day",
                    hovertemplate="Day: %{x}<br>Usage hours: %{y:.3f}<extra></extra>",
                ),
                row=1,
                col=1,
            )
        if week_rollup is not None and not week_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=week_rollup["week"].astype(str),
                    y=week_rollup["motor_hour_week"],
                    marker_color="#5591c7",
                    name="Usage/week",
                    hovertemplate="Week: %{x}<br>Usage hours: %{y:.3f}<extra></extra>",
                ),
                row=2,
                col=1,
            )
        fig.update_layout(
            template="plotly_white",
            height=720,
            title="Usage Hours from MotorHour",
            showlegend=False,
        )
        return fig

    def create_odometer_bar_chart(self, day_rollup: pd.DataFrame, week_rollup: pd.DataFrame) -> go.Figure:
        fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("Odometer Distance per Day", "Odometer Distance per Week"),
            vertical_spacing=0.18,
        )
        if day_rollup is not None and not day_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=day_rollup["day"].astype(str),
                    y=day_rollup["odometer_day_km"],
                    marker_color="#006494",
                    name="Distance/day",
                    hovertemplate="Day: %{x}<br>Distance: %{y:.3f} km<extra></extra>",
                ),
                row=1,
                col=1,
            )
        if week_rollup is not None and not week_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=week_rollup["week"].astype(str),
                    y=week_rollup["odometer_week_km"],
                    marker_color="#4f9ec4",
                    name="Distance/week",
                    hovertemplate="Week: %{x}<br>Distance: %{y:.3f} km<extra></extra>",
                ),
                row=2,
                col=1,
            )
        fig.update_layout(
            template="plotly_white",
            height=720,
            title="Distance Travelled from Odometer",
            showlegend=False,
        )
        return fig

    def create_speed_bar_chart(self, day_rollup: pd.DataFrame, week_rollup: pd.DataFrame) -> go.Figure:
        fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("Average Speed per Day", "Average Speed per Week"),
            vertical_spacing=0.18,
        )
        if day_rollup is not None and not day_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=day_rollup["day"].astype(str),
                    y=day_rollup["avg_speed_day"],
                    marker_color="#7a39bb",
                    name="Speed/day",
                    hovertemplate="Day: %{x}<br>Avg speed: %{y:.3f}<extra></extra>",
                ),
                row=1,
                col=1,
            )
        if week_rollup is not None and not week_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=week_rollup["week"].astype(str),
                    y=week_rollup["avg_speed_week"],
                    marker_color="#da7101",
                    name="Speed/week",
                    hovertemplate="Week: %{x}<br>Avg speed: %{y:.3f}<extra></extra>",
                ),
                row=2,
                col=1,
            )
        fig.update_layout(
            template="plotly_white",
            height=720,
            title="Average Speed",
            showlegend=False,
        )
        return fig

    def create_idle_hours_bar_chart(self, day_rollup: pd.DataFrame, week_rollup: pd.DataFrame) -> go.Figure:
        fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("Idle Hours per Day", "Idle Hours per Week"),
            vertical_spacing=0.18,
        )
        if day_rollup is not None and not day_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=day_rollup["day"].astype(str),
                    y=day_rollup["idle_hours_day"],
                    marker_color="#d19900",
                    name="Idle/day",
                    hovertemplate="Day: %{x}<br>Idle hours: %{y:.3f}<extra></extra>",
                ),
                row=1,
                col=1,
            )
        if week_rollup is not None and not week_rollup.empty:
            fig.add_trace(
                go.Bar(
                    x=week_rollup["week"].astype(str),
                    y=week_rollup["idle_hours_week"],
                    marker_color="#f0b429",
                    name="Idle/week",
                    hovertemplate="Week: %{x}<br>Idle hours: %{y:.3f}<extra></extra>",
                ),
                row=2,
                col=1,
            )
        fig.update_layout(
            template="plotly_white",
            height=720,
            title="Idle Hours",
            showlegend=False,
        )
        return fig

    def create_raw_telemetry_line_chart(self, raw_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        raw = self._downsample_df(raw_df, max_points=4500)
        if "motorHour" in raw.columns and raw["motorHour"].notna().any():
            fig.add_trace(go.Scattergl(x=raw["date"], y=raw["motorHour"], mode="lines", name="Motor Hour", line=dict(color="#da7101", width=2)))
        if "odometer" in raw.columns and raw["odometer"].notna().any():
            fig.add_trace(go.Scattergl(x=raw["date"], y=raw["odometer"], mode="lines", name="Odometer", line=dict(color="#006494", width=2)))
        fig.update_layout(template="plotly_white", height=520, title="Raw Telemetry: Motor Hour and Odometer vs Time", xaxis_title="Time", yaxis_title="Value", hovermode="x unified")
        return fig

    def create_soc_chart(self, soc_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if soc_df is not None and not soc_df.empty:
            soc = self._downsample_df(soc_df, max_points=3500)
            mode = "lines" if len(soc) > 1200 else "lines+markers"
            fig.add_trace(go.Scattergl(x=soc["date"], y=soc["soc"], mode=mode, name="SOC", line=dict(color="#2e8b57", width=2), marker=dict(size=5)))
        fig.update_layout(template="plotly_white", height=460, title="EV Battery State of Charge Evolution", xaxis_title="Time", yaxis_title="State of Charge (%)", hovermode="x unified")
        return fig

    def create_battery_current_chart(self, cur_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if cur_df is not None and not cur_df.empty:
            cur = self._downsample_df(cur_df, max_points=4000)
            fig.add_trace(go.Scattergl(x=cur["date"], y=cur["battery_current"], mode="lines", name="Battery Current", line=dict(color="#c0392b", width=1.5)))
            fig.add_hline(y=0, line_dash="dash", line_color="#7a7974", line_width=1)
        fig.update_layout(template="plotly_white", height=480, title="EV Battery Current over Time", xaxis_title="Time", yaxis_title="Current (A)", hovermode="x unified")
        return fig

    def create_deadman_switch_chart(self, deadman_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if deadman_df is not None and not deadman_df.empty:
            deadman = self._downsample_df(deadman_df, max_points=4500)
            mapped = deadman["deadman_state"].astype(str).str.strip().str.lower().map({"pressed": 1, "released": 0})
            valid = mapped.notna()
            fig.add_trace(
                go.Scattergl(
                    x=deadman.loc[valid, "date"],
                    y=mapped.loc[valid],
                    mode="lines",
                    line=dict(color="#6a0dad", width=2, shape="hv"),
                    marker=dict(size=5),
                    name="Deadman Switch",
                    text=deadman.loc[valid, "deadman_state"],
                )
            )
            fig.update_yaxes(tickmode="array", tickvals=[0, 1], ticktext=["Released", "Pressed"])
        fig.update_layout(template="plotly_white", height=460, title="Veh Deadman Switch State over Time", xaxis_title="Time", yaxis_title="Switch State", hovermode="x unified")
        return fig

    def create_cell_voltage_chart(self, cellvolt_df: pd.DataFrame) -> go.Figure:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if cellvolt_df is not None and not cellvolt_df.empty:
            cell = self._downsample_df(cellvolt_df, max_points=3500)
            fig.add_trace(go.Scattergl(x=cell["date"], y=cell["cell_volt_max"], mode="lines", name="Max Cell Voltage", line=dict(color="#2ca02c", width=1.5)), secondary_y=False)
            fig.add_trace(go.Scattergl(x=cell["date"], y=cell["cell_volt_min"], mode="lines", name="Min Cell Voltage", line=dict(color="#1f77b4", width=1.5)), secondary_y=False)
            fig.add_trace(go.Scattergl(x=cell["date"], y=cell["cell_volt_delta"], mode="lines", name="Delta (Max − Min)", line=dict(color="#d62728", width=2)), secondary_y=True)
        fig.update_yaxes(title_text="Cell Voltage (mV)", secondary_y=False)
        fig.update_yaxes(title_text="Delta (mV)", secondary_y=True, showgrid=False, zeroline=False)
        fig.update_layout(template="plotly_white", height=520, title="EV Battery Cell Voltage Min / Max and Delta over Time", xaxis_title="Time", hovermode="x unified")
        return fig

    def create_battery_voltage_chart(self, batvolt_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if batvolt_df is not None and not batvolt_df.empty:
            bat = self._downsample_df(batvolt_df, max_points=3500)
            fig.add_trace(go.Scattergl(x=bat["date"], y=bat["battery_voltage"], mode="lines", name="Battery Voltage", line=dict(color="#e37e00", width=2)))
            v_min = bat["battery_voltage"].min()
            v_max = bat["battery_voltage"].max()
            fig.add_hline(y=v_min, line_dash="dot", line_color="#d62728", line_width=1, annotation_text=f"Min {v_min:.1f} V")
            fig.add_hline(y=v_max, line_dash="dot", line_color="#2ca02c", line_width=1, annotation_text=f"Max {v_max:.1f} V")
        fig.update_layout(template="plotly_white", height=460, title="EV Battery Pack Voltage over Time", xaxis_title="Time", yaxis_title="Voltage (V)", hovermode="x unified")
        return fig
