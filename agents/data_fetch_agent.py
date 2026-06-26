"""Agent for fetching telemetry data from files."""

import pandas as pd
from typing import Optional, Tuple
from utils.file_handler import FileHandler
from utils.data_utils import DataUtils
from .column_uniqueness_agent import ColumnUniquenessAgent
from data_models.telemetry import TelemetryData, TelemetryParameter
from config.parameters import TELEMETRY_PARAMETERS


class DataFetchAgent:
    """Agent responsible for fetching telemetry data from various sources."""
    
    def __init__(self):
        self.file_handler = FileHandler()
        self.data_utils = DataUtils()
        self.fetched_data: Optional[TelemetryData] = None
    
    def fetch_from_file(self, filepath: str, timestamp_column: Optional[str] = None) -> TelemetryData:
        """
        Fetch telemetry data from a file.
        
        Args:
            filepath: Path to the data file (CSV, XLSX, etc.)
            timestamp_column: Name of timestamp column (auto-detected if None)
            
        Returns:
            TelemetryData object containing the loaded data
        """
        print(f"🔍 Fetching data from: {filepath}")
        
        # Read the file
        df = self.file_handler.read_file(filepath)
        print(f"✓ Loaded {len(df)} rows, {len(df.columns)} columns")

        # Normalize/de-duplicate semantic column names while *preserving duplicates*
        # so front-end preview/download can show duplicated column names.
        try:
            col_agent = ColumnUniquenessAgent(rename_duplicates=False)
            unique_result = col_agent.make_unique(df)
            df = unique_result.dataframe
        except Exception:
            # If column normalization fails, continue with raw df
            pass

        
        # Auto-detect timestamp column if not provided
        if timestamp_column is None:
            timestamp_column = self.data_utils.detect_timestamp_column(df)
            if timestamp_column is None:
                raise ValueError("Could not auto-detect timestamp column. Please specify it.")
            print(f"✓ Auto-detected timestamp column: {timestamp_column}")
        
        # Convert timestamp to datetime
        df[timestamp_column] = self.data_utils.convert_to_datetime(df[timestamp_column])
        
        # Create TelemetryParameter objects for known parameters
        parameters = []
        for col in df.columns:
            if col == timestamp_column:
                continue
            
            if col in TELEMETRY_PARAMETERS:
                param_config = TELEMETRY_PARAMETERS[col]
                parameters.append(TelemetryParameter(
                    name=col,
                    unit=param_config.get('unit'),
                    data_type=param_config.get('data_type', 'float'),
                    description=param_config.get('description', '')
                ))
            else:
                parameters.append(TelemetryParameter(
                    name=col,
                    data_type=df[col].dtype.name
                ))
        
        # Create TelemetryData object
        self.fetched_data = TelemetryData(
            dataframe=df,
            parameters=parameters,
            timestamp_column=timestamp_column,
            source_file=filepath
        )
        
        print(f"✓ Data fetch complete. Shape: {self.fetched_data.shape()}")
        return self.fetched_data
    
    def fetch_multiple_sheets(self, filepath: str, 
                             sheets: Optional[list] = None) -> dict:
        """
        Fetch data from multiple sheets in an Excel file.
        
        Args:
            filepath: Path to Excel file
            sheets: List of sheet names to fetch (None = all sheets)
            
        Returns:
            Dictionary with sheet names as keys and TelemetryData as values
        """
        print(f"🔍 Fetching multiple sheets from: {filepath}")
        
        excel_sheets = self.file_handler.read_excel_sheets(filepath)
        
        result = {}
        for sheet_name, df in excel_sheets.items():
            if sheets and sheet_name not in sheets:
                continue
            
            # Auto-detect timestamp column
            timestamp_col = self.data_utils.detect_timestamp_column(df)
            if timestamp_col:
                df[timestamp_col] = self.data_utils.convert_to_datetime(df[timestamp_col])
            
            result[sheet_name] = TelemetryData(
                dataframe=df,
                timestamp_column=timestamp_col or 'timestamp',
                source_file=filepath
            )
            print(f"✓ Loaded sheet '{sheet_name}': {len(df)} rows")
        
        return result
    
    def get_fetched_data(self) -> Optional[TelemetryData]:
        """Get the last fetched data."""
        return self.fetched_data
    
    def get_data_info(self) -> dict:
        """Get information about fetched data."""
        if self.fetched_data is None:
            return {}
        
        return {
            'shape': self.fetched_data.shape(),
            'parameters': [p.name for p in self.fetched_data.parameters],
            'timestamp_column': self.fetched_data.timestamp_column,
            'source_file': self.fetched_data.source_file,
            'loaded_at': str(self.fetched_data.loaded_at),
            'column_info': DataUtils.get_column_info(self.fetched_data.dataframe)
        }
