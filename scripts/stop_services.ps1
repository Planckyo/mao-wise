$names = @("uvicorn","python","streamlit")
foreach($n in $names){
  Get-Process | Where-Object { $_.ProcessName -match $n } | ForEach-Object {
    try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
  }
}
Write-Host "✅ 已尝试停止 uvicorn/streamlit/python 相关进程"
