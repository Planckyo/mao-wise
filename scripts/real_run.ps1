#!/usr/bin/env pwsh
# MAO-Wise Real Run Script
# Execute complete online pipeline with data processing, model training, batch generation and evaluation

param(
    [Parameter(Mandatory=$true)]
    [string]$LibraryDir,
    
    [switch]$Force = $false
)

# Set encoding and error handling
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
$ErrorActionPreference = "Stop"

# Color output functions
function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Write-Step { param([string]$Message); Write-ColorOutput "[INFO] $Message" "Cyan" }
function Write-Success { param([string]$Message); Write-ColorOutput "[OK] $Message" "Green" }
function Write-Warning { param([string]$Message); Write-ColorOutput "[WARN] $Message" "Yellow" }
function Write-Error { param([string]$Message); Write-ColorOutput "[ERROR] $Message" "Red" }

# Check environment
function Test-Environment {
    Write-Step "Checking environment configuration..."
    
    if (-not $env:OPENAI_API_KEY) {
        Write-Host "⚠️  OPENAI_API_KEY 环境变量未设置" -ForegroundColor Yellow
        Write-Host "请运行 scripts\set_llm_keys.ps1 交互式设置" -ForegroundColor Cyan
        Write-Host "或手动设置环境变量" -ForegroundColor Gray
    }
    
    if (-not (Test-Path $LibraryDir)) {
        Write-Error "Library directory does not exist: $LibraryDir"
        exit 1
    }
    
    $env:MAOWISE_LIBRARY_DIR = $LibraryDir
    Write-Success "Environment check passed"
    Write-Host "  OPENAI_API_KEY: $($env:OPENAI_API_KEY ? '已设置' : '未设置')" -ForegroundColor Gray
    Write-Host "  MAOWISE_LIBRARY_DIR: $LibraryDir" -ForegroundColor Gray
}

# Execute data pipeline
function Invoke-Pipeline {
    Write-Step "Executing data pipeline and model training..."
    
    try {
        $pipelineArgs = @(
            "-LibraryDir", $LibraryDir,
            "-Online:`$true",
            "-DoTrain:`$true"
        )
        
        if ($Force) { $pipelineArgs += "-Force:`$true" }
        
        Write-Host "Calling: powershell -File scripts\pipeline_real.ps1 $($pipelineArgs -join ' ')" -ForegroundColor Gray
        
        & powershell -ExecutionPolicy Bypass -File "scripts\pipeline_real.ps1" @pipelineArgs
        
        if ($LASTEXITCODE -ne 0) {
            throw "Data pipeline failed with exit code: $LASTEXITCODE"
        }
        
        Write-Success "Data pipeline completed"
        
    } catch {
        Write-Error "Data pipeline failed: $($_.Exception.Message)"
        exit 1
    }
}

# Generate batch plans
function New-BatchPlans {
    Write-Step "Generating batch experiment plans..."
    
    try {
        Write-Host "Generating silicate system plans..." -ForegroundColor Gray
        python scripts/generate_batch_plans.py --system silicate --n 6 --notes "real_run"
        
        if ($LASTEXITCODE -ne 0) { throw "Silicate plans generation failed" }
        
        Write-Host "Generating zirconate system plans..." -ForegroundColor Gray
        python scripts/generate_batch_plans.py --system zirconate --n 6 --notes "real_run"
        
        if ($LASTEXITCODE -ne 0) { throw "Zirconate plans generation failed" }
        
        Write-Success "Batch plans generation completed (12 plans)"
        
    } catch {
        Write-Error "Batch plans generation failed: $($_.Exception.Message)"
        exit 1
    }
}

# Get latest batch directory
function Get-LatestBatchDir {
    $tasksDir = "tasks"
    if (-not (Test-Path $tasksDir)) { throw "tasks directory does not exist" }
    
    $batchDirs = Get-ChildItem $tasksDir -Directory | Where-Object { $_.Name -match "^batch_" } | Sort-Object LastWriteTime -Descending
    
    if ($batchDirs.Count -eq 0) { throw "No batch directories found" }
    
    return $batchDirs[0].FullName
}

