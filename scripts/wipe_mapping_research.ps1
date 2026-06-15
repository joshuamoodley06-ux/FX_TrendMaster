param(
  [string]$ApiBase = "https://api01.apexcoastalrentals.co.za",
  [string[]]$Symbols = @("XAUUSD", "US500.cash")
)

foreach ($sym in $Symbols) {
  $body = @{ symbol = $sym; confirm = "RESET" } | ConvertTo-Json
  Write-Host "Wiping research mapping for $sym ..."
  $r = Invoke-RestMethod -Uri "$ApiBase/api/v1/mos/research-reset" -Method POST -ContentType "application/json" -Body $body
  if (-not $r.ok) { throw "Research reset failed for ${sym}: $($r | ConvertTo-Json -Compress)" }
  Write-Host ($r | ConvertTo-Json -Depth 6)

  Write-Host "Wiping raw mapping cases for $sym ..."
  $raw = Invoke-RestMethod -Uri "$ApiBase/api/v1/raw-mapping/cases?symbol=$([uri]::EscapeDataString($sym))&confirm=RESET" -Method DELETE
  Write-Host ($raw | ConvertTo-Json -Depth 4)
}

Write-Host "Done. OHLC candles were not touched."
