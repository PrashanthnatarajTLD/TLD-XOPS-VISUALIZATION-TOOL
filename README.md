# EV Telemetry Analysis Platform - README

## Overview

A comprehensive multi-agent system for analyzing Electric Vehicle (EV) telemetry data with support for data fetching, cleaning, alignment, visualization, and DTC analysis.

## Project Structure

```
telemetry-app/
├── agents/                          # Agent modules
│   ├── data_fetch_agent.py         # Fetch telemetry data
│   ├── display_agent.py            # Display data
│   ├── download_agent.py           # Export data
│   ├── clean_telemetry_agent.py    # Clean telemetry
│   ├── dtc_fetch_agent.py          # Fetch DTC codes
│   ├── dtc_clean_agent.py          # Clean DTC data
│   ├── timestamp_alignment_agent.py # Align timestamps (forward fill)
│   ├── visualization_agent.py       # Create visualizations
│   ├── optimize_agent.py           # Pipeline optimization
│   └── __init__.py
├── config/
│   ├── parameters.py               # Telemetry parameter definitions
│   └── __init__.py
├── data_models/
│   ├── telemetry.py               # TelemetryData model
│   ├── dtc.py                     # DTCData model
│   └── __init__.py
├── utils/
│   ├── file_handler.py            # File I/O operations
│   ├── data_utils.py              # Data manipulation utilities
│   └── __init__.py
├── app.py                         # Main Streamlit application
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd telemetry-app
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

```bash
-M streamlit run telemetry-app\agents\linkfms_fetch_app.py --server.port 8501 
```

The application will open in your default browser at `http://localhost:8501`

### Login Credentials

The application requires LINKFMS authentication. Use these demo credentials:

| User ID | Password | Role |
|---------|----------|------|
| `admin` | `linkfms@2024` | Administrator |
| `analyst` | `analyst@2024` | Data Analyst |
| `technician` | `tech@2024` | Technician |

**See [LOGIN_GUIDE.md](LOGIN_GUIDE.md) for detailed authentication documentation.**

## Features

### 1. 🔍 **Data Fetch Agent**
- Load telemetry data from CSV or Excel files
- Auto-detect timestamp columns
- Support for multiple sheets
- Display data info and statistics

### 2. 🧹 **Clean Telemetry Agent**
- Remove duplicate records
- Handle missing values (mean/median fill)
- Remove statistical outliers
- Validate parameter ranges
- Generate cleaning reports

### 3. ⏱️ **Timestamp Alignment Agent**
- Forward fill parameters to common timestamps
- Support for multiple alignment methods:
  - Forward fill (propagate last known value)
  - Linear interpolation
  - Nearest neighbor
- Configurable resample frequencies (1min, 5min, 10min, 30min, 1H)

**Example:**
```
At 10:00 AM: SOC = 80%
At 10:20 AM: Current = 100A

After alignment at 10:20 AM:
- SOC = 80% (forward filled from 10:00)
- Current = 100A (original value)
```

### 4. 📈 **Visualization Agent**
Available graph types:
- Line Chart (time series)
- Bar Chart (distributions)
- Histogram (frequency distribution)
- Pie Chart (categorical breakdown)
- Scatter Plot (parameter correlation)
- Box Plot (statistical summary)
- Area Chart (time series with fill)
- Stacked Column Chart (multi-category)
- Heatmap (correlation matrix)

### 5. 💾 **Download Agent**
- Export to CSV format
- Export to Excel format
- Export selected columns only
- Export date range filtered data
- Export summary statistics

### 6. 📋 **DTC Analysis**
- Fetch Diagnostic Trouble Codes from files
- Clean DTC data (remove duplicates, validate codes)
- Standardize DTC code format
- Generate DTC frequency reports
- Filter by severity levels

### 7. ⚡ **Optimize Agent**
Execute complete pipeline in one operation:
1. Fetch telemetry data
2. Clean telemetry data
3. Align timestamps (optional)
4. Fetch and clean DTC data (optional)
5. Generate visualization suggestions
6. Performance metrics and execution report

## Supported Parameters

The system supports the following EV telemetry parameters:

