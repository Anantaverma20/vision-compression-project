# Alternative deployment using Cloud Build (no local Docker push needed)
# This avoids Docker authentication issues

$ErrorActionPreference = "Stop"

# Find gcloud command
$gcloudCmd = "gcloud"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    $possiblePaths = @(
        "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        "$env:ProgramFiles\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        "$env:ProgramFiles(x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    )
    
    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $gcloudCmd = $path
            break
        }
    }
    
    if ($gcloudCmd -eq "gcloud") {
        Write-Host "❌ Error: gcloud command not found!" -ForegroundColor Red
        exit 1
    }
}

# Configuration
$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { 
    $proj = & $gcloudCmd config get-value project 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ No project ID set. Set GCP_PROJECT_ID or run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Red
        exit 1
    }
    $proj
}
$SERVICE_NAME = if ($env:SERVICE_NAME) { $env:SERVICE_NAME } else { "vision-compression-backend" }
$REGION = if ($env:REGION) { $env:REGION } else { "us-central1" }

Write-Host "Project ID: $PROJECT_ID" -ForegroundColor Cyan
Write-Host "Service: $SERVICE_NAME" -ForegroundColor Cyan
Write-Host "Region: $REGION" -ForegroundColor Cyan
Write-Host ""

# Enable APIs
Write-Host "Enabling required APIs..." -ForegroundColor Green
& $gcloudCmd services enable cloudbuild.googleapis.com --project=$PROJECT_ID 2>&1 | Out-Null
& $gcloudCmd services enable run.googleapis.com --project=$PROJECT_ID 2>&1 | Out-Null
& $gcloudCmd services enable artifactregistry.googleapis.com --project=$PROJECT_ID 2>&1 | Out-Null

# Create Artifact Registry repository if needed
$ARTIFACT_REGION = $REGION
$repoExists = & $gcloudCmd artifacts repositories describe cloud-run-source-deploy --location=$ARTIFACT_REGION --project=$PROJECT_ID 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating Artifact Registry repository..." -ForegroundColor Yellow
    & $gcloudCmd artifacts repositories create cloud-run-source-deploy `
        --repository-format=docker `
        --location=$ARTIFACT_REGION `
        --project=$PROJECT_ID `
        --description="Docker repository for Cloud Run deployments" 2>&1 | Out-Null
}

# Build and deploy using Cloud Build (no local Docker needed!)
Write-Host ""
Write-Host "Building and deploying using Cloud Build..." -ForegroundColor Green
Write-Host "This will build the Docker image in the cloud (no local Docker push needed)" -ForegroundColor Cyan
Write-Host ""

$IMAGE_NAME = "$REGION-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$SERVICE_NAME"

# Submit build to Cloud Build
& $gcloudCmd builds submit --tag $IMAGE_NAME --project=$PROJECT_ID

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Cloud Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Deploying to Cloud Run..." -ForegroundColor Green

# Get environment variables from .env file if it exists
$envVars = ""
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Write-Host "Reading environment variables from .env file..." -ForegroundColor Cyan
    $envContent = Get-Content $envFile
    $envList = @()
    
    foreach ($line in $envContent) {
        if ($line -match '^\s*([^=]+)=(.*)$' -and $line -notmatch '^\s*#') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($key -eq "GEMINI_API_KEY" -or $key -eq "SUPERMEMORY_API_KEY" -or $key -eq "GCP_PROJECT_ID") {
                $envList += "$key=$value"
            }
        }
    }
    
    if ($envList.Count -gt 0) {
        $envVars = $envList -join ","
        Write-Host "Found environment variables in .env file" -ForegroundColor Green
    }
}

# Deploy to Cloud Run
$deployCmd = @(
    "run", "deploy", $SERVICE_NAME,
    "--image", $IMAGE_NAME,
    "--platform", "managed",
    "--region", $REGION,
    "--allow-unauthenticated",
    "--memory", "2Gi",
    "--timeout", "900",
    "--max-instances", "10",
    "--project", $PROJECT_ID
)

if (-not [string]::IsNullOrEmpty($envVars)) {
    $deployCmd += "--set-env-vars", $envVars
}

& $gcloudCmd $deployCmd

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Deployment complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Service URL:" -ForegroundColor Yellow
    & $gcloudCmd run services describe $SERVICE_NAME --region $REGION --project $PROJECT_ID --format 'value(status.url)'
} else {
    Write-Host "❌ Deployment failed!" -ForegroundColor Red
    exit 1
}