# Validate recommendations
function Test-Recommendations {
    Write-Step "Validating recommendations..."
    
    try {
        $latestBatchDir = Get-LatestBatchDir
        $plansFile = Join-Path $latestBatchDir "plans.csv"
        
        if (-not (Test-Path $plansFile)) {
            throw "Plans file not found: $plansFile"
        }
        
        Write-Host "Validating plans file: $plansFile" -ForegroundColor Gray
        
        python scripts/validate_recommendations.py --plans $plansFile --kb "datasets/index_store" --topk 3
        
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Recommendation validation had warnings, continuing..."
        } else {
            Write-Success "Recommendation validation completed"
        }
        
        return $latestBatchDir
        
    } catch {
        Write-Warning "Recommendation validation failed: $($_.Exception.Message)"
        return $null
    }
}

# Evaluate predictions
function Test-Predictions {
    Write-Step "Evaluating prediction performance..."
    
    try {
        python scripts/evaluate_predictions.py
        
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Prediction evaluation had warnings, continuing..."
        } else {
            Write-Success "Prediction evaluation completed"
        }
        
    } catch {
        Write-Warning "Prediction evaluation failed: $($_.Exception.Message)"
    }
}

# Get model status
function Get-ModelStatus {
    Write-Step "Checking model status..."
    
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/maowise/v1/admin/model_status" -Method Get -ContentType "application/json"
        
        $summary = $response.summary
        Write-Host "Model Status:" -ForegroundColor Gray
        Write-Host "  Total models: $($summary.total_models)" -ForegroundColor Gray
        Write-Host "  Found models: $($summary.found_models)" -ForegroundColor Gray
        Write-Host "  Missing models: $($summary.missing_models)" -ForegroundColor Gray
        Write-Host "  Overall status: $($summary.overall_status)" -ForegroundColor Gray
        
        return $response
        
    } catch {
        Write-Warning "Cannot get model status: $($_.Exception.Message)"
        return $null
    }
}

