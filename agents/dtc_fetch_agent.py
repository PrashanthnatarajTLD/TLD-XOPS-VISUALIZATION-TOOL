"""Agent for fetching DTC (Diagnostic Trouble Code) data."""

import pandas as pd
from typing import Optional
from utils.file_handler import FileHandler
from utils.data_utils import DataUtils
from data_models.dtc import DTCData


class FetchDTCAgent:
    """Agent responsible for fetching DTC data from various sources."""
    
    def __init__(self):
        self.file_handler = FileHandler()
        self.data_utils = DataUtils()
        self.fetched_data: Optional[DTCData] = None
    
    def fetch_from_file(self, filepath: str, 
                       timestamp_column: Optional[str] = None,
                       dtc_code_column: Optional[str] = None) -> DTCData:
        """
        Fetch DTC data from a file.
        
        Args:
            filepath: Path to the DTC data file
            timestamp_column: Name of timestamp column (auto-detected if None)
            dtc_code_column: Name of DTC code column (auto-detected if None)
            
        Returns:
            DTCData object containing the loaded data
        """
        print(f"🔍 Fetching DTC data from: {filepath}")
        
        # Read the file
        df = self.file_handler.read_file(filepath)
        print(f"✓ Loaded {len(df)} DTC records")
        
        # Auto-detect timestamp column if not provided
        if timestamp_column is None:
            timestamp_column = self.data_utils.detect_timestamp_column(df)
            if timestamp_column is None:
                raise ValueError("Could not auto-detect timestamp column. Please specify it.")
            print(f"✓ Auto-detected timestamp column: {timestamp_column}")
        
        # Auto-detect DTC code column
        if dtc_code_column is None:
            dtc_aliases = ['dtc_code', 'dtc', 'code', 'fault_code', 'error_code']
            for col in df.columns:
                if col.lower() in dtc_aliases:
                    dtc_code_column = col
                    break
            
            if dtc_code_column is None:
                raise ValueError("Could not auto-detect DTC code column. Please specify it.")
            print(f"✓ Auto-detected DTC code column: {dtc_code_column}")
        
        # Convert timestamp to datetime
        df[timestamp_column] = self.data_utils.convert_to_datetime(df[timestamp_column])
        
        # Create DTCData object
        self.fetched_data = DTCData(
            dataframe=df,
            timestamp_column=timestamp_column,
            dtc_code_column=dtc_code_column,
            source_file=filepath
        )
        
        print(f"✓ DTC data fetch complete. Found {len(self.fetched_data.get_unique_dtcs())} unique DTC codes")
        return self.fetched_data
    
    def get_fetched_data(self) -> Optional[DTCData]:
        """Get the last fetched DTC data."""
        return self.fetched_data
    
    def get_dtc_summary(self) -> dict:
        """Get summary information about fetched DTC data."""
        if self.fetched_data is None:
            return {}
        
        df = self.fetched_data.dataframe
        dtc_code_col = self.fetched_data.dtc_code_column
        
        summary = {
            'total_records': self.fetched_data.get_dtc_count(),
            'unique_dtcs': len(self.fetched_data.get_unique_dtcs()),
            'dtc_codes': self.fetched_data.get_unique_dtcs(),
            'timestamp_range': {
                'start': df[self.fetched_data.timestamp_column].min(),
                'end': df[self.fetched_data.timestamp_column].max(),
            },
            'dtc_frequency': df[dtc_code_col].value_counts().to_dict(),
            'memory_usage': df.memory_usage(deep=True).sum() / 1024 / 1024,  # MB
        }
        
        return summary
    
    def fetch_multiple_sheets(self, filepath: str, 
                             sheets: Optional[list] = None) -> dict:
        """
        Fetch DTC data from multiple sheets in an Excel file.
        
        Args:
            filepath: Path to Excel file
            sheets: List of sheet names to fetch (None = all sheets)
            
        Returns:
            Dictionary with sheet names as keys and DTCData as values
        """
        print(f"🔍 Fetching multiple DTC sheets from: {filepath}")
        
        excel_sheets = self.file_handler.read_excel_sheets(filepath)
        
        result = {}
        for sheet_name, df in excel_sheets.items():
            if sheets and sheet_name not in sheets:
                continue
            
            # Auto-detect timestamp column
            timestamp_col = self.data_utils.detect_timestamp_column(df)
            if timestamp_col:
                df[timestamp_col] = self.data_utils.convert_to_datetime(df[timestamp_col])
            
            result[sheet_name] = DTCData(
                dataframe=df,
                timestamp_column=timestamp_col or 'timestamp',
                source_file=filepath
            )
            print(f"✓ Loaded DTC sheet '{sheet_name}': {len(df)} records")
        
        return result
