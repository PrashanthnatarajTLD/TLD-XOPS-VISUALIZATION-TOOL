"""Agent for timestamp alignment and forward filling of telemetry data."""

import pandas as pd
from typing import Optional, List
from data_models.telemetry import TelemetryData
from config.parameters import TIME_ALIGNMENT_CONFIG


class TimestampAlignmentAgent:
    """Agent responsible for aligning parameters to common timestamps."""
    
    def __init__(self, resample_frequency: str = "1min"):
        """
        Initialize the agent.
        
        Args:
            resample_frequency: Frequency for resampling (e.g., '1min', '5min', '1H')
        """
        self.resample_frequency = resample_frequency
    
    def align_parameters(self, telemetry_data: TelemetryData,
                        method: str = 'forward_fill',
                        resample_freq: Optional[str] = None) -> TelemetryData:
        """
        Align all parameters to common timestamps using forward fill or interpolation.
        
        For example:
        - 10:00 AM: SOC is updated (SOC = 80%)
        - 10:20 AM: Current is updated (Current = 100A)
        
        After alignment at 10:20 AM:
        - SOC = 80% (forward filled from 10:00 AM)
        - Current = 100A (original value)
        
        Args:
            telemetry_data: Input TelemetryData object
            method: 'forward_fill', 'interpolate', or 'nearest'
            resample_freq: Frequency for resampling (if None, uses default)
            
        Returns:
            TelemetryData with aligned parameters
        """
        df = telemetry_data.dataframe.copy()
        timestamp_col = telemetry_data.timestamp_column
        
        print(f"⏱ Aligning parameters to common timestamps...")
        print(f"  Original data points: {len(df)}")
        
        if resample_freq is None:
            resample_freq = self.resample_frequency
        
        # 1. Ensure data is sorted and forward filled BEFORE resampling.
        # This ensures that if SOC was reported at 10:00:05 and Speed at 10:00:45,
        # the 10:00:45 row actually contains the SOC value from 40 seconds ago.
        df = df.sort_values(timestamp_col).ffill()
        
        # 2. Set timestamp as index for resampling
        df = df.set_index(timestamp_col)

        # Resample to uniform grid
        df_resampled = df.resample(resample_freq).last()

        # Apply alignment method
        if method == 'forward_fill':
            df_aligned = df_resampled.ffill()
            print(f"✓ Applied forward fill method")

        elif method == 'backward_fill':
            df_aligned = df_resampled.bfill()
            print(f"✓ Applied backward fill method")

        elif method == 'interpolate':
            numeric_cols = df_resampled.select_dtypes(include=['number']).columns
            df_aligned = df_resampled.copy()
            df_aligned[numeric_cols] = df_aligned[numeric_cols].interpolate(method='linear', limit_direction='both')
            df_aligned = df_aligned.ffill().bfill()
            print(f"✓ Applied linear interpolation method")

        elif method == 'nearest':
            df_aligned = df_resampled.ffill().bfill()
            print(f"✓ Applied nearest neighbor method")

        else:
            raise ValueError(f"Unknown method: {method}")
        
        # Reset index to make timestamp a regular column again
        df_aligned = df_aligned.reset_index()
        
        print(f"  Final aligned data points: {len(df_aligned)}")
        print(f"✓ Parameter alignment complete")
        
        # Create new TelemetryData with aligned data
        return TelemetryData(
            dataframe=df_aligned,
            parameters=telemetry_data.parameters,
            timestamp_column=timestamp_col,
            source_file=telemetry_data.source_file
        )
    
    def forward_fill_specific_parameters(self, telemetry_data: TelemetryData,
                                        parameters: List[str],
                                        limit: Optional[int] = None) -> TelemetryData:
        """
        Forward fill specific parameters up to a certain limit.
        
        Args:
            telemetry_data: Input TelemetryData object
            parameters: List of parameter names to forward fill
            limit: Maximum number of consecutive NaN values to forward fill
            
        Returns:
            TelemetryData with forward filled parameters
        """
        df = telemetry_data.dataframe.copy()
        timestamp_col = telemetry_data.timestamp_column
        
        print(f"⏱ Forward filling parameters: {', '. join(parameters)}")
        
        for param in parameters:
            if param not in df.columns:
                print(f"⚠ Parameter '{param}' not found")
                continue
            
            initial_nulls = df[param].isna().sum()
            
            if limit is not None:
                df[param] = df[param].ffill(limit=limit)
            else:
                df[param] = df[param].ffill()
            
            final_nulls = df[param].isna().sum()
            filled = initial_nulls - final_nulls
            
            if filled > 0:
                print(f"✓ Forward filled {filled} values in '{param}'")
        
        print(f"✓ Forward fill complete")
        
        return TelemetryData(
            dataframe=df,
            parameters=telemetry_data.parameters,
            timestamp_column=timestamp_col,
            source_file=telemetry_data.source_file
        )
    
    def get_alignment_summary(self, original_data: TelemetryData,
                             aligned_data: TelemetryData) -> dict:
        """
        Get summary of alignment operation.
        
        Args:
            original_data: Original TelemetryData
            aligned_data: Aligned TelemetryData
            
        Returns:
            Dictionary with alignment summary
        """
        summary = {
            'original_records': len(original_data.dataframe),
            'aligned_records': len(aligned_data.dataframe),
            'original_timestamp_range': {
                'start': original_data.dataframe[original_data.timestamp_column].min(),
                'end': original_data.dataframe[original_data.timestamp_column].max(),
            },
            'aligned_timestamp_range': {
                'start': aligned_data.dataframe[aligned_data.timestamp_column].min(),
                'end': aligned_data.dataframe[aligned_data.timestamp_column].max(),
            },
        }
        
        # Missing values before and after
        summary['missing_values_before'] = original_data.dataframe.isna().sum().to_dict()
        summary['missing_values_after'] = aligned_data.dataframe.isna().sum().to_dict()
        
        return summary
