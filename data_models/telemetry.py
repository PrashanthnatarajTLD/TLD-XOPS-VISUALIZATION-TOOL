"""Data models for telemetry data."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd


@dataclass
class TelemetryParameter:
    """Represents a telemetry parameter."""
    name: str
    unit: Optional[str] = None
    data_type: str = "float"
    description: str = ""


@dataclass
class TelemetryData:
    """Container for processed telemetry data."""
    dataframe: pd.DataFrame
    parameters: List[TelemetryParameter] = field(default_factory=list)
    timestamp_column: str = "timestamp"
    source_file: Optional[str] = None
    loaded_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Validate dataframe structure."""
        if self.timestamp_column not in self.dataframe.columns:
            raise ValueError(f"Timestamp column '{self.timestamp_column}' not found in dataframe")
    
    def shape(self):
        return self.dataframe.shape
    
    def get_parameters(self) -> List[str]:
        """Get list of parameter names (excluding timestamp)."""
        return [col for col in self.dataframe.columns 
                if col != self.timestamp_column]
    
    def to_csv(self, filepath: str):
        """Export to CSV."""
        self.dataframe.to_csv(filepath, index=False)
    
    def to_excel(self, filepath: str):
        """Export to Excel."""
        self.dataframe.to_excel(filepath, index=False)


@dataclass
class CleaningReport:
    """Report of data cleaning operations."""
    original_rows: int
    cleaned_rows: int
    rows_removed: int
    parameters_cleaned: List[str]
    missing_value_counts: Dict[str, int]
    outliers_removed: Dict[str, int] = field(default_factory=dict)
    
    def summary(self) -> str:
        """Generate a summary of cleaning operations."""
        lines = [
            f"Cleaning Report:",
            f"  Original rows: {self.original_rows}",
            f"  Cleaned rows: {self.cleaned_rows}",
            f"  Rows removed: {self.rows_removed}",
            f"  Parameters cleaned: {', '.join(self.parameters_cleaned)}",
            f"  Missing values by parameter:",
        ]
        for param, count in self.missing_value_counts.items():
            lines.append(f"    {param}: {count}")
        
        if self.outliers_removed:
            lines.append(f"  Outliers removed by parameter:")
            for param, count in self.outliers_removed.items():
                lines.append(f"    {param}: {count}")
        
        return "\n".join(lines)
