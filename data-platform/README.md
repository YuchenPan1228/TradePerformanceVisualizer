# SnapTrade Data Platform (internal)

A **standalone** data explorer for the raw SnapTrade export JSON and synced
database tables. This is a separate app from the user-facing analytical
dashboard (`frontend/`) — it's meant for the creators only, lives on its own
URL, and is **not** linked from the dashboard.

It renders `SnapTradeExplorer` (accounts / positions / orders / transactions)
and talks to the shared Flask backend's `/api/explorer/*` and `/api/db/*`
endpoints.

## Running locally

The backend must be running first (from `../backend`, on port 5001):

```bash
cd ../backend
source venv/bin/activate
python app.py
```

Then start this app (defaults to port **3001** via `.env`):

```bash
cd data-platform
npm install        # first time only
npm start
```

Open http://localhost:3001

Port layout while everything runs:

| App                        | Port | Path        |
|----------------------------|------|-------------|
| Flask backend              | 5001 | `backend/`  |
| User-facing dashboard      | 3000 | `frontend/` |
| **Data platform (this)**   | 3001 | `data-platform/` |

API calls to `/api/*` are proxied to `http://localhost:5001` (see `proxy` in
`package.json`).

## Authentication

The data this app reads is gated by **HTTP Basic Auth** on the backend
(`/api/explorer/*` and `/api/db/*`). The browser prompts once for a shared
username/password. There is no per-user login.

Set the credentials via env vars when starting the backend (defaults shown):

```bash
EXPLORER_USER=admin EXPLORER_PASS=changeme python app.py
```

> **Change `EXPLORER_PASS` before exposing this anywhere non-local** — these
> endpoints serve real brokerage data for all users.

## Notes

- `SnapTradeExplorer.jsx` here is a copy of the component that previously lived
  in `frontend/src/`. The dashboard no longer renders it — the "Trade Explorer"
  tab was removed from `frontend/src/App.js`.
- Tailwind is loaded via CDN in `public/index.html`, matching the dashboard.
