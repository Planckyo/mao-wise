# MAO-Wise E2E Test Runner
# PowerShell script for one-click end-to-end testing

# Set UTF-8 encoding
chcp 65001 > $null
$OutputEncoding = [System.Text.Encoding]::UTF8

# Error handling
$ErrorActionPreference = "Continue"

Write-Host "MAO-Wise E2E Testing Started" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Green

# Check Python
Write-Host "`nChecking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Python OK: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "Python not found" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Python check failed: $_" -ForegroundColor Red
    exit 1
}

# Check dependencies
Write-Host "`nChecking dependencies..." -ForegroundColor Yellow
$packages = @("requests", "pyyaml", "uvicorn", "fastapi")

foreach ($pkg in $packages) {
    python -c "import $pkg" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Package $pkg: OK" -ForegroundColor Green
    } else {
        Write-Host "Installing $pkg..." -ForegroundColor Yellow
        pip install $pkg --quiet
    }
}

# Environment setup
Write-Host "`nEnvironment setup..." -ForegroundColor Yellow

if (-not $env:MAOWISE_LIBRARY_DIR) {
    Write-Host "MAOWISE_LIBRARY_DIR not set - using test fixtures" -ForegroundColor Cyan
}

if (-not $env:OPENAI_API_KEY) {
    Write-Host "OPENAI_API_KEY not set - using offline mode" -ForegroundColor Cyan
} else {
    $maskedKey = $env:OPENAI_API_KEY.Substring(0, 7) + "..."
    Write-Host "OPENAI_API_KEY: $maskedKey" -ForegroundColor Green
}

if (-not $env:DEBUG_LLM) {
    $env:DEBUG_LLM = "false"
}

# Step 1: Data preparation
Write-Host "`nStep 1: Data preparation..." -ForegroundColor Yellow
Write-Host "Running: python scripts/e2e_data_prep.py" -ForegroundColor Gray

try {
    python scripts/e2e_data_prep.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Data preparation completed" -ForegroundColor Green
    } else {
        Write-Host "Data preparation failed (code: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "Continuing with offline mode..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Data preparation error: $_" -ForegroundColor Red
    Write-Host "Continuing..." -ForegroundColor Yellow
}

Start-Sleep -Seconds 2

# Step 2: E2E validation
Write-Host "`nStep 2: E2E validation..." -ForegroundColor Yellow
Write-Host "Running: python scripts/e2e_validate.py" -ForegroundColor Gray

try {
    python scripts/e2e_validate.py
    $testResult = $LASTEXITCODE
    
    if ($testResult -eq 0) {
        Write-Host "All tests passed!" -ForegroundColor Green
    } else {
        Write-Host "Some tests failed (code: $testResult)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "E2E validation error: $_" -ForegroundColor Red
    $testResult = 1
}

# Step 3: Open reports
Write-Host "`nStep 3: Check reports..." -ForegroundColor Yellow

$reportsDir = "reports"
$mdReport = Join-Path $reportsDir "e2e_report.md"
$htmlReport = Join-Path $reportsDir "e2e_report.html"

if (Test-Path $reportsDir) {
    Write-Host "Reports directory exists" -ForegroundColor Green
    
    if (Test-Path $mdReport) {
        Write-Host "Markdown report: $mdReport" -ForegroundColor Green
    }
    
    if (Test-Path $htmlReport) {
        Write-Host "HTML report: $htmlReport" -ForegroundColor Green
    }
    
    try {
        Write-Host "Opening reports directory..." -ForegroundColor Yellow
        Invoke-Item $reportsDir
        Write-Host "Reports directory opened" -ForegroundColor Green
    } catch {
        Write-Host "Cannot auto-open directory: $_" -ForegroundColor Yellow
        Write-Host "Please manually open: $reportsDir" -ForegroundColor Cyan
    }
} else {
    Write-Host "Reports directory not found" -ForegroundColor Red
}

# Summary
Write-Host "`n" + "="*50 -ForegroundColor Green
Write-Host "E2E Test Summary" -ForegroundColor Green
Write-Host "="*50 -ForegroundColor Green

if ($testResult -eq 0) {
    Write-Host "Status: ALL PASSED" -ForegroundColor Green
    Write-Host "MAO-Wise system is working correctly" -ForegroundColor Green
} else {
    Write-Host "Status: SOME FAILED" -ForegroundColor Yellow
    Write-Host "Check reports for details" -ForegroundColor Yellow
}

Write-Host "`nReport files:" -ForegroundColor Cyan
Write-Host "  Markdown: $mdReport" -ForegroundColor White
Write-Host "  HTML: $htmlReport" -ForegroundColor White

Write-Host "`nRunning mode:" -ForegroundColor Cyan
if ($env:OPENAI_API_KEY) {
    Write-Host "  LLM: Online mode (OpenAI)" -ForegroundColor White
} else {
    Write-Host "  LLM: Offline fallback mode" -ForegroundColor White
}

if ($env:MAOWISE_LIBRARY_DIR) {
    Write-Host "  Data: Local library" -ForegroundColor White
} else {
    Write-Host "  Data: Test fixtures" -ForegroundColor White
}

Write-Host "`nTips:" -ForegroundColor Cyan
Write-Host "  Set OPENAI_API_KEY for online LLM features" -ForegroundColor White
Write-Host "  Set MAOWISE_LIBRARY_DIR for local literature" -ForegroundColor White
Write-Host "  Set DEBUG_LLM=true for detailed logs" -ForegroundColor White

Write-Host "`nE2E Testing Completed!" -ForegroundColor Green

# Return test result
exit $testResult