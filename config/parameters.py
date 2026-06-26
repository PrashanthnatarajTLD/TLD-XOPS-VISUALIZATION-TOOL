"""Configuration for telemetry parameters."""

# Standard EV telemetry parameters
TELEMETRY_PARAMETERS = {
    "EV Battery State of Charge": {
        "unit": "%",
        "min": 0,
        "max": 100,
        "data_type": "float",
        "description": "Battery state of charge percentage"
    },
    "EV Battery Min Voltage": {
        "unit": "V",
        "min": 0,
        "max": 500,
        "data_type": "float",
        "description": "Minimum voltage in battery pack"
    },
    "EV Battery Max Voltage": {
        "unit": "V",
        "min": 0,
        "max": 500,
        "data_type": "float",
        "description": "Maximum voltage in battery pack"
    },
    "EV Battery Current": {
        "unit": "A",
        "min": -500,
        "max": 500,
        "data_type": "float",
        "description": "Battery current (positive: discharge, negative: charge)"
    },
    "EV Battery Temperature": {
        "unit": "°C",
        "min": -40,
        "max": 80,
        "data_type": "float",
        "description": "Battery temperature"
    },
    "Vehicle Speed": {
        "unit": "km/h",
        "min": 0,
        "max": 200,
        "data_type": "float",
        "description": "Vehicle speed"
    },
    "Motor Power": {
        "unit": "kW",
        "min": -300,
        "max": 300,
        "data_type": "float",
        "description": "Motor power output"
    },
    "Motor RPM": {
        "unit": "rpm",
        "min": 0,
        "max": 10000,
        "data_type": "float",
        "description": "Motor RPM"
    },
    "Motor Temperature": {
        "unit": "°C",
        "min": -40,
        "max": 150,
        "data_type": "float",
        "description": "Motor temperature"
    },
    "Odometer": {
        "unit": "km",
        "min": 0,
        "max": 999999,
        "data_type": "float",
        "description": "Vehicle odometer reading"
    },
    "Engine State": {
        "unit": "state",
        "data_type": "string",
        "description": "Engine/Motor state (Running, Idle, Off)"
    },
    "Charger Connection": {
        "unit": "state",
        "data_type": "string",
        "description": "Charger connection status (Connected, Disconnected)"
    },
}

# Parameters for data cleaning
CLEANING_CONFIG = {
    "remove_duplicates": True,
    "handle_missing_values": True,
    "remove_outliers": True,
    "outlier_method": "iqr",  # Options: "iqr", "zscore"
    "iqr_multiplier": 1.5,
    "zscore_threshold": 3,
    "datetime_format": "%Y-%m-%d %H:%M:%S",
}

# Visualization configuration
GRAPH_TYPES = [
    "Line Chart",
    "Bar Chart",
    "Histogram",
    "Pie Chart",
    "Stacked Column Chart",
    "Scatter Plot",
    "Box Plot",
    "Area Chart",
    "Heatmap",
]

# Time alignment configuration
TIME_ALIGNMENT_CONFIG = {
    "method": "forward_fill",  # Options: "forward_fill", "interpolate", "nearest"
    "resample_frequency": "1min",  # Resample to 1-minute intervals
    "fill_limit": None,  # None means unlimited forward fill
}
