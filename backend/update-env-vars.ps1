# PowerShell script to update environment variables in Cloud Run
# Usage: .\update-env-vars.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$ProjectId = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ServiceName = "vision-compression-backend",
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1",
    
    [Parameter(Mandatory=$false)]
    [string]$GeminiApiKey = "",
    
    [Parameter(Mandatory=$false)]
    [string]$SupermemoryApiKey = ""
)

# Find gcloud command
$gcloudCmd = "gcloud"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    # Try common installation paths
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
        Write-Host "Please ensure Google Cloud SDK is installed and in your PATH." -ForegroundColor Yellow
        Write-Host "Or restart your terminal after installing gcloud CLI." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "You can also try running gcloud directly:" -ForegroundColor Cyan
        Write-Host "gcloud run services update vision-compression-backend --region us-central1 --update-env-vars `"GEMINI_API_KEY=your_key,SUPERMEMORY_API_KEY=your_key`"" -ForegroundColor White
        exit 1
    }
}

# Get project ID if not provided
if ([string]::IsNullOrEmpty($ProjectId)) {
    $ProjectId = & $gcloudCmd config get-value project 2>&1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($ProjectId)) {
        Write-Host "❌ No project ID set. Please provide --ProjectId or run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Project ID: $ProjectId" -ForegroundColor Cyan
Write-Host "Service: $ServiceName" -ForegroundColor Cyan
Write-Host "Region: $Region" -ForegroundColor Cyan
Write-Host ""

# Try to read API keys from .env file
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Write-Host "Reading API keys from .env file..." -ForegroundColor Cyan
    $envContent = Get-Content $envFile
    
    foreach ($line in $envContent) {
        # Skip comments and empty lines
        if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        
        # Parse KEY=VALUE format
        if ($line -match '^\s*([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            
            if ($key -eq "GEMINI_API_KEY" -and [string]::IsNullOrEmpty($GeminiApiKey)) {
                $GeminiApiKey = $value
            }
            if ($key -eq "SUPERMEMORY_API_KEY" -and [string]::IsNullOrEmpty($SupermemoryApiKey)) {
                $SupermemoryApiKey = $value
            }
        }
    }
    
    if (-not [string]::IsNullOrEmpty($GeminiApiKey)) {
        Write-Host "✓ Found GEMINI_API_KEY in .env file" -ForegroundColor Green
    }
    if (-not [string]::IsNullOrEmpty($SupermemoryApiKey)) {
        Write-Host "✓ Found SUPERMEMORY_API_KEY in .env file" -ForegroundColor Green
    }
    Write-Host ""
} else {
    Write-Host "⚠️  .env file not found at: $envFile" -ForegroundColor Yellow
    Write-Host ""
}

# Prompt for API keys only if not found in .env file
if ([string]::IsNullOrEmpty($GeminiApiKey)) {
    $GeminiApiKey = Read-Host "Enter GEMINI_API_KEY (or press Enter to skip)"
}

if ([string]::IsNullOrEmpty($SupermemoryApiKey)) {
    $SupermemoryApiKey = Read-Host "Enter SUPERMEMORY_API_KEY (or press Enter to skip)"
}

# Build environment variables string
$envVars = @()
if (-not [string]::IsNullOrEmpty($GeminiApiKey)) {
    $envVars += "GEMINI_API_KEY=$GeminiApiKey"
}
if (-not [string]::IsNullOrEmpty($SupermemoryApiKey)) {
    $envVars += "SUPERMEMORY_API_KEY=$SupermemoryApiKey"
}

if ($envVars.Count -eq 0) {
    Write-Host "⚠️  No environment variables provided. Nothing to update." -ForegroundColor Yellow
    exit 0
}

$envVarsString = $envVars -join ","

Write-Host "Updating environment variables in Cloud Run..." -ForegroundColor Green
Write-Host "This will create a new revision and may take 30-60 seconds." -ForegroundColor Yellow
Write-Host ""

& $gcloudCmd run services update $ServiceName `
  --region $Region `
  --project $ProjectId `
  --update-env-vars $envVarsString

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Environment variables updated successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Service URL:" -ForegroundColor Yellow
    & $gcloudCmd run services describe $ServiceName --region $Region --project $ProjectId --format 'value(status.url)'
    Write-Host ""
    Write-Host "Test the health endpoint:" -ForegroundColor Cyan
    $serviceUrl = & $gcloudCmd run services describe $ServiceName --region $Region --project $ProjectId --format 'value(status.url)'
    Write-Host "curl $serviceUrl/health" -ForegroundColor White
} else {
    Write-Host "❌ Failed to update environment variables" -ForegroundColor Red
    exit 1
}

