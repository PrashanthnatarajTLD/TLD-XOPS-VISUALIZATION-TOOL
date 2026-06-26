# Agent Architecture - Visual Reference & Quick Guide

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EV TELEMETRY PIPELINE                               │
└─────────────────────────────────────────────────────────────────────────────┘

INPUT SOURCES:
┌─────────────────┐  ┌──────────────────┐
│  LINKFMS API    │  │  CSV/XLSX Files  │
│  GraphQL Query  │  │  Upload UI       │
└────────┬────────┘  └─────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    │
         ┌──────────▼──────────┐
         │  DataFetchAgent OR  │
         │  LinkFMSAPIAgent    │
         └─────────┬──────────┘
                   │
              df["telemetry"] = "key1:val1,key2:val2,..."
                   │
        ┌──────────▼─────────────────────────────┐
        │   CleanTelemetryAgent.clean_data()     │
        │   (with extract_parameters=True)       │
        └──────────┬──────────────────────────────┘
                   │
      ┌────────────▼──────────────┐
      │ STAGE 0: EXTRACTION       │  ◄─ NEW!
      │ ═════════════════════════ │
      │                           │
      │ ParameterExtractionAgent  │
      │ • Parse "key:value" pairs │
      │ • Map to canonical names  │
      │ • Create columns          │
      │ • Type conversion         │
      │                           │
      │ Output:                   │
      │ ├─ SOC__cleaned (%)       │
      │ ├─ Speed__cleaned (km/h)  │
      │ ├─ Current__cleaned (A)   │
      │ └─ ... 60+ parameters     │
      └──────────┬─────────────────┘
                 │
      ┌──────────▼─────────────────────────┐
      │ STAGE 1: REMOVE DUPLICATES         │
      │ ═══════════════════════════════════ │
      │ Removes identical rows             │
      └──────────┬─────────────────────────┘
                 │
      ┌──────────▼──────────────────────────────┐
      │ STAGE 2: CLEAN INDIVIDUAL PARAMETERS   │
      │ ══════════════════════════════════════ │
      │                                       │
      │ For NUMERIC columns:                 │
      │ • Fill missing values (median)       │
      │ • Remove outliers (min/max bounds)   │
      │ • Clip or nullify out-of-range       │
      │ • Create "{param}__cleaned" column   │
      │                                       │
      │ For STRING columns:                  │
      │ • Fill missing values ('Unknown')    │
      │ • Create "{param}__cleaned" column   │
      │                                       │
      │ Numeric Cleaning via:                │
      │ • number_cleaners.clean_float_like() │
      │ • Handles units: "95%", "12 V"       │
      └──────────┬──────────────────────────────┘
                 │
      ┌──────────▼────────────────────┐
      │ STAGE 3: SORT BY TIMESTAMP    │
      │ ═══════════════════════════════ │
      │ Ensures chronological order   │
      └──────────┬────────────────────┘
                 │
        ┌────────▼─────────────┐
        │  CLEANED DATA        │
        │ (original + cleaned) │
        └────────┬─────────────┘
                 │
      ┌──────────▼──────────────────┐
      │ TimestampAlignmentAgent      │
      │ • Forward fill to freq       │
      │ • Align all params to common │
      │   timestamps (5min, 1H, etc) │
      └──────────┬──────────────────┘
                 │
      ┌──────────▼──────────────────┐
      │ VisualizationAgent           │
      │ • Line, Bar, Scatter charts  │
      │ • Heatmaps, Box plots, etc   │
      └──────────┬──────────────────┘
                 │
      ┌──────────▼──────────────────┐
      │ DisplayAgent                 │
      │ • Statistics, summaries      │
      │ • Data preview               │
      └──────────┬──────────────────┘
                 │
      ┌──────────▼──────────────────┐
      │ DownloadAgent                │
      │ • Export CSV/Excel           │
      │ • Maintain audit trail       │
      └──────────────────────────────┘
