param(
  [switch]$Full
)

$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Stop-PortListeners {
  param([int]$Port)

  $pids = @()
  if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  } else {
    netstat -ano | Select-String ":$Port\s+.*LISTENING" | ForEach-Object {
      $parts = ($_.Line -replace '\s+', ' ').Trim().Split(' ')
      if ($parts.Length -ge 5) { $parts[-1] }
    } | Sort-Object -Unique | ForEach-Object { [int]$_ }
  }

  foreach ($procId in $pids) {
    if ($procId -and $procId -gt 0) {
      Write-Host "  Killing PID $procId (port $Port)"
      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
  }
}

function Stop-ProjectProcesses {
  param([string]$MatchPattern)

  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and ($_.CommandLine -match $MatchPattern)
    } |
    ForEach-Object {
      Write-Host "  Killing $($_.Name) PID $($_.ProcessId)"
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "FX TrendMaster - restarting dev in $Root"
Write-Host "Stopping stale listeners and dev processes..."

Stop-PortListeners -Port 5173

$escapedRoot = [regex]::Escape($Root)
Stop-ProjectProcesses -MatchPattern "$escapedRoot.*(concurrently|vite|wait-on)"
Stop-ProjectProcesses -MatchPattern "electron\.exe.*--dev"
Stop-ProjectProcesses -MatchPattern "$escapedRoot.*electron\s+\."

Start-Sleep -Milliseconds 700

$stillListening = $false
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
  $stillListening = [bool](Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)
} else {
  $stillListening = [bool](netstat -ano | Select-String ":5173\s+.*LISTENING")
}

if ($stillListening) {
  Write-Host "Port 5173 still busy - forcing one more kill pass..."
  Stop-PortListeners -Port 5173
  Start-Sleep -Seconds 1
}

if ($Full) {
  Write-Host "Starting dev (full rebuild)..."
  npm run dev
} else {
  Write-Host "Starting dev (fast - skipping build:runner)..."
  npm run dev:fast
}
exit $LASTEXITCODE
