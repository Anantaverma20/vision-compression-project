# Cloud Run Deployment Guide

## Quick Setup

### 1. Update Environment Variables in Cloud Run

**Option A: Using the PowerShell script (Recommended)**

```powershell
cd backend
.\update-env-vars.ps1
```

The script will prompt you for:
- GEMINI_API_KEY
- SUPERMEMORY_API_KEY

**Option B: Using gcloud CLI directly**

```powershell
gcloud run services update vision-compression-backend `
  --region us-central1 `
  --update-env-vars "GEMINI_API_KEY=your_key,SUPERMEMORY_API_KEY=your_key"
```

**Option C: Using Cloud Console (Web UI)**

1. Go to: https://console.cloud.google.com/run
2. Click on your service: `vision-compression-backend`
3. Click "Edit & Deploy New Revision"
4. Go to "Variables & Secrets" tab
5. Add/update:
   - `GEMINI_API_KEY` = your_key
   - `SUPERMEMORY_API_KEY` = your_key
6. Click "Deploy"

**After updating, Cloud Run will automatically redeploy (takes 30-60 seconds).**

### 2. Get Your Cloud Run Service URL

```powershell
gcloud run services describe vision-compression-backend `
  --region us-central1 `
  --format 'value(status.url)'
```

### 3. Update Frontend to Use Cloud Run URL

1. Go to `frontend` directory
2. Create/update `.env.local` file:
   ```
   NEXT_PUBLIC_BACKEND_URL=https://your-cloud-run-url.run.app
   ```
3. Restart the frontend dev server:
   ```powershell
   npm run dev
   ```

### 4. Verify Everything Works

1. **Check backend health:**
   ```powershell
   curl https://your-cloud-run-url.run.app/health
   ```
   Should return: `{"ok":true}`

2. **Test from frontend:**
   - Open http://localhost:3000
   - Check that "Backend online" shows in the header
   - Try uploading a PDF

## Troubleshooting

### Backend shows "GEMINI_API_KEY not found"

- Environment variables were not set in Cloud Run
- Run `.\update-env-vars.ps1` to set them
- Wait 30-60 seconds for the new revision to deploy

### Frontend can't connect to backend

- Check that `NEXT_PUBLIC_BACKEND_URL` in `.env.local` matches your Cloud Run URL
- Make sure Cloud Run service allows unauthenticated requests
- Check browser console for CORS errors (backend should allow all origins)

### Check Cloud Run Logs

```powershell
gcloud run services logs read vision-compression-backend `
  --region us-central1 `
  --limit 50
```

## Required Environment Variables

- `GEMINI_API_KEY` - Get from: https://aistudio.google.com/app/apikey
- `SUPERMEMORY_API_KEY` - Get from: https://supermemory.ai

## Deployment Script

To redeploy with code changes:

```powershell
.\deploy.ps1
```

This will:
1. Build Docker image
2. Push to Artifact Registry
3. Deploy to Cloud Run
4. Set environment variables (if provided)

