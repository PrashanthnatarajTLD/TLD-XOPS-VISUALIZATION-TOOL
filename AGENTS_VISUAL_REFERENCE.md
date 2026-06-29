# Agent Architecture - Visual Reference and Current Guide

Last updated: 2026-06-26

This document reflects the current code in the agents folder.

## Current Top-Level Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        TLD/XOPS VISUALIZATION TOOL                          │
│                         agents/linkfms_fetch_app.py                         │
└──────────────────────────────────────────────────────────────────────────────┘

                Login
                  │
                  ▼
        agents/login_page_agent.py
                  │
                  ▼
        Select Data Type to Fetch
  ┌────────────────┼────────────────┐
  │                │                │
  ▼                ▼                ▼
Raw Telemetry      DTC              Visualize + KPI
  │                │                │
  │                │                │
  ▼                ▼                ▼
agents/linkfms_api_agent.py   agents/linkfms_dtc_agent.py
  │                │                │
  ▼                ▼                ▼
ParameterExtractionAgent      DTC dataframe in session
  │
  ▼
Alignment/fill in app UI
  │
  ▼
Preview + CSV/Excel downloads + Charts + KPI + HTML exports
```

## Important Current Behavior

1. Linked DTC + Raw Telemetry option is removed from Streamlit UI.
2. Raw telemetry fetch is batch-based by date range.
3. Parameter extraction reads telemetry_raw and creates structured columns.
4. EngineCodeDescription, Source, and EngineCode are no-fill columns.
5. Ops Work Mode 1 is fillable by selected alignment mode.
6. Date display/export includes seconds (YYYY-MM-DD HH:MM:SS).

## Agent Inventory (All Files Under agents)

### Core Pipeline Agents

| File | Purpose | Key Methods / Functions | Notes |
|---|---|---|---|
| agents/data_fetch_agent.py | Load telemetry from files and build TelemetryData | fetch_from_file, fetch_multiple_sheets, get_data_info | Uses ColumnUniquenessAgent while preserving duplicate semantics when needed |
| agents/clean_telemetry_agent.py | Telemetry cleaning and optional extraction-driven cleaning | clean_data, validate_parameter_ranges, get_cleaning_report | Creates param__cleaned columns, supports extract_parameters=True |
| agents/parameter_extraction_agent.py | Parse telemetry key-value strings into canonical columns | extract_parameters, add_parameter, validate_parameter_ranges | Supports key:value and key=value, bracket-safe parsing, engine-code nested payload parsing |
| agents/timestamp_alignment_agent.py | Align timestamps and fill/interpolate values | align_parameters, forward_fill_specific_parameters, get_alignment_summary | Supports forward_fill, backward_fill, interpolate, nearest |
| agents/visualization_agent.py | Telemetry and DTC chart generation | time_series, soc_current_dual, temperature_chart, dtc_frequency_bar, dtc_timeline, etc. | Plotly-based chart library for app views |
| agents/kpi_agent_v2.py | KPI calculations (daily/weekly, segment-based durations) | calculate_metrics + chart/report helpers | Current KPI implementation used by app |
| agents/kpi_agent.py | Older KPI logic | calculate_metrics + chart/report helpers | Legacy variant; keep for backward compatibility |

### LINKFMS API Agents

| File | Purpose | Key Methods / Functions | Notes |
|---|---|---|---|
| agents/linkfms_api_agent.py | Fetch telemetry from LINKFMS GraphQL | fetch_by_date_and_vehicle, fetch_by_filters, get_data_summary | Converts telemetry -> telemetry_raw, dateProcessed -> timestamp |
| agents/linkfms_dtc_agent.py | Fetch DTC records from LINKFMS GraphQL | fetch | Flattens nested equipment/model/org fields |
| agents/linkfms_fetch_app.py | Main Streamlit app orchestration | show_main_app | Data types: Raw Telemetry, DTC, Visualize, KPI Dashboard |
| agents/login_page_agent.py | Isolated login UI rendering | render_login_page | Uses LoginManager session flow |

### DTC and Utility Agents

| File | Purpose | Key Methods / Functions | Notes |
|---|---|---|---|
| agents/dtc_fetch_agent.py | File-based DTC loading | fetch_from_file, fetch_multiple_sheets, get_dtc_summary | Auto-detects timestamp and DTC code columns |
| agents/dtc_clean_agent.py | DTC cleaning and code standardization | clean_data, standardize_dtc_codes, remove_duplicate_dtcs_per_timestamp | Removes invalid/missing code entries |
| agents/display_agent.py | Dataset summaries/statistics helpers | display_summary, display_statistics, display_missing_values | Read-only data inspection helpers |
| agents/download_agent.py | Export telemetry to CSV/Excel and filtered subsets | download_csv, download_excel, download_filtered, download_date_range | Enforces unique export-safe column names |
| agents/column_uniqueness_agent.py | Normalize and de-duplicate semantic column names | make_unique | rename_duplicates True/False modes |
| agents/optimize_agent.py | End-to-end file pipeline orchestration | optimize_full_pipeline, estimate_processing_time, get_pipeline_report | Useful for staged batch processing outside app UI |

### HTML Export Agents

| File | Purpose | Key Methods / Functions | Notes |
|---|---|---|---|
| agents/save_html_visualize_agent.py | Build visual report HTML from Plotly figures | build_visualize_export_html | Uses VisualizeExportContext metadata |
| agents/save_html_kpi_agent.py | Build KPI report HTML from Plotly figures | build_kpi_export_html | Uses KPIExportContext and KPI cards |

### Parameter Cleaning Subpackage

| File | Purpose | Key Methods / Functions | Notes |
|---|---|---|---|
| agents/parameter_cleaning_agents/number_cleaners.py | Float-like numeric cleaning utilities | clean_float_like | Strips unit tokens and applies bounds/clamp |
| agents/parameter_cleaning_agents/__init__.py | Re-export package API | clean_float_like export | Convenience import layer |

### Package and Backup

| File | Purpose | Notes |
|---|---|---|
| agents/__init__.py | Package exports for major agents | Includes core agent classes |
| agents/linkfms_fetch_app.py.backup | Backup copy of app file | Reference only, not active execution target |

## Raw Telemetry Processing (Current)

```
Raw LINKFMS batch fetch
      │
      ▼
