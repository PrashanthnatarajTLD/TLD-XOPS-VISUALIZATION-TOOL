import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio


# ── helpers ───────────────────────────────────────────────────────────────────

def parse_telemetry_value(text, key):
    if pd.isna(text):
        return np.nan
    text = str(text)
    patterns = [
        re.escape(key) + r'\s*:\s*([^,]+)',
        re.escape(key) + r'\s*=\s*([^,]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            try:
                return float(value)
            except ValueError:
                return value
    return np.nan


def normalize_connection_value(v):
    if pd.isna(v):
        return np.nan
    s = str(v).strip().lower()
    if s in {'connected', 'connect', '1', 'true', 'yes', 'on'}:
        return 'Connected'
    if s in {'disconnected', 'disconnect', '0', 'false', 'no', 'off'}:
        return 'Disconnected'
    if 'connected' in s and 'dis' not in s:
        return 'Connected'
    if 'disconnected' in s:
        return 'Disconnected'
    return str(v).strip()


def parse_soc_value(raw):
    if pd.isna(raw):
        return np.nan
    try:
        return float(raw)
    except (ValueError, TypeError):
        pass
    m = re.search(r':\s*(-?[\d.]+)\s*$', str(raw).strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return np.nan


# ── file I/O ──────────────────────────────────────────────────────────────────

def read_input_file(file_path):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f'File not found: {file_path}')

    if path.suffix.lower() in ['.xlsx', '.xls']:
        xl = pd.ExcelFile(path)

        raw_sheet = next(
            (s for s in xl.sheet_names if s.strip().lower() == 'raw telemetry'),
            xl.sheet_names[0]
        )
        raw_df = pd.read_excel(path, sheet_name=raw_sheet)
        print(f"DEBUG: Raw telemetry sheet = '{raw_sheet}' ({len(raw_df)} rows)")

        soc_sheet = next(
            (s for s in xl.sheet_names if s.strip().lower() == 'ev battery state of charge'),
            None
        )
        soc_df = pd.read_excel(path, sheet_name=soc_sheet) if soc_sheet else pd.DataFrame()
        print(f"DEBUG: SOC sheet = '{soc_sheet}' ({len(soc_df)} rows)" if soc_sheet
              else "DEBUG: No SOC sheet found.")

        cur_sheet = next(
            (s for s in xl.sheet_names if s.strip().lower() == 'ev battery current'),
            None
        )
        cur_df = pd.read_excel(path, sheet_name=cur_sheet) if cur_sheet else pd.DataFrame()
        print(f"DEBUG: EV Battery Current sheet = '{cur_sheet}' ({len(cur_df)} rows)" if cur_sheet
              else "DEBUG: No EV Battery Current sheet found.")

        return raw_df, soc_df, cur_df

    elif path.suffix.lower() == '.csv':
        return pd.read_csv(path), pd.DataFrame(), pd.DataFrame()
    else:
        raise ValueError('Supported files: .xlsx, .xls, .csv')


# ── column normalisation ──────────────────────────────────────────────────────

def find_required_columns(df):
    norm_map = {str(c).strip().lower(): c for c in df.columns}
    aliases = {
        'date':        ['date', 'datetime', 'timestamp', 'time', 'dateprocessed'],
        'telemetry':   ['telemetry', 'telmetry'],
        'engineState': ['enginestate', 'engine state'],
        'odometer':    ['odometer', 'odo'],
        'motorHour':   ['motorhour', 'motor hour'],
        'speed':       ['speed', 'vehicle speed'],
    }
    found = {}
    for target, options in aliases.items():
        for opt in options:
            if opt.lower() in norm_map:
                found[target] = norm_map[opt.lower()]
                break
    missing = [k for k in ['date', 'telemetry', 'engineState', 'odometer', 'motorHour']
               if k not in found]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Available: {list(df.columns)}")
    return found


def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    colmap = find_required_columns(df)

    out = pd.DataFrame()
    out['date']        = pd.to_datetime(df[colmap['date']], errors='coerce', utc=True)
    out['telemetry']   = df[colmap['telemetry']]
    out['engineState'] = df[colmap['engineState']].astype(str).str.strip()
    out['odometer']    = pd.to_numeric(df[colmap['odometer']], errors='coerce')
    out['motorHour']   = pd.to_numeric(df[colmap['motorHour']], errors='coerce')
    out['speed']       = (pd.to_numeric(df[colmap['speed']], errors='coerce')
                          if 'speed' in colmap else np.nan)

    out = out.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

    # The API stores dates as UTC but extracted using Asia/Calcutta filter boundary
    # Using UTC directly avoids double +5:30 conversion causing next-day spillover
    utc_dt     = out['date'].dt.tz_convert('UTC')
    out['day']  = utc_dt.dt.date
    # Use the SUNDAY (end) of each ISO week as the label.
    # This prevents weekly bars from appearing before the dataset start date
    # (e.g. week of Apr 21–27 would show as Apr 27 not Apr 21).
    out['week'] = utc_dt.dt.to_period('W').apply(lambda p: p.end_time.date())

    out['charger_connection_raw'] = out['telemetry'].apply(
        lambda x: parse_telemetry_value(x, 'EV Charger Connection')
    )
    out['charger_connection'] = out['charger_connection_raw'].apply(normalize_connection_value)
    return out


def normalize_soc_sheet(soc_df):
    if soc_df is None or soc_df.empty:
        print("DEBUG: SOC sheet is empty.")
        return pd.DataFrame(columns=['date', 'soc'])

    soc_df = soc_df.copy()
    soc_df.columns = [str(c).strip() for c in soc_df.columns]

    date_aliases = ['date', 'datetime', 'timestamp', 'time', 'dateprocessed']
    date_col = next((c for c in soc_df.columns if c.lower() in date_aliases), soc_df.columns[0])
    soc_col  = next((c for c in soc_df.columns if c.strip().lower() == 'soc'), None)

    if soc_col is None:
        print(f"DEBUG: No 'SOC' column. Columns: {list(soc_df.columns)}")
        return pd.DataFrame(columns=['date', 'soc'])

    print(f"DEBUG: SOC raw samples: {soc_df[soc_col].dropna().head(3).tolist()}")

    out = pd.DataFrame()
    out['date'] = pd.to_datetime(soc_df[date_col], errors='coerce', utc=True)
    out['soc']  = soc_df[soc_col].apply(parse_soc_value)
    out = out.dropna(subset=['date', 'soc']).sort_values('date').reset_index(drop=True)
    print(f"DEBUG: SOC parsed — {len(out)} rows, range {out['soc'].min():.1f}%–{out['soc'].max():.1f}%")
    return out


def normalize_battery_current_sheet(cur_df):
    if cur_df is None or cur_df.empty:
        print("DEBUG: EV Battery Current sheet is empty.")
        return pd.DataFrame(columns=['date', 'battery_current'])

    cur_df = cur_df.copy()
    cur_df.columns = [str(c).strip() for c in cur_df.columns]

    date_aliases = ['date', 'datetime', 'timestamp', 'time', 'dateprocessed']
    date_col = next((c for c in cur_df.columns if c.lower() in date_aliases), cur_df.columns[0])
    tel_col  = next((c for c in cur_df.columns if c.strip().lower() in ['telemetry', 'telmetry']), None)

    if tel_col is None:
        print(f"DEBUG: No telemetry column in EV Battery Current sheet.")
        return pd.DataFrame(columns=['date', 'battery_current'])

    out = pd.DataFrame()
    out['date'] = pd.to_datetime(cur_df[date_col], errors='coerce', utc=True)
    out['battery_current'] = cur_df[tel_col].apply(
        lambda x: parse_telemetry_value(x, 'EV Battery Current')
    )
    out['battery_current'] = pd.to_numeric(out['battery_current'], errors='coerce')
    out = out.dropna(subset=['date', 'battery_current']).sort_values('date').reset_index(drop=True)
    print(f"DEBUG: Battery Current parsed — {len(out)} rows, "
          f"range {out['battery_current'].min():.2f}–{out['battery_current'].max():.2f} A")
    return out


# ── time features & metrics ───────────────────────────────────────────────────

def add_time_features(df):
    df = df.copy()
    df['next_date'] = df['date'].shift(-1)
    df['dt_hours']  = (df['next_date'] - df['date']).dt.total_seconds() / 3600.0

    median_dt   = df['dt_hours'].dropna().median() if len(df) > 1 else 5 / 3600
    fallback_dt = median_dt if pd.notna(median_dt) and median_dt > 0 else 5 / 3600

    df['dt_hours'] = df['dt_hours'].fillna(fallback_dt)
    df.loc[df['dt_hours'] <= 0, 'dt_hours'] = fallback_dt
    df.loc[df['dt_hours'] > 1,  'dt_hours'] = fallback_dt

    df['motor_delta'] = df['motorHour'].diff().clip(lower=0)
    df['odo_delta']   = df['odometer'].diff().clip(lower=0)
    return df


def compute_charge_cycles(df):
    temp = df[['date', 'day', 'week', 'charger_connection',
               'motorHour', 'odometer']].copy()
    temp = temp.dropna(subset=['charger_connection']).reset_index(drop=True)

    if temp.empty:
        return (
            pd.DataFrame(columns=['day', 'charge_cycles_day']),
            pd.DataFrame(columns=['week', 'charge_cycles_week']),
            pd.DataFrame(columns=['date', 'day', 'week', 'charger_connection',
                                  'prev_connection', 'cycle_completed', 'motorHour', 'odometer'])
        )

    temp['prev_connection'] = temp['charger_connection'].shift(1)
    temp['cycle_completed'] = (
        (temp['prev_connection'] == 'Connected') &
        (temp['charger_connection'] == 'Disconnected')
    ).astype(int)

    day_counts  = temp.groupby('day',  as_index=False).agg(charge_cycles_day=('cycle_completed',  'sum'))
    week_counts = temp.groupby('week', as_index=False).agg(charge_cycles_week=('cycle_completed', 'sum'))
    return day_counts, week_counts, temp


def compute_engine_state_pct(df):
    """
    Compute Running / Idle / Off % per day and per week using RAW uncapped
    durations directly from the timestamps — no 1-hour cap, no fallback.
    This gives accurate Off% including overnight gaps.

    Each segment duration = next_timestamp - current_timestamp.
    The segment is assigned to the current record's engineState and day.
    Cross-midnight segments are split at midnight so each day only gets its share.
    """
    tmp = df[['date', 'day', 'week', 'engineState']].copy().sort_values('date').reset_index(drop=True)
    tmp['next_date'] = tmp['date'].shift(-1)

    # Drop last row (no next timestamp)
    tmp = tmp.dropna(subset=['next_date']).copy()

    tmp['state_bucket'] = tmp['engineState'].str.strip().str.lower().map(
        lambda s: 'Running' if s == 'running' else ('Idle' if s == 'idle' else 'Off')
    )

    # Split cross-midnight segments so each calendar day gets its correct share
    rows = []
    for _, row in tmp.iterrows():
        seg_start = row['date']
        seg_end   = row['next_date']
        state     = row['state_bucket']
        week      = row['week']

        # Walk through calendar days covered by this segment
        cur = seg_start
        while cur < seg_end:
            # End of current calendar day in UTC
            next_midnight = (cur + pd.Timedelta(days=1)).normalize()
            chunk_end = min(seg_end, next_midnight)

            duration_h = (chunk_end - cur).total_seconds() / 3600.0

            # Day in IST
            ist_day = cur.tz_convert('UTC').date()

            rows.append({
                'day':          ist_day,
                'week':         week,
                'state_bucket': state,
                'duration_h':   duration_h,
            })
            cur = chunk_end

    segs = pd.DataFrame(rows)

    def pivot_pct(grp_col):
        pivot = (
            segs.groupby([grp_col, 'state_bucket'], as_index=False)['duration_h']
                .sum()
                .pivot(index=grp_col, columns='state_bucket', values='duration_h')
                .fillna(0)
                .reset_index()
        )
        for col in ['Running', 'Idle', 'Off']:
            if col not in pivot.columns:
                pivot[col] = 0.0
        pivot['total']       = pivot['Running'] + pivot['Idle'] + pivot['Off']
        pivot['running_pct'] = (pivot['Running'] / pivot['total'] * 100).round(1)
        pivot['idle_pct']    = (pivot['Idle']    / pivot['total'] * 100).round(1)
        pivot['off_pct']     = (pivot['Off']     / pivot['total'] * 100).round(1)
        return pivot

    day_pivot  = pivot_pct('day')
    week_pivot = pivot_pct('week')

    return day_pivot, week_pivot


def build_metrics(df):
    running = df[df['engineState'].str.lower() == 'running'].copy()
    idle    = df[df['engineState'].str.lower() == 'idle'].copy()

    usage_day  = running.groupby('day',  as_index=False).agg(usage_hours=('motor_delta', 'sum'), motor_hour_end=('motorHour', 'max'))
    usage_week = running.groupby('week', as_index=False).agg(usage_hours=('motor_delta', 'sum'))
    idle_day   = idle.groupby('day',  as_index=False).agg(idle_hours=('dt_hours', 'sum'), odometer_max=('odometer', 'max'), motor_hour_max=('motorHour', 'max'))
    idle_week  = idle.groupby('week', as_index=False).agg(idle_hours=('dt_hours', 'sum'))
    dist_day   = df.groupby('day',  as_index=False).agg(distance_km=('odo_delta', 'sum'), odometer_end=('odometer', 'max'))
    dist_week  = df.groupby('week', as_index=False).agg(distance_km=('odo_delta', 'sum'))
    spd_day    = df.groupby('day',  as_index=False).agg(avg_speed=('speed', 'mean'))
    spd_week   = df.groupby('week', as_index=False).agg(avg_speed=('speed', 'mean'))

    cyc_day, cyc_week, cyc_detail = compute_charge_cycles(df)
    state_day, state_week = compute_engine_state_pct(df)

    # Only average over days that have any motor activity (>0 motor hours)
    active_usage_day  = usage_day[usage_day['usage_hours'] > 0]
    active_idle_day   = idle_day[idle_day['idle_hours'] > 0]

    kpis = {
        'avg_motor_hours_day':          usage_day['usage_hours'].mean()        if not usage_day.empty   else 0,
        'avg_motor_hours_day_active':   active_usage_day['usage_hours'].mean() if not active_usage_day.empty else 0,
        'avg_motor_hours_week':         usage_week['usage_hours'].mean()       if not usage_week.empty  else 0,
        'avg_distance_day':             dist_day['distance_km'].mean()         if not dist_day.empty    else 0,
        'avg_distance_week':            dist_week['distance_km'].mean()        if not dist_week.empty   else 0,
        'total_idle_day_avg':           idle_day['idle_hours'].mean()          if not idle_day.empty    else 0,
        'total_idle_day_avg_active':    active_idle_day['idle_hours'].mean()   if not active_idle_day.empty else 0,
        'total_idle_week_avg':          idle_week['idle_hours'].mean()         if not idle_week.empty   else 0,
        'avg_speed_day':                spd_day['avg_speed'].mean()            if not spd_day.empty     else 0,
        'avg_speed_week':               spd_week['avg_speed'].mean()           if not spd_week.empty    else 0,
        'avg_charge_cycles_day':        cyc_day['charge_cycles_day'].mean()   if not cyc_day.empty     else 0,
        'avg_charge_cycles_week':       cyc_week['charge_cycles_week'].mean() if not cyc_week.empty    else 0,
        'avg_running_pct_day':          state_day['running_pct'].mean()        if not state_day.empty   else 0,
        'avg_idle_pct_day':             state_day['idle_pct'].mean()           if not state_day.empty   else 0,
        'avg_off_pct_day':              state_day['off_pct'].mean()            if not state_day.empty   else 0,
    }
    return {
        'usage_day': usage_day, 'usage_week': usage_week,
        'idle_day': idle_day,   'idle_week': idle_week,
        'distance_day': dist_day, 'distance_week': dist_week,
        'speed_day': spd_day,   'speed_week': spd_week,
        'cycle_day': cyc_day,   'cycle_week': cyc_week,
        'cycle_detail': cyc_detail,
        'state_day': state_day, 'state_week': state_week,
        'kpis': kpis,
    }


# ── charts ────────────────────────────────────────────────────────────────────

def chart_title(main, formula):
    return f"{main}<br><sup>{formula}</sup>"


def make_engine_state_pct_chart(state_day, state_week):
    """
    Stacked 100% bar chart — Running / Idle / Off per day (top) and per week (bottom).
    Colors match the Gantt: Running=green, Idle=red, Off=yellow.
    """
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Engine State % per Day', 'Engine State % per Week'),
        vertical_spacing=0.18
    )

    COLORS = {'Running': '#2ca02c', 'Idle': '#f0e442', 'Off': '#d62728'}

    added = set()
    for state, col in [('Running', 'running_pct'), ('Idle', 'idle_pct'), ('Off', 'off_pct')]:
        show = state not in added
        added.add(state)

        if not state_day.empty:
            fig.add_trace(
                go.Bar(
                    x=state_day['day'].astype(str),
                    y=state_day[col],
                    name=state,
                    marker_color=COLORS[state],
                    legendgroup=state,
                    showlegend=show,
                    hovertemplate=(
                        f'Day: %{{x}}<br>{state}: %{{y:.1f}}%'
                        f'<extra></extra>'
                    )
                ),
                row=1, col=1
            )

        if not state_week.empty:
            fig.add_trace(
                go.Bar(
                    x=state_week['week'].astype(str),
                    y=state_week[col],
                    name=state,
                    marker_color=COLORS[state],
                    legendgroup=state,
                    showlegend=False,
                    hovertemplate=(
                        f'Week: %{{x}}<br>{state}: %{{y:.1f}}%'
                        f'<extra></extra>'
                    )
                ),
                row=2, col=1
            )

  fig.update_layout(
        template='plotly_white',
        height=760,
        barmode='stack',
        title=chart_title(
            'Rate of Operational Status (Running / Idle / Off)',
            'Formula: time in each engineState bucket ÷ total recorded time per day/week × 100.'
        ),
        yaxis=dict(title='%', range=[0, 100]),
        yaxis2=dict(title='%', range=[0, 100]),
        legend=dict(title='Engine State', traceorder='normal'),
    )
    return fig


