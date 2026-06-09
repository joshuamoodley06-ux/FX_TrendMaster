# Run this in a SECOND PowerShell window after backend is running.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$body = @{
  symbol = "XAUUSD"
  case_name = "XAUUSD_W1_TEST"
  base_timeframe = "W1"
  price_scale_default = 100
} | ConvertTo-Json

Write-Host "Testing local raw mapping case create..."
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/raw-mapping/cases" -Method POST -ContentType "application/json" -Body $body
