"""Agent for cleaning telemetry data."""

import pandas as pd
from typing import List, Optional
from data_models.telemetry import TelemetryData, CleaningReport
from utils.data_utils import DataUtils
from config.parameters import TELEMETRY_PARAMETERS, CLEANING_CONFIG
from .parameter_extraction_agent import ParameterExtractionAgent
from .parameter_cleaning_agents.number_cleaners import clean_float_like


class CleanTelemetryAgent:
    """Agent responsible for cleaning telemetry data based on parameter specifications."""
    
    def __init__(self):
        self.data_utils = DataUtils()
        self.cleaning_report: Optional[CleaningReport] = None
    
    def clean_data(self, telemetry_data: TelemetryData, 
                   parameters_to_clean: Optional[List[str]] = None,
                   remove_duplicates: bool = True,
                   handle_missing: bool = True,
                   remove_outliers: bool = True,
                   extract_parameters: bool = False,
                   telemetry_source_column: str = 'telemetry') -> TelemetryData:
        """
        Clean telemetry data based on parameters.
        
        Args:
            telemetry_data: Input TelemetryData object
            parameters_to_clean: List of parameter names to clean
            remove_duplicates: Whether to remove duplicate rows
            handle_missing: Whether to handle missing values
            remove_outliers: Whether to remove outliers
            extract_parameters: Whether to extract structured parameters from telemetry string
            telemetry_source_column: Column name containing telemetry key:value string
            
        Returns:
            Cleaned TelemetryData object
        """
        df = telemetry_data.dataframe.copy()
        original_rows = len(df)
        timestamp_col = telemetry_data.timestamp_column
        
        print("🧹 Starting data cleaning...")
        
        # Step 0: Extract parameters from telemetry string (optional)
        if extract_parameters and telemetry_source_column in df.columns:
            print(f"📊 Extracting structured parameters from '{telemetry_source_column}' column...")
            param_agent = ParameterExtractionAgent()
            extraction_result = param_agent.extract_parameters(
                df,
                source_column=telemetry_source_column,
                parameters_to_extract=parameters_to_clean
            )
            df = extraction_result.dataframe
            print(f"✓ Successfully extracted {len(extraction_result.extracted_parameters)} parameters")
            
            # Use extracted parameters if none specified
            if parameters_to_clean is None:
                parameters_to_clean = extraction_result.extracted_parameters
        
        if parameters_to_clean is None:
            parameters_to_clean = telemetry_data.get_parameters()
        
        # Initialize cleaning report
        missing_counts = {}
        outliers_removed = {}
        
        # Step 1: Remove duplicates
        if remove_duplicates:
            initial_rows = len(df)
            df = self.data_utils.remove_duplicates(df)
            removed = initial_rows - len(df)
            if removed > 0:
                print(f"✓ Removed {removed} duplicate rows")
        
        # Step 2: Clean individual parameters
        for param in parameters_to_clean:
            if param not in df.columns:
                print(f"⚠ Parameter '{param}' not found in data")
                continue

            param_config = TELEMETRY_PARAMETERS.get(param, {})
            cleaned_col = f"{param}__cleaned"

            # Convert/clean into a new column (do not overwrite raw column)
            if pd.api.types.is_numeric_dtype(df[param]):
                # Handle numeric columns (fill + optional outlier removal)
                numeric_series = df[param]

                if handle_missing:
                    missing_before = numeric_series.isna().sum()
                    missing_counts[param] = missing_before
                    if missing_before > 0:
                        numeric_series = numeric_series.fillna(numeric_series.median())
                        print(f"✓ Filled {missing_before} missing values in '{param}'")

                if remove_outliers and 'min' in param_config and 'max' in param_config:
                    min_val = param_config['min']
                    max_val = param_config['max']
                    outlier_mask = ~numeric_series.between(min_val, max_val)
                    outliers = int(outlier_mask.sum())
                    if outliers > 0:
                        outliers_removed[param] = outliers
                        print(f"✓ Removed {outliers} outliers from '{param}' (range: {min_val}-{max_val})")
                        # drop rows for this parameter only (row-level filtering)
                        df = df[~outlier_mask.values]
                        # reset df reference to keep indexing aligned
                        numeric_series = df[param]

                df[cleaned_col] = numeric_series

            else:
                # Non-numeric parameters: missing handling only + passthrough
                if handle_missing:
                    missing_before = df[param].isna().sum()
                    missing_counts[param] = missing_before
                    if missing_before > 0:
                        df[cleaned_col] = df[param].fillna('Unknown')
                        print(f"✓ Filled {missing_before} missing values in '{param}'")
                    else:
                        df[cleaned_col] = df[param]
                else:
                    df[cleaned_col] = df[param]

                # Optional outlier removal for non-numeric not applied.

        
        # Step 3: Ensure proper timestamp sorting
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        print(f"✓ Data sorted by timestamp")
        
        cleaned_rows = len(df)
        rows_removed = original_rows - cleaned_rows
        
        # Create cleaning report
        self.cleaning_report = CleaningReport(
            original_rows=original_rows,
            cleaned_rows=cleaned_rows,
            rows_removed=rows_removed,
            parameters_cleaned=parameters_to_clean,
            missing_value_counts=missing_counts,
            outliers_removed=outliers_removed
        )
        
        print(f"✓ Cleaning complete. Removed {rows_removed} rows total")
        
        # Create new TelemetryData with cleaned data
        return TelemetryData(
            dataframe=df,
            parameters=telemetry_data.parameters,
            timestamp_column=timestamp_col,
            source_file=telemetry_data.source_file
        )
    
    def validate_parameter_ranges(self, telemetry_data: TelemetryData,
                                 parameter: str) -> dict:
        """
        Validate if parameter values are within expected ranges.
        
        Args:
            telemetry_data: TelemetryData object
            parameter: Parameter name to validate
            
        Returns:
            Dictionary with validation results
        """
        df = telemetry_data.dataframe
        
        if parameter not in df.columns:
            raise ValueError(f"Parameter '{parameter}' not found")
        
        param_config = TELEMETRY_PARAMETERS.get(parameter, {})
        
        results = {
            'parameter': parameter,
            'valid_count': 0,
            'invalid_count': 0,
            'out_of_range': []
        }
        
        if 'min' in param_config and 'max' in param_config:
            min_val = param_config['min']
            max_val = param_config['max']
            
            valid = (df[parameter] >= min_val) & (df[parameter] <= max_val)
            results['valid_count'] = valid.sum()
            results['invalid_count'] = (~valid).sum()
            
            if results['invalid_count'] > 0:
                invalid_rows = df[~valid]
                results['out_of_range'] = [
                    {'index': idx, 'value': val, 'expected_range': f"{min_val}-{max_val}"}
                    for idx, val in invalid_rows[parameter].items()
                ]
        
        return results
    
    def get_cleaning_report(self) -> Optional[CleaningReport]:
        """Get the last cleaning report."""
        return self.cleaning_report
    
    def get_cleaning_report_summary(self) -> str:
        """Get summary of cleaning operations."""
        if self.cleaning_report is None:
            return "No cleaning report available"
        return self.cleaning_report.summary()
