"""Agent for fetching data directly from LINKFMS GraphQL API."""

import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
from data_models.telemetry import TelemetryData, TelemetryParameter
from config.parameters import TELEMETRY_PARAMETERS


class LinkFMSAPIAgent:
    """Agent for fetching telemetry data from LINKFMS GraphQL API."""
    
    # LINKFMS API Configuration
    API_URL = "https://www.linkfms.com/fms/graphql"
    
    # GraphQL Query for fetching position data
    POSITION_QUERY = """
    query q($params: FindByFilterParamsInput) {
      positionService_findByFilter(params: $params) {
        results {
          id
          gpsProvider
          date
          dateReceived
          dateProcessed
          plateNumber
          longitude
          latitude
          telemetry
          accuracy
          speed
          engineState
          odometer
          motorHour
          __typename
        }
        totalCount
        __typename
      }
    }
    """
    
    def __init__(self, username: str, password: str):
        """
        Initialize LinkFMS API agent with credentials.
        
        Args:
            username: LINKFMS username
            password: LINKFMS password
        """
        self.username = username
        self.password = password
        self.fetched_data: Optional[TelemetryData] = None
        self.last_response: Optional[Dict] = None
    
    def _make_request(self, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Make authenticated request to LINKFMS API.
        
        Args:
            variables: GraphQL variables
            
        Returns:
            Response data or None if request failed
        """
        try:
            print(f"🔗 Connecting to LINKFMS API: {self.API_URL}")
            
            response = requests.post(
                self.API_URL,
                json={
                    "operationName": "q",
                    "query": self.POSITION_QUERY,
                    "variables": variables
                },
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for GraphQL errors
                if 'errors' in data and data['errors']:
                    print(f"❌ GraphQL Error: {data['errors']}")
                    return None
                
                self.last_response = data
                return data
            else:
                print(f"❌ API Error {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            print("❌ Request timed out. API is taking too long to respond.")
            return None
        except requests.exceptions.ConnectionError:
            print("❌ Connection error. Unable to reach LINKFMS API.")
            return None
        except Exception as e:
            print(f"❌ Error making request: {str(e)}")
            return None
    
    def fetch_by_date_and_vehicle(self, plate_number: str,
                                 start_date: str, end_date: str,
                                 page_size: int = 1000000,
                                 filter_diagnostic: bool = False) -> Optional[TelemetryData]:
        """
        Fetch telemetry data for a specific vehicle within a date range.
        
        Args:
            plate_number: Vehicle plate number (e.g., "T118059")
            start_date: Start date in format "YYYY-MM-DD" or ISO format
            end_date: End date in format "YYYY-MM-DD" or ISO format
            page_size: Maximum number of records to fetch
            filter_diagnostic: If True, only fetch records where telemetry contains "Diagnostic"
            
        Returns:
            TelemetryData object or None if fetch failed
        """
        # Format dates for API
        if 'T' not in start_date:
            start_date = f"{start_date}T00:00:01.000+05:30"
        if 'T' not in end_date:
            end_date = f"{end_date}T23:59:59.000+05:30"
        
        print(f"🚗 Fetching data for vehicle: {plate_number}")
        print(f"📅 Date range: {start_date} to {end_date}")
        if filter_diagnostic:
            print("🔍 Filter: Diagnostic records only")
        
        # Build filters list
        filters = [
            {
                "field": "date",
                "operator": "between",
                "value": f"{start_date} AND {end_date}",
                "timezone": "Asia/Calcutta"
            },
            {
                "field": "plateNumber",
                "operator": "equals",
                "value": plate_number
            }
        ]
        
        # Add diagnostic filter only if requested
        if filter_diagnostic:
            filters.append({
                "field": "telemetry",
                "operator": "contains",
                "value": "Diagnostic"
            })
        
        variables = {
            "params": {
                "startIndex": 0,
                "pageSize": page_size,
                "filter": {
                    "operator": "and",
                    "filters": filters
                },
                "sorts": [
                    {
                        "field": "date",
                        "direction": "DESC"
                    }
                ]
            }
        }
        
        # Make API request
        response_data = self._make_request(variables)
        
        if response_data is None:
            return None
        
        # Extract results
        try:
            results = response_data['data']['positionService_findByFilter']['results']
            total_count = response_data['data']['positionService_findByFilter']['totalCount']
            
            print(f"✓ Fetched {len(results)} records (Total available: {total_count})")
            
            if not results:
                print("⚠️ No records found for the specified criteria")
                return None
            
            # Create DataFrame
            df = pd.DataFrame(results)
            
            # Only rename telemetry column; keep date columns with original names
            df = df.rename(columns={
                'telemetry': 'telemetry_raw'
            })

            # Convert all 3 date columns to UTC (timezone conversion handled in app)
            for col in ['date', 'dateReceived', 'dateProcessed']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

            # Use dateProcessed as the main timestamp column
            df = df.rename(columns={'dateProcessed': 'timestamp'})
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            print(f"✓ Created DataFrame with shape: {df.shape}")
            
            # Create TelemetryData object
            parameters = []
            for col in df.columns:
                if col == 'timestamp':
                    continue
                
                if col in TELEMETRY_PARAMETERS:
                    param_config = TELEMETRY_PARAMETERS[col]
                    parameters.append(TelemetryParameter(
                        name=col,
                        unit=param_config.get('unit'),
                        data_type=param_config.get('data_type', 'string'),
                        description=param_config.get('description', '')
                    ))
                else:
                    parameters.append(TelemetryParameter(name=col))
            
            self.fetched_data = TelemetryData(
                dataframe=df,
                parameters=parameters,
                timestamp_column='timestamp',
                source_file=f"LINKFMS API - {plate_number}"
            )
            
            return self.fetched_data
            
        except KeyError as e:
            print(f"❌ Error parsing API response: {str(e)}")
            return None
        except Exception as e:
            print(f"❌ Error processing data: {str(e)}")
            return None
    
    def fetch_by_filters(self, filters: Dict[str, Any],
                        page_size: int = 1000000) -> Optional[TelemetryData]:
        """
        Fetch data using custom filters.

        Args:
            filters: Custom filter dictionary
            page_size: Maximum number of records to fetch

        Returns:
            TelemetryData object or None
        """
        print("🔍 Fetching data with custom filters...")
        
        variables = {
            "params": {
                "startIndex": 0,
                "pageSize": page_size,
                "filter": filters,
                "sorts": [
                    {
                        "field": "date",
                        "direction": "DESC"
                    }
                ]
            }
        }
        
        response_data = self._make_request(variables)
        
        if response_data is None:
            return None
        
        try:
            results = response_data['data']['positionService_findByFilter']['results']
            
            if not results:
                print("⚠️ No records found")
                return None
            
            df = pd.DataFrame(results)
            df = df.rename(columns={'dateProcessed': 'timestamp'})
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            print(f"✓ Fetched {len(df)} records")
            
            self.fetched_data = TelemetryData(
                dataframe=df,
                parameters=[],
                timestamp_column='timestamp',
                source_file="LINKFMS API"
            )
            
            return self.fetched_data
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None
    
    def get_fetched_data(self) -> Optional[TelemetryData]:
        """Get last fetched data."""
        return self.fetched_data
    
    def get_data_summary(self) -> Dict[str, Any]:
        """Get summary of fetched data."""
        if self.fetched_data is None:
            return {}
        
        df = self.fetched_data.dataframe
        
        summary = {
            'total_records': len(df),
            'timestamp_range': {
                'start': df['timestamp'].min(),
                'end': df['timestamp'].max(),
            },
            'columns': list(df.columns),
            'memory_usage_mb': df.memory_usage(deep=True).sum() / 1024 / 1024,
            'plate_numbers': df['plateNumber'].unique().tolist() if 'plateNumber' in df.columns else [],
            'gps_providers': df['gpsProvider'].unique().tolist() if 'gpsProvider' in df.columns else [],
        }
        
        return summary
    
    def test_connection(self) -> bool:
        """
        Test LINKFMS API connection with dummy query.
        
        Returns:
            True if connection successful, False otherwise
        """
        print("🔗 Testing LINKFMS API connection...")
        
        test_variables = {
            "params": {
                "startIndex": 0,
                "pageSize": 1,
                "filter": {
                    "operator": "and",
                    "filters": []
                }
            }
        }
        
        response = self._make_request(test_variables)
        
        if response is not None:
            print("✓ Connection successful!")
            return True
        else:
            print("❌ Connection failed!")
            return False
    
    def get_available_vehicles(self, start_date: str, end_date: str) -> Optional[List[str]]:
        """
        Get list of vehicles with data in specified date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of plate numbers or None
        """
        print("📋 Fetching available vehicles...")
        
        if 'T' not in start_date:
            start_date = f"{start_date}T00:00:01.000+05:30"
        if 'T' not in end_date:
            end_date = f"{end_date}T23:59:59.000+05:30"
        
        variables = {
            "params": {
                "startIndex": 0,
                "pageSize": 10000,
                "filter": {
                    "operator": "and",
                    "filters": [
                        {
                            "field": "date",
                            "operator": "between",
                            "value": f"{start_date} AND {end_date}",
                            "timezone": "Asia/Calcutta"
                        }
                    ]
                },
                "sorts": [
                    {
                        "field": "date",
                        "direction": "DESC"
                    }
                ]
            }
        }
        
        response_data = self._make_request(variables)
        
        if response_data is None:
            return None
        
        try:
            results = response_data['data']['positionService_findByFilter']['results']
            df = pd.DataFrame(results)
            
            if 'plateNumber' in df.columns:
                vehicles = df['plateNumber'].unique().tolist()
                print(f"✓ Found {len(vehicles)} vehicles")
                return vehicles
            else:
                return None
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None
