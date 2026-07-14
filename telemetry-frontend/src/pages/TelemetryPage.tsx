import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTelemetry } from '../services/telemetryApi'
import { getSession } from '../auth/session'

export function TelemetryPage() {
  const [plateNumber, setPlateNumber] = useState('T118059')
  const [startDate, setStartDate] = useState('2026-06-01')
  const [endDate, setEndDate] = useState('2026-06-30')
  const [timezone, setTimezone] = useState('Asia/Kolkata')
  const [submitted, setSubmitted] = useState(false)
  const session = getSession()

  const query = useQuery({
    queryKey: ['telemetry', plateNumber, startDate, endDate, timezone],
    queryFn: () =>
      fetchTelemetry({
        plateNumber,
        startDate,
        endDate,
        timezone,
        sessionId: session?.sessionId,
      }),
    enabled: submitted,
  })

  return (
    <section className="page">
      <header className="page-head">
        <h2>Raw Telemetry</h2>
        <p>Fetch Parameters</p>
      </header>

      <div className="panel">
        <div className="form-grid">
          <label>
            Plate Number
            <input value={plateNumber} onChange={(e) => setPlateNumber(e.target.value)} />
          </label>
          <label>
            Start Date
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            End Date
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <label>
            Timezone
            <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              <option value="Asia/Kolkata">Asia/Kolkata</option>
              <option value="Europe/Paris">Europe/Paris</option>
              <option value="UTC">UTC</option>
            </select>
          </label>
        </div>

        <button
          className="btn-primary"
          onClick={() => setSubmitted(true)}
          type="button"
          disabled={query.isLoading}
        >
          {query.isLoading ? 'Fetching...' : 'Fetch Telemetry'}
        </button>
      </div>

      {query.isError && (
        <p className="error-text">Unable to fetch telemetry. Please verify your login session and try again.</p>
      )}

      {query.data && (
        <div className="panel">
          <h3>Result Summary</h3>
          <p>Total Rows: {query.data.totalRows}</p>
          <p>Returned Rows: {query.data.returnedRows ?? query.data.records.length}</p>
          <p>
            Date Range: {query.data.dateRange?.start ?? 'N/A'} to {query.data.dateRange?.end ?? 'N/A'}
          </p>
          {query.data.message && <p>{query.data.message}</p>}
        </div>
      )}
    </section>
  )
}
