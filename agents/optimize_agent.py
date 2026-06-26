"""Agent for optimizing the entire telemetry processing pipeline."""

import time
from typing import Optional, Dict, Any
from data_models.telemetry import TelemetryData
from data_models.dtc import DTCData
from agents.data_fetch_agent import DataFetchAgent
from agents.clean_telemetry_agent import CleanTelemetryAgent
from agents.dtc_fetch_agent import FetchDTCAgent
from agents.dtc_clean_agent import CleanDTCAgent
from agents.timestamp_alignment_agent import TimestampAlignmentAgent
from agents.visualization_agent import VisualizationAgent


class OptimizeAgent:
    """Agent responsible for optimizing the entire pipeline."""
    
    def __init__(self):
        self.fetch_agent = DataFetchAgent()
        self.clean_agent = CleanTelemetryAgent()
        self.dtc_fetch_agent = FetchDTCAgent()
        self.dtc_clean_agent = CleanDTCAgent()
        self.alignment_agent = TimestampAlignmentAgent()
        self.visualization_agent = VisualizationAgent()
        self.execution_log = []
    
    def optimize_full_pipeline(self, telemetry_file: str,
                              dtc_file: Optional[str] = None,
                              parameters_to_clean: Optional[list] = None,
                              align_timestamps: bool = True,
                              resample_frequency: str = "1min") -> Dict[str, Any]:
        """
        Execute the complete optimized pipeline from fetch to visualization.
        
        Args:
            telemetry_file: Path to telemetry data file
            dtc_file: Path to DTC data file (optional)
            parameters_to_clean: List of parameters to clean
            align_timestamps: Whether to align timestamps
            resample_frequency: Frequency for timestamp alignment
            
        Returns:
            Dictionary with results and statistics
        """
        pipeline_start = time.time()
        results = {
            'stages': {},
            'total_time': 0,
            'success': False,
            'errors': []
        }
        
        try:
            # Stage 1: Fetch Telemetry Data
            print("\n" + "="*60)
            print("STAGE 1: FETCHING TELEMETRY DATA")
            print("="*60)
            stage_start = time.time()
            
            telemetry_data = self.fetch_agent.fetch_from_file(telemetry_file)
            results['stages']['fetch_telemetry'] = {
                'time': time.time() - stage_start,
                'rows': telemetry_data.shape()[0],
                'columns': telemetry_data.shape()[1],
                'status': 'success'
            }
            
            # Stage 2: Clean Telemetry Data
            print("\n" + "="*60)
            print("STAGE 2: CLEANING TELEMETRY DATA")
            print("="*60)
            stage_start = time.time()
            
            cleaned_telemetry = self.clean_agent.clean_data(
                telemetry_data,
                parameters_to_clean=parameters_to_clean,
                remove_duplicates=True,
                handle_missing=True,
                remove_outliers=True
            )
            
            cleaning_report = self.clean_agent.get_cleaning_report()
            results['stages']['clean_telemetry'] = {
                'time': time.time() - stage_start,
                'original_rows': cleaning_report.original_rows,
                'cleaned_rows': cleaning_report.cleaned_rows,
                'rows_removed': cleaning_report.rows_removed,
                'status': 'success'
            }
            
            # Stage 3: Align Timestamps (Optional)
            if align_timestamps:
                print("\n" + "="*60)
                print("STAGE 3: ALIGNING TIMESTAMPS")
                print("="*60)
                stage_start = time.time()
                
                aligned_telemetry = self.alignment_agent.align_parameters(
                    cleaned_telemetry,
                    method='forward_fill',
                    resample_freq=resample_frequency
                )
                
                results['stages']['align_timestamps'] = {
                    'time': time.time() - stage_start,
                    'aligned_rows': aligned_telemetry.shape()[0],
                    'resample_frequency': resample_frequency,
                    'status': 'success'
                }
                
                telemetry_data = aligned_telemetry
            else:
                telemetry_data = cleaned_telemetry
                results['stages']['align_timestamps'] = {
                    'time': 0,
                    'status': 'skipped'
                }
            
            # Stage 4: Fetch and Clean DTC Data (Optional)
            if dtc_file:
                print("\n" + "="*60)
                print("STAGE 4: FETCHING DTC DATA")
                print("="*60)
                stage_start = time.time()
                
                dtc_data = self.dtc_fetch_agent.fetch_from_file(dtc_file)
                results['stages']['fetch_dtc'] = {
                    'time': time.time() - stage_start,
                    'records': dtc_data.get_dtc_count(),
                    'unique_codes': len(dtc_data.get_unique_dtcs()),
                    'status': 'success'
                }
                
                # Clean DTC Data
                print("\n" + "="*60)
                print("STAGE 5: CLEANING DTC DATA")
                print("="*60)
                stage_start = time.time()
                
                dtc_data = self.dtc_clean_agent.clean_data(dtc_data)
                dtc_cleaning_report = self.dtc_clean_agent.get_cleaning_report()
                
                results['stages']['clean_dtc'] = {
                    'time': time.time() - stage_start,
                    'original_records': dtc_cleaning_report.original_records,
                    'cleaned_records': dtc_cleaning_report.cleaned_records,
                    'records_removed': dtc_cleaning_report.records_removed,
                    'status': 'success'
                }
            else:
                results['stages']['fetch_dtc'] = {'status': 'skipped'}
                results['stages']['clean_dtc'] = {'status': 'skipped'}
            
            # Stage 6: Generate Visualization Suggestions
            print("\n" + "="*60)
            print("STAGE 6: VISUALIZATION SUGGESTIONS")
            print("="*60)
            stage_start = time.time()
            
            viz_suggestions = {}
            for param in telemetry_data.get_parameters()[:5]:  # Top 5 parameters
                viz_suggestions[param] = self.visualization_agent.suggest_graphs(
                    telemetry_data, param
                )
            
            results['stages']['visualization'] = {
                'time': time.time() - stage_start,
                'suggestions': viz_suggestions,
                'status': 'success'
            }
            
            # Final summary
            results['success'] = True
            results['total_time'] = time.time() - pipeline_start
            
            print("\n" + "="*60)
            print("PIPELINE SUMMARY")
            print("="*60)
            print(f"✓ Total execution time: {results['total_time']:.2f} seconds")
            print(f"✓ Final telemetry records: {telemetry_data.shape()[0]}")
            print(f"✓ Final parameters: {len(telemetry_data.get_parameters())}")
            print("="*60 + "\n")
            
        except Exception as e:
            results['success'] = False
            results['errors'].append(str(e))
            results['total_time'] = time.time() - pipeline_start
            print(f"\n❌ Pipeline failed: {str(e)}")
        
        return results
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics about pipeline execution."""
        total_time = sum(
            stage.get('time', 0) 
            for stage in self.execution_log
        )
        
        return {
            'total_stages': len(self.execution_log),
            'total_time': total_time,
            'stages': self.execution_log
        }
    
    def estimate_processing_time(self, file_size_mb: float,
                                row_count: int) -> Dict[str, float]:
        """
        Estimate processing time based on file characteristics.
        
        Args:
            file_size_mb: File size in MB
            row_count: Number of rows
            
        Returns:
            Estimated times for each stage in seconds
        """
        # Rough estimates based on typical performance
        estimates = {
            'fetch': 0.5 + (file_size_mb * 0.1),
            'clean': 0.1 + (row_count * 0.0001),
            'align': 0.2 + (row_count * 0.00005),
            'visualize': 0.3,
        }
        
        total = sum(estimates.values())
        
        return {
            **estimates,
            'total': total
        }
    
    def get_pipeline_report(self, results: Dict[str, Any]) -> str:
        """Generate a detailed pipeline report."""
        report = []
        report.append("\n" + "="*60)
        report.append("TELEMETRY PIPELINE EXECUTION REPORT")
        report.append("="*60)
        
        report.append(f"\n📊 Pipeline Status: {'✓ SUCCESS' if results['success'] else '❌ FAILED'}")
        report.append(f"⏱ Total Execution Time: {results['total_time']:.2f} seconds\n")
        
        for stage_name, stage_data in results['stages'].items():
            report.append(f"\n{stage_name.upper().replace('_', ' ')}:")
            report.append(f"  Status: {stage_data.get('status', 'unknown')}")
            
            if 'time' in stage_data:
                report.append(f"  Time: {stage_data['time']:.2f} seconds")
            
            if 'rows' in stage_data:
                report.append(f"  Rows: {stage_data['rows']}")
            
            if 'columns' in stage_data:
                report.append(f"  Columns: {stage_data['columns']}")
            
            if 'rows_removed' in stage_data:
                report.append(f"  Rows Removed: {stage_data['rows_removed']}")
        
        if results['errors']:
            report.append(f"\n❌ Errors:")
            for error in results['errors']:
                report.append(f"  - {error}")
        
        report.append("\n" + "="*60 + "\n")
        
        return "\n".join(report)
