# Agents Architecture Review & Changes Analysis

## Overview
The system has been significantly enhanced with **parameter extraction and cleaning capabilities** to handle raw telemetry data in concatenated key:value format.

---

## 1. NEW AGENT: ParameterExtractionAgent

### Purpose
Parses concatenated telemetry strings into structured DataFrame columns.

### Input Format
```
"VehicleEntity_MaxRPM:5000,fleetName:TLD MAINI,EV Battery State of Charge:95,Device_ID:6132129,..."
```

### Output Format
DataFrame with separate columns:
```
| VehicleEntity Max RPM | Fleet Name  | EV Battery State of Charge (%) | Vehicle ID |
|----------------------|-------------|------------------------------|-----------
| 5000                 | TLD MAINI   | 95                             | 6132129    |
```

### Key Features

#### 1. **Comprehensive Parameter Mapping** (60+ parameters)
Located in `PARAMETER_MAPPING` dict with structure:
```python
{
    "Canonical Parameter Name": {
        "aliases": ["raw_name1", "raw_name2", "raw_name3"],
        "unit": "measurement unit",
        "data_type": "float|int|string",
        "min": minimum_valid_value,
        "max": maximum_valid_value
    }
}
```

#### 2. **Supported Parameters by Category**

**EV Battery Parameters:**
- EV Battery State of Charge (%) - Multiple aliases including "SOC", "Energy level percentage"
- EV Battery Min/Max Cell Voltage (V)
- EV Battery Cell Temp Min/Max (°C)
- EV Battery Current (A)
- Battery Voltage (V)
- Battery Current Charge Limit (A)

**Vehicle State:**
- Veh Ignition / Veh Ignition I/O
- Veh Gear Selector (PN)
- Veh Parking Brake
- Veh Deadman Switch
- Veh Inching
- Veh Impact Event

**Charger Parameters:**
- EV Charger State
- EV Charger AC Input Current (A)
- EV Charger Output DC Current (A)
- EV Charger Output Current (A)

**Motor Parameters:**
- Veh Motor Trl Temperature (°C)
- Veh Motor Trl Inverter Temperature (°C)
- Veh Motor Trl Inverter Current (A)

**OBU (On Board Unit) Parameters:**
- OBU External Power Lost
- OBU External Power Voltage (V)
- OBU Internal Battery State (%)
- OBU Internal Battery Voltage (V)
- OBU Motion Detected
- OBU Vin State
- OBU Internal Temperature (°C)

**Alarms:**
- Alrm Harsh Braking
- Alrm Excessive Acceleration
- Alrm No Trip Motion

**Cell Identification:**
- Tmax cell ID, Tmin cell ID
- Vmax cell ID, Vmin cell ID

**Other:**
- Fleet Name, Fleet Owner Name
- Vehicle ID / Device ID
- Trip Event ID
- Speed (km/h)
- Driver / Employee Name
- VCM Vehicle Access Control State I/O

### Core Methods

#### **`extract_parameters()`**
Main extraction method with arguments:
```python
extract_parameters(
    telemetry_data,                           # TelemetryData object or DataFrame
    source_column: str = "telemetry",         # Column with key:value strings
    parameters_to_extract: Optional[List] = None,  # Specific params or all
    fill_missing_numeric_with: Optional[float] = None  # Fill NaN values
) -> ExtractionResult
```

**Process:**
1. Parses concatenated key:value strings
2. Maps raw keys to canonical parameter names
3. Converts values to proper data types
4. Creates separate columns for each parameter
5. Generates extraction report with statistics

#### **`_parse_telemetry_string()`**
Parses individual telemetry string:
- Splits by comma `,`
- Extracts key:value pairs separated by `:`
- Maps keys to canonical names (case-insensitive)
- Handles whitespace trimming

#### **`_convert_value()`**
Converts string values to proper types:
- `float`: 95 → 95.0
- `int`: 100 → 100
- `string`: "Active" → "Active"

#### **`_apply_data_type()`**
Applies pandas data type conversion after extraction

#### **`add_parameter()`**
Dynamically add new parameters:
```python
agent.add_parameter(
    parameter_name="New Parameter",
    aliases=["alias1", "alias2"],
    unit="meters",
    data_type="float",
    min_val=0,
    max_val=1000
)
```

