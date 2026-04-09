param([string]$Json)
Invoke-WebRequest -Uri "http://127.0.0.1:8001/tts" -Method POST -Body $Json -ContentType "application/json" -UseBasicParsing
