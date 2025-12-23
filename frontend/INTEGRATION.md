# Frontend-Backend Integration Guide

Your backend is deployed at: **https://vision-compression-backend-55kvrg242a-uc.a.run.app**

## Quick Setup

### Step 1: Create Environment File

Create a `.env.local` file in the `frontend` directory:

```bash
cd frontend
```

Create `.env.local` with this content:

```
NEXT_PUBLIC_BACKEND_URL=https://vision-compression-backend-55kvrg242a-uc.a.run.app
```

**Windows PowerShell:**
```powershell
cd frontend
@"
NEXT_PUBLIC_BACKEND_URL=https://vision-compression-backend-55kvrg242a-uc.a.run.app
"@ | Out-File -FilePath .env.local -Encoding utf8
```

**macOS/Linux:**
```bash
cd frontend
echo "NEXT_PUBLIC_BACKEND_URL=https://vision-compression-backend-55kvrg242a-uc.a.run.app" > .env.local
```

### Step 2: Install Dependencies (if not done)

```bash
npm install
# or
yarn install
# or
pnpm install
```

### Step 3: Run Development Server

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Verify Integration

1. **Test Backend Connection:**
   - Visit: https://vision-compression-backend-55kvrg242a-uc.a.run.app/health
   - Should return: `{"ok": true}`

2. **Test Frontend:**
   - Open http://localhost:3000
   - Try uploading a PDF file
   - The frontend should connect to your Cloud Run backend

## CORS Configuration

The backend already has CORS enabled to allow all origins (`allow_origins=["*"]`), so your frontend should work without any CORS issues.

## Production Deployment

### Option 1: Deploy Frontend to Vercel

1. **Push to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

2. **Deploy to Vercel:**
   - Go to [vercel.com](https://vercel.com)
   - Import your GitHub repository
   - Set **Root Directory** to `frontend` (if deploying from monorepo)
   - Add environment variable:
     - **Name**: `NEXT_PUBLIC_BACKEND_URL`
     - **Value**: `https://vision-compression-backend-55kvrg242a-uc.a.run.app`
   - Deploy!

### Option 2: Update CORS for Production (Optional)

If you want to restrict CORS to specific domains, update `backend/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-frontend.vercel.app",
        # Add your production frontend URL here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Then redeploy the backend.

## Troubleshooting

### Frontend can't connect to backend

1. **Check environment variable:**
   ```bash
   # In frontend directory
   cat .env.local  # Should show your backend URL
   ```

2. **Verify backend is accessible:**
   - Visit: https://vision-compression-backend-55kvrg242a-uc.a.run.app/health
   - Should return: `{"ok": true}`

3. **Check browser console:**
   - Open DevTools (F12)
   - Look for CORS or network errors
   - Check if requests are going to the correct URL

### CORS Errors

If you see CORS errors:
- The backend already allows all origins, so this shouldn't happen
- If it does, check that the backend URL in `.env.local` is correct
- Make sure you restarted the dev server after creating `.env.local`

### Environment Variable Not Working

- Make sure the file is named `.env.local` (not `.env.local.example`)
- Restart the Next.js dev server after creating/updating `.env.local`
- In production (Vercel), set the environment variable in the Vercel dashboard

## Testing the Full Flow

1. **Upload a PDF:**
   - Go to http://localhost:3000
   - Click "Upload PDF"
   - Select a PDF file
   - Wait for processing (may take a few minutes)

2. **Ask Questions:**
   - After upload completes, you'll see a chat interface
   - Type a question about the document
   - The AI will retrieve relevant pages and answer with citations

3. **View Evidence:**
   - Check the "Evidence" panel on the right
   - See which pages were retrieved and their excerpts

## Next Steps

- ✅ Backend deployed to Cloud Run
- ✅ Frontend configured to use backend
- ⏭️ Deploy frontend to Vercel (optional)
- ⏭️ Set up custom domain (optional)
- ⏭️ Configure monitoring and alerts (optional)

