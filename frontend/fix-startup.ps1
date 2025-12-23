# Script to fix Next.js stuck at "Starting..." issue
# Usage: .\fix-startup.ps1

Write-Host "Fixing Next.js startup issues..." -ForegroundColor Cyan
Write-Host ""

# Step 1: Kill any existing Next.js processes
Write-Host "1. Killing existing Node processes..." -ForegroundColor Yellow
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Step 2: Clean .next folder
Write-Host "2. Cleaning .next folder..." -ForegroundColor Yellow
if (Test-Path ".next") {
    Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
    Write-Host "   ✓ .next folder deleted" -ForegroundColor Green
} else {
    Write-Host "   ✓ .next folder doesn't exist" -ForegroundColor Green
}

# Step 3: Clean node_modules/.cache if exists
Write-Host "3. Cleaning cache..." -ForegroundColor Yellow
if (Test-Path "node_modules\.cache") {
    Remove-Item -Recurse -Force "node_modules\.cache" -ErrorAction SilentlyContinue
    Write-Host "   ✓ Cache cleaned" -ForegroundColor Green
}

# Step 4: Check .env.local exists
Write-Host "4. Checking .env.local..." -ForegroundColor Yellow
if (Test-Path ".env.local") {
    Write-Host "   ✓ .env.local exists" -ForegroundColor Green
    Get-Content .env.local | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
} else {
    Write-Host "   ⚠️  .env.local not found - you may need to create it" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ Cleanup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Now try running:" -ForegroundColor Cyan
Write-Host "  npm run dev" -ForegroundColor White
Write-Host ""

