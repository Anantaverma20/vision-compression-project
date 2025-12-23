# Quick script to enable all required APIs

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
}

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

Write-Host "Enabling all required APIs for project: $PROJECT_ID" -ForegroundColor Cyan
Write-Host ""

$apis = @(
    @{Name="Container Registry"; Api="containerregistry.googleapis.com"},
    @{Name="Artifact Registry"; Api="artifactregistry.googleapis.com"},
    @{Name="Cloud Run"; Api="run.googleapis.com"},
    @{Name="Cloud Build"; Api="cloudbuild.googleapis.com"}
)

foreach ($api in $apis) {
    Write-Host "Enabling $($api.Name)..." -ForegroundColor Yellow
    $result = & $gcloudCmd services enable $api.Api --project=$PROJECT_ID 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ $($api.Name) enabled" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  $($api.Name) - check manually" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "✅ APIs enabled! Wait 30-60 seconds for propagation, then retry deployment." -ForegroundColor Green

