# LINKFMS API Integration Guide

## Overview

The EV Telemetry Analysis Platform now includes a **LinkFMSAPIAgent** that allows you to fetch real-time telemetry data directly from the LINKFMS GraphQL API.

## Features

- 🌐 Direct API connection to LINKFMS
- 🔐 Secure authentication with HTTPBasicAuth
- 📅 Date range filtering
- 🚗 Vehicle-specific data fetching
- 📊 Automatic DataFrame creation
- ✓ Connection testing
- 📋 Available vehicle discovery

## LINKFMS API Configuration

### Endpoint
```
https://www.linkfms.com/fms/graphql
```

### Authentication
- **Method:** HTTP Basic Authentication
- **Username:** Your LINKFMS username
- **Password:** Your LINKFMS password

### Data Available
The API provides the following fields for each position record:

- `id` - Unique record identifier
- `gpsProvider` - GPS provider information
- `date` - Timestamp of the reading
- `dateReceived` - When data was received
- `dateProcessed` - When data was processed
- `plateNumber` - Vehicle license plate
- `longitude` - GPS longitude
- `latitude` - GPS latitude
- `telemetry` - Raw telemetry data string
- `accuracy` - GPS accuracy
- `speed` - Vehicle speed
- `engineState` - Engine status (Running/Idle/Off)
- `odometer` - Odometer reading
- `motorHour` - Motor hour meter

## Using LinkFMSAPIAgent Programmatically

### Basic Usage

```python
from agents import LinkFMSAPIAgent

# Initialize agent with credentials
api_agent = LinkFMSAPIAgent(
    username="prashanth.nataraj",
    password="Prashanth@2026"
)

# Test connection
if api_agent.test_connection():
    print("✓ Connected to LINKFMS!")

# Fetch data for a vehicle
telemetry_data = api_agent.fetch_by_date_and_vehicle(
    plate_number="T118059",
    start_date="2026-04-23",
    end_date="2026-05-12"
)

# Access the data
df = telemetry_data.dataframe
print(f"Fetched {len(df)} records")
```

### Get Data Summary

```python
summary = api_agent.get_data_summary()
print(f"Total records: {summary['total_records']}")
print(f"Date range: {summary['timestamp_range']}")
print(f"Plate numbers: {summary['plate_numbers']}")
```

### Custom Filters

```python
# Define custom filter
custom_filter = {
    "operator": "and",
    "filters": [
        {
            "field": "date",
            "operator": "between",
            "value": "2026-04-23T00:00:01.000Z AND 2026-05-12T23:59:59.000Z",
            "timezone": "Asia/Calcutta"
        },
        {
            "field": "plateNumber",
            "operator": "equals",
            "value": "T118059"
        }
    ]
}

# Fetch with custom filter
data = api_agent.fetch_by_filters(custom_filter)
```

### Discover Available Vehicles

```python
# Get list of vehicles with data in date range
vehicles = api_agent.get_available_vehicles(
    start_date="2026-04-23",
    end_date="2026-05-12"
)

print(f"Available vehicles: {vehicles}")
```

## Web UI Usage

### Step-by-Step Guide

1. **Navigate to LINKFMS API Fetch Module**
   - Click "🌐 LINKFMS API Fetch" in the sidebar

2. **Enter Your Credentials**
   - Username: Your LINKFMS username
   - Password: Your LINKFMS password

3. **Test Connection (Optional)**
   - Click "🔗 Test Connection" to verify credentials
   - You'll see a success or error message

4. **Enter Search Parameters**
   - Vehicle Plate Number: License plate (e.g., "T118059")
   - Start Date: Beginning of date range
   - End Date: End of date range

5. **Fetch Data**
   - Click "📥 Fetch Data"
   - Wait for the API call to complete
   - Data will be displayed in preview table

6. **Review Results**
   - See total records, date range, and memory usage
   - Review data preview (first 10 rows)
   - Check statistics and missing values

## Data Processing Pipeline

After fetching from LINKFMS API, you can:

1. **Clean Data** - Remove duplicates, outliers, handle missing values
2. **Align Timestamps** - Forward fill to common timestamps
3. **Visualize** - Create charts and graphs
4. **Download** - Export to CSV or Excel

## API Query Structure

### Example Query Variables

```json
{
  "params": {
    "startIndex": 0,
    "pageSize": 1000000,
    "filter": {
      "operator": "and",
      "filters": [
        {
          "field": "date",
          "operator": "between",
          "value": "2026-04-23T00:00:01.000Z AND 2026-05-12T23:59:59.000Z",
          "timezone": "Asia/Calcutta"
        },
        {
          "field": "plateNumber",
          "operator": "equals",
          "value": "T118059"
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
```

## Filter Operators

The API supports the following filter operators:

- `equals` - Exact match
- `between` - Range (for dates)
- `contains` - String contains
- `startsWith` - String starts with
- `endsWith` - String ends with
- `greaterThan` - Greater than
- `lessThan` - Less than
- `greaterThanOrEqual` - Greater than or equal
- `lessThanOrEqual` - Less than or equal

