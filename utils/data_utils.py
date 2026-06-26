"""Utility functions for data processing."""

import pandas as pd
import numpy as np
from typing import List, Optional


class DataUtils:
    """Utility functions for data manipulation and analysis."""
    
    @staticmethod
    def detect_timestamp_column(df: pd.DataFrame) -> Optional[str]:
        """
        Auto-detect timestamp column.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Name of timestamp column or None
        """
        timestamp_aliases = ['timestamp', 'date', 'time', 'datetime', 
                            'dateprocessed', 'created_at', 'updated_at']
        
        for col in df.columns:
            if col.lower() in timestamp_aliases:
                return col
        
        # Try to infer from column types
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                return col
        
        return None
    
    @staticmethod
    def convert_to_datetime(series: pd.Series) -> pd.Series:
        """Convert series to datetime."""
        return pd.to_datetime(series, errors='coerce')
    
    @staticmethod
    def get_column_info(df: pd.DataFrame) -> dict:
        """
        Get detailed information about DataFrame columns.
        
        Returns:
            Dictionary with column information
        """
        info = {}
        for col in df.columns:
            info[col] = {
                'dtype': str(df[col].dtype),
                'non_null_count': df[col].notna().sum(),
                'null_count': df[col].isna().sum(),
                'null_percentage': round(df[col].isna().sum() / len(df) * 100, 2),
                'unique_values': df[col].nunique() if df[col].dtype == 'object' else None,
            }
        return info
    
    @staticmethod
    def remove_duplicates(df: pd.DataFrame, subset: Optional[List[str]] = None) -> pd.DataFrame:
        """Remove duplicate rows."""
        return df.drop_duplicates(subset=subset, keep='first')
    
    @staticmethod
    def handle_missing_values(df: pd.DataFrame, method: str = 'drop', 
                             columns: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Handle missing values.
        
        Args:
            df: Input DataFrame
            method: 'drop', 'mean', 'median', 'ffill', 'bfill'
            columns: Specific columns to process
            
        Returns:
            DataFrame with handled missing values
        """
        df = df.copy()
        cols = columns if columns else df.columns
        
        if method == 'drop':
            return df.dropna(subset=cols)
        elif method == 'mean':
            for col in cols:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col].fillna(df[col].mean(), inplace=True)
        elif method == 'median':
            for col in cols:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col].fillna(df[col].median(), inplace=True)
        elif method == 'ffill':
            df[cols] = df[cols].fillna(method='ffill')
        elif method == 'bfill':
            df[cols] = df[cols].fillna(method='bfill')
        
        return df
    
    @staticmethod
    def remove_outliers(df: pd.DataFrame, columns: List[str], 
                       method: str = 'iqr', threshold: float = 1.5) -> pd.DataFrame:
        """
        Remove outliers from numeric columns.
        
        Args:
            df: Input DataFrame
            columns: Columns to check for outliers
            method: 'iqr' or 'zscore'
            threshold: IQR multiplier or Z-score threshold
            
        Returns:
            DataFrame with outliers removed
        """
        df = df.copy()
        
        for col in columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue
            
            if method == 'iqr':
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - threshold * IQR
                upper = Q3 + threshold * IQR
                df = df[(df[col] >= lower) & (df[col] <= upper)]
            
            elif method == 'zscore':
                z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
                df = df[z_scores < threshold]
        
        return df
    
    @staticmethod
    def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names (lowercase, remove spaces)."""
        df = df.copy()
        df.columns = [col.lower().replace(' ', '_') for col in df.columns]
        return df