- **EV Battery State of Charge** (%) - Battery capacity remaining
- **EV Battery Min Voltage** (V) - Minimum cell voltage
- **EV Battery Max Voltage** (V) - Maximum cell voltage
- **EV Battery Current** (A) - Battery charge/discharge current
- **EV Battery Temperature** (°C) - Battery pack temperature
- **Vehicle Speed** (km/h) - Vehicle velocity
- **Motor Power** (kW) - Motor output power
- **Motor RPM** (rpm) - Motor speed
- **Motor Temperature** (°C) - Motor thermal state
- **Odometer** (km) - Total distance traveled
- **Engine State** - Running/Idle/Off status
- **Charger Connection** - Connected/Disconnected status

## File Format Requirements

### Telemetry Data
- **CSV or Excel format**
- **Required columns**: Date/Timestamp, Parameter columns
- **Supported timestamp names**: date, datetime, timestamp, time, dateprocessed

### DTC Data
- **CSV or Excel format**
- **Required columns**: Timestamp, DTC Code
- **Optional columns**: Description, Severity, Parameter Affected

## Data Cleaning Configuration

Default cleaning parameters (configurable in `config/parameters.py`):

- **Outlier detection method**: IQR (Interquartile Range)
- **IQR multiplier**: 1.5
- **Z-score threshold**: 3 (alternative method)
- **Missing value handling**: Mean/Median fill for numeric, 'Unknown' for categorical

## Timestamp Alignment Details

The timestamp alignment agent uses forward fill to synchronize parameters measured at different times:

1. **Resample** data to uniform time intervals
2. **Forward fill** (propagate last known value forward)
3. **Handle cross-midnight** scenarios
4. **Validate** timestamp monotonicity

This ensures precise analysis when different sensors update at different intervals.

## Usage Examples

### Example 1: Basic Analysis
1. Go to "Fetch Data" → Upload telemetry file
2. Go to "Clean Data" → Select parameters → Clean
3. Go to "Visualize" → Select parameter → Generate charts
4. Go to "Download" → Export processed data

### Example 2: Advanced Analysis with Alignment
1. Fetch telemetry data
2. Clean data
3. Align timestamps (1min frequency, forward fill)
4. Visualize aligned data
5. Export aligned dataset

### Example 3: Full Pipeline Optimization
1. Go to "Optimize Pipeline"
2. Upload telemetry file
3. (Optional) Upload DTC file
4. Click "Run Full Pipeline"
5. Review execution report and metrics

## Performance Considerations

- **Forward fill limit**: None (unlimited propagation)
- **Resample frequency**: Default 1 minute (adjustable)
- **Memory usage**: Depends on dataset size
- **Processing time**: Typically <5 seconds for 100K rows

## Troubleshooting

### Issue: "Timestamp column not found"
**Solution**: Check file format and timestamp column name. Use the text input to specify column name.

### Issue: "No numeric columns for visualization"
**Solution**: Ensure selected parameter is numeric. Use Bar/Pie charts for categorical data.

### Issue: Forward fill creates too much data
**Solution**: Adjust resample frequency to a larger interval (5min, 10min, etc.)

## API Reference

### DataFetchAgent
```python
fetch_agent = DataFetchAgent()
data = fetch_agent.fetch_from_file("data.csv", timestamp_column="timestamp")
```

### CleanTelemetryAgent
```python
clean_agent = CleanTelemetryAgent()
cleaned = clean_agent.clean_data(data, parameters_to_clean=['SOC', 'Current'])
report = clean_agent.get_cleaning_report()
```

### TimestampAlignmentAgent
```python
alignment = TimestampAlignmentAgent(resample_frequency="1min")
aligned = alignment.align_parameters(data, method="forward_fill")
```

### VisualizationAgent
```python
viz = VisualizationAgent()
fig = viz.create_line_chart(data, "EV Battery State of Charge")
fig.show()
```

### OptimizeAgent
```python
optimizer = OptimizeAgent()
results = optimizer.optimize_full_pipeline(
    telemetry_file="data.csv",
    align_timestamps=True,
    resample_frequency="1min"
)
```

## Contributing

Contributions are welcome! Please ensure:
- Code follows Python style guidelines
- New agents inherit from base classes
- Documentation is updated
- Tests are included for new features

## License

This project is provided as-is for EV telemetry analysis purposes.

## Support

For issues or questions, please refer to the agent documentation or check the execution logs in the Streamlit app.

---

**Version**: 1.0  
**Last Updated**: May 2026  
**Language**: Python 3.8+
