# PowerShell script to enable required Google Cloud APIs

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
        Write-Host "Please restart your terminal after installing gcloud CLI." -ForegroundColor Yellow
        exit 1
    }
}

# Get project ID
$PROJECT_ID = if ($env:GCP_PROJECT_ID) { 
    $env:GCP_PROJECT_ID 
} else { 
    $input = Read-Host "Enter your Google Cloud Project ID"
    if ([string]::IsNullOrWhiteSpace($input)) {
        Write-Host "❌ Project ID is required!" -ForegroundColor Red
        exit 1
    }
    $input
}

Write-Host "Enabling required APIs for project: $PROJECT_ID" -ForegroundColor Cyan
Write-Host ""

# Enable APIs
$apis = @(
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "containerregistry.googleapis.com"
)

foreach ($api in $apis) {
    Write-Host "Enabling $api..." -ForegroundColor Green
    & $gcloudCmd services enable $api --project=$PROJECT_ID
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ $api enabled" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Failed to enable $api" -ForegroundColor Yellow
    }
    Write-Host ""
}

Write-Host "Configuring Docker authentication..." -ForegroundColor Cyan
& $gcloudCmd auth configure-docker us-central1-docker.pkg.dev --quiet
& $gcloudCmd auth configure-docker gcr.io --quiet

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host "You can now run: .\deploy.ps1" -ForegroundColor Cyan