def make_figures(df, m):
    T = 'plotly_white'

    # Usage
    fig_usage = make_subplots(rows=2, cols=1,
                              subplot_titles=('Usage Hours per Day', 'Usage Hours per Week'),
                              vertical_spacing=0.18)
    if not m['usage_day'].empty:
        fig_usage.add_trace(
            go.Bar(x=m['usage_day']['day'].astype(str), y=m['usage_day']['usage_hours'],
                   marker_color='#01696f',
                   customdata=np.stack([m['usage_day']['motor_hour_end'].fillna(np.nan)], axis=-1),
                   hovertemplate='Day: %{x}<br>Usage hours: %{y:.3f}<br>MotorHour: %{customdata[0]:.3f}<extra></extra>'),
            row=1, col=1)
    if not m['usage_week'].empty:
        fig_usage.add_trace(
            go.Bar(x=m['usage_week']['week'].astype(str), y=m['usage_week']['usage_hours'],
                   marker_color='#5591c7',
                   hovertemplate='Week: %{x}<br>Usage hours: %{y:.3f}<extra></extra>'),
            row=2, col=1)
    fig_usage.update_layout(template=T, height=720,
                            title=chart_title('Hours of Usage from motorHour',
                                              'Formula: sum of positive motorHour differences per day/week.'),
                            showlegend=False)

    # Idle
    fig_idle = go.Figure()
    if not m['idle_day'].empty:
        fig_idle.add_trace(
            go.Bar(x=m['idle_day']['day'].astype(str), y=m['idle_day']['idle_hours'],
                   marker_color='#d19900',
                   customdata=np.stack([m['idle_day']['odometer_max'].fillna(np.nan),
                                        m['idle_day']['motor_hour_max'].fillna(np.nan)], axis=-1),
                   hovertemplate='Day: %{x}<br>Idle hours: %{y:.3f}<br>Odometer: %{customdata[0]:.3f}<br>MotorHour: %{customdata[1]:.3f}<extra></extra>'))
    fig_idle.update_layout(template=T, height=460,
                           title=chart_title('Idle Time per Day (engineState = Idle)',
                                             'Formula: sum of time gaps where engineState = Idle.'))

    # Charge cycles
    fig_charge = make_subplots(rows=2, cols=1,
                               subplot_titles=('EV Charger Connection over Time', 'Charge Cycle Count'),
                               vertical_spacing=0.18)
    detail = m['cycle_detail']
    if not detail.empty:
        y_num  = detail['charger_connection'].map({'Disconnected': 0, 'Connected': 1})
        custom = np.stack([detail['motorHour'].fillna(np.nan),
                           detail['odometer'].fillna(np.nan),
                           detail['cycle_completed'].fillna(0)], axis=-1)
        fig_charge.add_trace(
            go.Scatter(x=detail['date'], y=y_num, mode='lines+markers',
                       line=dict(color='#a13544', width=2), marker=dict(size=6),
                       customdata=custom, text=detail['charger_connection'],
                       hovertemplate='Time: %{x}<br>Connection: %{text}<br>MotorHour: %{customdata[0]:.3f}<br>Odometer: %{customdata[1]:.3f}<br>Cycle completed: %{customdata[2]}<extra></extra>'),
            row=1, col=1)
        fig_charge.update_yaxes(tickmode='array', tickvals=[0, 1],
                                ticktext=['Disconnected', 'Connected'], row=1, col=1)
    if not m['cycle_day'].empty:
        fig_charge.add_trace(
            go.Bar(x=m['cycle_day']['day'].astype(str), y=m['cycle_day']['charge_cycles_day'],
                   name='Cycles/day', marker_color='#437a22',
                   hovertemplate='Day: %{x}<br>Charge cycles: %{y}<extra></extra>'),
            row=2, col=1)
    if not m['cycle_week'].empty:
        fig_charge.add_trace(
            go.Bar(x=m['cycle_week']['week'].astype(str), y=m['cycle_week']['charge_cycles_week'],
                   name='Cycles/week', marker_color='#964219',
                   hovertemplate='Week: %{x}<br>Charge cycles: %{y}<extra></extra>'),
            row=2, col=1)
    fig_charge.update_layout(template=T, height=780,
                             title=chart_title('Charging Cycle Count using EV Charger Connection',
                                               'Formula: one cycle = Connected → Disconnected transition.'))

    # Distance
    fig_distance = go.Figure()
    if not m['distance_day'].empty:
        fig_distance.add_trace(
            go.Bar(x=m['distance_day']['day'].astype(str), y=m['distance_day']['distance_km'],
                   marker_color='#006494',
                   customdata=np.stack([m['distance_day']['odometer_end'].fillna(np.nan)], axis=-1),
                   hovertemplate='Day: %{x}<br>Distance: %{y:.3f} km<br>Odometer: %{customdata[0]:.3f}<extra></extra>'))
    fig_distance.update_layout(template=T, height=460,
                               title=chart_title('Distance Travelled per Day from odometer',
                                                 'Formula: sum of positive odometer differences within each day.'))

    # Speed
    fig_speed = make_subplots(rows=2, cols=1,
                              subplot_titles=('Average Speed per Day', 'Average Speed per Week'),
                              vertical_spacing=0.18)
    if not m['speed_day'].empty:
        fig_speed.add_trace(
            go.Bar(x=m['speed_day']['day'].astype(str), y=m['speed_day']['avg_speed'],
                   marker_color='#7a39bb',
                   hovertemplate='Day: %{x}<br>Avg speed: %{y:.3f}<extra></extra>'),
            row=1, col=1)
    if not m['speed_week'].empty:
        fig_speed.add_trace(
            go.Bar(x=m['speed_week']['week'].astype(str), y=m['speed_week']['avg_speed'],
                   marker_color='#da7101',
                   hovertemplate='Week: %{x}<br>Avg speed: %{y:.3f}<extra></extra>'),
            row=2, col=1)
    fig_speed.update_layout(template=T, height=720,
                            title=chart_title('Average Speed',
                                              'Formula: arithmetic mean of speed values per day/week.'),
                            showlegend=False)

    return fig_usage, fig_idle, fig_charge, fig_distance, fig_speed