## Error Handling

### Connection Error
```
❌ Connection error. Unable to reach LINKFMS API.
```
**Solution:** Check internet connection and API endpoint

### Authentication Error
```
❌ API Error 401: Unauthorized
```
**Solution:** Verify username and password are correct

### GraphQL Error
```
❌ GraphQL Error: [error details]
```
**Solution:** Check filter syntax and field names

### Timeout Error
```
❌ Request timed out. API is taking too long to respond.
```
**Solution:** Try with smaller date range or later

### No Data Found
```
⚠️ No records found for the specified criteria
```
**Solution:** Check plate number, date range, or vehicle availability

## Date Format

The API accepts dates in multiple formats:

### Format Options
- **ISO 8601**: `2026-05-12T23:59:59.000Z`
- **Date only**: `2026-05-12` (auto-converted to time range)
- **Timezone**: Default is `Asia/Calcutta` (IST/UTC+5:30)

### Examples
```python
# These are equivalent
api_agent.fetch_by_date_and_vehicle(
    plate_number="T118059",
    start_date="2026-04-23",        # Auto-formatted to 2026-04-23T00:00:01.000Z
    end_date="2026-05-12"            # Auto-formatted to 2026-05-12T23:59:59.000Z
)

api_agent.fetch_by_date_and_vehicle(
    plate_number="T118059",
    start_date="2026-04-23T00:00:01.000Z",
    end_date="2026-05-12T23:59:59.000Z"
)
```

## Timezone Handling

The API uses `Asia/Calcutta` (IST) timezone by default:

- **IST Offset:** UTC+5:30
- **Data Processing:** Timestamps are converted to UTC in the DataFrame

### Example
```
Request: Date range in IST (Asia/Calcutta)
Response: Timestamps stored in UTC
Display: Converts to local timezone
```

## Performance Tips

1. **Limit Date Range**
   - Smaller date ranges = faster response
   - Recommended: Max 30-60 days per request

2. **Batch Processing**
   - For large datasets, fetch in multiple date ranges
   - Combine results before analysis

3. **Page Size**
   - Default: 1,000,000 records
   - Adjust if server timeouts occur

## Troubleshooting

### Issue: "Invalid credentials"
- Check username and password spelling
- Verify account is active in LINKFMS
- Test with credentials manually in LINKFMS portal

### Issue: "No records found"
- Verify plate number exists in LINKFMS system
- Check date range has data for that vehicle
- Try a wider date range
- Use "Get Available Vehicles" to verify plate number

### Issue: "Request timeout"
- Reduce the date range
- Try again later (API might be busy)
- Check network connectivity

### Issue: "Memory error with large dataset"
- Reduce page size
- Fetch data in multiple requests
- Filter by more specific criteria

## Security Best Practices

### Do's
✓ Use environment variables for credentials in production
✓ Keep password secure
✓ Don't share credentials in code
✓ Use HTTPS (API already uses HTTPS)
✓ Test connection before bulk operations

### Don'ts
✗ Don't hardcode credentials in scripts
✗ Don't commit credentials to version control
✗ Don't share credentials with unauthorized users
✗ Don't log passwords or sensitive data

## Integration with Other Agents

After fetching from LINKFMS API:

```python
# 1. Fetch from API
api_agent = LinkFMSAPIAgent(username, password)
telemetry_data = api_agent.fetch_by_date_and_vehicle(...)

# 2. Clean the data
from agents import CleanTelemetryAgent
clean_agent = CleanTelemetryAgent()
cleaned = clean_agent.clean_data(telemetry_data)

# 3. Align timestamps
from agents import TimestampAlignmentAgent
align_agent = TimestampAlignmentAgent()
aligned = align_agent.align_parameters(cleaned)

# 4. Visualize
from agents import VisualizationAgent
viz_agent = VisualizationAgent()
fig = viz_agent.create_line_chart(aligned, "EV Battery State of Charge")

# 5. Download
from agents import DownloadAgent
download_agent = DownloadAgent()
download_agent.download_excel(aligned, "output.xlsx")
```

## API Response Structure

### Successful Response
```json
{
  "data": {
    "positionService_findByFilter": {
      "results": [
        {
          "id": "...",
          "gpsProvider": "...",
          "date": "2026-05-12T10:30:00.000Z",
          "dateProcessed": "2026-05-12T10:31:00.000Z",
          "plateNumber": "T118059",
          ...
        }
      ],
      "totalCount": 15000
    }
  }
}
```

### Error Response
```json
{
  "errors": [
    {
      "message": "Error details",
      "extensions": {}
    }
  ]
}
```

## Support

For issues with LINKFMS API:
1. Verify credentials are correct
2. Check LINKFMS account status
3. Verify date range has data
4. Check network connectivity
5. Contact LINKFMS support with error details

---

**Version:** 1.0  
**Last Updated:** May 2026  
**Author:** LINKFMS Development Team
