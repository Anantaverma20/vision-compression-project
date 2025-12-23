# Vision Compression Document Chat Frontend

A Next.js frontend application for the Vision Compression Document Chatbot demo. This application provides a polished UI for uploading PDF documents, processing them, and chatting with an AI assistant that retrieves evidence from the documents.

## Features

- **Document Upload**: Upload PDF files and process them through the vision compression pipeline
- **Chat Interface**: Ask questions about uploaded documents with real-time responses
- **Evidence Panel**: View retrieved pages and excerpts that support the AI's answers
- **Markdown Rendering**: Beautiful markdown rendering for answers with citation support
- **Responsive Design**: Works on desktop and tablet devices

## Tech Stack

- **Next.js 14+** (App Router)
- **TypeScript**
- **TailwindCSS**
- **shadcn/ui** components
- **React Markdown** for answer rendering

## Getting Started

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Backend API running (see backend README)

### Installation

1. Install dependencies:

```bash
npm install
# or
yarn install
# or
pnpm install
```

2. Set up environment variables:

Copy `.env.local.example` to `.env.local` and update the backend URL:

```bash
cp .env.local.example .env.local
```

Edit `.env.local`:
```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

3. Run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Deployment to Vercel

### Step 1: Push to GitHub

1. Initialize git repository (if not already done):
```bash
git init
git add .
git commit -m "Initial commit"
```

2. Create a new repository on GitHub and push:
```bash
git remote add origin <your-github-repo-url>
git push -u origin main
```

### Step 2: Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) and sign in with your GitHub account
2. Click "Add New Project"
3. Import your GitHub repository
4. Configure the project:
   - **Framework Preset**: Next.js (auto-detected)
   - **Root Directory**: `vision-compression-project/frontend` (if deploying from monorepo root) or leave blank if deploying frontend folder separately
   - **Build Command**: `npm run build` (or `yarn build` / `pnpm build`)
   - **Output Directory**: `.next` (default)
   - **Install Command**: `npm install` (or `yarn install` / `pnpm install`)

### Step 3: Set Environment Variables

In the Vercel project settings:

1. Go to **Settings** → **Environment Variables**
2. Add the following variable:
   - **Name**: `NEXT_PUBLIC_BACKEND_URL`
   - **Value**: Your deployed backend URL (e.g., `https://your-backend.vercel.app` or `https://api.yourdomain.com`)
   - **Environment**: Production, Preview, and Development (select all)

### Step 4: Deploy

1. Click **Deploy**
2. Wait for the build to complete
3. Your app will be live at `https://your-project.vercel.app`

### Important Notes for Deployment

- **CORS**: Ensure your backend API allows requests from your Vercel domain. Update CORS settings in your backend to include your Vercel URL.
- **Backend URL**: Make sure your backend is deployed and accessible. Update `NEXT_PUBLIC_BACKEND_URL` accordingly.
- **Monorepo**: If your frontend is in a monorepo, you may need to:
  - Set **Root Directory** in Vercel to `vision-compression-project/frontend`
  - Or deploy the frontend folder as a separate repository

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # Main page component
│   └── globals.css         # Global styles
├── components/
│   └── ui/                 # shadcn/ui components
│       ├── button.tsx
│       ├── card.tsx
│       ├── input.tsx
│       └── textarea.tsx
├── lib/
│   └── utils.ts            # Utility functions
├── .env.local.example      # Environment variables example
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── README.md
```

## API Integration

The frontend communicates with the backend API:

- **POST `/ingest`**: Upload and process PDF files (multipart/form-data)
- **POST `/chat`**: Send questions and get answers (JSON)
- **GET `/health`**: Health check endpoint

See the backend README for API documentation.

## Development

### Build for Production

```bash
npm run build
```

### Start Production Server

```bash
npm start
```

### Lint

```bash
npm run lint
```

## Troubleshooting

### CORS Errors

If you see CORS errors in the browser console:
- Ensure your backend allows requests from your frontend domain
- Check that `NEXT_PUBLIC_BACKEND_URL` is set correctly
- Verify the backend CORS configuration includes your frontend URL

### Build Errors

- Make sure all dependencies are installed: `npm install`
- Check Node.js version (requires 18+)
- Clear `.next` folder and rebuild: `rm -rf .next && npm run build`

### Environment Variables Not Working

- Ensure `.env.local` exists (not `.env.local.example`)
- Restart the dev server after changing environment variables
- In production, verify environment variables are set in Vercel dashboard

## License

MIT

