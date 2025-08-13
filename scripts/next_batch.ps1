Write-Host "Generating next round batch (R2)..." -ForegroundColor Cyan

# 简单策略：基于最新 batch，直接再选出 R2（此处沿用与R1相同阈值；实际可根据round1_summary动态调整）
$latest = (Get-ChildItem tasks\batch_* | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
if (-not $latest) {
    Write-Host "No batch_* directory found under tasks" -ForegroundColor Red
    exit 1
}

python scripts/select_and_package_for_lab.py `
  --plans "$latest\plans.csv" `
  --alpha_max 0.20 --epsilon_min 0.80 --conf_min 0.55 --mass_max 0.40 --uniform_max 0.20 `
  --k_explore 6 --n_top 4 --outdir lab_package_R2

if ($LASTEXITCODE -ne 0) {
    Write-Host "R2 selection failed" -ForegroundColor Red
    exit 1
}

Write-Host "R2 generated at lab_package_R2" -ForegroundColor Green