TelemetryData dataframe
      │
      ▼
ParameterExtractionAgent.extract_parameters(source_column="telemetry_raw")
      │
      ▼
Drop selected raw API columns
      │
      ▼
Apply alignment_method in UI:
- forward_fill
- backward_fill
- interpolate
- nearest
      │
      ├─ no fill on: EngineCodeDescription, Source, EngineCode
      └─ fill allowed on: Ops Work Mode 1 and other columns
      ▼
Timezone conversion for date/dateReceived/dateProcessed
      │
      ▼
Preview + styled fill mask + CSV/Excel export
```

## DTC Processing (Current)

```
LINKFMS DTC GraphQL fetch
      │
      ▼
Flatten nested response fields
      │
      ▼
Convert timestamp to UTC
      │
      ▼
Timezone display conversion in app
      │
      ▼
DTC preview + CSV/Excel export
```

## ParameterExtractionAgent Notes (Current)

1. Supports telemetry alias mapping to canonical names.
2. Parses key:value and key=value pairs.
3. Comma splitting is bracket-aware for nested payloads.
4. Extracts nested AccessoryEvent_EngineCodeDetails values.
5. Populates EngineCodeDescription, Source, EngineCode from nested detail lists.
6. Preserves missing string values as true nulls for proper fill behavior.

## Streamlit Options (Current)

```
Select Data Type to Fetch:
- Raw Telemetry
- DTC (Diagnostic Trouble Codes)
- Visualize
- KPI Dashboard
```

No linked timestamp-join mode is currently active in the app UI.

## Quick Method Reference

### Telemetry fetch

- agents/linkfms_api_agent.py
- fetch_by_date_and_vehicle(plate_number, start_date, end_date, page_size=..., filter_diagnostic=False)

### DTC fetch

- agents/linkfms_dtc_agent.py
- fetch(plate_number, start_date, end_date, page_size=...)

### Parameter extraction

- agents/parameter_extraction_agent.py
- extract_parameters(telemetry_data, source_column="telemetry", parameters_to_extract=None, fill_missing_numeric_with=None)

### Timestamp alignment

- agents/timestamp_alignment_agent.py
- align_parameters(telemetry_data, method="forward_fill", resample_freq=None)

### KPI

- agents/kpi_agent_v2.py
- calculate_metrics(df, timestamp_col="dateProcessed", ...)

## Maintenance Checklist for Future Updates

1. If Streamlit fetch options change, update Streamlit Options and Top-Level Flow.
2. If new agents are added, update Agent Inventory tables.
3. If extraction aliases change, update ParameterExtractionAgent Notes.
4. If export behavior changes, update Raw Telemetry Processing and DTC Processing sections.