def make_raw_telemetry_line_chart(df):
    fig = go.Figure()
    if df['motorHour'].notna().any():
        fig.add_trace(go.Scatter(x=df['date'], y=df['motorHour'], mode='lines',
                                 name='Motor Hour', line=dict(color='#da7101', width=2),
                                 hovertemplate='Time: %{x}<br>Motor Hour: %{y:.3f}<extra></extra>'))
    if df['odometer'].notna().any():
        fig.add_trace(go.Scatter(x=df['date'], y=df['odometer'], mode='lines',
                                 name='Odometer', line=dict(color='#006494', width=2),
                                 hovertemplate='Time: %{x}<br>Odometer: %{y:.3f}<extra></extra>'))
    fig.update_layout(template='plotly_white', height=520,
                      title='Raw Telemetry: Motor Hour and Odometer vs Time<br>'
                            '<sup>Direct line plot of motorHour and odometer against timestamp.</sup>',
                      xaxis_title='Time', yaxis_title='Value', hovermode='x unified')
    return fig


def make_soc_chart(soc_df):
    fig = go.Figure()
    if soc_df is not None and not soc_df.empty:
        fig.add_trace(
            go.Scatter(x=soc_df['date'], y=soc_df['soc'],
                       mode='lines+markers', name='SOC',
                       line=dict(color='#2e8b57', width=2), marker=dict(size=5),
                       hovertemplate='Time: %{x}<br>SOC: %{y:.1f}%<extra></extra>'))
        print(f"DEBUG: SOC chart — {len(soc_df)} points, "
              f"{soc_df['soc'].min():.1f}%–{soc_df['soc'].max():.1f}%")
    else:
        print("DEBUG: SOC chart — no data.")
    fig.update_layout(
        template='plotly_white', height=460,
        title='EV Battery State of Charge Evolution<br>'
              '<sup>Parsed from SOC column of "EV Battery State of Charge" sheet.</sup>',
        xaxis_title='Time', yaxis_title='State of Charge (%)', hovermode='x unified')
    return fig


