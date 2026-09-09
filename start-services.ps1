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
    # -d overrides apply only to this dev server process, not global
    # php.ini: raised upload/post limits for the Health Connect export
    # upload (real exports have been ~500MB), and unlimited execution
    # time since the sync/import endpoints run synchronously and can
    # take minutes.
    $phpArgs = "-d upload_max_filesize=1024M -d post_max_size=1024M -d max_execution_time=0 -d max_input_time=-1 -S localhost:$port -t public"
    Start-Process powershell -WorkingDirectory $projectRoot -ArgumentList '-NoExit', '-Command', "& '$phpExe' $phpArgs"
}

Write-Host ""
Write-Host "Once up: http://localhost:$port" -ForegroundColor Cyan
