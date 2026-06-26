"""Agent for downloading/exporting telemetry data."""

from pathlib import Path
from typing import Optional
from data_models.telemetry import TelemetryData
from utils.file_handler import FileHandler
from .column_uniqueness_agent import ColumnUniquenessAgent


class DownloadAgent:
    """Agent responsible for exporting telemetry data in various formats."""
    
    def __init__(self):
        self.file_handler = FileHandler()
    
    def download_csv(self, telemetry_data: TelemetryData, output_path: str) -> str:
        """
        Export telemetry data to CSV format.
        
        Args:
            telemetry_data: TelemetryData object
            output_path: Path where CSV will be saved
            
        Returns:
            Path to saved file
        """
        print(f"💾 Exporting to CSV: {output_path}")

        # Ensure unique columns right before export (preview/download safety)
        df = telemetry_data.dataframe
        try:
            df = ColumnUniquenessAgent(rename_duplicates=True).make_unique(df).dataframe
        except Exception:
            pass

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.file_handler.save_csv(df, output_path)
        
        file_size = Path(output_path).stat().st_size / 1024  # KB
        print(f"✓ CSV export complete. File size: {file_size:.2f} KB")
        
        return output_path
    
    def download_excel(self, telemetry_data: TelemetryData, output_path: str) -> str:
        """
        Export telemetry data to Excel format.
        
        Args:
            telemetry_data: TelemetryData object
            output_path: Path where Excel file will be saved
            
        Returns:
            Path to saved file
        """
        print(f"💾 Exporting to Excel: {output_path}")

        # Ensure unique columns right before export (preview/download safety)
        df = telemetry_data.dataframe
        try:
            df = ColumnUniquenessAgent(rename_duplicates=True).make_unique(df).dataframe
        except Exception:
            pass

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.file_handler.save_excel(df, output_path)
        
        file_size = Path(output_path).stat().st_size / 1024  # KB
        print(f"✓ Excel export complete. File size: {file_size:.2f} KB")
        
        return output_path
    
    def download_filtered(self, telemetry_data: TelemetryData, 
                         columns: list, output_path: str, 
                         file_format: str = 'csv') -> str:
        """
        Export filtered columns to file.
        
        Args:
            telemetry_data: TelemetryData object
            columns: List of column names to export
            output_path: Output file path
            file_format: 'csv' or 'excel'
            
        Returns:
            Path to saved file
        """
        df = telemetry_data.dataframe[columns]
        
        if file_format.lower() == 'csv':
            FileHandler.save_csv(df, output_path)
            print(f"✓ Filtered CSV saved: {output_path}")
        else:
            FileHandler.save_excel(df, output_path)
            print(f"✓ Filtered Excel saved: {output_path}")
        
        return output_path
    
    def download_date_range(self, telemetry_data: TelemetryData,
                           start_date: str, end_date: str,
                           output_path: str, file_format: str = 'csv') -> str:
        """
        Export data for a specific date range.
        
        Args:
            telemetry_data: TelemetryData object
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            output_path: Output file path
            file_format: 'csv' or 'excel'
            
        Returns:
            Path to saved file
        """
        df = telemetry_data.dataframe.copy()
        timestamp_col = telemetry_data.timestamp_column
        
        # Filter by date range
        df_filtered = df[(df[timestamp_col] >= start_date) & 
                         (df[timestamp_col] <= end_date)]
        
        print(f"📅 Filtering {len(df_filtered)} records between {start_date} and {end_date}")
        
        if file_format.lower() == 'csv':
            FileHandler.save_csv(df_filtered, output_path)
        else:
            FileHandler.save_excel(df_filtered, output_path)
        
        print(f"✓ Date-range export complete: {output_path}")
        return output_path
    
    def download_summary_statistics(self, telemetry_data: TelemetryData,
                                   output_path: str) -> str:
        """
        Export summary statistics of all numeric columns.
        
        Args:
            telemetry_data: TelemetryData object
            output_path: Output Excel file path
            
        Returns:
            Path to saved file
        """
        df = telemetry_data.dataframe
        
        # Get statistics
        stats = df.describe()
        
        # Save to Excel
        FileHandler.save_excel(stats, output_path)
        print(f"✓ Summary statistics exported: {output_path}")
        
        return output_path
