"""
Parameter Extraction Agent - Parses concatenated telemetry key:value strings into structured columns
Handles extraction of specific parameters from raw telemetry data format
"""

import pandas as pd
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    """Result of parameter extraction operation"""
    dataframe: pd.DataFrame
    extracted_parameters: List[str]
    extraction_report: Dict
    
    def summary(self) -> str:
        """Get extraction summary"""
        report = self.extraction_report
        return f"""
        Extraction Summary:
        ==================
        Total Rows Processed: {report.get('total_rows', 0)}
        Successfully Extracted: {report.get('successful_extractions', 0)}
        Failed Extractions: {report.get('failed_extractions', 0)}
        Parameters Found: {len(self.extracted_parameters)}
        Extracted Parameters: {', '.join(self.extracted_parameters)}
        Missing Values by Parameter: {report.get('missing_by_parameter', {})}
        """


class ParameterExtractionAgent:
    """
    Extracts structured parameters from concatenated telemetry key:value strings
    
    Input format: "key1:value1,key2:value2,key3:value3,..."
    Output: DataFrame with separate columns for each parameter
    """
    
    # Define the telemetry parameters to extract and their properties
    #
    # Canonical parameter names are used as column names after extraction.
    # Aliases must match the raw keys exactly as they appear in the telemetry string
    # (case-insensitive, leading/trailing spaces tolerated).
    PARAMETER_MAPPING = {
        # EV Battery Parameters
        "EV Battery State of Charge (%)": {
            "aliases": [
                "EV Battery State of Charge (%)",
                "EV Battery State of Charge",
                "EV Battery State of Charge (% )",
                "Battery SOC",
                "SOC",
                "Energy level percentage (%)",
                "Energy level percentage %",
                "Energy level percentage",
                "EV Battery State of Charge (% )",
                "Battery SOC (%)",
                "SOC (%)",
                "State of Charge"
            ],
            "unit": "%",
            "data_type": "float",
            "min": 0,
            "max": 100
        },
        "EV Battery Cell Temp Min": {
            "aliases": ["EV Battery Cell Temp Min", "Battery Temp Min", "MinCellTemp", "EV Battery Cell Temperature Min"],
            "unit": "°C",
            "data_type": "float",
            "min": -40,
            "max": 80
        },
        "EV Battery Cell Temp Max": {
            "aliases": ["EV Battery Cell Temp Max", "Battery Temp Max", "MaxCellTemp", "EV Battery Cell Temperature Max"],
            "unit": "°C",
            "data_type": "float",
            "min": -40,
            "max": 80
        },
        "Driver": {
            "aliases": ["Driver", "employeeName", "Employee Name"],
            "unit": "",
            "data_type": "string",
            "min": None,
            "max": None
        },
        "EV Charger Connection": {
            "aliases": ["EV Charger Connection", "Charger Connection", "ChargingStatus"],
            "unit": "",
            "data_type": "string",
            "min": None,
            "max": None
        },
        "EV Charger Output Current": {
            "aliases": ["EV Charger Output Current", "Charger Current", "ChargerCurrent"],
            "unit": "A",
            "data_type": "float",
            "min": 0,
            "max": 100
        },
        "Vehicle ID": {
            "aliases": ["Vehicle ID", "Device_ID", "DeviceID"],
            "unit": "",
            "data_type": "string",
            "min": None,
            "max": None
        },
        "Fleet Name": {
            "aliases": ["Fleet Name", "fleetName"],
            "unit": "",
            "data_type": "string",
            "min": None,
            "max": None
        },
        "Fleet Owner Name": {
            "aliases": ["Fleet Owner Name", "fleetOwnerName"],
            "unit": "",
            "data_type": "string",
            "min": None,
            "max": None
        },
        "VehicleEntity Max RPM": {
            "aliases": ["VehicleEntity_MaxRPM", "Max RPM", "MaxRPM"],
            "unit": "RPM",
            "data_type": "float",
            "min": 0,
            "max": 10000
        },
        "VehicleEntity Max Idle": {
            "aliases": ["VehicleEntity_MaxIdle", "Max Idle", "MaxIdle"],
            "unit": "min",
            "data_type": "float",
            "min": 0,
            "max": 1000
        },
        "VehicleEntity Max Speed": {
            "aliases": ["VehicleEntity_MaxSpeed", "Max Speed", "MaxSpeed"],
            "unit": "km/h",
            "data_type": "float",
            "min": 0,
            "max": 300
        },
        "Trip Event ID": {
            "aliases": ["PositionEvent_TripEventID", "TripEventID", "Trip Event ID"],
            "unit": "",
            "data_type": "string",
            "min": None,
            "max": None
        },

        # --- Newly added parameters from user list ---
        # Ignition / vehicle state
        "Veh Ignition": {"aliases": ["Veh Ignition"], "unit": "", "data_type": "float"},
        "Veh Ignition I/O": {"aliases": ["Veh Ignition I/O"], "unit": "", "data_type": "float"},
        "Veh Gear Selector (PN)": {"aliases": ["Veh Gear Selector (PN)", "Veh Gear Selector", "Veh Gear Selector (FNR)"], "unit": "", "data_type": "string"},
        "Veh Parking Brake": {"aliases": ["Veh Parking Brake"], "unit": "", "data_type": "string"},
        "Veh Deadman Switch": {"aliases": ["Veh Deadman Switch"], "unit": "", "data_type": "string"},
        "Veh Inching": {"aliases": ["Veh Inching"], "unit": "", "data_type": "float"},
        "Veh Impact Event": {"aliases": ["Veh Impact Event"], "unit": "", "data_type": "float"},

        # Speed already exists as Speed; add alias that matches list formatting
        "Speed (km/h)": {"aliases": ["Speed (km/h)", "Speed", "Vehicle Speed"], "unit": "km/h", "data_type": "float", "min": 0, "max": 300},

        # Charger
        "EV Charger State": {"aliases": ["EV Charger State"], "unit": "", "data_type": "string"},
        "EV Charger AC Input Current (A)": {"aliases": ["EV Charger AC Input Current (A)", "EV Charger AC Input Current"], "unit": "A", "data_type": "float", "min": 0, "max": 1000},
        "EV Charger Output DC Current (A)": {"aliases": ["EV Charger Output DC Current (A)", "EV Charger Output DC Current"], "unit": "A", "data_type": "float", "min": 0, "max": 1000},

        # Battery
        "EV Battery Min Cell Voltage (V)": {"aliases": ["EV Battery Min Cell Voltage (V)", "EV Battery Min Cell Voltage", "Battery Min Voltage", "MinCellVoltage"], "unit": "V", "data_type": "float", "min": 0, "max": 500},
        "EV Battery Max Cell Voltage (V)": {"aliases": ["EV Battery Max Cell Voltage (V)", "EV Battery Max Cell Voltage", "Battery Max Voltage", "MaxCellVoltage"], "unit": "V", "data_type": "float", "min": 0, "max": 500},
        "EV Battery Cell Temp Min (°C)": {"aliases": ["EV Battery Cell Temp Min (°C)", "EV Battery Cell Temp Min"], "unit": "°C", "data_type": "float", "min": -40, "max": 120},
        "EV Battery Cell Temp Max (°C)": {"aliases": ["EV Battery Cell Temp Max (°C)", "EV Battery Cell Temp Max"], "unit": "°C", "data_type": "float", "min": -40, "max": 120},
        "EV Battery Current (A)": {"aliases": ["EV Battery Current (A)", "EV Battery Current", "Battery Current", "Current"], "unit": "A", "data_type": "float", "min": -5000, "max": 5000},
        "Battery Voltage (V)": {"aliases": ["Battery Voltage (V)", "Battery Voltage", "EV Battery Voltage"], "unit": "V", "data_type": "float", "min": 0, "max": 10000},
        "Battery Current Charge Limit (A)": {"aliases": ["Battery Current Charge Limit (A)", "Battery Current Charge Limit", "EV Battery Current Charge Limit"], "unit": "A", "data_type": "float", "min": -5000, "max": 5000},
        "Energy level percentage (%)": {"aliases": ["Energy level percentage (%)", "Energy level percentage"], "unit": "%", "data_type": "float", "min": 0, "max": 100},

        # Motor temperatures / currents
        "Veh Motor Trl Temperature (°C)": {"aliases": ["Veh Motor Trl Temperature (°C)", "Veh Motor Trl Temperature", "Veh Motor1 Tr1 Temperature"], "unit": "°C", "data_type": "float", "min": -40, "max": 250},
        "Veh Motor Trl Inverter Temperature (°C)": {"aliases": ["Veh Motor Trl Inverter Temperature (°C)", "Veh Motor Trl Inverter Temperature", "Veh Motor1 Tr1 Inverter Temperature"], "unit": "°C", "data_type": "float", "min": -40, "max": 250},
        "Veh Motor Trl Inverter Current (A)": {"aliases": ["Veh Motor Trl Inverter Current (A)", "Veh Motor Trl Inverter Current", "Veh Motor1 Tr1 Inverter Current"], "unit": "A", "data_type": "float", "min": -5000, "max": 5000},

        # OBU / power
        "OBU External Power Lost": {"aliases": ["OBU External Power Lost"], "unit": "", "data_type": "float"},
        "OBU External Power Voltage (V)": {"aliases": ["OBU External Power Voltage (V)", "OBU External Power Voltage"], "unit": "V", "data_type": "float", "min": 0, "max": 10000},
        "OBU Internal Battery State (%)": {"aliases": ["OBU Internal Battery State (%)", "OBU Internal Battery State"], "unit": "%", "data_type": "string"},
        "OBU Internal Battery Voltage (V)": {"aliases": ["OBU Internal Battery Voltage (V)", "OBU Internal Battery Voltage"], "unit": "V", "data_type": "float", "min": 0, "max": 10000},
        "OBU Motion Detected": {"aliases": ["OBU Motion Detected"], "unit": "", "data_type": "string"},
        "OBU Vin State": {"aliases": ["OBU Vin State"], "unit": "", "data_type": "string"},
        "OBU Vin Data Mb/M": {"aliases": ["OBU Vin Data Mb/M", "OBU Vin Data"], "unit": "", "data_type": "string"},
        "OBU Internal Temperature (C)": {"aliases": ["OBU Internal Temperature (°C)", "OBU Internal Temperature"], "unit": "°C", "data_type": "float", "min": -40, "max": 200},

        # Alarms
        "Alrm Harsh Braking": {"aliases": ["Alrm Harsh Braking"], "unit": "", "data_type": "float"},
        "Alrm Excessive Acceleration": {"aliases": ["Alrm Excessive Acceleration"], "unit": "", "data_type": "float"},
        "Alrm No Trip Motion": {"aliases": ["Alrm No Trip Motion"], "unit": "", "data_type": "float"},

        # Cell IDs
        "Tmax cell ID": {"aliases": ["Tmax cell ID", "Battery Tmax Cell ID", "Max Cell Temp ID", "Ev Tmax battery cell ID"], "unit": "", "data_type": "string"},
        "Tmin cell ID": {"aliases": ["Tmin cell ID", "Battery Tmin Cell ID", "Min Cell Temp ID", "Ev Tmin battery cell ID"], "unit": "", "data_type": "string"},
        "Vmax cell ID": {"aliases": ["Vmax cell ID", "Battery Vmax Cell ID", "Max Cell Volt ID", "Ev Vmax battery cell ID"], "unit": "", "data_type": "string"},
        "Vmin cell ID": {"aliases": ["Vmin cell ID", "Vmin cell id", "Battery Vmin Cell ID", "Min Cell Volt ID", "Ev Vmin battery cell ID"], "unit": "", "data_type": "string"},

        # VCM state
        "VCM Vehicle Access Control State I/O": {"aliases": ["VCM Vehicle Access Control State I/O"], "unit": "", "data_type": "float"},
    }
    
    def __init__(self):
        """Initialize the parameter extraction agent"""
        self.extraction_mapping = self._build_extraction_mapping()
        self.last_extraction_report = {}
    
    def _build_extraction_mapping(self) -> Dict[str, str]:
        """
        Build a mapping from raw parameter names (aliases) to canonical parameter names
        Returns: dict mapping all aliases to their canonical names
        """
        mapping = {}
        for canonical_name, config in self.PARAMETER_MAPPING.items():
            for alias in config["aliases"]:
                mapping[alias.lower()] = canonical_name
        return mapping
    
    def extract_parameters(self, telemetry_data, 
                          source_column: str = "telemetry",
                          parameters_to_extract: Optional[List[str]] = None,
                          fill_missing_numeric_with: Optional[float] = None) -> ExtractionResult:
        """
        Extract parameters from concatenated telemetry string
        
        Args:
            telemetry_data: TelemetryData object or DataFrame
            source_column: Column containing concatenated key:value strings
            parameters_to_extract: List of specific parameters to extract (None = extract all)
            fill_missing_numeric_with: If provided, numeric NaN values (from missing parameters) will be filled with this value.
        
        Returns:
            ExtractionResult with extracted DataFrame and report
        """
        # Handle both TelemetryData objects and raw DataFrames
        if hasattr(telemetry_data, 'dataframe'):
            df = telemetry_data.dataframe.copy()
        else:
            df = telemetry_data.copy()
        
        # Determine which parameters to extract
        if parameters_to_extract:
            params_to_extract = parameters_to_extract
        else:
            params_to_extract = list(self.PARAMETER_MAPPING.keys())
        
        # Initialize columns for each parameter
        for param in params_to_extract:
            df[param] = None
        
        # Parse and extract parameters
        successful = 0
        failed = 0
        missing_counts = {param: 0 for param in params_to_extract}
        
        for idx, row in df.iterrows():
            if source_column not in df.columns:
                failed += 1
                continue
            
            telemetry_str = str(row[source_column])
            if pd.isna(telemetry_str) or telemetry_str == "":
                failed += 1
                continue
            
            # Parse the key:value pairs
            parsed_params = self._parse_telemetry_string(telemetry_str)
            
            # Extract and assign values
            for canonical_name in params_to_extract:
                value = parsed_params.get(canonical_name)
                if value is not None:
                    df.at[idx, canonical_name] = self._convert_value(
                        canonical_name, value
                    )
                else:
                    missing_counts[canonical_name] += 1
            
            successful += 1
        
        # Convert data types
        for param in params_to_extract:
            df = self._apply_data_type(df, param)

        # Fill missing numeric values if requested
        if fill_missing_numeric_with is not None:
            numeric_cols_to_fill = [
                p for p in params_to_extract
                if self.PARAMETER_MAPPING.get(p, {}).get("data_type") in ["float", "int"]
                and p in df.columns # Ensure column exists after extraction
            ]
            for col in numeric_cols_to_fill:
                df[col] = df[col].fillna(fill_missing_numeric_with)
        
        # Build extraction report
        extraction_report = {
            "total_rows": len(df),
            "successful_extractions": successful,
            "failed_extractions": failed,
            "parameters_extracted": len(params_to_extract),
            "missing_by_parameter": missing_counts,
            "extraction_rate": (successful / len(df) * 100) if len(df) > 0 else 0
        }
        
        self.last_extraction_report = extraction_report
        
        return ExtractionResult(
            dataframe=df,
            extracted_parameters=params_to_extract,
            extraction_report=extraction_report
        )
    
    def _parse_telemetry_string(self, telemetry_str: str) -> Dict[str, str]:
        """
        Parse concatenated key:value string into dictionary.
        Handles values that contain commas inside brackets [], {}, ().
        """
        parsed = {}

        if not isinstance(telemetry_str, str) or not telemetry_str:
            return parsed

        # Split by comma only when not inside brackets
        pairs = []
        depth = 0
        current = []
        for ch in telemetry_str:
            if ch in '([{':
                depth += 1
                current.append(ch)
            elif ch in ')]}':
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0:
                pairs.append(''.join(current))
                current = []
            else:
                current.append(ch)
        if current:
            pairs.append(''.join(current))

        for pair in pairs:
            if ':' not in pair:
                continue
            try:
                key, value = pair.split(':', 1)
                key = key.strip()
                value = value.strip()
                canonical_name = self.extraction_mapping.get(key.lower())
                if canonical_name:
                    parsed[canonical_name] = value
            except Exception:
                continue

        return parsed
    
    def _convert_value(self, parameter_name: str, value: str):
        """Convert string value to appropriate data type"""
        if parameter_name not in self.PARAMETER_MAPPING:
            return value
        
        config = self.PARAMETER_MAPPING[parameter_name]
        data_type = config.get("data_type", "string")
        
        try:
            if data_type == "float":
                return float(value)
            elif data_type == "int":
                return int(value)
            elif data_type == "string":
                return str(value)
            else:
                return value
        except (ValueError, TypeError):
            return None
    
    def _apply_data_type(self, df: pd.DataFrame, parameter_name: str) -> pd.DataFrame:
        """Apply proper data type to column"""
        if parameter_name not in df.columns:
            return df
        
        config = self.PARAMETER_MAPPING.get(parameter_name, {})
        data_type = config.get("data_type", "string")
        
        try:
            if data_type == "float":
                df[parameter_name] = pd.to_numeric(df[parameter_name], errors='coerce')
            elif data_type == "int":
                df[parameter_name] = pd.to_numeric(df[parameter_name], errors='coerce').astype('Int64')
            elif data_type == "string":
                df[parameter_name] = df[parameter_name].astype(str)
        except Exception:
            pass
        
        return df
    
    def add_parameter(self, parameter_name: str, aliases: List[str], 
                     unit: str = "", data_type: str = "string",
                     min_val: Optional[float] = None, 
                     max_val: Optional[float] = None) -> None:
        """
        Add a new parameter to the extraction mapping (for dynamic parameter addition)
        
        Args:
            parameter_name: Canonical name of the parameter
            aliases: List of possible names this parameter might appear as
            unit: Unit of measurement
            data_type: "string", "float", or "int"
            min_val: Minimum valid value
            max_val: Maximum valid value
        """
        self.PARAMETER_MAPPING[parameter_name] = {
            "aliases": aliases + [parameter_name],
            "unit": unit,
            "data_type": data_type,
            "min": min_val,
            "max": max_val
        }
        
        # Update extraction mapping
        for alias in aliases + [parameter_name]:
            self.extraction_mapping[alias.lower()] = parameter_name
    
    def validate_parameter_ranges(self, df: pd.DataFrame) -> Dict[str, List[int]]:
        """
        Validate that numeric parameters are within acceptable ranges
        
        Returns: Dictionary with parameter names and list of out-of-range row indices
        """
        out_of_range = {}
        
        for param_name, config in self.PARAMETER_MAPPING.items():
            if param_name not in df.columns:
                continue
            
            if config["data_type"] != "float":
                continue
            
            min_val = config.get("min")
            max_val = config.get("max")
            
            if min_val is not None or max_val is not None:
                out_of_range[param_name] = []
                
                for idx, val in df[param_name].items():
                    if pd.isna(val):
                        continue
                    
                    if min_val is not None and val < min_val:
                        out_of_range[param_name].append(idx)
                    elif max_val is not None and val > max_val:
                        out_of_range[param_name].append(idx)
        
        return out_of_range
    
    def get_extraction_report(self) -> Dict:
        """Get the last extraction report"""
        return self.last_extraction_report
    
    def get_available_parameters(self) -> List[str]:
        """Get list of all available parameters"""
        return list(self.PARAMETER_MAPPING.keys())
    
    def get_parameter_info(self, parameter_name: str) -> Optional[Dict]:
        """Get detailed info about a specific parameter"""
        return self.PARAMETER_MAPPING.get(parameter_name)


# Example usage
if __name__ == "__main__":
    # Create sample data
    sample_data = pd.DataFrame({
        "telemetry": [
            "VehicleEntity_MaxRPM:5000,fleetName:TLD MAINI,EV Battery State of Charge:95,fleetOwnerName:Alvest Group,PositionEvent_TripEventID:10560504,Device_ID:6132129",
            "VehicleEntity_MaxRPM:4500,fleetName:TLD MAINI,EV Battery State of Charge:87,fleetOwnerName:Alvest Group,Speed:45.5,Device_ID:6132130",
            "VehicleEntity_MaxRPM:5000,EV Battery Current:25.5,EV Battery Min Cell Voltage:3.2,Device_ID:6132131",
        ]
    })
    
    # Extract parameters
    agent = ParameterExtractionAgent()
    result = agent.extract_parameters(sample_data)
    
    print(result.summary())
    print("\nExtracted DataFrame:")
    print(result.dataframe)
