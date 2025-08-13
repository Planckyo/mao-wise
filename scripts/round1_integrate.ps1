param(
    [string]$ResultFile = "results/round1_results.xlsx"
)

Write-Host "Round-1 integrate starting..." -ForegroundColor Cyan

$tasksWithIds = "lab_package_R1/exp_tasks_with_ids.csv"
if (-not (Test-Path $tasksWithIds)) {
    Write-Host "Tasks with IDs not found: $tasksWithIds" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ResultFile)) {
    Write-Host "Result file not found: $ResultFile" -ForegroundColor Yellow
}

# 生成回传评估汇总
python scripts/compute_round1_summary.py --tasks_with_ids $tasksWithIds --result_file $ResultFile --out_md reports/round1_summary.md
if ($LASTEXITCODE -ne 0) {
    Write-Host "Compute summary failed" -ForegroundColor Red
    exit 1
}

Write-Host "Round-1 integrate done." -ForegroundColor Green

