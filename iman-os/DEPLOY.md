# Deploying IMAN OS to Railway

## Prerequisites

1. Install Railway CLI:
   ```bash
   npm install -g @railway/cli
   ```

2. Login to Railway:
   ```bash
   railway login
   ```

## Deployment Steps

### Option 1: Deploy as Monorepo (Recommended)

1. Create a new Railway project:
   ```bash
   cd iman-os
   railway init
   ```

2. Deploy the backend:
   ```bash
   cd backend
   railway up
   ```

3. Get the backend URL:
   ```bash
   railway domain
   ```
   Copy the URL (e.g., `https://your-backend.up.railway.app`)

4. Set backend environment variables in Railway dashboard:
   - `SMARTLEAD_API_KEY` = your Smartlead API key
   - `CORS_ORIGINS` = your frontend URL (after deploying frontend)

5. Deploy the frontend:
   ```bash
   cd ../frontend
   railway up
   ```

6. Set frontend environment variable in Railway dashboard:
   - `VITE_API_URL` = your backend URL + `/api` (e.g., `https://your-backend.up.railway.app/api`)

7. Generate domain for frontend:
   ```bash
   railway domain
   ```

### Option 2: Deploy via GitHub

1. Push your code to GitHub

2. Go to [Railway Dashboard](https://railway.app/dashboard)

3. Click "New Project" → "Deploy from GitHub repo"

4. Select your repository

5. Railway will auto-detect the Dockerfile and deploy

6. Set environment variables in the Railway dashboard

## Environment Variables

### Backend
| Variable | Required | Description |
|----------|----------|-------------|
| `SMARTLEAD_API_KEY` | Yes | Your Smartlead API key |
| `PORT` | No | Server port (default: 8000) |
| `CORS_ORIGINS` | No | Allowed CORS origins (default: *) |
| `DATABASE_URL` | No | Database connection string |
| `DEBUG` | No | Enable debug mode (default: false) |

### Frontend
| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes | Backend API URL (e.g., https://api.example.com/api) |

## Verify Deployment

1. Check backend health:
   ```bash
   curl https://your-backend.up.railway.app/health
   ```

2. Open frontend in browser:
   ```
   https://your-frontend.up.railway.app
   ```

## Troubleshooting

### Backend not starting
- Check that `SMARTLEAD_API_KEY` is set
- View logs: `railway logs`

### Frontend can't connect to backend
- Verify `VITE_API_URL` is set correctly
- Check that backend `CORS_ORIGINS` includes frontend URL

### Database issues
- Railway provides ephemeral storage by default
- For persistent data, add a Railway PostgreSQL database
