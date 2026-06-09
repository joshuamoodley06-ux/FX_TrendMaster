$Base = "https://api01.apexcoastalrentals.co.za"

Write-Host "Market memory status"
Invoke-RestMethod -Uri "$Base/api/v1/market-memory/status" -Method GET

Write-Host "Raw mapping export test"
Invoke-RestMethod -Uri "$Base/api/v1/raw-mapping/events/export?case_id=4a029f89-d810-4bc5-90b4-0efb4c4346f3" -Method GET
