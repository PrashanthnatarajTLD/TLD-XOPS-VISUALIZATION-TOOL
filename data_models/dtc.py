"""Data models for DTC (Diagnostic Trouble Code) data."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd


@dataclass
class DTCRecord:
    """Represents a single DTC record."""
    dtc_code: str
    description: str
    timestamp: datetime
    severity: str  # Critical, Warning, Info
    parameter_affected: Optional[str] = None
    raw_data: Optional[Dict] = None


@dataclass
class DTCData:
    """Container for processed DTC data."""
    dataframe: pd.DataFrame
    timestamp_column: str = "timestamp"
    dtc_code_column: str = "dtc_code"
    source_file: Optional[str] = None
    loaded_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Validate dataframe structure."""
        if self.timestamp_column not in self.dataframe.columns:
            raise ValueError(f"Timestamp column '{self.timestamp_column}' not found")
        if self.dtc_code_column not in self.dataframe.columns:
            raise ValueError(f"DTC code column '{self.dtc_code_column}' not found")
    
    def get_unique_dtcs(self) -> List[str]:
        """Get list of unique DTC codes."""
        return self.dataframe[self.dtc_code_column].unique().tolist()
    
    def get_dtc_count(self) -> int:
        """Get total count of DTC records."""
        return len(self.dataframe)
    
    def filter_by_severity(self, severity: str) -> pd.DataFrame:
        """Filter DTCs by severity level."""
        if 'severity' in self.dataframe.columns:
            return self.dataframe[self.dataframe['severity'] == severity]
        return pd.DataFrame()
    
    def to_csv(self, filepath: str):
        """Export to CSV."""
        self.dataframe.to_csv(filepath, index=False)
    
    def to_excel(self, filepath: str):
        """Export to Excel."""
        self.dataframe.to_excel(filepath, index=False)


@dataclass
class DTCCleaningReport:
    """Report of DTC data cleaning operations."""
    original_records: int
    cleaned_records: int
    records_removed: int
    duplicate_codes_removed: int
    invalid_codes_removed: int
    
    def summary(self) -> str:
        """Generate a summary of cleaning operations."""
        return (
            f"DTC Cleaning Report:\n"
            f"  Original records: {self.original_records}\n"
            f"  Cleaned records: {self.cleaned_records}\n"
            f"  Records removed: {self.records_removed}\n"
            f"  Duplicate codes removed: {self.duplicate_codes_removed}\n"
            f"  Invalid codes removed: {self.invalid_codes_removed}"
        )