def make_battery_current_chart(cur_df):
    fig = go.Figure()
    if cur_df is not None and not cur_df.empty:
        fig.add_trace(
            go.Scatter(x=cur_df['date'], y=cur_df['battery_current'], mode='lines',
                       name='Battery Current', line=dict(color='#c0392b', width=1.5),
                       hovertemplate='Time: %{x}<br>Battery Current: %{y:.2f} A<extra></extra>'))
        fig.add_hline(y=0, line_dash='dash', line_color='#7a7974', line_width=1,
                      annotation_text='0 A', annotation_position='right')
        print(f"DEBUG: Battery Current chart — {len(cur_df)} points, "
              f"range {cur_df['battery_current'].min():.2f}–{cur_df['battery_current'].max():.2f} A")
    else:
        print("DEBUG: Battery Current chart — no data.")
    fig.update_layout(
        template='plotly_white', height=480,
        title='EV Battery Current over Time<br>'
              '<sup>Negative = discharging, Positive = charging.</sup>',
        xaxis_title='Time', yaxis_title='Current (A)', hovermode='x unified')
    return fig


# ── Engine State Gantt ────────────────────────────────────────────────────────

def make_engine_state_gantt(df, file_name=""):
    """
    Efficient Gantt chart — merges consecutive records with the same engineState
    into single segments before plotting. Reduces traces from ~100k to ~hundreds,
    making the page load fast while preserving identical visuals and accuracy.
    """
    COLOR_MAP = {'running': '#2ca02c', 'idle': '#f0e442', 'off': '#d62728'}
    DEFAULT_COLOR = '#aaaaaa'

    # ── Step 1: build raw segments (start, end, state) ───────────────────────
    df2 = df[['date', 'engineState']].copy().sort_values('date').reset_index(drop=True)
    df2['next_date'] = df2['date'].shift(-1)
    df2 = df2.dropna(subset=['next_date'])

    utc            = df2['date'].dt.tz_convert('UTC')
    df2['day_str'] = utc.dt.date.astype(str)
    df2['state']   = df2['engineState'].str.strip()

    # ── Step 2: merge consecutive records with the same state on the same day ─
    # Assign a group id whenever state or day changes
    df2['grp'] = (
        (df2['state']   != df2['state'].shift()) |
        (df2['day_str'] != df2['day_str'].shift())
    ).cumsum()

    segments = (
        df2.groupby('grp', as_index=False)
           .agg(
               seg_start=('date',      'first'),
               seg_end  =('next_date', 'last'),
               state    =('state',     'first'),
               day_str  =('day_str',   'first'),
           )
    )

    # Convert segments to UTC hour floats for x-axis positioning
    seg_utc_start = segments['seg_start'].dt.tz_convert('UTC')
    seg_utc_end   = segments['seg_end'].dt.tz_convert('UTC')

    segments['hour_start'] = (seg_utc_start.dt.hour
                              + seg_utc_start.dt.minute / 60
                              + seg_utc_start.dt.second / 3600)
    segments['hour_end']   = (seg_utc_end.dt.hour
                              + seg_utc_end.dt.minute / 60
                              + seg_utc_end.dt.second / 3600)
    segments['duration_h'] = (
        (segments['seg_end'] - segments['seg_start']).dt.total_seconds() / 3600
    )

    # Handle cross-midnight segments: clip hour_end at 24
    segments['hour_end'] = segments['hour_end'].clip(upper=24)
    segments['bar_width'] = (segments['hour_end'] - segments['hour_start']).clip(lower=0)

    # Drop zero-width bars
    segments = segments[segments['bar_width'] > 0].copy()

    days_sorted = sorted(segments['day_str'].unique())
    # Map day string → numeric y position (oldest = 0 at bottom)
    day_to_y = {d: i for i, d in enumerate(days_sorted)}

    # ── Step 3: one Scatter trace per state (thick horizontal lines) ─────────
    # Each segment: x = [start, end, None]  y = [y_pos, y_pos, None]
    # None breaks the line between segments so they don't connect.
    fig = go.Figure()

    for state, grp in segments.groupby('state'):
        state_low = state.lower()
        color     = COLOR_MAP.get(state_low, DEFAULT_COLOR)

        xs, ys, texts = [], [], []
        for _, row in grp.iterrows():
            y_pos = day_to_y[row['day_str']]
            xs  += [row['hour_start'], row['hour_end'], None]
            ys  += [y_pos,             y_pos,           None]
            texts += [
                f"Day: {row['day_str']}<br>State: {state}<br>"
                f"Start: {row['hour_start']:.2f}h<br>"
                f"End: {row['hour_end']:.2f}h<br>"
                f"Duration: {row['duration_h']:.2f}h",
                f"Day: {row['day_str']}<br>State: {state}<br>"
                f"Start: {row['hour_start']:.2f}h<br>"
                f"End: {row['hour_end']:.2f}h<br>"
                f"Duration: {row['duration_h']:.2f}h",
                None
            ]

        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode='lines',
            name=state,
            legendgroup=state,
            line=dict(color=color, width=20),   # ← thick lines = solid blocks
            hoverinfo='text',
            text=texts,
            connectgaps=False,
        ))

    print(f"DEBUG: Gantt — {len(segments)} merged segments "
          f"(from {len(df2)} raw records), {len(days_sorted)} days.")

    fig.update_layout(
        template='plotly_white',
        height=max(600, len(days_sorted) * 40 + 150),
        title=f"{file_name}<br><sup>Engine State Timeline "
              f"({days_sorted[0]} to {days_sorted[-1]} 23:59:59)</sup>",
        xaxis=dict(title='Hour of Day (0-23)', range=[0, 24],
                   tickmode='linear', tick0=0, dtick=5),
        yaxis=dict(
            title='Day',
            tickmode='array',
            tickvals=list(range(len(days_sorted))),
            ticktext=days_sorted,
        ),
        legend=dict(title='Engine State'),
        hovermode='closest',
    )
    return fig