# Generate comprehensive report
function New-ComprehensiveReport {
    param([string]$BatchDir, [object]$ModelStatus)
    
    Write-Step "Generating comprehensive report..."
    
    try {
        $reportsDir = "reports"
        if (-not (Test-Path $reportsDir)) { New-Item -ItemType Directory -Path $reportsDir | Out-Null }
        
        $reportTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $reportFile = "reports/real_run_report.md"
        $reportHtml = "reports/real_run_report.html"
        
        # Collect batch information
        $batchInfo = @()
        $totalPlans = 0
        
        $taskDirs = Get-ChildItem "tasks" -Directory | Where-Object { $_.Name -match "^batch_.*real_run" } | Sort-Object LastWriteTime -Descending | Select-Object -First 2
        
        foreach ($taskDir in $taskDirs) {
            $csvFile = Join-Path $taskDir.FullName "plans.csv"
            if (Test-Path $csvFile) {
                $plans = Import-Csv $csvFile
                $totalPlans += $plans.Count
                
                $excellentCount = 0
                $thinCount = 0
                $uniformCount = 0
                
                foreach ($plan in $plans) {
                    $massProxy = [double]$plan.mass_proxy
                    $uniformityPenalty = [double]$plan.uniformity_penalty
                    
                    if ($massProxy -lt 0.4) { $thinCount++ }
                    if ($uniformityPenalty -lt 0.2) { $uniformCount++ }
                    if ($massProxy -lt 0.4 -and $uniformityPenalty -lt 0.2) { $excellentCount++ }
                }
                
                $batchInfo += @{
                    BatchId = $taskDir.Name
                    System = if ($taskDir.Name -match "silicate") { "silicate" } else { "zirconate" }
                    TotalPlans = $plans.Count
                    ExcellentCount = $excellentCount
                    ThinCount = $thinCount
                    UniformCount = $uniformCount
                    ExcellentRatio = if ($plans.Count -gt 0) { [math]::Round($excellentCount / $plans.Count * 100, 1) } else { 0 }
                }
            }
        }
        
        # Check evaluation results
        $evalResults = @()
        $evalFiles = Get-ChildItem "reports" -Filter "eval_experiments_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        
        if ($evalFiles) {
            $evalData = Get-Content $evalFiles[0].FullName | ConvertFrom-Json
            $evalResults = @{
                AlphaMAE = $evalData.metrics.alpha_mae
                EpsilonMAE = $evalData.metrics.epsilon_mae
                AlphaHitRate = $evalData.metrics.alpha_hit_rate_003
                EpsilonHitRate = $evalData.metrics.epsilon_hit_rate_003
                LowConfidenceRatio = $evalData.metrics.low_confidence_ratio
            }
        }
        
        # Generate report content
        $content = @"
# MAO-Wise Real Run Report

## Basic Information

- **Run Time**: $reportTime
- **Library Directory**: $LibraryDir
- **Online Mode**: Enabled (OPENAI_API_KEY)
- **Total Generated Plans**: $totalPlans

## Data Pipeline Results

### Model Status
"@

        if ($ModelStatus) {
            $content += @"

- **Total Models**: $($ModelStatus.summary.total_models)
- **Found Models**: $($ModelStatus.summary.found_models)
- **Missing Models**: $($ModelStatus.summary.missing_models)
- **Overall Status**: $($ModelStatus.summary.overall_status)

#### Detailed Model Status
"@
            foreach ($modelName in $ModelStatus.models.PSObject.Properties.Name) {
                $model = $ModelStatus.models.$modelName
                $status = if ($model.status -eq "found") { "[OK]" } else { "[MISSING]" }
                $content += "`n- **$modelName**: $status $($model.status)"
                if ($model.path) { $content += " (Path: $($model.path))" }
            }
        } else {
            $content += "`n- **Status Check**: [ERROR] API service not responding"
        }

        $content += @"

## Batch Plan Generation Results

### Plan Quality Statistics
"@

        foreach ($batch in $batchInfo) {
            $content += @"

#### $($batch.System.ToUpper()) System ($($batch.BatchId))
- **Total Plans**: $($batch.TotalPlans)
- **Excellent Plans**: $($batch.ExcellentCount) / $($batch.TotalPlans) ($($batch.ExcellentRatio)%)
- **Thin Film Plans**: $($batch.ThinCount) (mass_proxy < 0.4)
- **Uniform Plans**: $($batch.UniformCount) (uniformity_penalty < 0.2)
"@
        }

        if ($evalResults) {
            $epsilonStatus = if ($evalResults.EpsilonMAE -le 0.06) { "[OK] Achieved" } else { "[FAIL] Not achieved" }
            $alphaStatus = if ($evalResults.AlphaMAE -le 0.03) { "[OK] Achieved" } else { "[FAIL] Not achieved" }
            
            $content += @"

## Prediction Performance Evaluation

### Core Metrics
- **Epsilon MAE**: $([math]::Round($evalResults.EpsilonMAE, 4)) $epsilonStatus (Target ≤ 0.06)
- **Alpha MAE**: $([math]::Round($evalResults.AlphaMAE, 4)) $alphaStatus (Target ≤ 0.03)
- **Alpha Hit Rate** (±0.03): $([math]::Round($evalResults.AlphaHitRate * 100, 1))%
- **Epsilon Hit Rate** (±0.03): $([math]::Round($evalResults.EpsilonHitRate * 100, 1))%
- **Low Confidence Ratio**: $([math]::Round($evalResults.LowConfidenceRatio * 100, 1))%
"@
        } else {
            $content += @"

## Prediction Performance Evaluation

[WARN] Evaluation result files not found
"@
        }

        $content += @"

## Result Files

### Batch Plan Files
"@

        foreach ($taskDir in $taskDirs) {
            $csvFile = "tasks/$($taskDir.Name)/plans.csv"
            $yamlDir = "tasks/$($taskDir.Name)/plans_yaml/"
            $readmeFile = "tasks/$($taskDir.Name)/README.md"
            
            $content += @"
- **$($taskDir.Name)**:
  - [Plan Summary CSV]($csvFile)
  - [Detailed YAML Files]($yamlDir)
  - [Batch Report]($readmeFile)
"@
        }

        $content += @"

### Evaluation Reports
- [Prediction Performance](reports/eval_experiments_*.json)
- [Recommendation Validation](reports/recommendation_validation_*.json)

## Usage Recommendations

### Excellent Plan Filtering
1. Check `plans.csv` files in each batch
2. Filter conditions: `mass_proxy < 0.4` AND `uniformity_penalty < 0.2`
3. Prioritize plans with `confidence >= 0.7`

---
*This report was automatically generated by MAO-Wise Real Run at $reportTime*
"@

        # Save reports
        Set-Content -Path $reportFile -Value $content -Encoding UTF8
        
        $htmlContent = @"
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>MAO-Wise Real Run Report</title>
<style>body{font-family:Arial,sans-serif;margin:40px;line-height:1.6;}h1,h2,h3{color:#333;}.status-ok{color:#28a745;}.status-error{color:#dc3545;}</style>
</head><body>
$($content -replace '###? ', '<h3>' -replace '\n', '<br>' -replace '\*\*(.*?)\*\*', '<strong>$1</strong>')
</body></html>
"@
        
        Set-Content -Path $reportHtml -Value $htmlContent -Encoding UTF8
        
        Write-Success "Comprehensive report generated"
        Write-Host "  Markdown: $reportFile" -ForegroundColor Gray
        Write-Host "  HTML: $reportHtml" -ForegroundColor Gray
        
        $totalExcellent = ($batchInfo | Measure-Object -Property ExcellentCount -Sum).Sum
        $excellentRatio = if ($totalPlans -gt 0) { $totalExcellent / $totalPlans } else { 0 }
        
        return @{
            MarkdownFile = $reportFile
            HtmlFile = $reportHtml
            TotalPlans = $totalPlans
            ExcellentRatio = $excellentRatio
        }
        
    } catch {
        Write-Error "Report generation failed: $($_.Exception.Message)"
        return $null
    }
}

# Main execution
function Main {
    Write-ColorOutput "MAO-Wise Real Run Started" "Magenta"
    Write-Host "================================================" -ForegroundColor Magenta
    
    $startTime = Get-Date
    
    try {
        Test-Environment
        Invoke-Pipeline
        New-BatchPlans
        $batchDir = Test-Recommendations
        Test-Predictions
        $modelStatus = Get-ModelStatus
        $reportResult = New-ComprehensiveReport -BatchDir $batchDir -ModelStatus $modelStatus
        
        $endTime = Get-Date
        $duration = $endTime - $startTime
        
        Write-ColorOutput "Real Run Completed Successfully!" "Green"
        Write-Host "================================================" -ForegroundColor Green
        Write-Host "Total Duration: $([math]::Round($duration.TotalMinutes, 1)) minutes" -ForegroundColor Green
        
        if ($reportResult) {
            Write-Host "Generated Plans: $($reportResult.TotalPlans)" -ForegroundColor Green
            Write-Host "Excellent Ratio: $([math]::Round($reportResult.ExcellentRatio * 100, 1))%" -ForegroundColor Green
            Write-Host "Report File: $($reportResult.HtmlFile)" -ForegroundColor Green
        }
        
    } catch {
        Write-Error "Real Run failed: $($_.Exception.Message)"
        Write-Host $_.ScriptStackTrace -ForegroundColor Red
        exit 1
    }
}

# Script entry point
if ($MyInvocation.InvocationName -ne '.') { Main }