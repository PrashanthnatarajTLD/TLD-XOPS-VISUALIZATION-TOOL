# Telemetry Frontend (React + Vite + TypeScript)

Frontend migration workspace for TLD/XOPS Telemetry. This app is designed to replace Streamlit screens module-by-module without disrupting the current backend workflows.

## Stack

- React + TypeScript + Vite
- React Router for module routing
- TanStack Query for API caching and async server state
- Axios for API integration

## Current Routes

- `/` Overview
- `/telemetry` Raw telemetry fetch module (API-wired skeleton)
- `/dtc` DTC module placeholder
- `/visualize` Visualization module placeholder
- `/kpi` KPI module placeholder
- `/ai` AI module placeholder for later integration

## Local Development

1. Install dependencies:

```bash
npm install
```

2. Start dev server:

```bash
npm run dev
```

3. Build for production:

```bash
npm run build
```

## Backend API Base URL

The frontend reads API base URL from `VITE_API_BASE_URL`.

Default fallback is:

`http://localhost:8000`

Example:

```bash
VITE_API_BASE_URL=http://10.11.192.94:8000
```

## Run Backend Bridge (FastAPI)

From the project root (`telemetry-app`):

```bash
pip install -r requirements.txt
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

Credential options for LINKFMS calls:

1. Set environment variables on backend server:

```bash
LINKFMS_USERNAME=your_user
LINKFMS_PASSWORD=your_password
```

2. Or provide username/password directly from the Telemetry page form.

## Migration Plan

1. Wire `/telemetry` to existing Python fetch flow via FastAPI endpoints.
2. Add paginated table + server-side filtering.
3. Migrate DTC module.
4. Migrate KPI and export flows.
5. Add AI module when backend and guardrails are finalized.
