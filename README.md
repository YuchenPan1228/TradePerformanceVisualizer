# TradePerformanceVisualizer

A full-stack application for visualizing trade performance with a Flask backend and React frontend.

## Prerequisites

- Python 3.12+ (virtual environment already set up in `backend/venv/`)
- Node.js and npm (for the React frontend)

## Running the Application

### Backend (Flask API)

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Activate the virtual environment:
   ```bash
   source venv/bin/activate  # On macOS/Linux
   # or
   venv\Scripts\activate  # On Windows
   ```

3. Install dependencies (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```

4. Run the Flask server:
   ```bash
   python app.py
   ```

   The backend will run on `http://localhost:5000`

### Frontend (React)

1. Open a new terminal window and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies (if not already installed):
   ```bash
   npm install
   ```

3. Start the React development server:
   ```bash
   npm start
   ```

   The frontend will run on `http://localhost:3000` and automatically open in your browser.

## Quick Start (Both Services)

To run both services simultaneously, open two terminal windows:

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
python app.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm start
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