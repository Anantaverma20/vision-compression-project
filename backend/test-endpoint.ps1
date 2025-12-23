# Script to test the Cloud Run endpoint
# Usage: .\test-endpoint.ps1 [service-url]

param(
    [Parameter(Mandatory=$false)]
    [string]$ServiceUrl = ""
)

if ([string]::IsNullOrEmpty($ServiceUrl)) {
    Write-Host "Getting Cloud Run service URL..." -ForegroundColor Cyan
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
    
    $ServiceUrl = & $gcloudCmd run services describe vision-compression-backend --region us-central1 --format 'value(status.url)'
}

Write-Host "Testing backend endpoints..." -ForegroundColor Cyan
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Gray
Write-Host ""

# Test health endpoint
Write-Host "1. Testing /health endpoint..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-WebRequest -Uri "$ServiceUrl/health" -Method GET -UseBasicParsing
    Write-Host "   ✓ Health check passed: $($healthResponse.StatusCode)" -ForegroundColor Green
    Write-Host "   Response: $($healthResponse.Content)" -ForegroundColor Gray
} catch {
    Write-Host "   ✗ Health check failed: $_" -ForegroundColor Red
}

Write-Host ""

# Test root endpoint
Write-Host "2. Testing / endpoint..." -ForegroundColor Yellow
try {
    $rootResponse = Invoke-WebRequest -Uri "$ServiceUrl/" -Method GET -UseBasicParsing
    Write-Host "   ✓ Root endpoint passed: $($rootResponse.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "   ✗ Root endpoint failed: $_" -ForegroundColor Red
}

Write-Host ""

# Test CORS preflight (OPTIONS request)
Write-Host "3. Testing CORS preflight (OPTIONS)..." -ForegroundColor Yellow
try {
    $optionsResponse = Invoke-WebRequest -Uri "$ServiceUrl/ingest" -Method OPTIONS -UseBasicParsing -Headers @{
        "Origin" = "http://localhost:3001"
        "Access-Control-Request-Method" = "POST"
        "Access-Control-Request-Headers" = "Content-Type"
    }
    Write-Host "   ✓ CORS preflight passed: $($optionsResponse.StatusCode)" -ForegroundColor Green
    Write-Host "   CORS Headers:" -ForegroundColor Gray
    $optionsResponse.Headers | ForEach-Object {
        if ($_.Key -like "*Access-Control*") {
            Write-Host "     $($_.Key): $($_.Value)" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "   ✗ CORS preflight failed: $_" -ForegroundColor Red
    Write-Host "   This might be the issue!" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "If CORS preflight failed, check:" -ForegroundColor Cyan
Write-Host "1. Backend CORS configuration allows localhost:3001" -ForegroundColor White
Write-Host "2. Cloud Run allows OPTIONS requests" -ForegroundColor White
Write-Host "3. Check browser console (F12) for specific CORS errors" -ForegroundColor White

