# Fix CORS Issue

## Problem
CORS error: "No 'Access-Control-Allow-Origin' header is present"

## Root Cause
The CORS middleware had `allow_origins=["*"]` with `allow_credentials=True`, which is not allowed by CORS specification.

## Solution Applied
Changed `allow_credentials=False` when using `allow_origins=["*"]`.

## Next Steps: Redeploy Backend

You need to redeploy the backend to Cloud Run for the CORS fix to take effect:

```powershell
cd backend
.\deploy.ps1
```

This will:
1. Build a new Docker image with the CORS fix
2. Push to Artifact Registry
3. Deploy to Cloud Run

**After deployment (takes 2-5 minutes), try uploading again!**

## Alternative: Quick Test

If you want to test locally first:

```powershell
cd backend
# Make sure you have .env file with API keys
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then update frontend `.env.local`:
```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Restart frontend and test.