```

---

## Agent Interaction Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      AGENT ECOSYSTEM                             │
└──────────────────────────────────────────────────────────────────┘

DATA SOURCES:
  LinkFMSAPIAgent ──┐
                    ├──► [TelemetryData DataFrame]
  DataFetchAgent ──┤
                    └──► [source: LINKFMS API or CSV]


PROCESSING PIPELINE:
  
  [TelemetryData]
        │
        └──► ParameterExtractionAgent ◄────┐
                    │                       │
                    └──► [Extracted Cols]   │ Called by
                            │               │ CleanTelemetryAgent
        [Extracted DataFrame] 
                    │
                    └──► CleanTelemetryAgent
                         • Remove duplicates
                         • Handle missing
                         • Remove outliers
                         • Create __cleaned cols
                            │
                            ├─► TimestampAlignmentAgent
                            │    │
                            │    └─► [Aligned Data]
                            │
                            ├─► VisualizationAgent
                            │    │
                            │    └─► [Charts]
                            │
                            ├─► DisplayAgent
                            │    │
                            │    └─► [Stats, Preview]
                            │
                            └─► DownloadAgent
                                 │
                                 └─► [CSV/XLSX Export]


ORCHESTRATION:
  
  OptimizeAgent ──► Execute All Steps
                   └─► Fetch + Extract + Clean + Align 
                       + Visualize + Download
                       (Full Pipeline)
```

---

## ParameterExtractionAgent - Detailed Flow

```
┌──────────────────────────────────────────────────────────────────┐
│         PARAMETER EXTRACTION DETAILED PROCESS                   │
└──────────────────────────────────────────────────────────────────┘

INPUT: DataFrame with column
  df["telemetry"] = [
    "VehicleEntity_MaxRPM:5000,EV Battery State of Charge:95,...",
    "VehicleEntity_MaxRPM:4500,EV Battery State of Charge:87,...",
    ...
  ]

STEP 1: INITIALIZATION
  ├─ Load PARAMETER_MAPPING (60+ parameters)
  ├─ Build extraction_mapping (aliases → canonical names)
  └─ Initialize empty columns for each target parameter

STEP 2: FOR EACH ROW:
  │
  ├─ Get telemetry string: "key1:val1,key2:val2,..."
  │
  ├─ PARSE STRING:
  │  ├─ Split by comma: ["key1:val1", "key2:val2", ...]
  │  ├─ For each pair:
  │  │  ├─ Split by colon: key="key1", value="val1"
  │  │  ├─ Map key to canonical name (case-insensitive)
  │  │  ├─ Store: {canonical_name: value}
  │  │  └─ Skip if unknown key
  │  └─ Result: {param1: value1, param2: value2, ...}
  │
  ├─ EXTRACT VALUES:
  │  ├─ For each target parameter:
  │  │  ├─ Get value from parsed dict
  │  │  ├─ Convert to proper type (float/int/string)
  │  │  ├─ Assign to df[parameter][row]
  │  │  └─ Track missing if not found
  │  └─ Result: Row has all parameter columns filled
  │
  └─ Increment success counter

STEP 3: DATA TYPE CONVERSION
  ├─ For each extracted parameter:
  │  ├─ Get data_type from PARAMETER_MAPPING
  │  ├─ Apply pandas conversion
  │  │  ├─ "float" → pd.to_numeric(..., errors='coerce')
  │  │  ├─ "int" → convert to Int64 with NaN support
  │  │  └─ "string" → str type
  │  └─ Result: Column has correct dtype
  └─ NaN values preserved for missing/invalid

STEP 4: OPTIONAL FILLING
  ├─ If fill_missing_numeric_with provided:
  │  ├─ Find all numeric columns with NaN
  │  ├─ Fill NaN with specified value
  │  └─ Example: Fill with 0 for sensors not sending data
  └─ Result: No NaN in specified columns

STEP 5: GENERATE REPORT
  ├─ total_rows: Count of input rows
  ├─ successful_extractions: Rows processed
  ├─ failed_extractions: Rows skipped (empty/malformed)
  ├─ parameters_extracted: Count of parameters found
  ├─ missing_by_parameter: Dict of NaN counts per parameter
  ├─ extraction_rate: Success % = successful / total * 100
  └─ Result: ExtractionResult object

OUTPUT: DataFrame with new columns
  df["EV Battery State of Charge (%)"] = [95.0, 87.0, ...]
  df["Speed (km/h)"] = [45.5, 32.1, ...]
  df["EV Battery Current (A)"] = [25.3, 18.7, ...]
  df["VehicleEntity Max RPM"] = [5000.0, 4500.0, ...]
  ... (60+ columns)
```

---

## Alias Mapping Example