#### **`validate_parameter_ranges()`**
Validates numeric values are within min/max bounds
Returns: Dict with parameter names and out-of-range row indices

### ExtractionResult Object
```python
ExtractionResult(
    dataframe: pd.DataFrame,              # Extracted data
    extracted_parameters: List[str],      # Parameters found
    extraction_report: Dict               # Statistics
)

# Report contains:
{
    "total_rows": 1000,
    "successful_extractions": 950,
    "failed_extractions": 50,
    "parameters_extracted": 30,
    "missing_by_parameter": {"SOC": 15, ...},
    "extraction_rate": 95.0
}
```

---

## 2. NEW: Number Cleaners Utility Module

**File:** `agents/parameter_cleaning_agents/number_cleaners.py`

### Purpose
Handles messy numeric telemetry values with units and garbage characters.

### Problem Solved
```
Raw values: "95%", "12 V", "35°C", "10A", "95.5%", "12 V ", "NaN"
Cleaned:    95.0   12.0   35.0   10.0   95.5    12.0    NaN
```

### Key Functions

#### **`_coerce_series_to_float()`**
Converts Series with messy numeric values to float:
- Handles None, NaN, "nan", "none", "null"
- Strips non-numeric characters (keeps decimal, sign, exponent)
- Returns NaN on parsing failure

#### **`clean_float_like()`**
Complete numeric cleaning with bounds checking:
```python
clean_float_like(
    series: pd.Series,
    min_val: Optional[float] = None,    # Minimum bound
    max_val: Optional[float] = None,    # Maximum bound
    clamp: bool = False                 # Clamp vs nullify outliers
)
```

**Modes:**
- `clamp=False`: Out-of-range values → NaN
- `clamp=True`: Clip values to [min_val, max_val]

---

## 3. UPDATED: CleanTelemetryAgent

**File:** `agents/clean_telemetry_agent.py`

### Changes Made

#### **New Parameters in `clean_data()` method:**
```python
clean_data(
    telemetry_data: TelemetryData,
    parameters_to_clean: Optional[List[str]] = None,
    remove_duplicates: bool = True,
    handle_missing: bool = True,
    remove_outliers: bool = True,
    
    # NEW PARAMETERS:
    extract_parameters: bool = False,           # Enable extraction
    telemetry_source_column: str = 'telemetry'  # Source column name
)
```

#### **Step 0: Parameter Extraction (NEW)**
If `extract_parameters=True`:
1. Instantiates `ParameterExtractionAgent()`
2. Calls `extract_parameters()` on the data
3. Creates new columns with extracted values
4. Uses extracted parameters for subsequent cleaning

```python
if extract_parameters and telemetry_source_column in df.columns:
    param_agent = ParameterExtractionAgent()
    extraction_result = param_agent.extract_parameters(
        df,
        source_column=telemetry_source_column,
        parameters_to_extract=parameters_to_clean
    )
    df = extraction_result.dataframe
```

#### **Step 1: Remove Duplicates**
- Same as before
- Removes rows with identical values across all columns

#### **Step 2: Clean Individual Parameters (ENHANCED)**
**Key Changes:**
- Creates `"{param}__cleaned"` columns instead of overwriting originals
- Numeric cleaning:
  - Fill missing with median
  - Remove outliers using min/max bounds
  - Rows with outliers are dropped
  
- String/categorical cleaning:
  - Fill missing with 'Unknown'
  - Passthrough without modification

```python
cleaned_col = f"{param}__cleaned"  # e.g., "SOC__cleaned"

# After cleaning:
df["{param}__cleaned"] = cleaned_values
# Original df["{param}"] preserved for audit trail
```

#### **Step 3: Timestamp Sorting**
- Sorts by timestamp column
- Resets index

### Integration Example

