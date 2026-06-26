"""Agent for fetching DTC data from LINKFMS GraphQL API."""

import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from typing import Optional
from datetime import datetime


class LinkFMSDTCAgent:
    """Fetches Diagnostic Trouble Code data from LINKFMS."""

    API_URL = "https://www.linkfms.com/fms/graphql"

    DTC_QUERY = """
    query q($params: FindByFilterParamsInput) {
      diagnosticTroubleCodeService_findByFilter(params: $params) {
        results {
          id
          timestamp
          equipmentResource {
            id
            plateNumber
            identifier
            equipmentModel {
              id
              name
              equipmentModelFamily {
                id
                equipmentProductType {
                  id
                  name
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          name
          categoryDescription
          categoryCode
          severity
          description
          code
          source
          rawValue
          organization {
            id
            qualifiedName
            __typename
          }
          __typename
        }
        totalCount
        __typename
      }
    }
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def fetch(self, plate_number: str, start_date: str, end_date: str,
              page_size: int = 100000) -> Optional[pd.DataFrame]:
        """
        Fetch DTC records for a vehicle within a date range.
        Returns a flat DataFrame or None on failure.
        """
        if 'T' not in start_date:
            start_date = f"{start_date}T00:00:01.000+05:30"
        if 'T' not in end_date:
            end_date = f"{end_date}T23:59:59.000+05:30"

        variables = {
            "params": {
                "startIndex": 0,
                "pageSize": page_size,
                "aggregateFunctions": None,
                "sorts": [{"field": "timestamp", "direction": "DESC"}],
                "filter": {
                    "operator": "and",
                    "filters": [
                        {
                            "operator": "or",
                            "filters": [
                                {
                                    "field": "timestamp",
                                    "operator": "between",
                                    "value": f"{start_date} AND {end_date}",
                                    "timezone": "Asia/Calcutta"
                                }
                            ]
                        },
                        {
                            "field": "equipmentResource.plateNumber",
                            "operator": "equals",
                            "value": plate_number
                        }
                    ]
                }
            }
        }

        try:
            response = requests.post(
                self.API_URL,
                json={"operationName": "q", "query": self.DTC_QUERY, "variables": variables},
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=60
            )

            if response.status_code != 200:
                print(f"❌ HTTP {response.status_code}: {response.text}")
                return None

            data = response.json()
            if 'errors' in data and data['errors']:
                print(f"❌ GraphQL error: {data['errors']}")
                return None

            results = data['data']['diagnosticTroubleCodeService_findByFilter']['results']
            total = data['data']['diagnosticTroubleCodeService_findByFilter']['totalCount']
            print(f"✓ Fetched {len(results)} DTC records (Total: {total})")

            if not results:
                return None

            # Flatten nested fields
            rows = []
            for r in results:
                eq = r.get('equipmentResource') or {}
                model = eq.get('equipmentModel') or {}
                family = model.get('equipmentModelFamily') or {}
                product_type = family.get('equipmentProductType') or {}
                rows.append({
                    'timestamp':           r.get('timestamp'),
                    'plateNumber':         eq.get('plateNumber'),
                    'equipmentResourceId': eq.get('id'),
                    'identifier':          eq.get('identifier'),
                    'equipmentModel':      model.get('name'),
                    'equipmentProductType': product_type.get('name'),
                    'code':                r.get('code'),
                    'name':                r.get('name'),
                    'description':         r.get('description'),
                    'categoryCode':        r.get('categoryCode'),
                    'categoryDescription': r.get('categoryDescription'),
                    'severity':            r.get('severity'),
                    'source':              r.get('source'),
                    'rawValue':            r.get('rawValue'),
                    'organization':        (r.get('organization') or {}).get('qualifiedName'),
                })

            df = pd.DataFrame(rows)
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df

        except requests.exceptions.Timeout:
            print("❌ Request timed out.")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