```
RAW KEY (from telemetry string)    →    CANONICAL NAME (Column)
═══════════════════════════════════     ═══════════════════════════

"EV Battery State of Charge"           "EV Battery State of Charge (%)"
"EV Battery State of Charge (%)"       "EV Battery State of Charge (%)"
"EV Battery State of Charge (% )"      "EV Battery State of Charge (%)"
"Battery SOC"                          "EV Battery State of Charge (%)"
"SOC"                                  "EV Battery State of Charge (%)"
"Energy level percentage (%)"          "EV Battery State of Charge (%)"
"Energy level percentage %"            "EV Battery State of Charge (%)"
"Energy level percentage"              "EV Battery State of Charge (%)"
"StateOfCharge"                        "EV Battery State of Charge (%)"

↓ All variations map to same canonical name ↓
↓ Creates single column with consistent name ↓

OUTPUT COLUMN: df["EV Battery State of Charge (%)"]

Same process for all 60+ parameters
```

---

## Numeric Cleaning Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│            NUMBER CLEANERS CLEANING PROCESS                     │
└──────────────────────────────────────────────────────────────────┘

INPUT VALUES (messy):
  "95%", "12 V", "35°C", "10A", "95.5%", "12 V ", "NaN", "", None

STEP 1: COERCE TO FLOAT (_coerce_series_to_float)
  ├─ "95%" → strip "%" → "95" → 95.0 ✓
  ├─ "12 V" → strip "V" → "12" → 12.0 ✓
  ├─ "35°C" → strip "°C" → "35" → 35.0 ✓
  ├─ "10A" → strip "A" → "10" → 10.0 ✓
  ├─ "95.5%" → strip "%" → "95.5" → 95.5 ✓
  ├─ "NaN" → recognized → NaN
  ├─ "" (empty) → NaN
  └─ None → NaN

OUTPUT: [95.0, 12.0, 35.0, 10.0, 95.5, NaN, NaN, NaN]

STEP 2: BOUNDS CHECKING (clean_float_like)
  
  With min_val=0, max_val=100, clamp=False:
  ├─ 95.0: 0 ≤ 95.0 ≤ 100 ✓ → 95.0
  ├─ 12.0: 0 ≤ 12.0 ≤ 100 ✓ → 12.0
  ├─ 35.0: 0 ≤ 35.0 ≤ 100 ✓ → 35.0
  ├─ 10.0: 0 ≤ 10.0 ≤ 100 ✓ → 10.0
  ├─ 95.5: 0 ≤ 95.5 ≤ 100 ✓ → 95.5
  ├─ -5.0: -5.0 < 0 ✗ → NaN (outlier)
  ├─ 150.0: 150.0 > 100 ✗ → NaN (outlier)
  └─ NaN: → NaN (already)

OUTPUT: [95.0, 12.0, 35.0, 10.0, 95.5, NaN, NaN, NaN]

ALTERNATIVE WITH clamp=True:
  ├─ -5.0: clip(lower=0) → 0.0 ✓
  ├─ 150.0: clip(upper=100) → 100.0 ✓
  └─ NaN: → NaN (unchanged)

OUTPUT: [95.0, 12.0, 35.0, 10.0, 95.5, 0.0, 100.0, NaN]
```

---

## CleanTelemetryAgent Processing

```
┌──────────────────────────────────────────────────────────────────┐
│         CLEAN TELEMETRY AGENT - 3 STAGE PROCESS                 │
└──────────────────────────────────────────────────────────────────┘

INPUT: 
  ├─ TelemetryData object
  ├─ Columns: ["timestamp", "telemetry", ...]
  │           telemetry = "key1:val1,key2:val2,..."
  └─ Parameters to clean: ["SOC", "Speed", "Current"]


STAGE 0: EXTRACT PARAMETERS (if extract_parameters=True)
  │
  ├─ Instantiate ParameterExtractionAgent
  ├─ Call extract_parameters()
  ├─ Adds columns: ["SOC", "Speed", "Current", ...]
  └─ If parameters_to_clean=None, use extracted params

  Before:
    timestamp | telemetry
    ─────────┼─────────────────────────
    10:00    | "SOC:95,Speed:45,..."

  After:
    timestamp | SOC  | Speed | ... 
    ─────────┼──────┼───────┼────
    10:00    | 95.0 | 45.0  | ...


STAGE 1: REMOVE DUPLICATES (if remove_duplicates=True)
  │
  ├─ Find rows with identical values across all columns
  ├─ Keep first occurrence
  ├─ Drop duplicates
  └─ Report: "Removed X duplicate rows"

  Before:  1000 rows
  After:   985 rows (15 duplicates removed)