```python
from agents import CleanTelemetryAgent

agent = CleanTelemetryAgent()

# Method 1: Extract then clean
cleaned_data = agent.clean_data(
    telemetry_data,
    extract_parameters=True,              # Enable extraction
    telemetry_source_column='telemetry',  # Source column
    parameters_to_clean=['EV Battery State of Charge (%)', 'Speed (km/h)'],
    remove_duplicates=True,
    handle_missing=True,
    remove_outliers=True
)

# Method 2: Just clean (no extraction)
cleaned_data = agent.clean_data(
    telemetry_data,
    extract_parameters=False,
    parameters_to_clean=['column1', 'column2']
)
```

---

## 4. OVERVIEW: Complete Agent Ecosystem

### Data Flow Pipeline

```
Raw XLSX File
    ↓
LinkFMSAPIAgent (fetch from API) OR DataFetchAgent (load CSV/XLSX)
    ↓
[DataFrame with telemetry="key1:val1,key2:val2,..."]
    ↓
CleanTelemetryAgent (with extract_parameters=True)
    ├─→ ParameterExtractionAgent
    │   ├─→ Parse concatenated strings
    │   ├─→ Map to canonical names
    │   └─→ Create individual columns
    ├─→ Remove duplicates
    ├─→ Clean individual parameters
    │   ├─→ For numeric: fill missing + remove outliers
    │   └─→ For strings: fill missing
    └─→ Sort by timestamp
    ↓
[Cleaned DataFrame with separate columns: SOC, Speed, Voltage, etc.]
    ↓
TimestampAlignmentAgent (forward fill to common timestamps)
    ↓
VisualizationAgent (create charts)
    ↓
DownloadAgent (export CSV/XLSX)
```

### All 11 Agents in System

1. **DataFetchAgent** - Load from CSV/Excel files
2. **LinkFMSAPIAgent** - Fetch from LINKFMS GraphQL API
3. **ParameterExtractionAgent** ⭐ NEW - Parse concatenated key:value strings
4. **CleanTelemetryAgent** (UPDATED) - Clean with extraction step
5. **CleanDTCAgent** - Clean diagnostic trouble codes
6. **TimestampAlignmentAgent** - Forward fill alignment
7. **DisplayAgent** - Show data summaries
8. **DownloadAgent** - Export to CSV/Excel
9. **VisualizationAgent** - Create 9+ chart types
10. **OptimizeAgent** - Orchestrate full pipeline
11. **FetchDTCAgent** - Fetch DTC records

---

## 5. DETAILED PARAMETER MAPPING

### Complete List (60+ parameters)

#### Core EV Battery
| Parameter | Aliases | Unit | Type | Min | Max |
|-----------|---------|------|------|-----|-----|
| EV Battery State of Charge (%) | "SOC", "Energy level percentage (%)" | % | float | 0 | 100 |
| EV Battery Min Cell Voltage (V) | "Battery Min Voltage" | V | float | 0 | 500 |
| EV Battery Max Cell Voltage (V) | "Battery Max Voltage" | V | float | 0 | 500 |
| EV Battery Current (A) | "Battery Current" | A | float | -5000 | 5000 |

#### Vehicle State
| Parameter | Aliases | Unit | Type |
|-----------|---------|------|------|
| Veh Ignition | - | - | float |
| Veh Gear Selector (PN) | "Veh Gear Selector" | - | string |
| Veh Parking Brake | - | - | float |

#### Temperatures
| Parameter | Unit | Min | Max |
|-----------|------|-----|-----|
| EV Battery Cell Temp Min (°C) | °C | -40 | 120 |
| EV Battery Cell Temp Max (°C) | °C | -40 | 120 |
| Veh Motor Trl Temperature (°C) | °C | -40 | 250 |
| OBU Internal Temperature (°C) | °C | -40 | 200 |

#### Power & Voltage
| Parameter | Unit | Min | Max |
|-----------|------|-----|-----|
| OBU External Power Voltage (V) | V | 0 | 10000 |
| OBU Internal Battery Voltage (V) | V | 0 | 10000 |
| Battery Voltage (V) | V | 0 | 10000 |
| OBU Internal Battery State (%) | % | 0 | 100 |

#### Charger
| Parameter | Unit | Min | Max |
|-----------|------|-----|-----|
| EV Charger AC Input Current (A) | A | 0 | 1000 |
| EV Charger Output DC Current (A) | A | 0 | 1000 |

