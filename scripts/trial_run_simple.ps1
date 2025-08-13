# MAO-Wise Simple Trial Run Script
param(
    [string]$LibraryDir = $env:MAOWISE_LIBRARY_DIR,
    [switch]$Online = $false
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null

Write-Host "MAO-Wise Trial Run Starting..." -ForegroundColor Cyan

# Set working directory
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..
$env:PYTHONPATH = (Get-Location).Path

Write-Host "Working Directory: $(Get-Location)" -ForegroundColor Green

# Step 1: Prepare environment
Write-Host "Step 1: Environment preparation..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env" -ErrorAction SilentlyContinue
    } else {
        New-Item -Path ".env" -ItemType File -Force | Out-Null
    }
    Write-Host "Created .env file" -ForegroundColor Green
}

if ($LibraryDir) {
    $envContent = Get-Content ".env" -Raw -ErrorAction SilentlyContinue
    if (-not $envContent -or $envContent -notmatch "MAOWISE_LIBRARY_DIR=") {
        Add-Content ".env" "`nMAOWISE_LIBRARY_DIR=$LibraryDir"
        Write-Host "Set library directory: $LibraryDir" -ForegroundColor Green
    }
}

$mode = if ($Online.IsPresent) { "online" } else { "offline" }
Write-Host "Mode: $mode" -ForegroundColor Green

# Step 2: Prepare data
Write-Host "Step 2: Data preparation..." -ForegroundColor Yellow

try {
    python scripts/e2e_data_prep.py
    Write-Host "Data preparation completed" -ForegroundColor Green
} catch {
    Write-Host "Data preparation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 3: Generate batch plans
Write-Host "Step 3: Generate batch plans..." -ForegroundColor Yellow

try {
    python scripts/generate_batch_plans.py --system silicate --n 6 --target-alpha 0.20 --target-epsilon 0.80 --notes "trial_run"
    Write-Host "Silicate plans generated" -ForegroundColor Green
    
    python scripts/generate_batch_plans.py --system zirconate --n 6 --target-alpha 0.20 --target-epsilon 0.80 --notes "trial_run"
    Write-Host "Zirconate plans generated" -ForegroundColor Green
} catch {
    Write-Host "Batch generation failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Step 4: Validate recommendations
Write-Host "Step 4: Validate recommendations..." -ForegroundColor Yellow

try {
    $latestBatch = Get-ChildItem "tasks" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestBatch) {
        $batchPath = $latestBatch.FullName
        Write-Host "Latest batch: $($latestBatch.Name)" -ForegroundColor Green
        
        python scripts/validate_recommendations.py --plans "$batchPath\plans.csv" --kb datasets/index_store --topk 3
        Write-Host "Validation completed" -ForegroundColor Green
    } else {
        Write-Host "No batch directory found, skipping validation" -ForegroundColor Yellow
        $batchPath = ""
    }
} catch {
    Write-Host "Validation failed: $($_.Exception.Message)" -ForegroundColor Red
    $batchPath = ""
}

# Step 5: Start services
Write-Host "Step 5: Start services..." -ForegroundColor Yellow

# Check if API is running
$apiRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/maowise/v1/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $apiRunning = $true
        Write-Host "API service already running" -ForegroundColor Green
    }
} catch {
    # API not running
}

if (-not $apiRunning) {
    Start-Process powershell -ArgumentList "-NoProfile", "-WindowStyle", "Minimized", "-Command", "Set-Location '$((Get-Location).Path)'; `$env:PYTHONPATH='$((Get-Location).Path)'; uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload" -WindowStyle Minimized
    Write-Host "API service starting..." -ForegroundColor Green
    Start-Sleep -Seconds 6
    
    # Verify API startup
    $retries = 0
    while ($retries -lt 5) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/maowise/v1/health" -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                Write-Host "API service started successfully" -ForegroundColor Green
                break
            }
        } catch {
            $retries++
            Start-Sleep -Seconds 2
        }
    }
    
    if ($retries -eq 5) {
        Write-Host "API service startup may have failed" -ForegroundColor Yellow
        exit 1
    }
}

# Check if UI is running
$uiRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8501" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $uiRunning = $true
        Write-Host "UI service already running" -ForegroundColor Green
    }
} catch {
    # UI not running
}

if (-not $uiRunning) {
    Start-Process powershell -ArgumentList "-NoProfile", "-WindowStyle", "Minimized", "-Command", "Set-Location '$((Get-Location).Path)'; `$env:PYTHONPATH='$((Get-Location).Path)'; streamlit run apps/ui/app.py --server.address 127.0.0.1 --server.port 8501" -WindowStyle Minimized
    Write-Host "UI service starting..." -ForegroundColor Green
    Start-Sleep -Seconds 8
}

# Step 6: Run main trial logic
Write-Host "Step 6: Execute API tests and validation..." -ForegroundColor Yellow

try {
    python scripts/trial_run.py --mode $mode --batch "$batchPath"
    Write-Host "Trial run main logic completed" -ForegroundColor Green
} catch {
    Write-Host "Trial run main logic failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Complete
Write-Host "Trial run completed!" -ForegroundColor Green
Write-Host "Generated files:" -ForegroundColor Cyan
Write-Host "   - Batch plans: tasks/batch_*/plans.csv" -ForegroundColor Gray
Write-Host "   - Validation report: tasks/batch_*/validation_report.xlsx" -ForegroundColor Gray
Write-Host "   - UI screenshots: reports/ui_*.png" -ForegroundColor Gray
Write-Host "   - Trial run report: reports/trial_run_report.md/html" -ForegroundColor Gray

Write-Host "Service URLs:" -ForegroundColor Cyan
Write-Host "   - API: http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host "   - UI: http://127.0.0.1:8501" -ForegroundColor Gray

# Open reports directory
try {
    if (Test-Path "reports/trial_run_report.html") {
        Write-Host "Opening reports directory..." -ForegroundColor Yellow
        Start-Process "explorer.exe" -ArgumentList "reports"
    }
} catch {
    # Ignore error
}

Write-Host "Trial run process completed!" -ForegroundColor Green
