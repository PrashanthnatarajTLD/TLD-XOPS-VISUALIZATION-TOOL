"""
EV Telemetry Visualization Agent
Provides all chart methods for telemetry and DTC data.
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import List, Optional


class VisualizationAgent:

    # ─────────────────────────────────────────────────────────────────────
    # TIME-SERIES
    # ─────────────────────────────────────────────────────────────────────

    def time_series(self, df: pd.DataFrame, timestamp_col: str,
                    parameters: List[str], title: str = "Time Series") -> go.Figure:
        """Multi-parameter line chart on shared x-axis (subplots per parameter)."""
        params = [p for p in parameters if p in df.columns]
        if not params:
            return self._empty("No matching columns found.")

        fig = make_subplots(
            rows=len(params), cols=1,
            shared_xaxes=True,
            subplot_titles=params,
            vertical_spacing=0.05
        )
        for i, param in enumerate(params, 1):
            fig.add_trace(
                go.Scatter(x=df[timestamp_col], y=df[param], mode='lines', name=param),
                row=i, col=1
            )
        fig.update_layout(
            title=title, height=300 * len(params),
            template="plotly_dark", showlegend=True, hovermode='x unified'
        )
        return fig

    def soc_current_dual(self, df: pd.DataFrame, timestamp_col: str,
                         soc_col: str = "EV Battery State of Charge (%)",
                         current_col: str = "EV Battery Current (A)") -> go.Figure:
        """SOC and Battery Current on dual y-axis."""
        if soc_col not in df.columns and current_col not in df.columns:
            return self._empty("SOC and Current columns not found.")

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        if soc_col in df.columns:
            fig.add_trace(go.Scatter(
                x=df[timestamp_col], y=df[soc_col],
                name="SOC (%)", line=dict(color="#00cc96")
            ), secondary_y=False)

        if current_col in df.columns:
            fig.add_trace(go.Scatter(
                x=df[timestamp_col], y=df[current_col],
                name="Battery Current (A)", line=dict(color="#ef553b")
            ), secondary_y=True)

        fig.update_layout(
            title="SOC vs Battery Current",
            template="plotly_dark", hovermode='x unified', height=450
        )
        fig.update_yaxes(title_text="SOC (%)", secondary_y=False)
        fig.update_yaxes(title_text="Current (A)", secondary_y=True)
        return fig

    def temperature_chart(self, df: pd.DataFrame, timestamp_col: str) -> go.Figure:
        """All temperature parameters on one chart."""
        temp_cols = [c for c in df.columns if 'temp' in c.lower() or 'temperature' in c.lower()]
        if not temp_cols:
            return self._empty("No temperature columns found.")

        fig = go.Figure()
        for col in temp_cols:
            fig.add_trace(go.Scatter(x=df[timestamp_col], y=df[col], mode='lines', name=col))

        fig.update_layout(
            title="Temperature Parameters Over Time",
            xaxis_title="Time", yaxis_title="Temperature (°C)",
            template="plotly_dark", hovermode='x unified', height=450
        )
        return fig

    def speed_chart(self, df: pd.DataFrame, timestamp_col: str,
                    speed_col: str = "Speed (km/h)") -> go.Figure:
        """Speed over time as area chart."""
        if speed_col not in df.columns:
            return self._empty(f"Column '{speed_col}' not found.")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df[timestamp_col], y=df[speed_col],
            mode='lines', fill='tozeroy', name='Speed',
            line=dict(color="#636efa")
        ))
        fig.update_layout(
            title="Vehicle Speed Over Time",
            xaxis_title="Time", yaxis_title="Speed (km/h)",
            template="plotly_dark", hovermode='x unified', height=400
        )
        return fig

    # ─────────────────────────────────────────────────────────────────────
    # SOC DAILY ANALYSIS
    # ─────────────────────────────────────────────────────────────────────

    def soc_daily_bar(self, df: pd.DataFrame, timestamp_col: str,
                      soc_col: str = "EV Battery State of Charge (%)") -> go.Figure:
        """SOC min/max per day bar chart."""
        if soc_col not in df.columns:
            return self._empty(f"Column '{soc_col}' not found.")

        df = df.copy()
        df['_date'] = pd.to_datetime(df[timestamp_col]).dt.date
        daily = df.groupby('_date')[soc_col].agg(['min', 'max']).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily['_date'], y=daily['max'], name='Max SOC', marker_color='#00cc96'))
        fig.add_trace(go.Bar(x=daily['_date'], y=daily['min'], name='Min SOC', marker_color='#ef553b'))
        fig.update_layout(
            title="Daily SOC Min/Max",
            xaxis_title="Date", yaxis_title="SOC (%)",
            barmode='group', template="plotly_dark", height=400
        )
        return fig

    # ─────────────────────────────────────────────────────────────────────
    # CHARGING SESSION HIGHLIGHT
    # ─────────────────────────────────────────────────────────────────────

    def charging_sessions(self, df: pd.DataFrame, timestamp_col: str,
                          soc_col: str = "EV Battery State of Charge (%)",
                          charger_col: str = "EV Charger State") -> go.Figure:
        """SOC line with charging sessions highlighted."""
        if soc_col not in df.columns:
            return self._empty(f"Column '{soc_col}' not found.")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df[timestamp_col], y=df[soc_col],
            mode='lines', name='SOC (%)', line=dict(color='#00cc96')
        ))

        if charger_col in df.columns:
            charging = df[df[charger_col].astype(str).str.contains('charg', case=False, na=False)]
            if not charging.empty:
                fig.add_trace(go.Scatter(
                    x=charging[timestamp_col], y=charging[soc_col],
                    mode='markers', name='Charging',
                    marker=dict(color='yellow', size=4)
                ))

        fig.update_layout(
            title="SOC with Charging Sessions",
            xaxis_title="Time", yaxis_title="SOC (%)",
            template="plotly_dark", hovermode='x unified', height=450
        )
        return fig

    # ─────────────────────────────────────────────────────────────────────
    # CORRELATION
    # ─────────────────────────────────────────────────────────────────────

    def scatter_correlation(self, df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
        """Scatter plot for two numeric parameters."""
        if x_col not in df.columns or y_col not in df.columns:
            return self._empty(f"Columns '{x_col}' or '{y_col}' not found.")

        fig = px.scatter(
            df, x=x_col, y=y_col, opacity=0.5,
            title=f"{x_col} vs {y_col}",
            template="plotly_dark"
        )
        fig.update_layout(height=450)
        return fig

    def heatmap_correlation(self, df: pd.DataFrame) -> go.Figure:
        """Correlation heatmap of all numeric columns."""
        numeric_df = df.select_dtypes(include='number')
        if numeric_df.shape[1] < 2:
            return self._empty("Need at least 2 numeric columns for heatmap.")

        corr = numeric_df.corr()
        fig = go.Figure(go.Heatmap(
            z=corr.values,
            x=corr.columns.tolist(),
            y=corr.columns.tolist(),
            colorscale='RdBu', zmid=0,
            text=corr.round(2).values,
            texttemplate="%{text}"
        ))
        fig.update_layout(
            title="Parameter Correlation Heatmap",
            template="plotly_dark",
            height=max(400, 80 * len(corr.columns))
        )
        return fig

    def box_plots(self, df: pd.DataFrame, parameters: List[str]) -> go.Figure:
        """Box plots for selected numeric parameters."""
        params = [p for p in parameters if p in df.columns and pd.api.types.is_numeric_dtype(df[p])]
        if not params:
            return self._empty("No numeric columns found.")

        fig = go.Figure()
        for p in params:
            fig.add_trace(go.Box(y=df[p], name=p, boxmean=True))

        fig.update_layout(
            title="Parameter Distribution (Box Plots)",
            template="plotly_dark", height=450
        )
        return fig

    def histogram(self, df: pd.DataFrame, parameter: str, bins: int = 30) -> go.Figure:
        """Histogram for a single parameter."""
        if parameter not in df.columns:
            return self._empty(f"Column '{parameter}' not found.")

        fig = px.histogram(df, x=parameter, nbins=bins, title=f"{parameter} Distribution",
                           template="plotly_dark")
        fig.update_layout(height=400)
        return fig

    # ─────────────────────────────────────────────────────────────────────
    # DTC CHARTS
    # ─────────────────────────────────────────────────────────────────────

    def dtc_frequency_bar(self, dtc_df: pd.DataFrame,
                          code_col: str = 'code',
                          desc_col: str = 'description') -> go.Figure:
        """Horizontal bar chart of DTC code frequency."""
        if code_col not in dtc_df.columns:
            return self._empty("DTC code column not found.")

        freq = dtc_df[code_col].value_counts().reset_index()
        freq.columns = ['code', 'count']

        if desc_col in dtc_df.columns:
            desc_map = dtc_df.drop_duplicates(code_col).set_index(code_col)[desc_col]
            freq['label'] = freq['code'].astype(str) + ' — ' + freq['code'].map(desc_map).fillna('').astype(str)
        else:
            freq['label'] = freq['code'].astype(str)

        fig = px.bar(
            freq, x='count', y='label', orientation='h',
            title="DTC Frequency", template="plotly_dark",
            color='count', color_continuous_scale='reds'
        )
        fig.update_layout(height=max(400, 40 * len(freq)), yaxis={'categoryorder': 'total ascending'})
        return fig

    def dtc_timeline(self, dtc_df: pd.DataFrame,
                     timestamp_col: str = 'timestamp',
                     code_col: str = 'code',
                     severity_col: str = 'severity') -> go.Figure:
        """Scatter timeline of DTC events colored by severity."""
        if timestamp_col not in dtc_df.columns or code_col not in dtc_df.columns:
            return self._empty("Required DTC columns not found.")

        color_col = severity_col if severity_col in dtc_df.columns else code_col

        fig = px.scatter(
            dtc_df, x=timestamp_col, y=code_col,
            color=color_col,
            hover_data=[c for c in ['description', 'categoryDescription', 'source'] if c in dtc_df.columns],
            title="DTC Event Timeline",
            template="plotly_dark"
        )
        fig.update_layout(height=450, hovermode='closest')
        return fig

    def dtc_severity_pie(self, dtc_df: pd.DataFrame,
                         severity_col: str = 'severity') -> go.Figure:
        """Pie chart of DTC records by severity."""
        if severity_col not in dtc_df.columns:
            return self._empty("Severity column not found.")

        counts = dtc_df[severity_col].value_counts().reset_index()
        counts.columns = ['severity', 'count']

        fig = px.pie(counts, names='severity', values='count',
                     title="DTC by Severity", template="plotly_dark")
        fig.update_layout(height=400)
        return fig

    def dtc_unique_codes_over_time(self, dtc_df: pd.DataFrame,
                                   timestamp_col: str = 'timestamp',
                                   code_col: str = 'code') -> go.Figure:
        """Line chart showing the number of unique DTC codes over time."""
        if timestamp_col not in dtc_df.columns or code_col not in dtc_df.columns:
            return self._empty("Timestamp or code column not found.")

        df = dtc_df.copy()
        df['date'] = pd.to_datetime(df[timestamp_col]).dt.to_period('D')
        daily_unique_dtcs = df.groupby('date')[code_col].nunique().reset_index()
        daily_unique_dtcs['date'] = daily_unique_dtcs['date'].dt.to_timestamp()

        fig = px.line(daily_unique_dtcs, x='date', y=code_col,
                      title="Unique DTC Codes Over Time", template="plotly_dark")
        fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Number of Unique DTC Codes")
        return fig

    def dtc_daily_count(self, dtc_df: pd.DataFrame,
                        timestamp_col: str = 'timestamp') -> go.Figure:
        """Bar chart of DTC count per day."""
        if timestamp_col not in dtc_df.columns:
            return self._empty("Timestamp column not found.")

        df = dtc_df.copy()
        df['_date'] = pd.to_datetime(df[timestamp_col]).dt.date
        daily = df.groupby('_date').size().reset_index(name='count')

        fig = px.bar(daily, x='_date', y='count',
                     title="Daily DTC Count", template="plotly_dark")
        fig.update_layout(height=400, xaxis_title="Date", yaxis_title="DTC Count")
        return fig

    def custom_chart(self, df: pd.DataFrame, x_col: str, y_cols: List[str],
                     chart_type: str = 'line', colors: Optional[List[str]] = None,
                     title: str = "Custom Chart") -> go.Figure:
        """
        Fully customizable chart.
        chart_type: 'line', 'bar', 'scatter', 'area'
        colors: list of hex colors per y_col (auto-assigned if None)
        Multiple y_cols = multiple y-axes (first on left, rest on right)
        """
        if x_col not in df.columns:
            return self._empty(f"X column '{x_col}' not found.")
        y_cols = [c for c in y_cols if c in df.columns]
        if not y_cols:
            return self._empty("No valid Y columns found.")

        multi_axis = len(y_cols) > 1
        specs = [[{"secondary_y": True}]] if multi_axis else [[{}]]
        fig = make_subplots(specs=specs)

        default_colors = px.colors.qualitative.Plotly
        for i, col in enumerate(y_cols):
            color = (colors[i] if colors and i < len(colors) else default_colors[i % len(default_colors)])
            secondary = (i > 0)

            if chart_type == 'line':
                trace = go.Scatter(x=df[x_col], y=df[col], mode='lines', name=col, line=dict(color=color))
            elif chart_type == 'bar':
                trace = go.Bar(x=df[x_col], y=df[col], name=col, marker_color=color)
            elif chart_type == 'scatter':
                trace = go.Scatter(x=df[x_col], y=df[col], mode='markers', name=col, marker=dict(color=color, size=5))
            elif chart_type == 'area':
                trace = go.Scatter(x=df[x_col], y=df[col], mode='lines', fill='tozeroy', name=col, line=dict(color=color))
            else:
                trace = go.Scatter(x=df[x_col], y=df[col], mode='lines', name=col, line=dict(color=color))

            if multi_axis:
                fig.add_trace(trace, secondary_y=secondary)
            else:
                fig.add_trace(trace)

        fig.update_layout(
            title=title, template="plotly_dark",
            hovermode='x unified', height=500,
            barmode='group'
        )
        return fig

    # ─────────────────────────────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────────────────────────────

    def _empty(self, message: str) -> go.Figure:
        fig = go.Figure()
        fig.add_annotation(text=message, xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=16))
        fig.update_layout(template="plotly_dark", height=300)
        return fig
