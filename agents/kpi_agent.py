"""
KPI Agent for generating key performance indicators from telemetry data.
Calculates daily/weekly metrics like idle hours, motor hours, running hours, stopped hours, and odometer values.

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
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
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
    """Agent for calculating and visualizing key performance indicators."""
    
    def __init__(self):
        self.formulas = {
            'running_hours': 'Sum of time periods where speed > 0.5 km/h per day/week',
            'idle_hours': 'Sum of time periods where engineState = "Idle" per day/week',
            'stopped_hours': 'Sum of time periods where engineState = "Off" per day/week',
            'motor_hours': 'Sum of positive motorHour differences per day/week',
            'distance': 'Sum of positive odometer differences per day/week',
            'percentages': '(State Hours / Total Time in Period) × 100'
        }
    
    def calculate_metrics(self, df: pd.DataFrame, timestamp_col: str = 'dateProcessed',
                         engine_state_col: str = 'engineState',
                         motor_hour_col: str = 'motorHour',
                         speed_col: str = 'speed',
                         odometer_col: str = 'odometer') -> KPIMetrics:
        """
        Calculate KPI metrics from telemetry data using segment-based analysis.
        
        Formula: Each consecutive pair of records defines a time segment.
        The segment duration = next_timestamp - current_timestamp.
        The segment is attributed to the current record's state and day.
        Cross-midnight segments are split so each day gets its correct share.
        """
        df = df.copy()
        
        # Ensure timestamp is datetime
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
        df = df.dropna(subset=[timestamp_col])
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        
        # Add next timestamp and calculate duration
        df['next_ts'] = df[timestamp_col].shift(-1)
        df['dt_hours'] = (df['next_ts'] - df[timestamp_col]).dt.total_seconds() / 3600.0
        df = df.dropna(subset=['next_ts'])  # Drop last row (no next timestamp)
        
        # Extract date for grouping (UTC date)
        utc_ts = df[timestamp_col].dt.tz_convert('UTC') if df[timestamp_col].dt.tz else df[timestamp_col]
        df['date'] = utc_ts.dt.date
        df['week'] = utc_ts.dt.isocalendar().week
        df['year'] = utc_ts.dt.isocalendar().year
        df['year_week'] = df['year'].astype(str) + '-W' + df['week'].astype(str).str.zfill(2)
        
        # Normalize engine state
        if engine_state_col in df.columns:
            df['engine_state_norm'] = df[engine_state_col].astype(str).str.strip().str.lower()
            df['engine_state_norm'] = df['engine_state_norm'].map(
                lambda s: 'running' if s == 'running' else ('idle' if s == 'idle' else 'off')
            )
        else:
            df['engine_state_norm'] = 'off'
        
        # Prepare numeric columns
        if motor_hour_col in df.columns:
            df['motor_hour_numeric'] = pd.to_numeric(df[motor_hour_col], errors='coerce')
        else:
            df['motor_hour_numeric'] = 0
        
        if speed_col in df.columns:
            df['speed_numeric'] = pd.to_numeric(df[speed_col], errors='coerce')
        else:
            df['speed_numeric'] = 0
        
        if odometer_col in df.columns:
            df['odometer_numeric'] = pd.to_numeric(df[odometer_col], errors='coerce')
        else:
            df['odometer_numeric'] = 0
        
        # Calculate deltas
        df['motor_delta'] = df['motor_hour_numeric'].diff().clip(lower=0)
        df['odo_delta'] = df['odometer_numeric'].diff().clip(lower=0)
        
        # Handle cross-midnight segments
        daily_metrics = self._calculate_daily_metrics_advanced(df, timestamp_col)
        weekly_metrics = self._calculate_weekly_metrics_advanced(df)
        overall_stats = self._calculate_overall_stats_advanced(df, timestamp_col)
        daily_odometer = self._calculate_daily_odometer_advanced(df)
        weekly_odometer = self._calculate_weekly_odometer_advanced(df)
        
        return KPIMetrics(
            daily_metrics=daily_metrics,
            weekly_metrics=weekly_metrics,
            overall_stats=overall_stats,
            daily_odometer=daily_odometer,
            weekly_odometer=weekly_odometer,
            formulas=self.formulas
        )
    
    def _calculate_daily_metrics(self, df: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
        """Calculate daily metrics."""
        daily = df.groupby('date').agg({
            'engine_on': lambda x: (x.sum() / len(x) * 24),  # Engine on hours
            'is_running': lambda x: (x.sum() / len(x) * 24),  # Running hours (moving)
            'motor_hour_numeric': ['first', 'last'],
            'speed': 'mean'
        }).reset_index()
        
        # Flatten column names
        daily.columns = ['date', 'engine_on_hours', 'running_hours_approx', 'motor_hour_start', 'motor_hour_end', 'avg_speed']
        
        # Calculate actual motor hours delta if available
        daily['motor_hours'] = daily['motor_hour_end'] - daily['motor_hour_start']
        daily['motor_hours'] = daily['motor_hours'].fillna(0).clip(lower=0)
        
        # Idle = engine on but not moving
        daily['idle_hours_approx'] = daily['engine_on_hours'] - daily['running_hours_approx']
        daily['idle_hours_approx'] = daily['idle_hours_approx'].clip(lower=0)  # Ensure no negative values
        
        # Stopped = 24 - engine on (engine is completely off)
        daily['stopped_hours'] = 24 - daily['engine_on_hours']
        daily['stopped_hours'] = daily['stopped_hours'].clip(lower=0)
        
        # Calculate percentages
        total_hours = 24
        daily['running_pct'] = (daily['running_hours_approx'] / total_hours * 100).round(2)
        daily['idle_pct'] = (daily['idle_hours_approx'] / total_hours * 100).round(2)
        daily['stopped_pct'] = (daily['stopped_hours'] / total_hours * 100).round(2)
        
        return daily
    
    def _calculate_weekly_metrics(self, df: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
        """Calculate weekly metrics."""
        weekly = df.groupby('year_week').agg({
            'engine_on': lambda x: (x.sum() / len(x) * 24 * 7),  # Weekly hours engine on
            'is_running': lambda x: (x.sum() / len(x) * 24 * 7),  # Weekly running hours
            'motor_hour_numeric': ['first', 'last'],
            'speed': 'mean'
        }).reset_index()
        
        # Flatten column names
        weekly.columns = ['week', 'engine_on_hours', 'running_hours_approx', 'motor_hour_start', 'motor_hour_end', 'avg_speed']
        
        # Calculate actual motor hours delta
        weekly['motor_hours'] = weekly['motor_hour_end'] - weekly['motor_hour_start']
        weekly['motor_hours'] = weekly['motor_hours'].fillna(0).clip(lower=0)
        
        # Idle = engine on but not moving
        weekly['idle_hours_approx'] = weekly['engine_on_hours'] - weekly['running_hours_approx']
        weekly['idle_hours_approx'] = weekly['idle_hours_approx'].clip(lower=0)  # Ensure no negative values
        
        # Stopped = engine completely off
        total_weekly_hours = 24 * 7
        weekly['stopped_hours'] = total_weekly_hours - weekly['engine_on_hours']
        weekly['stopped_hours'] = weekly['stopped_hours'].clip(lower=0)
        
        # Calculate percentages
        weekly['running_pct'] = (weekly['running_hours_approx'] / total_weekly_hours * 100).round(2)
        weekly['idle_pct'] = (weekly['idle_hours_approx'] / total_weekly_hours * 100).round(2)
        weekly['stopped_pct'] = (weekly['stopped_hours'] / total_weekly_hours * 100).round(2)
        
        return weekly
    
    def _calculate_overall_stats(self, df: pd.DataFrame, timestamp_col: str) -> Dict[str, Any]:
        """Calculate overall statistics."""
        total_days = (df[timestamp_col].max() - df[timestamp_col].min()).days + 1
        total_hours = total_days * 24
        
        # Calculate proportions from the data
        engine_on_proportion = df['engine_on'].sum() / len(df) if len(df) > 0 else 0
        is_running_proportion = df['is_running'].sum() / len(df) if len(df) > 0 else 0
        
        # Calculate hours
        total_engine_on_hours = engine_on_proportion * total_hours
        total_running_hours = is_running_proportion * total_hours
        total_idle_hours = total_engine_on_hours - total_running_hours  # Engine on but not moving
        total_stopped_hours = total_hours - total_engine_on_hours  # Engine off
        
        total_motor_hours = df['motor_hour_numeric'].max() - df['motor_hour_numeric'].min() if len(df) > 0 else 0
        total_motor_hours = max(0, total_motor_hours)
        
        total_distance = df['odometer_numeric'].max() - df['odometer_numeric'].min() if len(df) > 0 else 0
        total_distance = max(0, total_distance)
        
        return {
            'total_days': total_days,
            'total_hours': total_hours,
            'total_running_hours': round(total_running_hours, 2),
            'total_idle_hours': round(total_idle_hours, 2),
            'total_stopped_hours': round(total_stopped_hours, 2),
            'total_motor_hours': round(total_motor_hours, 2),
            'total_distance': round(total_distance, 2),
            'running_pct': round((total_running_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'idle_pct': round((total_idle_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'stopped_pct': round((total_stopped_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'avg_speed': round(df['speed'].mean(), 2) if 'speed' in df.columns else 0,
            'start_date': df[timestamp_col].min(),
            'end_date': df[timestamp_col].max(),
        }
    
    def _calculate_daily_odometer(self, df: pd.DataFrame, timestamp_col: str = 'timestamp') -> pd.DataFrame:
        """Calculate daily odometer statistics."""
        daily_odo = df.groupby('date').agg({
            'odometer_numeric': ['min', 'max', 'mean'],
            timestamp_col: ['min', 'max']
        }).reset_index()
        
        daily_odo.columns = ['date', 'start_odometer', 'end_odometer', 'avg_odometer', 'start_time', 'end_time']
        daily_odo['distance_traveled'] = daily_odo['end_odometer'] - daily_odo['start_odometer']
        daily_odo['distance_traveled'] = daily_odo['distance_traveled'].clip(lower=0)
        
        return daily_odo
    
    def _calculate_weekly_odometer(self, df: pd.DataFrame, timestamp_col: str = 'timestamp') -> pd.DataFrame:
        """Calculate weekly odometer statistics."""
        weekly_odo = df.groupby('year_week').agg({
            'odometer_numeric': ['min', 'max', 'mean'],
            timestamp_col: ['min', 'max']
        }).reset_index()
        
        weekly_odo.columns = ['week', 'start_odometer', 'end_odometer', 'avg_odometer', 'start_time', 'end_time']
        weekly_odo['distance_traveled'] = weekly_odo['end_odometer'] - weekly_odo['start_odometer']
        weekly_odo['distance_traveled'] = weekly_odo['distance_traveled'].clip(lower=0)
        
        return weekly_odo
    
    def create_daily_hours_chart(self, daily_metrics: pd.DataFrame) -> go.Figure:
        """Create stacked bar chart for daily running/idle/stopped hours."""
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['running_hours_approx'],
            name='Running Hours',
            marker_color='#00cc96'
        ))
        fig.add_trace(go.Bar(
            x=daily_metrics['date'],
            y=daily_metrics['idle_hours_approx'],
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
            y=weekly_metrics['running_hours_approx'],
            name='Running Hours',
            marker_color='#00cc96'
        ))
        fig.add_trace(go.Bar(
            x=weekly_metrics['week'],
            y=weekly_metrics['idle_hours_approx'],
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
    
    def create_odometer_gauge(self, total_distance: float, unit: str = 'km') -> go.Figure:
        """Create a gauge chart for total distance."""
        fig = go.Figure(go.Indicator(
            mode="number+gauge",
            value=total_distance,
            title={'text': f"Total Distance ({unit})"},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [None, total_distance * 1.2]},
                'bar': {'color': '#00cc96'},
                'steps': [
                    {'range': [0, total_distance * 0.5], 'color': '#ef553b'},
                    {'range': [total_distance * 0.5, total_distance], 'color': '#ffa15a'}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': total_distance
                }
            }
        ))
        
        fig.update_layout(height=300, template='plotly_dark')
        return fig
