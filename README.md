# TradePerformanceVisualizer

A full-stack application for visualizing trade performance.

## Components

| Component       | Path             | Port | Deployed | Description                                                      |
| --------------- | ---------------- | ---- | -------- | ---------------------------------------------------------------- |
| Backend (Flask) | `backend/`       | 5001 | yes      | REST API for the dashboard + the internal explorer endpoints.   |
| Dashboard       | `frontend/`      | 3000 | yes      | User-facing React app (session auth).                           |
| Data explorer   | `data-platform/` | 3001 | no (local-only) | Internal, creators-only React explorer behind HTTP Basic Auth. |

The dashboard and explorer both talk to the single Flask backend on `:5001`.
The explorer's API (`/api/explorer/*`, `/api/db/*`) lives inside the backend,
gated by HTTP Basic Auth.

## Prerequisites

- Python 3.12+
- Node.js and npm

## Setup

### Backend

```bash
cd backend
python3 -m venv venv            # create the virtual environment
source venv/bin/activate        # macOS/Linux  (venv\Scripts\activate on Windows)
pip install -r requirements.txt
```

Secrets and runtime data are **not** committed. On first run the backend
auto-creates the files it needs; templates are provided:

- `backend/users.example.json` → copy to `backend/users.json`
- `backend/data-export/account-data.example.json` → copy to `backend/data-export/account-data.json`

## Running the Application

### Dashboard + backend (quick start)

```bash
cd frontend
npm install        # first time only
npm run dev        # starts the Flask backend (:5001) then the dashboard (:3000)
```

### Running services separately

**Backend (Flask API):**

```bash
cd backend
source venv/bin/activate
python app.py      # http://localhost:5001
```

**Dashboard (React):**

```bash
cd frontend
npm install        # first time only
npm start          # http://localhost:3000
```

**Data explorer (React, local-only):**

```bash
cd data-platform
npm install        # first time only
cp .env.example .env   # first time only (sets PORT=3001)
npm start          # http://localhost:3001 — requires the backend on :5001
```

## API Endpoints

The backend provides the following endpoints:

- `GET /api/health` - Health check
- `GET /api/portfolio/summary` - Portfolio summary
- `GET /api/portfolio/positions` - Portfolio positions
- `GET /api/portfolio/history` - Portfolio history
- `GET /api/accounts` - User accounts
- `GET /api/transactions` - Recent transactions
- `GET /api/watchlist` - Watchlist
- `GET /api/watchlist/quotes` - Watchlist quotes
- `GET /api/symbols/quote` - Single symbol quote
- `GET /api/search` - Search holdings and watchlist

Internal explorer endpoints (HTTP Basic Auth): `/api/explorer/*`, `/api/db/*`.