#### Metadata
| Parameter | Type | Example |
|-----------|------|---------|
| Fleet Name | string | "TLD MAINI" |
| Fleet Owner Name | string | "Alvest Group" |
| Vehicle ID | string | "6132129" |
| Driver / employeeName | string | "John Doe" |
| Trip Event ID | string | "10560504" |

#### Cell IDs
- Tmax cell ID (ID of cell with max temp)
- Tmin cell ID (ID of cell with min temp)
- Vmax cell ID (ID of cell with max voltage)
- Vmin cell ID (ID of cell with min voltage)

---

## 6. USAGE WORKFLOW

### Example: Complete Data Pipeline

```python
from agents import (
    LinkFMSAPIAgent,
    CleanTelemetryAgent,
    TimestampAlignmentAgent,
    VisualizationAgent,
    DownloadAgent
)

# Step 1: Fetch from LINKFMS API
api_agent = LinkFMSAPIAgent("username", "password")
telemetry_data = api_agent.fetch_by_date_and_vehicle(
    plate_number="T118059",
    start_date="2026-04-23",
    end_date="2026-05-12"
)

# Step 2: Extract parameters and clean
clean_agent = CleanTelemetryAgent()
cleaned = clean_agent.clean_data(
    telemetry_data,
    extract_parameters=True,                      # PARSE KEY:VALUE STRINGS
    telemetry_source_column='telemetry',
    parameters_to_clean=['EV Battery State of Charge (%)', 
                        'Speed (km/h)',
                        'EV Battery Current (A)'],
    remove_duplicates=True,
    handle_missing=True,
    remove_outliers=True
)

# Step 3: Align timestamps (forward fill)
alignment_agent = TimestampAlignmentAgent(resample_frequency="1min")
aligned = alignment_agent.align_parameters(
    cleaned,
    method='forward_fill'
)

# Step 4: Visualize
viz_agent = VisualizationAgent()
fig = viz_agent.create_line_chart(aligned, "EV Battery State of Charge (%)")

# Step 5: Download
download_agent = DownloadAgent()
download_agent.download_excel(aligned, "processed_telemetry.xlsx")
```

---

## 7. KEY ARCHITECTURAL CHANGES SUMMARY

### Before (Original)
- Loaded pre-structured CSV files
- Only cleaned existing columns
- Parameters already in separate columns

### After (Enhanced)
- **Parses concatenated key:value strings** ← MAJOR CHANGE
- **Extracts 60+ parameters from raw telemetry**
- **Creates cleaned versions with `__cleaned` suffix**
- **Preserves original columns for audit trail**
- **Handles messy numeric values with units**
- **Supports dynamic parameter addition**

### Core Enhancements
1. ✅ ParameterExtractionAgent - Parse raw strings
2. ✅ Number Cleaners - Handle units and garbage chars
3. ✅ Enhanced CleanTelemetryAgent - Integrates extraction
4. ✅ Comprehensive parameter mapping (60+ params)
5. ✅ Better data quality metrics
6. ✅ Audit trail (original + cleaned columns)

---

## 8. Error Handling & Edge Cases

### Handled Scenarios
- ✅ Missing parameters → NaN or fill value
- ✅ Invalid numeric strings → NaN
- ✅ Out-of-range values → NaN or clamp
- ✅ Empty telemetry strings → Skip
- ✅ Malformed key:value pairs → Skip
- ✅ Unknown parameter aliases → Ignore
- ✅ Mixed data types → Proper conversion

### Extraction Report
```python
{
    "total_rows": 1000,
    "successful_extractions": 950,
    "failed_extractions": 50,
    "parameters_extracted": 35,
    "missing_by_parameter": {
        "EV Battery State of Charge (%)": 15,
        "Speed (km/h)": 25,
        "EV Battery Current (A)": 5
    },
    "extraction_rate": 95.0
}
```

---

## Summary

The agent system has evolved from handling pre-structured data to processing **raw concatenated telemetry strings**. The key innovation is the **ParameterExtractionAgent** that intelligently parses hundreds of different parameter formats and aliases into clean, structured columns. Combined with numeric cleaning utilities and enhanced CleanTelemetryAgent, the system can now handle real-world messy telemetry data efficiently.

