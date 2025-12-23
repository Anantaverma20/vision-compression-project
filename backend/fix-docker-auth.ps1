# Script to fix Docker authentication with Google Cloud
# Usage: .\fix-docker-auth.ps1

Write-Host "Fixing Docker authentication for Google Cloud..." -ForegroundColor Cyan
Write-Host ""

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
        Write-Host "❌ gcloud CLI not found!" -ForegroundColor Red
        Write-Host "Please install Google Cloud SDK first." -ForegroundColor Yellow
        exit 1
    }
}

# Step 1: Check if authenticated
Write-Host "1. Checking gcloud authentication..." -ForegroundColor Yellow
$authCheck = & $gcloudCmd auth list --filter=status:ACTIVE --format="value(account)" 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($authCheck)) {
    Write-Host "   ⚠️  Not authenticated. Logging in..." -ForegroundColor Yellow
    & $gcloudCmd auth login
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   ❌ Login failed!" -ForegroundColor Red
        exit 1
    }
    Write-Host "   ✅ Logged in successfully" -ForegroundColor Green
} else {
    Write-Host "   ✅ Already authenticated as: $authCheck" -ForegroundColor Green
}

Write-Host ""

# Step 2: Get project ID
Write-Host "2. Getting project ID..." -ForegroundColor Yellow
$PROJECT_ID = & $gcloudCmd config get-value project 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($PROJECT_ID)) {
    Write-Host "   ❌ No project ID set!" -ForegroundColor Red
    Write-Host "   Run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Yellow
    exit 1
}
Write-Host "   ✅ Project ID: $PROJECT_ID" -ForegroundColor Green

Write-Host ""

# Step 3: Configure Docker for Artifact Registry
Write-Host "3. Configuring Docker for Artifact Registry..." -ForegroundColor Yellow
& $gcloudCmd auth configure-docker us-central1-docker.pkg.dev --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ Artifact Registry configured" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Artifact Registry configuration may have failed" -ForegroundColor Yellow
}

# Step 4: Configure Docker for Container Registry (GCR)
Write-Host "4. Configuring Docker for Container Registry (GCR)..." -ForegroundColor Yellow
& $gcloudCmd auth configure-docker gcr.io --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ Container Registry configured" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Container Registry configuration may have failed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ Docker authentication configured!" -ForegroundColor Green
Write-Host ""
Write-Host "You can now run: .\deploy.ps1" -ForegroundColor Cyan

