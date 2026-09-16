# Starts the NutriPal PHP dev server (only if not already running).
# Never touches XAMPP/MySQL - start that yourself via the XAMPP Control
# Panel if/when the app starts using it.

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$phpExe = 'C:\xampp\php\php.exe'
$phpPort = 8080
$vitePort = 5173

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

Write-Host "Checking NutriPal PHP server (port $phpPort)..."
if (Test-PortListening -Port $phpPort) {
    Write-Host "  Already running - skipping." -ForegroundColor Yellow
} else {
    Write-Host "  Starting..." -ForegroundColor Green
    # -d overrides apply only to this dev server process, not global
    # php.ini: raised upload/post limits for the Health Connect export
    # upload (real exports have been ~500MB), and unlimited execution
    # time since the sync/import endpoints run synchronously and can
    # take minutes.
    $phpArgs = "-d upload_max_filesize=1024M -d post_max_size=1024M -d max_execution_time=0 -d max_input_time=-1 -S localhost:$phpPort -t public"
    Start-Process powershell -WorkingDirectory $projectRoot -ArgumentList '-NoExit', '-Command', "& '$phpExe' $phpArgs"
}

Write-Host "Checking NutriPal frontend dev server (port $vitePort)..."
if (Test-PortListening -Port $vitePort) {
    Write-Host "  Already running - skipping." -ForegroundColor Yellow
} else {
    Write-Host "  Starting..." -ForegroundColor Green
    # Vite proxies /api to the PHP server (see frontend/vite.config.js).
    Start-Process powershell -WorkingDirectory $frontendRoot -ArgumentList '-NoExit', '-Command', 'npm run dev'
}

Write-Host ""
Write-Host "Backend:  http://localhost:$phpPort" -ForegroundColor Cyan
Write-Host "App:      http://localhost:$vitePort" -ForegroundColor Cyan