# ── HTML output ───────────────────────────────────────────────────────────────

def build_kpi_cards(kpis):
    cards = [
        ('Avg Motor Hours / Day (all)',      f"{kpis['avg_motor_hours_day']:.3f} h"),
        ('Avg Motor Hours / Day (active)',   f"{kpis['avg_motor_hours_day_active']:.3f} h"),
        ('Avg Motor Hours / Week',           f"{kpis['avg_motor_hours_week']:.3f} h"),
        ('Avg Distance / Day',               f"{kpis['avg_distance_day']:.3f} km"),
        ('Avg Distance / Week',              f"{kpis['avg_distance_week']:.3f} km"),
        ('Avg Idle Hours / Day (all)',        f"{kpis['total_idle_day_avg']:.3f} h"),
        ('Avg Idle Hours / Day (active)',     f"{kpis['total_idle_day_avg_active']:.3f} h"),
        ('Avg Idle Hours / Week',             f"{kpis['total_idle_week_avg']:.3f} h"),
        ('Avg Speed / Day',                  f"{kpis['avg_speed_day']:.3f}"),
        ('Avg Speed / Week',                 f"{kpis['avg_speed_week']:.3f}"),
        ('Avg Charge Cycles / Day',          f"{kpis['avg_charge_cycles_day']:.3f}"),
        ('Avg Charge Cycles / Week',         f"{kpis['avg_charge_cycles_week']:.3f}"),
        ('Avg Running % / Day',              f"{kpis['avg_running_pct_day']:.1f}%"),
        ('Avg Idle % / Day',                 f"{kpis['avg_idle_pct_day']:.1f}%"),
        ('Avg Off % / Day',                  f"{kpis['avg_off_pct_day']:.1f}%"),
    ]
    html = ""
    for title, value in cards:
        html += f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
        </div>"""
    return html


def write_dashboard_html(output_html, figs, fig_state_pct, fig_gantt,
                         fig_soc, fig_raw, fig_cur, input_name, kpis):
    fig_usage, fig_idle, fig_charge, fig_distance, fig_speed = figs
    divs = [
        pio.to_html(fig_usage,      include_plotlyjs='cdn', full_html=False),
        pio.to_html(fig_state_pct,  include_plotlyjs=False, full_html=False),
        pio.to_html(fig_gantt,      include_plotlyjs=False, full_html=False),
        pio.to_html(fig_idle,       include_plotlyjs=False, full_html=False),
        pio.to_html(fig_charge,     include_plotlyjs=False, full_html=False),
        pio.to_html(fig_distance,   include_plotlyjs=False, full_html=False),
        pio.to_html(fig_speed,      include_plotlyjs=False, full_html=False),
        pio.to_html(fig_soc,        include_plotlyjs=False, full_html=False),
        pio.to_html(fig_raw,        include_plotlyjs=False, full_html=False),
        pio.to_html(fig_cur,        include_plotlyjs=False, full_html=False),
    ]
    kpi_html = build_kpi_cards(kpis)

    cards_html = ''.join(f"  <div class='card'>__DIV{i}__</div>\n" for i in range(1, len(divs)+1))

    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>TMX-150-E Dashboard</title>
<style>
:root{{--bg:#f7f6f2;--surface:#fff;--text:#28251d;--muted:#7a7974;--border:#d4d1ca;--accent:#01696f}}
body{{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}}
header{{padding:20px 24px 8px}}
h1{{margin:0 0 6px;font-size:28px}}
p{{margin:0;color:var(--muted)}}
main{{padding:8px 16px 32px;display:grid;gap:16px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px;box-shadow:0 4px 12px rgba(0,0,0,.05)}}
.kpi-title{{font-size:14px;color:var(--muted);margin-bottom:8px}}
.kpi-value{{font-size:28px;font-weight:700;color:var(--accent)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px;box-shadow:0 4px 12px rgba(0,0,0,.05)}}
</style>
</head>
<body>
<header>
  <h1>TMX-150-E Demo Dashboard – AISATS – T118059</h1>
  <p>Input file: __INPUT_NAME__</p>
</header>
<main>
  <div class='kpi-grid'>__KPI_HTML__</div>
{cards_html}</main>
</body>
</html>"""

    html = html.replace('__INPUT_NAME__', str(input_name))
    html = html.replace('__KPI_HTML__', kpi_html)
    for i, div in enumerate(divs, start=1):
        html = html.replace(f'__DIV{i}__', div)
    Path(output_html).write_text(html, encoding='utf-8')


