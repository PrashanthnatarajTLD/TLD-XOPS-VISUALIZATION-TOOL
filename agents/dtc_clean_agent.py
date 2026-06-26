"""Agent for cleaning DTC data."""

import pandas as pd
from typing import List, Optional
from data_models.dtc import DTCData, DTCCleaningReport
from utils.data_utils import DataUtils


class CleanDTCAgent:
    """Agent responsible for cleaning DTC data."""
    
    def __init__(self):
        self.data_utils = DataUtils()
        self.cleaning_report: Optional[DTCCleaningReport] = None
    
    def clean_data(self, dtc_data: DTCData,
                   remove_duplicates: bool = True,
                   validate_codes: bool = True,
                   remove_invalid: bool = True) -> DTCData:
        """
        Clean DTC data.
        
        Args:
            dtc_data: Input DTCData object
            remove_duplicates: Whether to remove duplicate records
            validate_codes: Whether to validate DTC codes
            remove_invalid: Whether to remove invalid records
            
        Returns:
            Cleaned DTCData object
        """
        df = dtc_data.dataframe.copy()
        original_records = len(df)
        dtc_col = dtc_data.dtc_code_column
        timestamp_col = dtc_data.timestamp_column
        
        print("🧹 Starting DTC data cleaning...")
        
        duplicate_count = 0
        invalid_count = 0
        
        # Step 1: Remove duplicates
        if remove_duplicates:
            initial_rows = len(df)
            df = self.data_utils.remove_duplicates(df)
            duplicate_count = initial_rows - len(df)
            if duplicate_count > 0:
                print(f"✓ Removed {duplicate_count} duplicate DTC records")
        
        # Step 2: Validate DTC codes
        if validate_codes and remove_invalid:
            initial_rows = len(df)
            
            # Remove rows with missing DTC codes
            df = df.dropna(subset=[dtc_col])
            
            # Remove rows where DTC code is empty string
            df = df[df[dtc_col].astype(str).str.strip() != '']
            
            invalid_count = initial_rows - len(df)
            if invalid_count > 0:
                print(f"✓ Removed {invalid_count} records with invalid DTC codes")
        
        # Step 3: Validate timestamps
        df = df.dropna(subset=[timestamp_col])
        print(f"✓ Removed records with missing timestamps")
        
        # Step 4: Sort by timestamp
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        print(f"✓ Data sorted by timestamp")
        
        cleaned_records = len(df)
        records_removed = original_records - cleaned_records
        
        # Create cleaning report
        self.cleaning_report = DTCCleaningReport(
            original_records=original_records,
            cleaned_records=cleaned_records,
            records_removed=records_removed,
            duplicate_codes_removed=duplicate_count,
            invalid_codes_removed=invalid_count
        )
        
        print(f"✓ DTC cleaning complete. Removed {records_removed} records total")
        
        # Create new DTCData with cleaned data
        return DTCData(
            dataframe=df,
            timestamp_column=timestamp_col,
            dtc_code_column=dtc_col,
            source_file=dtc_data.source_file
        )
    
    def standardize_dtc_codes(self, dtc_data: DTCData) -> DTCData:
        """
        Standardize DTC code format.
        
        Args:
            dtc_data: Input DTCData object
            
        Returns:
            DTCData with standardized codes
        """
        df = dtc_data.dataframe.copy()
        dtc_col = dtc_data.dtc_code_column
        
        print("📐 Standardizing DTC code format...")
        
        # Convert to uppercase and remove whitespace
        df[dtc_col] = df[dtc_col].astype(str).str.upper().str.strip()
        
        print(f"✓ Standardized {len(df)} DTC codes")
        
        return DTCData(
            dataframe=df,
            timestamp_column=dtc_data.timestamp_column,
            dtc_code_column=dtc_col,
            source_file=dtc_data.source_file
        )
    
    def remove_duplicate_dtcs_per_timestamp(self, dtc_data: DTCData) -> DTCData:
        """
        Remove duplicate DTC codes that occur at the same timestamp.
        
        Args:
            dtc_data: Input DTCData object
            
        Returns:
            DTCData with duplicates removed
        """
        df = dtc_data.dataframe.copy()
        initial_rows = len(df)
        
        # Remove duplicates based on timestamp and DTC code
        df = df.drop_duplicates(
            subset=[dtc_data.timestamp_column, dtc_data.dtc_code_column],
            keep='first'
        )
        
        removed = initial_rows - len(df)
        print(f"✓ Removed {removed} duplicate DTC codes at same timestamp")
        
        return DTCData(
            dataframe=df,
            timestamp_column=dtc_data.timestamp_column,
            dtc_code_column=dtc_data.dtc_code_column,
            source_file=dtc_data.source_file
        )
    
    def get_cleaning_report(self) -> Optional[DTCCleaningReport]:
        """Get the last cleaning report."""
        return self.cleaning_report
    
    def get_cleaning_report_summary(self) -> str:
        """Get summary of cleaning operations."""
        if self.cleaning_report is None:
            return "No cleaning report available"
        return self.cleaning_report.summary()
