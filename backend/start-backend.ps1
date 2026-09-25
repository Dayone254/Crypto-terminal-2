$ErrorActionPreference = "SilentlyContinue"

Write-Host "TapeRadar Backend Watchdog Starting..." -ForegroundColor Green
Write-Host "Monitoring Uvicorn API for crashes. Press Ctrl+C to stop." -ForegroundColor Cyan

while ($true) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting Uvicorn API Server..." -ForegroundColor Yellow
    
    # Run Uvicorn directly, blocking this script
    C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe -m uvicorn tpt.api.main:create_app --factory --host 0.0.0.0 --port 8000
    
    $exitCode = $LASTEXITCODE
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Uvicorn exited with code $exitCode" -ForegroundColor Red
    
    # Wait 5 seconds before restarting
    Write-Host "Restarting in 2 seconds..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 2
}
