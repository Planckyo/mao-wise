$ErrorActionPreference = "Stop"
chcp 65001 > $null

# 启动 API
$apiCmd = "uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process -WindowStyle Minimized -FilePath "powershell.exe" -ArgumentList "-NoExit","-Command",$apiCmd
Start-Sleep -Seconds 3

# 启动 UI
$uiCmd = "streamlit run apps/ui/app.py --server.address 127.0.0.1 --server.port 8501"
Start-Process -WindowStyle Minimized -FilePath "powershell.exe" -ArgumentList "-NoExit","-Command",$uiCmd
Start-Sleep -Seconds 5

# 自测 /predict
$body = @{ description = "AZ91 substrate; silicate electrolyte: Na2SiO3 10 g/L, KOH 2 g/L; bipolar 500 Hz 30% duty; 420 V; 12 A/dm2; 10 min; sealing none." } | ConvertTo-Json
try {
  $res = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/maowise/v1/predict" -ContentType "application/json" -Body $body -TimeoutSec 20
  Write-Host "✅ /predict OK  α=$($res.alpha)  ε=$($res.epsilon)  conf=$($res.confidence)"
  Write-Host "UI: http://127.0.0.1:8501"
} catch {
  Write-Host "❌ /predict 调用失败，请检查 API/端口占用" -ForegroundColor Red
}
