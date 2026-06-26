"""Agent for displaying fetched telemetry data."""

import pandas as pd
from typing import Optional
from data_models.telemetry import TelemetryData


class DisplayAgent:
    """Agent responsible for displaying telemetry data in various formats."""
    
    @staticmethod
    def display_summary(telemetry_data: TelemetryData) -> dict:
        """
        Display a summary of the telemetry data.
        
        Args:
            telemetry_data: TelemetryData object
            
        Returns:
            Dictionary with summary information
        """
        df = telemetry_data.dataframe
        
        summary = {
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'parameters': telemetry_data.get_parameters(),
            'timestamp_range': {
                'start': df[telemetry_data.timestamp_column].min(),
                'end': df[telemetry_data.timestamp_column].max(),
                'duration': df[telemetry_data.timestamp_column].max() - 
                           df[telemetry_data.timestamp_column].min()
            },
            'memory_usage': df.memory_usage(deep=True).sum() / 1024 / 1024,  # MB
        }
        
        return summary
    
    @staticmethod
    def display_head(telemetry_data: TelemetryData, rows: int = 10) -> pd.DataFrame:
        """Display first N rows of data."""
        return telemetry_data.dataframe.head(rows)
    
    @staticmethod
    def display_tail(telemetry_data: TelemetryData, rows: int = 10) -> pd.DataFrame:
        """Display last N rows of data."""
        return telemetry_data.dataframe.tail(rows)
    
    @staticmethod
    def display_statistics(telemetry_data: TelemetryData) -> pd.DataFrame:
        """Display statistical summary of numeric columns."""
        df = telemetry_data.dataframe
        numeric_cols = df.select_dtypes(include=['number']).columns
        return df[numeric_cols].describe()
    
    @staticmethod
    def display_column_info(telemetry_data: TelemetryData) -> dict:
        """Display detailed information about each column."""
        df = telemetry_data.dataframe
        
        info = {}
        for col in df.columns:
            info[col] = {
                'dtype': str(df[col].dtype),
                'non_null': int(df[col].notna().sum()),
                'null': int(df[col].isna().sum()),
                'null_%': round(df[col].isna().sum() / len(df) * 100, 2),
                'unique': int(df[col].nunique()),
                'min': str(df[col].min()) if pd.notna(df[col].min()) else 'N/A',
                'max': str(df[col].max()) if pd.notna(df[col].max()) else 'N/A',
            }
        
        return info
    
    @staticmethod
    def display_missing_values(telemetry_data: TelemetryData) -> pd.DataFrame:
        """Display missing values information."""
        df = telemetry_data.dataframe
        
        missing = pd.DataFrame({
            'Column': df.columns,
            'Missing_Count': df.isnull().sum().values,
            'Missing_%': (df.isnull().sum().values / len(df) * 100).round(2)
        })
        
        return missing[missing['Missing_Count'] > 0].sort_values('Missing_%', ascending=False)
    
    @staticmethod
    def display_parameter_details(telemetry_data: TelemetryData, parameter_name: str) -> dict:
        """Display detailed information about a specific parameter."""
        df = telemetry_data.dataframe
        
        if parameter_name not in df.columns:
            raise ValueError(f"Parameter '{parameter_name}' not found in data")
        
        col_data = df[parameter_name]
        
        details = {
            'name': parameter_name,
            'dtype': str(col_data.dtype),
            'count': int(col_data.notna().sum()),
            'missing': int(col_data.isna().sum()),
            'unique_values': int(col_data.nunique()),
        }
        
        if pd.api.types.is_numeric_dtype(col_data):
            details.update({
                'min': float(col_data.min()),
                'max': float(col_data.max()),
                'mean': float(col_data.mean()),
                'median': float(col_data.median()),
                'std_dev': float(col_data.std()),
            })
        
        return details
