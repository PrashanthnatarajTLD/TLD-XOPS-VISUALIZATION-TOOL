import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { ProtectedRoute } from '../auth/ProtectedRoute'
import { OverviewPage } from '../pages/OverviewPage'
import { TelemetryPage } from '../pages/TelemetryPage'
import { DtcPage } from '../pages/DtcPage'
import { VisualizePage } from '../pages/VisualizePage'
import { KpiPage } from '../pages/KpiPage'
import { AiPage } from '../pages/AiPage'
import { LoginPage } from '../pages/LoginPage'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'telemetry', element: <TelemetryPage /> },
      { path: 'dtc', element: <DtcPage /> },
      { path: 'visualize', element: <VisualizePage /> },
      { path: 'kpi', element: <KpiPage /> },
      { path: 'ai', element: <AiPage /> },
    ],
  },
])
