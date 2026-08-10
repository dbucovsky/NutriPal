# Starts the NutriPal PHP dev server (only if not already running).
# Never touches XAMPP/MySQL - start that yourself via the XAMPP Control
# Panel if/when the app starts using it.

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$phpExe = 'C:\xampp\php\php.exe'
$port = 8080

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

Write-Host "Checking NutriPal PHP server (port $port)..."
if (Test-PortListening -Port $port) {
    Write-Host "  Already running - skipping." -ForegroundColor Yellow
} else {
    Write-Host "  Starting..." -ForegroundColor Green
    Start-Process powershell -WorkingDirectory $projectRoot -ArgumentList '-NoExit', '-Command', "& '$phpExe' -S localhost:$port -t public"
}

Write-Host ""
Write-Host "Once up: http://localhost:$port" -ForegroundColor Cyan
