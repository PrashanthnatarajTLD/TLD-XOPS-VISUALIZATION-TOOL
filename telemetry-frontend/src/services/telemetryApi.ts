import { apiClient } from './apiClient'
import type { DtcFetchResponse, TelemetryFetchParams, TelemetryFetchResponse } from '../types/telemetry'

export async function fetchTelemetry(params: TelemetryFetchParams): Promise<TelemetryFetchResponse> {
  const response = await apiClient.post<TelemetryFetchResponse>('/api/telemetry/fetch', params)
  return response.data
}

export async function fetchDtc(params: TelemetryFetchParams): Promise<DtcFetchResponse> {
  const response = await apiClient.post<DtcFetchResponse>('/api/dtc/fetch', params)
  return response.data
}
