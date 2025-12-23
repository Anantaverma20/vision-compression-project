# Environment Variables Setup Guide

## Important: You MUST restart the backend server after creating/updating the .env file!

## Option 1: Local Development (uvicorn)

### Step 1: Create `.env` file in `backend/` directory

```bash
cd backend
```

Create a file named `.env` (not `.env.example`) with:

```bash
GEMINI_API_KEY=your_actual_gemini_api_key_here
SUPERMEMORY_API_KEY=your_actual_supermemory_api_key_here

# Note: Langfuse removed - using local observability in eval/ instead
```

### Step 2: Restart the backend server

**Stop the current server** (Ctrl+C in the terminal where it's running), then:

```bash
# Make sure you're in the backend directory
cd backend

# Activate your virtual environment (if using one)
# On Windows:
.\venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**The server MUST be restarted** for it to read the new .env file!

## Option 2: Running in Docker (Local)

If you're running the backend in Docker, the `.env` file won't work. You need to pass environment variables:

```bash
docker run -p 8000:8080 \
  -e GEMINI_API_KEY=your_key \
  -e SUPERMEMORY_API_KEY=your_key \
  vision-compression-backend
```

Or use a `.env` file with docker-compose or pass it with `--env-file`:

```bash
docker run -p 8000:8080 --env-file .env vision-compression-backend
```

## Option 3: Deployed to Cloud Run

If your backend is deployed to Google Cloud Run, you need to update environment variables there:

### Via gcloud CLI:

```powershell
gcloud run services update vision-compression-backend `
  --region us-central1 `
  --update-env-vars "GEMINI_API_KEY=your_key,SUPERMEMORY_API_KEY=your_key"
```

### Via Cloud Console:

1. Go to: https://console.cloud.google.com/run
2. Click on your service: `vision-compression-backend`
3. Click "Edit & Deploy New Revision"
4. Go to "Variables & Secrets" tab
5. Add/update:
   - `GEMINI_API_KEY` = your_key
   - `SUPERMEMORY_API_KEY` = your_key
6. Click "Deploy"

**After updating, Cloud Run will automatically redeploy with the new environment variables.**

## Observability

The evaluation framework (`eval/`) includes local observability and tracing. See the main README.md for details on:
- JSONL trace files
- Per-question artifacts  
- Local evaluation system

## Verify Environment Variables are Loaded

You can check if the backend is reading the environment variables by:

1. **Check the startup logs** - Look for warnings about missing API keys
2. **Test the health endpoint**: `curl http://localhost:8000/health`
3. **Try uploading a file** - If it still fails, check the error message

## Troubleshooting

### Still getting "GEMINI_API_KEY not found"?

1. **Verify .env file location**: Must be in `backend/.env` (same directory as `app/` folder)
2. **Check .env file format**: No spaces around `=`, no quotes needed:
   ```
   GEMINI_API_KEY=your_key_here
   ```
   NOT:
   ```
   GEMINI_API_KEY = "your_key_here"  ❌ Wrong!
   ```
3. **Restart the server**: The server only reads .env on startup
4. **Check file encoding**: Make sure it's saved as plain text (UTF-8)
5. **Check for typos**: Variable names are case-sensitive: `GEMINI_API_KEY` not `gemini_api_key`

### If running in Docker:

- Make sure you're passing `-e` flags or using `--env-file`
- The .env file in your local directory won't be automatically loaded by Docker

### If deployed to Cloud Run:

- Environment variables must be set in Cloud Run, not in a local .env file
- After updating, wait for the new revision to deploy (usually 30-60 seconds)

