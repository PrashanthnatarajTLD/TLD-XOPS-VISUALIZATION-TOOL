"""
KPI Agent for generating key performance indicators from telemetry data.
Calculates daily/weekly metrics using segment-based analysis with proper handling of cross-midnight boundaries.

Formula Reference:
- Engine State %: Based on RAW time durations between consecutive records, split at midnight
- Running Hours: Sum of time periods where speed > 0.5 km/h
- Idle Hours: Sum of time periods where engineState = 'idle'
- Stopped Hours: Sum of time periods where engineState = 'off' or 0
- Motor Hours Delta: Positive differences in motorHour column
- Distance: Positive differences in odometer column
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
from plotly.subplots import make_subplots
from pathlib import Path


@dataclass
class KPIMetrics:
    """Container for KPI calculations"""
    daily_metrics: pd.DataFrame
    weekly_metrics: pd.DataFrame
    overall_stats: Dict[str, Any]
    daily_odometer: pd.DataFrame
    weekly_odometer: pd.DataFrame
    formulas: Dict[str, str]


class KPIAgent:
    """Agent for calculating and visualizing key performance indicators using segment-based analysis."""
    
    def __init__(self):
        self.formulas = {
            'time_segment': 'Each consecutive record pair defines one segment with duration = next_timestamp - current_timestamp',
            'running_hours': 'Sum of segment durations where engineState = "Running" until the next engine state change',
            'idle_hours': 'Sum of segment durations where engineState = "Idle" until the next engine state change',
            'stopped_hours': 'Sum of segment durations where engineState = "Off" (or non-running/non-idle) until the next state change',
            'active_hours': 'Running Hours + Idle Hours',
            'motor_hours': 'Sum of positive motorHour differences across segments',
            'distance': 'Sum of positive odometer differences across segments',
            'percentages': '(Metric Hours / Total Hours in Period) × 100',
            'avg_speed': 'Weighted average speed = Sum(speed × segment_hours) / Sum(segment_hours)',
            'avg_moving_speed': 'Weighted moving average speed = Sum(speed × running_hours) / Sum(running_hours)',
            'distance_per_running_hour': 'Total Distance / Running Hours',
            'distance_per_motor_hour': 'Total Distance / Motor Hours',
            'idle_to_running_ratio': 'Idle Hours / Running Hours',
            'odometer_daily': 'Daily distance = max(odometer) - min(odometer) for each day',
            'odometer_weekly': 'Weekly distance = max(odometer) - min(odometer) for each week',
        }
    
    def calculate_metrics(self, df: pd.DataFrame, timestamp_col: str = 'dateProcessed',
                         engine_state_col: str = 'engineState',
                         motor_hour_col: str = 'motorHour',
                         speed_col: str = 'speed',
                         odometer_col: str = 'odometer') -> KPIMetrics:
        """
        Calculate KPI metrics using segment-based analysis.
        Each consecutive pair of records defines a time segment.
        """
        df = df.copy()
        
        # Ensure timestamp is datetime
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
        df = df.dropna(subset=[timestamp_col])
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        
        df_seg = self._build_segment_frame(
            df,
            timestamp_col=timestamp_col,
            engine_state_col=engine_state_col,
            motor_hour_col=motor_hour_col,
            speed_col=speed_col,
            odometer_col=odometer_col,
        )

        daily_metrics = self._calculate_daily_metrics(df_seg)
        weekly_metrics = self._calculate_weekly_metrics(df_seg)
        overall_stats = self._calculate_overall_stats(df_seg, df, timestamp_col, daily_metrics)
        daily_odometer = self._calculate_daily_odometer(df, timestamp_col, odometer_col)
        weekly_odometer = self._calculate_weekly_odometer(df, timestamp_col, odometer_col)
        
        return KPIMetrics(
            daily_metrics=daily_metrics,
            weekly_metrics=weekly_metrics,
            overall_stats=overall_stats,
            daily_odometer=daily_odometer,
            weekly_odometer=weekly_odometer,
            formulas=self.formulas
        )

    def _normalize_engine_state(self, series: pd.Series) -> pd.Series:
        normalized = series.astype(str).str.strip().str.lower()
        return normalized.map(
            lambda state: 'idle' if 'idle' in state else ('running' if 'running' in state else 'off')
        ).fillna('off')

    def _build_segment_frame(
        self,
        df: pd.DataFrame,
        *,
        timestamp_col: str,
        engine_state_col: str,
        motor_hour_col: str,
        speed_col: str,
        odometer_col: str,
    ) -> pd.DataFrame:
        df_seg = df.copy()
        df_seg['next_ts'] = df_seg[timestamp_col].shift(-1)
        df_seg['dt_hours'] = (df_seg['next_ts'] - df_seg[timestamp_col]).dt.total_seconds() / 3600.0
        df_seg = df_seg.dropna(subset=['next_ts']).copy()
        df_seg = df_seg[df_seg['dt_hours'] > 0].reset_index(drop=True)

        if engine_state_col and engine_state_col in df_seg.columns:
            df_seg['engine_state_raw'] = self._normalize_engine_state(df_seg[engine_state_col])
        else:
            df_seg['engine_state_raw'] = 'off'

        if motor_hour_col and motor_hour_col in df_seg.columns:
            df_seg['motor_hour'] = pd.to_numeric(df_seg[motor_hour_col], errors='coerce')
        else:
            df_seg['motor_hour'] = 0.0

        if speed_col and speed_col in df_seg.columns:
            df_seg['speed'] = pd.to_numeric(df_seg[speed_col], errors='coerce').fillna(0.0)
        else:
            df_seg['speed'] = 0.0

        if odometer_col and odometer_col in df_seg.columns:
            df_seg['odometer'] = pd.to_numeric(df_seg[odometer_col], errors='coerce')
        else:
            df_seg['odometer'] = 0.0

        df_seg['motor_delta'] = df_seg['motor_hour'].diff().fillna(0).clip(lower=0)
        df_seg['odo_delta'] = df_seg['odometer'].diff().fillna(0).clip(lower=0)
        if not df_seg.empty:
            df_seg.loc[df_seg.index[0], 'motor_delta'] = 0
            df_seg.loc[df_seg.index[0], 'odo_delta'] = 0

        is_running = df_seg['engine_state_raw'] == 'running'
        is_idle = df_seg['engine_state_raw'] == 'idle'
        is_off = ~(is_running | is_idle)

        df_seg['running_hours'] = np.where(is_running, df_seg['dt_hours'], 0.0)
        df_seg['idle_hours'] = np.where(is_idle, df_seg['dt_hours'], 0.0)
        df_seg['stopped_hours'] = np.where(is_off, df_seg['dt_hours'], 0.0)
        df_seg['active_hours'] = df_seg['running_hours'] + df_seg['idle_hours']
        df_seg['engine_on_hours'] = df_seg['active_hours']
        df_seg['speed_x_hours'] = df_seg['speed'].clip(lower=0).fillna(0.0) * df_seg['dt_hours']
        df_seg['moving_speed_x_hours'] = df_seg['speed'].clip(lower=0).fillna(0.0) * df_seg['running_hours']

        df_seg = self._split_segments_across_midnight(df_seg, timestamp_col)

        ts_for_group = df_seg[timestamp_col]
        if getattr(ts_for_group.dt, 'tz', None) is not None:
            ts_for_group = ts_for_group.dt.tz_localize(None)

        iso_calendar = ts_for_group.dt.isocalendar()
        df_seg['date'] = ts_for_group.dt.date
        df_seg['week'] = iso_calendar.week
        df_seg['year'] = iso_calendar.year
        df_seg['year_week'] = df_seg['year'].astype(str) + '-W' + df_seg['week'].astype(str).str.zfill(2)

        return df_seg

    def _split_segments_across_midnight(self, df_seg: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
        if df_seg.empty:
            return df_seg

        same_day_mask = df_seg[timestamp_col].dt.date == df_seg['next_ts'].dt.date
        same_day_segments = df_seg[same_day_mask].copy()
        crossing_segments = df_seg[~same_day_mask].copy()

        if crossing_segments.empty:
            return df_seg

        prorate_cols = [
            'dt_hours',
            'running_hours',
            'idle_hours',
            'stopped_hours',
            'active_hours',
            'engine_on_hours',
            'motor_delta',
            'odo_delta',
            'speed_x_hours',
            'moving_speed_x_hours',
        ]

        split_rows = []
        for _, row in crossing_segments.iterrows():
            segment_start = row[timestamp_col]
            segment_end = row['next_ts']
            total_hours = float(row['dt_hours'])

            if total_hours <= 0:
                continue

            current_start = segment_start
            while current_start.date() != segment_end.date():
                next_midnight = current_start.normalize() + pd.Timedelta(days=1)
                part_hours = (next_midnight - current_start).total_seconds() / 3600.0
                ratio = part_hours / total_hours
                split_row = row.copy()
                split_row[timestamp_col] = current_start
                split_row['next_ts'] = next_midnight
                for col in prorate_cols:
                    split_row[col] = float(row[col]) * ratio
                split_rows.append(split_row)
                current_start = next_midnight

            remaining_hours = (segment_end - current_start).total_seconds() / 3600.0
            if remaining_hours > 0:
                ratio = remaining_hours / total_hours
                split_row = row.copy()
                split_row[timestamp_col] = current_start
                split_row['next_ts'] = segment_end
                for col in prorate_cols:
                    split_row[col] = float(row[col]) * ratio
                split_rows.append(split_row)

        split_df = pd.DataFrame(split_rows)
        combined = pd.concat([same_day_segments, split_df], ignore_index=True, sort=False)
        combined = combined.sort_values(timestamp_col).reset_index(drop=True)
        return combined
    
    def _calculate_daily_metrics(self, df_seg: pd.DataFrame) -> pd.DataFrame:
        """Calculate daily metrics from segments."""
        return self._calculate_period_metrics(df_seg, 'date', 'date')
    
    def _calculate_weekly_metrics(self, df_seg: pd.DataFrame) -> pd.DataFrame:
        """Calculate weekly metrics from segments."""
        return self._calculate_period_metrics(df_seg, 'year_week', 'week')

    def _calculate_period_metrics(self, df_seg: pd.DataFrame, group_col: str, label_col: str) -> pd.DataFrame:
        grouped = (
            df_seg.groupby(group_col)
            .agg(
                running_hours=('running_hours', 'sum'),
                idle_hours=('idle_hours', 'sum'),
                stopped_hours=('stopped_hours', 'sum'),
                active_hours=('active_hours', 'sum'),
                engine_on_hours=('engine_on_hours', 'sum'),
                motor_hours=('motor_delta', 'sum'),
                distance_km=('odo_delta', 'sum'),
                speed_x_hours=('speed_x_hours', 'sum'),
                moving_speed_x_hours=('moving_speed_x_hours', 'sum'),
                max_speed=('speed', 'max'),
            )
            .reset_index()
            .rename(columns={group_col: label_col})
        )

        grouped['total_hours'] = (
            grouped[['running_hours', 'idle_hours', 'stopped_hours']].sum(axis=1)
        ).clip(lower=0.1)
        grouped['running_pct'] = (grouped['running_hours'] / grouped['total_hours'] * 100).round(2)
        grouped['idle_pct'] = (grouped['idle_hours'] / grouped['total_hours'] * 100).round(2)
        grouped['stopped_pct'] = (grouped['stopped_hours'] / grouped['total_hours'] * 100).round(2)
        grouped['active_pct'] = (grouped['active_hours'] / grouped['total_hours'] * 100).round(2)
        grouped['avg_speed'] = np.where(
            grouped['total_hours'] > 0,
            grouped['speed_x_hours'] / grouped['total_hours'],
            0,
        ).round(2)
        grouped['avg_moving_speed'] = np.where(
            grouped['running_hours'] > 0,
            grouped['moving_speed_x_hours'] / grouped['running_hours'],
            0,
        ).round(2)
        grouped['distance_per_running_hour'] = np.where(
            grouped['running_hours'] > 0,
            grouped['distance_km'] / grouped['running_hours'],
            0,
        ).round(2)
        grouped['distance_per_motor_hour'] = np.where(
            grouped['motor_hours'] > 0,
            grouped['distance_km'] / grouped['motor_hours'],
            0,
        ).round(2)
        grouped['idle_to_running_ratio'] = np.where(
            grouped['running_hours'] > 0,
            grouped['idle_hours'] / grouped['running_hours'],
            0,
        ).round(2)
        grouped['utilization_pct'] = grouped['active_pct']

        return grouped.drop(columns=['speed_x_hours', 'moving_speed_x_hours'])
    
    def _calculate_overall_stats(
        self,
        df_seg: pd.DataFrame,
        df_full: pd.DataFrame,
        timestamp_col: str,
        daily_metrics: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Calculate overall statistics."""
        total_running_hours = df_seg['running_hours'].sum()
        total_idle_hours = df_seg['idle_hours'].sum()
        total_off_hours = df_seg['stopped_hours'].sum()
        total_active_hours = df_seg['active_hours'].sum()
        
        total_hours = total_running_hours + total_idle_hours + total_off_hours
        total_hours = max(total_hours, 0.1)
        
        total_motor_hours = df_seg['motor_delta'].sum()
        total_distance = df_seg['odo_delta'].sum()
        
        start_date = df_full[timestamp_col].min()
        end_date = df_full[timestamp_col].max()
        total_days = (end_date - start_date).days + 1
        
        avg_speed = (df_seg['speed_x_hours'].sum() / total_hours) if total_hours > 0 else 0
        avg_moving_speed = (df_seg['moving_speed_x_hours'].sum() / total_running_hours) if total_running_hours > 0 else 0
        max_speed = df_seg['speed'].max() if 'speed' in df_seg.columns else 0
        distance_per_running_hour = (total_distance / total_running_hours) if total_running_hours > 0 else 0
        distance_per_motor_hour = (total_distance / total_motor_hours) if total_motor_hours > 0 else 0
        idle_to_running_ratio = (total_idle_hours / total_running_hours) if total_running_hours > 0 else 0
        days_with_data = int(daily_metrics['date'].nunique()) if not daily_metrics.empty else 0
        active_days = int((daily_metrics['active_hours'] > 0).sum()) if not daily_metrics.empty else 0
        avg_daily_distance = daily_metrics['distance_km'].mean() if not daily_metrics.empty else 0
        avg_daily_running_hours = daily_metrics['running_hours'].mean() if not daily_metrics.empty else 0
        avg_daily_motor_hours = daily_metrics['motor_hours'].mean() if not daily_metrics.empty else 0
        peak_daily_distance = daily_metrics['distance_km'].max() if not daily_metrics.empty else 0
        peak_daily_running_hours = daily_metrics['running_hours'].max() if not daily_metrics.empty else 0
        peak_daily_idle_hours = daily_metrics['idle_hours'].max() if not daily_metrics.empty else 0
        
        return {
            'total_days': total_days,
            'days_with_data': days_with_data,
            'active_days': active_days,
            'data_points': int(len(df_full)),
            'total_hours': round(total_hours, 2),
            'total_running_hours': round(total_running_hours, 2),
            'total_idle_hours': round(total_idle_hours, 2),
            'total_stopped_hours': round(total_off_hours, 2),
            'total_active_hours': round(total_active_hours, 2),
            'total_motor_hours': round(total_motor_hours, 2),
            'total_distance': round(total_distance, 2),
            'running_pct': round((total_running_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'idle_pct': round((total_idle_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'stopped_pct': round((total_off_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'active_pct': round((total_active_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'avg_speed': round(avg_speed, 2),
            'avg_moving_speed': round(avg_moving_speed, 2),
            'max_speed': round(max_speed, 2),
            'distance_per_running_hour': round(distance_per_running_hour, 2),
            'distance_per_motor_hour': round(distance_per_motor_hour, 2),
            'idle_to_running_ratio': round(idle_to_running_ratio, 2),
            'avg_daily_distance': round(avg_daily_distance, 2),
            'avg_daily_running_hours': round(avg_daily_running_hours, 2),
            'avg_daily_motor_hours': round(avg_daily_motor_hours, 2),
            'peak_daily_distance': round(peak_daily_distance, 2),
            'peak_daily_running_hours': round(peak_daily_running_hours, 2),
            'peak_daily_idle_hours': round(peak_daily_idle_hours, 2),
            'start_date': start_date,
            'end_date': end_date,
        }
    
    def _calculate_daily_odometer(self, df_full: pd.DataFrame, timestamp_col: str, odometer_col: str) -> pd.DataFrame:
        """Calculate daily odometer statistics."""
        if odometer_col not in df_full.columns:
            return pd.DataFrame(columns=['date', 'start_odometer', 'end_odometer', 'avg_odometer', 'distance_traveled'])

        odo_df = df_full[[timestamp_col, odometer_col]].copy()
        odo_df[odometer_col] = pd.to_numeric(odo_df[odometer_col], errors='coerce')
        odo_df = odo_df.dropna(subset=[timestamp_col, odometer_col])

        ts_for_group = odo_df[timestamp_col]
        if getattr(ts_for_group.dt, 'tz', None) is not None:
            ts_for_group = ts_for_group.dt.tz_localize(None)
        odo_df['date'] = ts_for_group.dt.date

        daily_odo = odo_df.groupby('date').agg({
            odometer_col: ['min', 'max', 'mean'],
        }).reset_index()
        
        daily_odo.columns = ['date', 'start_odometer', 'end_odometer', 'avg_odometer']
        daily_odo['distance_traveled'] = (daily_odo['end_odometer'] - daily_odo['start_odometer']).clip(lower=0)
        
        return daily_odo
    
    def _calculate_weekly_odometer(self, df_full: pd.DataFrame, timestamp_col: str, odometer_col: str) -> pd.DataFrame:
        """Calculate weekly odometer statistics."""
        if odometer_col not in df_full.columns:
            return pd.DataFrame(columns=['week', 'start_odometer', 'end_odometer', 'avg_odometer', 'distance_traveled'])

        odo_df = df_full[[timestamp_col, odometer_col]].copy()
        odo_df[odometer_col] = pd.to_numeric(odo_df[odometer_col], errors='coerce')
        odo_df = odo_df.dropna(subset=[timestamp_col, odometer_col])

        ts_for_group = odo_df[timestamp_col]
        if getattr(ts_for_group.dt, 'tz', None) is not None:
            ts_for_group = ts_for_group.dt.tz_localize(None)
        iso_calendar = ts_for_group.dt.isocalendar()
        odo_df['year_week'] = iso_calendar.year.astype(str) + '-W' + iso_calendar.week.astype(str).str.zfill(2)

        weekly_odo = odo_df.groupby('year_week').agg({
            odometer_col: ['min', 'max', 'mean'],
        }).reset_index()
        
        weekly_odo.columns = ['week', 'start_odometer', 'end_odometer', 'avg_odometer']
        weekly_odo['distance_traveled'] = (weekly_odo['end_odometer'] - weekly_odo['start_odometer']).clip(lower=0)
        
        return weekly_odo
    
    def create_daily_hours_chart(self, daily_metrics: pd.DataFrame) -> go.Figure:
        """Create stacked bar chart for daily running/idle/stopped hours."""
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['running_hours'],
            name='Running Hours',
            marker_color='#00cc96'
        ))
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['idle_hours'],
            name='Idle Hours',
            marker_color='#ffa15a'
        ))
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['stopped_hours'],
            name='Stopped Hours',
            marker_color='#ef553b'
        ))
        
        fig.update_layout(
            barmode='stack',
            title='Daily Running, Idle & Stopped Hours',
            xaxis_title='Date',
            yaxis_title='Hours',
            hovermode='x unified',
            template='plotly_dark',
            height=400
        )
        
        return fig
    
    def create_daily_percentage_chart(self, daily_metrics: pd.DataFrame) -> go.Figure:
        """Create stacked bar chart for daily percentages."""
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['running_pct'],
            name='Running %',
            marker_color='#00cc96'
        ))
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['idle_pct'],
            name='Idle %',
            marker_color='#ffa15a'
        ))
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['stopped_pct'],
            name='Stopped %',
            marker_color='#ef553b'
        ))
        
        fig.update_layout(
            barmode='stack',
            title='Daily Running, Idle & Stopped Percentages',
            xaxis_title='Date',
            yaxis_title='Percentage (%)',
            hovermode='x unified',
            template='plotly_dark',
            height=400
        )
        
        return fig
    
    def create_weekly_hours_chart(self, weekly_metrics: pd.DataFrame) -> go.Figure:
        """Create stacked bar chart for weekly hours."""
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['running_hours'],
            name='Running Hours',
            marker_color='#00cc96'
        ))
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['idle_hours'],
            name='Idle Hours',
            marker_color='#ffa15a'
        ))
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['stopped_hours'],
            name='Stopped Hours',
            marker_color='#ef553b'
        ))
        
        fig.update_layout(
            barmode='stack',
            title='Weekly Running, Idle & Stopped Hours',
            xaxis_title='Week',
            yaxis_title='Hours',
            hovermode='x unified',
            template='plotly_dark',
            height=400
        )
        
        return fig
    
    def create_weekly_percentage_chart(self, weekly_metrics: pd.DataFrame) -> go.Figure:
        """Create stacked bar chart for weekly percentages."""
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['running_pct'],
            name='Running %',
            marker_color='#00cc96'
        ))
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['idle_pct'],
            name='Idle %',
            marker_color='#ffa15a'
        ))
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['stopped_pct'],
            name='Stopped %',
            marker_color='#ef553b'
        ))
        
        fig.update_layout(
            barmode='stack',
            title='Weekly Running, Idle & Stopped Percentages',
            xaxis_title='Week',
            yaxis_title='Percentage (%)',
            hovermode='x unified',
            template='plotly_dark',
            height=400
        )
        
        return fig

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
        """Build TMX-style advanced KPI dataframes and summary metrics."""
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
        raw_df = pd.DataFrame({"date": work["date"]})
        raw_df["motorHour"] = pd.to_numeric(work[raw_motor_col], errors="coerce") if raw_motor_col else np.nan
        raw_df["odometer"] = pd.to_numeric(work[raw_odo_col], errors="coerce") if raw_odo_col else np.nan

        kpis = {
            "avg_charge_cycles_day": float(cycle_day["charge_cycles_day"].mean()) if not cycle_day.empty else 0.0,
            "avg_charge_cycles_week": float(cycle_week["charge_cycles_week"].mean()) if not cycle_week.empty else 0.0,
            "avg_running_pct_day": float(state_day["running_pct"].mean()) if not state_day.empty else 0.0,
            "avg_idle_pct_day": float(state_day["idle_pct"].mean()) if not state_day.empty else 0.0,
            "avg_off_pct_day": float(state_day["off_pct"].mean()) if not state_day.empty else 0.0,
        }

        return {
            "state_day": state_day,
            "state_week": state_week,
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
            y_map = cycle_detail["charger_connection"].map({"Disconnected": 0, "Connected": 1})
            fig.add_trace(
                go.Scatter(x=cycle_detail["date"], y=y_map, mode="lines+markers", line=dict(color="#a13544", width=2), marker=dict(size=6), text=cycle_detail["charger_connection"], hovertemplate="Time: %{x}<br>Connection: %{text}<extra></extra>"),
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

    def create_raw_telemetry_line_chart(self, raw_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if "motorHour" in raw_df.columns and raw_df["motorHour"].notna().any():
            fig.add_trace(go.Scatter(x=raw_df["date"], y=raw_df["motorHour"], mode="lines", name="Motor Hour", line=dict(color="#da7101", width=2)))
        if "odometer" in raw_df.columns and raw_df["odometer"].notna().any():
            fig.add_trace(go.Scatter(x=raw_df["date"], y=raw_df["odometer"], mode="lines", name="Odometer", line=dict(color="#006494", width=2)))
        fig.update_layout(template="plotly_white", height=520, title="Raw Telemetry: Motor Hour and Odometer vs Time", xaxis_title="Time", yaxis_title="Value", hovermode="x unified")
        return fig

    def create_soc_chart(self, soc_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if soc_df is not None and not soc_df.empty:
            fig.add_trace(go.Scatter(x=soc_df["date"], y=soc_df["soc"], mode="lines+markers", name="SOC", line=dict(color="#2e8b57", width=2), marker=dict(size=5)))
        fig.update_layout(template="plotly_white", height=460, title="EV Battery State of Charge Evolution", xaxis_title="Time", yaxis_title="State of Charge (%)", hovermode="x unified")
        return fig

    def create_battery_current_chart(self, cur_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if cur_df is not None and not cur_df.empty:
            fig.add_trace(go.Scatter(x=cur_df["date"], y=cur_df["battery_current"], mode="lines", name="Battery Current", line=dict(color="#c0392b", width=1.5)))
            fig.add_hline(y=0, line_dash="dash", line_color="#7a7974", line_width=1)
        fig.update_layout(template="plotly_white", height=480, title="EV Battery Current over Time", xaxis_title="Time", yaxis_title="Current (A)", hovermode="x unified")
        return fig

    def create_deadman_switch_chart(self, deadman_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if deadman_df is not None and not deadman_df.empty:
            mapped = deadman_df["deadman_state"].astype(str).str.strip().str.lower().map({"pressed": 1, "released": 0})
            valid = mapped.notna()
            fig.add_trace(
                go.Scatter(
                    x=deadman_df.loc[valid, "date"],
                    y=mapped.loc[valid],
                    mode="lines+markers",
                    line=dict(color="#6a0dad", width=2, shape="hv"),
                    marker=dict(size=5),
                    name="Deadman Switch",
                    text=deadman_df.loc[valid, "deadman_state"],
                )
            )
            fig.update_yaxes(tickmode="array", tickvals=[0, 1], ticktext=["Released", "Pressed"])
        fig.update_layout(template="plotly_white", height=460, title="Veh Deadman Switch State over Time", xaxis_title="Time", yaxis_title="Switch State", hovermode="x unified")
        return fig

    def create_cell_voltage_chart(self, cellvolt_df: pd.DataFrame) -> go.Figure:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if cellvolt_df is not None and not cellvolt_df.empty:
            fig.add_trace(go.Scatter(x=cellvolt_df["date"], y=cellvolt_df["cell_volt_max"], mode="lines", name="Max Cell Voltage", line=dict(color="#2ca02c", width=1.5)), secondary_y=False)
            fig.add_trace(go.Scatter(x=cellvolt_df["date"], y=cellvolt_df["cell_volt_min"], mode="lines", name="Min Cell Voltage", line=dict(color="#1f77b4", width=1.5)), secondary_y=False)
            fig.add_trace(go.Scatter(x=cellvolt_df["date"], y=cellvolt_df["cell_volt_delta"], mode="lines", name="Delta (Max − Min)", line=dict(color="#d62728", width=2)), secondary_y=True)
        fig.update_yaxes(title_text="Cell Voltage (mV)", secondary_y=False)
        fig.update_yaxes(title_text="Delta (mV)", secondary_y=True, showgrid=False, zeroline=False)
        fig.update_layout(template="plotly_white", height=520, title="EV Battery Cell Voltage Min / Max and Delta over Time", xaxis_title="Time", hovermode="x unified")
        return fig

    def create_battery_voltage_chart(self, batvolt_df: pd.DataFrame) -> go.Figure:
        fig = go.Figure()
        if batvolt_df is not None and not batvolt_df.empty:
            fig.add_trace(go.Scatter(x=batvolt_df["date"], y=batvolt_df["battery_voltage"], mode="lines", name="Battery Voltage", line=dict(color="#e37e00", width=2)))
            v_min = batvolt_df["battery_voltage"].min()
            v_max = batvolt_df["battery_voltage"].max()
            fig.add_hline(y=v_min, line_dash="dot", line_color="#d62728", line_width=1, annotation_text=f"Min {v_min:.1f} V")
            fig.add_hline(y=v_max, line_dash="dot", line_color="#2ca02c", line_width=1, annotation_text=f"Max {v_max:.1f} V")
        fig.update_layout(template="plotly_white", height=460, title="EV Battery Pack Voltage over Time", xaxis_title="Time", yaxis_title="Voltage (V)", hovermode="x unified")
        return fig
    
    def generate_html_report(self, output_path: str, plate_number: str, 
                            start_date: str, end_date: str, timezone: str,
                            metrics: KPIMetrics, figs: Dict[str, go.Figure]) -> str:
        """Generate an interactive HTML dashboard report."""
        stats = metrics.overall_stats
        
        # Build chart divs
        charts_html = ""
        for fig_name, fig in figs.items():
            charts_html += pio.to_html(fig, include_plotlyjs='cdn' if fig_name == list(figs.keys())[0] else False, full_html=False)
        
        # Build KPI cards
        kpi_cards = f"""
        <div class="kpi-card">
            <div class="kpi-title">🏃 Running %</div>
            <div class="kpi-value">{stats['running_pct']:.1f}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">⏸️ Idle %</div>
            <div class="kpi-value">{stats['idle_pct']:.1f}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">⛔ Stopped %</div>
            <div class="kpi-value">{stats['stopped_pct']:.1f}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">📍 Total Distance</div>
            <div class="kpi-value">{stats['total_distance']:.1f} km</div>
        </div>
        """
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Vehicle KPI Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ 
            max-width: 1400px; 
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        h1 {{ font-size: 32px; margin-bottom: 10px; }}
        .report-info {{ font-size: 14px; opacity: 0.9; }}
        main {{ padding: 40px 30px; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .kpi-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .kpi-title {{ font-size: 12px; opacity: 0.9; margin-bottom: 10px; }}
        .kpi-value {{ font-size: 28px; font-weight: bold; }}
        .charts-section {{
            display: grid;
            gap: 30px;
        }}
        .chart-container {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        footer {{
            background: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            color: #666;
            font-size: 12px;
            border-top: 1px solid #eee;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Vehicle Performance Report</h1>
            <div class="report-info">
                <p><strong>Plate Number:</strong> {plate_number}</p>
                <p><strong>Period:</strong> {start_date} to {end_date} ({timezone})</p>
            </div>
        </header>
        <main>
            <div class="kpi-grid">
                {kpi_cards}
            </div>
            <div class="charts-section">
                {charts_html}
            </div>
        </main>
        <footer>
            <p>Generated from LINKFMS Telemetry Data | {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </footer>
    </div>
</body>
</html>"""
        
        Path(output_path).write_text(html, encoding='utf-8')
        return output_path
