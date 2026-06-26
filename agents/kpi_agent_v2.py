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
    """Agent for calculating and visualizing key performance indicators using segment-based analysis."""
    
    def __init__(self):
        self.formulas = {
            'running_hours': 'Sum of time periods where speed > 0.5 km/h per day/week',
            'idle_hours': 'Sum of time periods where engineState = "Idle" per day/week',
            'stopped_hours': 'Sum of time periods where engineState = "Off" per day/week',
            'motor_hours': 'Sum of positive motorHour differences per day/week',
            'distance': 'Sum of positive odometer differences per day/week',
            'percentages': '(State Hours / Total Time in Period) × 100',
            'time_segment': 'Each record pair defines segment: duration = next_timestamp - current_timestamp'
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
        
        # Add next timestamp and calculate duration
        df['next_ts'] = df[timestamp_col].shift(-1)
        df['dt_hours'] = (df['next_ts'] - df[timestamp_col]).dt.total_seconds() / 3600.0
        df_seg = df.dropna(subset=['next_ts']).copy()  # Drop last row
        
        # Extract date/week for grouping
        utc_ts = df_seg[timestamp_col].dt.tz_convert('UTC') if df_seg[timestamp_col].dt.tz else df_seg[timestamp_col]
        df_seg['date'] = utc_ts.dt.date
        df_seg['week'] = utc_ts.dt.isocalendar().week
        df_seg['year'] = utc_ts.dt.isocalendar().year
        df_seg['year_week'] = df_seg['year'].astype(str) + '-W' + df_seg['week'].astype(str).str.zfill(2)
        
        # Normalize engine state
        if engine_state_col in df_seg.columns:
            df_seg['engine_state'] = df_seg[engine_state_col].astype(str).str.strip().str.lower()
            df_seg['engine_state'] = df_seg['engine_state'].map(
                lambda s: 'running' if 'running' in s else ('idle' if 'idle' in s else 'off')
            ).fillna('off')
        else:
            df_seg['engine_state'] = 'off'
        
        # Prepare numeric columns
        if motor_hour_col in df_seg.columns:
            df_seg['motor_hour'] = pd.to_numeric(df_seg[motor_hour_col], errors='coerce')
        else:
            df_seg['motor_hour'] = 0
        
        if speed_col in df_seg.columns:
            df_seg['speed'] = pd.to_numeric(df_seg[speed_col], errors='coerce')
        else:
            df_seg['speed'] = 0
        
        if odometer_col in df_seg.columns:
            df_seg['odometer'] = pd.to_numeric(df_seg[odometer_col], errors='coerce')
        else:
            df_seg['odometer'] = 0
        
        # Calculate deltas (use full df for start/end values)
        df_seg['motor_delta'] = df_seg['motor_hour'].diff().fillna(0).clip(lower=0)
        df_seg.loc[df_seg.index[0], 'motor_delta'] = 0  # First row has no previous value
        
        df_seg['odo_delta'] = df_seg['odometer'].diff().fillna(0).clip(lower=0)
        df_seg.loc[df_seg.index[0], 'odo_delta'] = 0
        
        # Calculate metrics
        daily_metrics = self._calculate_daily_metrics(df_seg)
        weekly_metrics = self._calculate_weekly_metrics(df_seg)
        overall_stats = self._calculate_overall_stats(df_seg, df, timestamp_col)
        daily_odometer = self._calculate_daily_odometer(df_seg)
        weekly_odometer = self._calculate_weekly_odometer(df_seg)
        
        return KPIMetrics(
            daily_metrics=daily_metrics,
            weekly_metrics=weekly_metrics,
            overall_stats=overall_stats,
            daily_odometer=daily_odometer,
            weekly_odometer=weekly_odometer,
            formulas=self.formulas
        )
    
    def _calculate_daily_metrics(self, df_seg: pd.DataFrame) -> pd.DataFrame:
        """Calculate daily metrics from segments."""
        # Group by date and engine state, sum durations
        state_daily = df_seg.groupby(['date', 'engine_state'])['dt_hours'].sum().reset_index()
        state_pivot = state_daily.pivot_table(index='date', columns='engine_state', values='dt_hours', fill_value=0)
        
        # Ensure all states exist
        for state in ['running', 'idle', 'off']:
            if state not in state_pivot.columns:
                state_pivot[state] = 0
        
        daily = state_pivot.reset_index()
        daily.columns.name = None
        daily.columns = ['date'] + list(daily.columns[1:])
        
        # Motor hours and distance
        motor_daily = df_seg.groupby('date')['motor_delta'].sum().reset_index().rename(columns={'motor_delta': 'motor_hours'})
        odo_daily = df_seg.groupby('date')['odo_delta'].sum().reset_index().rename(columns={'odo_delta': 'distance_km'})
        
        # Merge
        result = daily.merge(motor_daily, on='date', how='left').merge(odo_daily, on='date', how='left').fillna(0)
        
        # Calculate total and percentages (before renaming)
        result['total_hours'] = result[['running', 'idle', 'off']].sum(axis=1).clip(lower=0.1)
        result['running_pct'] = (result['running'] / result['total_hours'] * 100).round(2)
        result['idle_pct'] = (result['idle'] / result['total_hours'] * 100).round(2)
        result['stopped_pct'] = (result['off'] / result['total_hours'] * 100).round(2)
        
        # Rename columns for display
        result = result.rename(columns={'running': 'running_hours', 'idle': 'idle_hours', 'off': 'stopped_hours'})
        
        return result
    
    def _calculate_weekly_metrics(self, df_seg: pd.DataFrame) -> pd.DataFrame:
        """Calculate weekly metrics from segments."""
        state_weekly = df_seg.groupby(['year_week', 'engine_state'])['dt_hours'].sum().reset_index()
        state_pivot = state_weekly.pivot_table(index='year_week', columns='engine_state', values='dt_hours', fill_value=0)
        
        # Ensure all states exist
        for state in ['running', 'idle', 'off']:
            if state not in state_pivot.columns:
                state_pivot[state] = 0
        
        weekly = state_pivot.reset_index()
        weekly.columns.name = None
        weekly.columns = ['week'] + list(weekly.columns[1:])
        
        # Motor hours and distance
        motor_weekly = df_seg.groupby('year_week')['motor_delta'].sum().reset_index().rename(columns={'motor_delta': 'motor_hours', 'year_week': 'week'})
        odo_weekly = df_seg.groupby('year_week')['odo_delta'].sum().reset_index().rename(columns={'odo_delta': 'distance_km', 'year_week': 'week'})
        
        # Merge
        result = weekly.merge(motor_weekly, on='week', how='left').merge(odo_weekly, on='week', how='left').fillna(0)
        
        # Calculate total and percentages (before renaming)
        result['total_hours'] = result[['running', 'idle', 'off']].sum(axis=1).clip(lower=0.1)
        result['running_pct'] = (result['running'] / result['total_hours'] * 100).round(2)
        result['idle_pct'] = (result['idle'] / result['total_hours'] * 100).round(2)
        result['stopped_pct'] = (result['off'] / result['total_hours'] * 100).round(2)
        
        # Rename columns
        result = result.rename(columns={'running': 'running_hours', 'idle': 'idle_hours', 'off': 'stopped_hours'})
        
        return result
    
    def _calculate_overall_stats(self, df_seg: pd.DataFrame, df_full: pd.DataFrame, timestamp_col: str) -> Dict[str, Any]:
        """Calculate overall statistics."""
        total_running_hours = df_seg[df_seg['engine_state'] == 'running']['dt_hours'].sum()
        total_idle_hours = df_seg[df_seg['engine_state'] == 'idle']['dt_hours'].sum()
        total_off_hours = df_seg[df_seg['engine_state'] == 'off']['dt_hours'].sum()
        
        total_hours = total_running_hours + total_idle_hours + total_off_hours
        total_hours = max(total_hours, 0.1)
        
        total_motor_hours = df_seg['motor_delta'].sum()
        total_distance = df_seg['odo_delta'].sum()
        
        start_date = df_full[timestamp_col].min()
        end_date = df_full[timestamp_col].max()
        total_days = (end_date - start_date).days + 1
        
        avg_speed = df_seg['speed'].mean()
        
        return {
            'total_days': total_days,
            'total_hours': round(total_hours, 2),
            'total_running_hours': round(total_running_hours, 2),
            'total_idle_hours': round(total_idle_hours, 2),
            'total_stopped_hours': round(total_off_hours, 2),
            'total_motor_hours': round(total_motor_hours, 2),
            'total_distance': round(total_distance, 2),
            'running_pct': round((total_running_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'idle_pct': round((total_idle_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'stopped_pct': round((total_off_hours / total_hours * 100) if total_hours > 0 else 0, 2),
            'avg_speed': round(avg_speed, 2),
            'start_date': start_date,
            'end_date': end_date,
        }
    
    def _calculate_daily_odometer(self, df_seg: pd.DataFrame) -> pd.DataFrame:
        """Calculate daily odometer statistics."""
        daily_odo = df_seg.groupby('date').agg({
            'odometer': ['min', 'max', 'mean'],
        }).reset_index()
        
        daily_odo.columns = ['date', 'start_odometer', 'end_odometer', 'avg_odometer']
        daily_odo['distance_traveled'] = (daily_odo['end_odometer'] - daily_odo['start_odometer']).clip(lower=0)
        
        return daily_odo
    
    def _calculate_weekly_odometer(self, df_seg: pd.DataFrame) -> pd.DataFrame:
        """Calculate weekly odometer statistics."""
        weekly_odo = df_seg.groupby('year_week').agg({
            'odometer': ['min', 'max', 'mean'],
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