STAGE 2: CLEAN INDIVIDUAL PARAMETERS (if handle_missing/remove_outliers)
  │
  ├─ For each parameter in parameters_to_clean:
  │
  ├─ IF NUMERIC:
  │  │
  │  ├─ Handle missing (if handle_missing=True):
  │  │  ├─ Count NaN values
  │  │  ├─ Fill with median
  │  │  └─ Create "{param}__cleaned" column
  │  │
  │  ├─ Remove outliers (if remove_outliers=True):
  │  │  ├─ Get min/max bounds from config
  │  │  ├─ Find rows outside bounds
  │  │  ├─ Drop those rows (row-level filtering)
  │  │  └─ Report: "Removed X outliers from {param}"
  │  │
  │  └─ Result: Clean numeric values in "{param}__cleaned"
  │
  ├─ IF STRING/CATEGORICAL:
  │  │
  │  ├─ Handle missing (if handle_missing=True):
  │  │  ├─ Replace NaN with "Unknown"
  │  │  └─ Create "{param}__cleaned" column
  │  │
  │  └─ Result: Strings in "{param}__cleaned"
  │
  └─ NOTE: Original columns preserved for audit trail

  Before:
    SOC (original) | Speed (original) |
    ───────────────┼─────────────────┤
    95.0           | 45.0            |
    NaN            | 32.1            |
    150.0 (outlier)| 20.5            |

  After:
    SOC__cleaned | Speed__cleaned |
    ─────────────┼────────────────┤
    95.0         | 45.0           |
    93.5 (median)| 32.1           |
    [row removed]|                |


STAGE 3: SORT BY TIMESTAMP
  │
  ├─ Sort all rows by timestamp column ascending
  ├─ Reset index (0-based sequential)
  └─ Report: "Data sorted by timestamp"

  Before:
    timestamp
    ─────────
    10:15
    10:00
    10:30

  After:
    timestamp
    ─────────
    10:00
    10:15
    10:30


OUTPUT:
  ├─ Original columns: ["timestamp", "telemetry", "SOC", "Speed", ...]
  ├─ New cleaned columns: ["SOC__cleaned", "Speed__cleaned", ...]
  ├─ Removed rows: 15 (duplicates) + X (outliers)
  ├─ Cleaned rows: Original - Removed
  └─ CleaningReport with full statistics
```

---

## Quick Reference - Method Signatures

```python
# ParameterExtractionAgent
agent = ParameterExtractionAgent()

extract_parameters(
    telemetry_data,                           # DataFrame or TelemetryData
    source_column: str = "telemetry",         # Column with "key:val,..." strings
    parameters_to_extract: Optional[List] = None,  # Which params to extract
    fill_missing_numeric_with: Optional[float] = None  # Fill NaN with value
) -> ExtractionResult

validate_parameter_ranges(df) -> Dict[str, List[int]]  # Out-of-range rows
add_parameter(name, aliases, unit, data_type, min_val, max_val)  # Add new param
get_available_parameters() -> List[str]  # All available params
get_parameter_info(param_name) -> Dict  # Parameter details
get_extraction_report() -> Dict  # Last extraction stats


# CleanTelemetryAgent
agent = CleanTelemetryAgent()

clean_data(
    telemetry_data: TelemetryData,
    parameters_to_clean: Optional[List[str]] = None,
    remove_duplicates: bool = True,
    handle_missing: bool = True,
    remove_outliers: bool = True,
    extract_parameters: bool = False,        # NEW!
    telemetry_source_column: str = 'telemetry'  # NEW!
) -> TelemetryData


# Number Cleaners
clean_float_like(
    series: pd.Series,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    clamp: bool = False  # False=nullify, True=clip
) -> pd.Series
```

---

## Parameter Statistics

```
TOTAL PARAMETERS SUPPORTED: 60+

BREAKDOWN BY CATEGORY:
├─ EV Battery: 12 parameters
├─ Vehicle State: 7 parameters
├─ Charger: 4 parameters
├─ Motor: 3 parameters
├─ OBU: 8 parameters
├─ Alarms: 3 parameters
├─ Temperature: 4+ parameters
├─ Voltage/Power: 5+ parameters
├─ Cell IDs: 4 parameters
└─ Metadata: 4+ parameters

DATA TYPES:
├─ Float: ~45 parameters
├─ String: ~10 parameters
└─ Int: ~5 parameters

SUPPORTED ALIASES PER PARAMETER:
├─ Min: 1 alias
├─ Avg: 3-5 aliases
└─ Max: 10+ aliases (e.g., SOC has 9 variations)
```

