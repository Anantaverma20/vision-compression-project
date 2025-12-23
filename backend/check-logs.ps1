# Quick script to check Cloud Run logs
# Usage: .\check-logs.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$ServiceName = "vision-compression-backend",
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1",
    
    [Parameter(Mandatory=$false)]
    [int]$Limit = 100
)

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

Write-Host "Fetching recent logs for $ServiceName..." -ForegroundColor Cyan
Write-Host ""

& $gcloudCmd run services logs read $ServiceName --region $Region --limit $Limit

