# Stops the NutriPal PHP dev server by port, whichever way it was started.
# Never touches XAMPP/MySQL - stop that yourself via the XAMPP Control Panel.

function Stop-ProcessOnPort {
    param([int]$Port, [string]$Name)

    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "$Name (port $Port) is not running." -ForegroundColor Yellow
        return
    }

    $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
        try {
            Write-Host "Stopping $Name (PID $procId, port $Port)..." -ForegroundColor Green
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            Write-Host "Could not stop PID $procId for $Name`: $_" -ForegroundColor Red
        }
    }
}

Stop-ProcessOnPort -Port 8080 -Name "NutriPal PHP server"

Write-Host ""
Write-Host "Done. XAMPP/MySQL was not touched - stop it via the XAMPP Control Panel if needed." -ForegroundColor Cyan
