export interface TelemetryFetchParams {
  plateNumber: string
  startDate: string
  endDate: string
  timezone: string
  sessionId?: string
  username?: string
  password?: string
  pageSize?: number
  previewRows?: number
}

export interface TelemetryFetchResponse {
  records: Array<Record<string, string | number | boolean | null>>
  totalRows: number
  returnedRows?: number
  dateRange?: {
    start?: string
    end?: string
  }
  message?: string
}

export interface DtcFetchResponse {
  records: Array<Record<string, string | number | boolean | null>>
  totalRows: number
  returnedRows?: number
  message?: string
}