# ── entry point ───────────────────────────────────────────────────────────────

def main(file_path):
    raw_df, soc_sheet_df, cur_sheet_df = read_input_file(file_path)

    df      = normalize_columns(raw_df)
    df      = add_time_features(df)
    soc_df  = normalize_soc_sheet(soc_sheet_df)
    cur_df  = normalize_battery_current_sheet(cur_sheet_df)

    metrics       = build_metrics(df)
    figs          = make_figures(df, metrics)
    fig_state_pct = make_engine_state_pct_chart(metrics['state_day'], metrics['state_week'])
    fig_gantt     = make_engine_state_gantt(df, Path(file_path).name)
    fig_soc       = make_soc_chart(soc_df)
    fig_raw       = make_raw_telemetry_line_chart(df)
    fig_cur       = make_battery_current_chart(cur_df)

    out_dir = Path('output')
    out_dir.mkdir(exist_ok=True)
    stem           = Path(file_path).stem
    output_html    = out_dir / f'{stem}_tmx150_dashboard.html'
    output_csv     = out_dir / f'{stem}_parsed_metrics.csv'
    output_soc_csv = out_dir / f'{stem}_soc_parsed.csv'
    output_cur_csv = out_dir / f'{stem}_battery_current_parsed.csv'

    df.to_csv(output_csv, index=False)
    soc_df.to_csv(output_soc_csv, index=False)
    cur_df.to_csv(output_cur_csv, index=False)
    write_dashboard_html(output_html, figs, fig_state_pct, fig_gantt,
                         fig_soc, fig_raw, fig_cur,
                         Path(file_path).name, metrics['kpis'])

    print(f'\nDashboard created        : {output_html}')
    print(f'Parsed raw data          : {output_csv}')
    print(f'Parsed SOC data          : {output_soc_csv}')
    print(f'Parsed battery current   : {output_cur_csv}')


if __name__ == '__main__':
    file_path = input('Enter your .xlsx / .csv file path: ').strip()
    main(file_path)