# IMAN OS

Campaign Analytics Dashboard for Smartlead - Monitor, analyze, and optimize cold email campaigns.

## Features

- **Dashboard**: Overview of all campaign metrics and performance
- **Campaign Health**: Detailed table with suggestions (Keep/Monitor/Pause/Kill)
- **Auto-suggestions**: Based on reply rate thresholds
- **Sync**: Pull latest data from Smartlead API
- **Status Management**: Change campaign status directly from UI

## Tech Stack

**Backend:**
- Python 3.11+
- FastAPI
- SQLAlchemy + aiosqlite (async SQLite)
- Smartlead API integration

**Frontend:**
- React 18
- Tailwind CSS (dark theme)
- React Router
- Lucide Icons

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

### Backend Setup

```bash
cd iman-os/backend

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your Smartlead API key

# Run the server
python run.py
```

Backend runs at: http://localhost:8000

API docs: http://localhost:8000/docs

### Frontend Setup

```bash
cd iman-os/frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

Frontend runs at: http://localhost:5173

## Environment Variables

Create a `.env` file in `/backend/` with:

```env
# Required
SMARTLEAD_API_KEY=your_smartlead_api_key_here

# Optional
DATABASE_URL=sqlite+aiosqlite:///./iman_os.db
PORT=8000
DEBUG=false
LOG_LEVEL=INFO
CORS_ORIGINS=*
```

**IMPORTANT:** Never commit your `.env` file or API keys to git.

## Suggestion Thresholds

| Suggestion | Color  | Reply Rate |
|------------|--------|------------|
| KEEP       | Green  | ≥ 2%       |
| MONITOR    | Yellow | ≥ 1%       |
| PAUSE      | Orange | ≥ 0.5%     |
| KILL       | Red    | < 0.5%     |
| LOW DATA   | Gray   | < 200 sends|

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /api/campaigns | List campaigns with stats |
| GET | /api/campaigns/{id} | Get single campaign |
| POST | /api/campaigns/{id}/status | Update campaign status |
| GET | /api/stats/overview | Dashboard stats |
| POST | /api/sync | Trigger full sync |
| GET | /api/sync/status | Last sync info |
| GET | /api/suggestions | Campaigns needing action |
| POST | /api/suggestions/{id}/apply | Apply suggestion |

## Usage

1. Start the backend: `cd backend && python run.py`
2. Start the frontend: `cd frontend && npm run dev`
3. Open http://localhost:5173
4. Click "Run Sync" to fetch campaigns from Smartlead
5. View Campaign Health page for detailed analysis
6. Apply suggestions to pause/stop underperforming campaigns

## Project Structure

```
iman-os/
├── backend/
│   ├── app/
│   │   ├── api/routes/      # API endpoints
│   │   ├── db/              # Database models
│   │   └── services/        # Business logic
│   ├── run.py               # Entry point
│   ├── requirements.txt
│   └── .env                 # Environment variables (not committed)
│
├── frontend/
│   ├── src/
│   │   ├── components/      # Reusable UI components
│   │   ├── pages/           # Page components
│   │   ├── hooks/           # Custom React hooks
│   │   └── utils/           # Utilities and API client
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

## Development

### Running Tests

```bash
# Backend sync test
cd backend
python test_sync.py
```

### Building for Production

```bash
# Frontend
cd frontend
npm run build
```

## License

Private - Internal use only.
