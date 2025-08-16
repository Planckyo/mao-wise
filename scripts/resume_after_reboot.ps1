# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    MAO-Wise 一键恢复脚本 - 开机后快速恢复运行环境与服务

.DESCRIPTION
    支持虚拟环境激活、LLM连通性检查、KB重建、服务启动、健康检查和报告生成。
    兼容中文路径，优雅降级，不依赖人工输入。

.PARAMETER RebuildKB
    是否重建知识库索引，默认 false

.PARAMETER OpenUI
    完成后是否打开UI，默认 true

.PARAMETER ApiPort
    API服务端口，默认 8000

.PARAMETER UiPort
    UI服务端口，默认 8501

.PARAMETER Quick
    快速模式，跳过耗时项，默认 false

.EXAMPLE
    .\scripts\resume_after_reboot.ps1 -RebuildKB:$false -OpenUI:$true
#>

param(
    [bool]$RebuildKB = $false,
    [bool]$OpenUI = $true,
    [int]$ApiPort = 8000,
    [int]$UiPort = 8501,
    [bool]$Quick = $false
)

# 设置UTF-8编码
chcp 65001 > $null

# 初始化日志变量
$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$logFile = "reports/resume_$timestamp.txt"
$startTime = Get-Date

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $logMessage = "$(Get-Date -Format 'HH:mm:ss') [$Level] $Message"
    Write-Host $logMessage
    if (Test-Path "reports") {
        Add-Content -Path $logFile -Value $logMessage -Encoding UTF8
    }
}

function Test-RepoRoot {
    $requiredItems = @("apps", "maowise", "requirements.txt")
    foreach ($item in $requiredItems) {
        if (-not (Test-Path $item)) {
            return $false
        }
    }
    return $true
}

function Find-RepoRoot {
    $currentDir = Get-Location
    $maxLevels = 5
    
    for ($i = 0; $i -lt $maxLevels; $i++) {
        if (Test-RepoRoot) {
            return $true
        }
        $parent = Split-Path (Get-Location) -Parent
        if (-not $parent -or $parent -eq (Get-Location)) {
            break
        }
        Set-Location $parent
    }
    
    Set-Location $currentDir
    return $false
}

function Initialize-Environment {
    Write-Log "Initialize environment..."
    
    # 创建reports目录
    if (-not (Test-Path "reports")) {
        New-Item -ItemType Directory -Path "reports" -Force | Out-Null
    }
    
    # 检查并切换到仓库根目录
    if (-not (Test-RepoRoot)) {
        Write-Log "Current directory is not repo root, searching..." -Level "WARN"
        if (-not (Find-RepoRoot)) {
            $errorMsg = "Error: MAO-Wise repo root not found. Please ensure directory contains apps, maowise, requirements.txt."
            Write-Log $errorMsg -Level "ERROR"
            throw $errorMsg
        }
    }
    
    $repoRoot = Get-Location
    Write-Log "Repo root: $repoRoot"
    
    # 设置PYTHONPATH
    $env:PYTHONPATH = $repoRoot
    Write-Log "Set PYTHONPATH: $repoRoot"
    
    return $repoRoot
}

function Setup-VirtualEnvironment {
    Write-Log "Check and setup virtual environment..."
    
    $venvPath = ".venv"
    $activatePath = "$venvPath\Scripts\activate"
    
    if (-not (Test-Path $activatePath)) {
        Write-Log "Virtual environment not found, creating..." -Level "WARN"
        try {
            python -m venv $venvPath
            if ($LASTEXITCODE -ne 0) {
                throw "Virtual environment creation failed"
            }
            
            & $activatePath
            pip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) {
                throw "Dependencies installation failed"
            }
            
            Write-Log "Virtual environment created and activated successfully"
        }
        catch {
            $errorMsg = "Virtual environment setup failed: $($_.Exception.Message). Please check Python installation."
            Write-Log $errorMsg -Level "ERROR"
            throw $errorMsg
        }
    }
    else {
        Write-Log "Activating existing virtual environment..."
        & $activatePath
        Write-Log "Virtual environment activated successfully"
    }
}

function Load-EnvironmentVariables {
    Write-Log "Loading environment variables..."
    
    $envFile = ".env"
    if (Test-Path $envFile) {
        Write-Log "Reading .env file"
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                
                # Remove quotes
                if ($value -match '^["''](.*)["'']$') {
                    $value = $matches[1]
                }
                
                Set-Item -Path "env:$key" -Value $value
                
                # Mask sensitive variables
                if ($key -eq "OPENAI_API_KEY" -and $value) {
                    $maskedKey = if ($value.Length -gt 6) {
                        $value.Substring(0, 3) + "****" + $value.Substring($value.Length - 3)
                    } else {
                        "****"
                    }
                    Write-Log "  $key = $maskedKey"
                }
                elseif ($key -in @("LLM_PROVIDER", "MAOWISE_LIBRARY_DIR")) {
                    Write-Log "  $key = $value"
                }
            }
        }
    }
    else {
        Write-Log ".env file not found, skipping environment variables loading" -Level "WARN"
    }
}

function Test-LLMConnectivity {
    Write-Log "Execute LLM connectivity check..."
    
    if ($Quick) {
        Write-Log "Quick mode: Skip LLM connectivity check" -Level "WARN"
        return "SKIPPED"
    }
    
    try {
        $result = python -X dev scripts/test_llm_connectivity.py 2>&1
        $exitCode = $LASTEXITCODE
        
        # Log complete output
        $result | ForEach-Object { 
            if (Test-Path "reports") {
                Add-Content -Path $logFile -Value "  $_" -Encoding UTF8 
            }
        }
        
        if ($exitCode -eq 0) {
            Write-Log "LLM connectivity check passed"
            return "PASS"
        }
        else {
            Write-Log "LLM connectivity check failed (exit code: $exitCode)" -Level "WARN"
            return "FAIL"
        }
    }
    catch {
        Write-Log "LLM connectivity check exception: $($_.Exception.Message)" -Level "WARN"
        return "ERROR"
    }
}

function Check-RebuildKnowledgeBase {
    Write-Log "Check knowledge base status..."
    
    $indexDir = "datasets/index_store"
    $needRebuild = $RebuildKB -or (-not (Test-Path $indexDir))
    
    if ($needRebuild) {
        if ($Quick) {
            Write-Log "Quick mode: Skip KB rebuild" -Level "WARN"
            return "SKIPPED"
        }
        
        Write-Log "Rebuild knowledge base index..."
        
        try {
            $corpusFile = "datasets/data_parsed/corpus.jsonl"
            if (-not (Test-Path $corpusFile)) {
                Write-Log "Corpus file not found: $corpusFile" -Level "WARN"
                return "MISSING_CORPUS"
            }
            
            python -m maowise.kb.build_index --corpus $corpusFile --out_dir $indexDir
            
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Knowledge base index rebuilt successfully"
                
                # Check index files
                $vectorCount = "Unknown"
                if (Test-Path "$indexDir/meta.json") {
                    try {
                        $meta = Get-Content "$indexDir/meta.json" | ConvertFrom-Json
                        $vectorCount = $meta.total_vectors
                    } catch {
                        $vectorCount = "Unknown"
                    }
                }
                
                Write-Log "FAISS/NumPy backend, vector count: $vectorCount"
                return "REBUILT"
            }
            else {
                Write-Log "Knowledge base index rebuild failed" -Level "ERROR"
                return "REBUILD_FAILED"
            }
        }
        catch {
            Write-Log "Knowledge base rebuild exception: $($_.Exception.Message)" -Level "ERROR"
            return "REBUILD_ERROR"
        }
    }
    else {
        Write-Log "Knowledge base index exists, skip rebuild"
        return "EXISTS"
    }
}

function Start-Services {
    Write-Log "Starting services..."
    
    # Check for existing start_services.ps1 script
    $startServicesScript = "scripts/start_services.ps1"
    
    if (Test-Path $startServicesScript) {
        Write-Log "Using existing startup script: $startServicesScript"
        try {
            & $startServicesScript -ApiPort $ApiPort -UiPort $UiPort
            return $true
        }
        catch {
            Write-Log "Existing startup script failed: $($_.Exception.Message)" -Level "WARN"
            Write-Log "Fallback to manual startup..."
        }
    }
    
    # Manual parallel service startup
    Write-Log "Parallel startup of API and UI services..."
    
    try {
        # Start API service
        Write-Log "Starting API service (port: $ApiPort)..."
        $apiJob = Start-Job -ScriptBlock {
            param($port, $pythonPath)
            $env:PYTHONPATH = $pythonPath
            Set-Location $using:PWD
            uvicorn apps.api.main:app --host 127.0.0.1 --port $port
        } -ArgumentList $ApiPort, $env:PYTHONPATH
        
        # Start UI service
        Write-Log "Starting UI service (port: $UiPort)..."
        $uiJob = Start-Job -ScriptBlock {
            param($port, $pythonPath)
            $env:PYTHONPATH = $pythonPath
            Set-Location $using:PWD
            streamlit run apps/ui/app.py --server.port $port
        } -ArgumentList $UiPort, $env:PYTHONPATH
        
        # Wait for services to start
        Start-Sleep -Seconds 5
        
        Write-Log "Service startup jobs submitted (API Job: $($apiJob.Id), UI Job: $($uiJob.Id))"
        return $true
    }
    catch {
        Write-Log "Service startup failed: $($_.Exception.Message)" -Level "ERROR"
        return $false
    }
}

function Test-ServiceHealth {
    Write-Log "Execute service health check..."
    
    $maxRetries = 5
    $retryDelay = 3
    $healthEndpoint = "http://127.0.0.1:$ApiPort/api/maowise/v1/health"
    $statusEndpoint = "http://127.0.0.1:$ApiPort/api/maowise/v1/admin/model_status"
    
    $healthResult = $null
    $statusResult = $null
    
    for ($i = 1; $i -le $maxRetries; $i++) {
        Write-Log "Health check attempt $i/$maxRetries..."
        
        try {
            # Check health endpoint
            if (-not $healthEndpoint) {
                throw "Health check endpoint URL is empty"
            }
            
            $healthResponse = Invoke-RestMethod -Uri $healthEndpoint -Method GET -TimeoutSec 10
            $healthResult = $healthResponse
            Write-Log "Health check passed: $($healthResponse | ConvertTo-Json -Compress)"
            
            # Check model status endpoint
            if (-not $statusEndpoint) {
                throw "Model status endpoint URL is empty"
            }
            
            $statusResponse = Invoke-RestMethod -Uri $statusEndpoint -Method GET -TimeoutSec 10
            $statusResult = $statusResponse
            Write-Log "Model status check passed"
            
            break
        }
        catch {
            Write-Log "Health check failed (attempt $i/$maxRetries): $($_.Exception.Message)" -Level "WARN"
            
            if ($i -eq $maxRetries) {
                $errorMsg = @"
Service health check failed, possible causes:
1. Check if API service is running on port $ApiPort
2. Check firewall settings
3. Review service startup logs
4. Confirm virtual environment and dependencies are correctly installed

Suggested manual execution:
  uvicorn apps.api.main:app --host 127.0.0.1 --port $ApiPort
  streamlit run apps/ui/app.py --server.port $UiPort
"@
                Write-Log $errorMsg -Level "ERROR"
                throw "Service health check failed"
            }
            
            Start-Sleep -Seconds $retryDelay
        }
    }
    
    return @{
        Health = $healthResult
        Status = $statusResult
    }
}

function Update-Reports {
    Write-Log "Check and update reports..."
    
    # Check for leakage evaluation related files
    $leakageFiles = @(
        "reports/fwd_eval_lopo.json",
        "reports/fwd_eval_timesplit.json"
    )
    
    $hasLeakageFiles = $false
    foreach ($file in $leakageFiles) {
        if (Test-Path $file) {
            $hasLeakageFiles = $true
            Write-Log "Found leakage evaluation file: $file"
        }
    }
    
    if ($hasLeakageFiles) {
        Write-Log "Generate leakage comparison analysis..."
        
        try {
            # Execute leakage analysis
            python scripts/analyze_group_split.py
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Leakage analysis completed"
            }
            
            # Update HTML report
            $makeReportArgs = @(
                "--extras", "leakage",
                "--output", "reports/real_run_report.html"
            )
            
            # Add leakage related parameters
            if (Test-Path "reports/fwd_eval_lopo.json") {
                $makeReportArgs += "--leakage-json"
                $makeReportArgs += "reports/fwd_eval_lopo.json"
            }
            if (Test-Path "reports/fwd_eval_timesplit.json") {
                $makeReportArgs += "reports/fwd_eval_timesplit.json"
            }
            
            Write-Log "Update HTML report..."
            python scripts/make_html_report.py @makeReportArgs
            
            if ($LASTEXITCODE -eq 0) {
                Write-Log "HTML report updated successfully, includes leakage review section"
                return "LEAKAGE_INCLUDED"
            }
            else {
                Write-Log "HTML report update failed" -Level "WARN"
                return "LEAKAGE_FAILED"
            }
        }
        catch {
            Write-Log "Leakage report generation exception: $($_.Exception.Message)" -Level "WARN"
            return "LEAKAGE_ERROR"
        }
    }
    else {
        Write-Log "No leakage evaluation files found, skip leakage section generation"
        return "NO_LEAKAGE"
    }
}

function Generate-Summary {
    param($healthCheck, $llmStatus, $kbStatus, $reportStatus)
    
    $endTime = Get-Date
    $duration = $endTime - $startTime
    
    $summary = @"

========================
MAO-Wise Recovery Summary Report
========================
Start Time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))
Total Duration: $($duration.ToString('mm\:ss'))

Service Configuration:
- API Port: $ApiPort
- UI Port: $UiPort
- Repo Root: $(Get-Location)

Status Check:
- LLM Connectivity: $llmStatus
- Knowledge Base Status: $kbStatus
- API Health Check: $(if ($healthCheck.Health) { 'PASS' } else { 'FAIL' })
- Model Status Check: $(if ($healthCheck.Status) { 'PASS' } else { 'FAIL' })
- Leakage Report: $reportStatus

Access URLs:
- API Documentation: http://127.0.0.1:$ApiPort/docs
- User Interface: http://127.0.0.1:$UiPort
- Health Check: http://127.0.0.1:$ApiPort/api/maowise/v1/health

Log File: $logFile
HTML Report: reports/real_run_report.html (if generated)

========================
"@
    
    Write-Log $summary
    return $summary
}

# Main execution flow
try {
    Write-Log "========================================"
    Write-Log "MAO-Wise One-Click Recovery Script Started"
    Write-Log "========================================"
    Write-Log "Parameters: RebuildKB=$RebuildKB, OpenUI=$OpenUI, Quick=$Quick"
    Write-Log "Ports: API=$ApiPort, UI=$UiPort"
    
    # 1. Initialize environment
    $repoRoot = Initialize-Environment
    
    # 2. Setup virtual environment
    Setup-VirtualEnvironment
    
    # 3. Load environment variables
    Load-EnvironmentVariables
    
    # 4. LLM connectivity check
    $llmStatus = Test-LLMConnectivity
    
    # 5. Knowledge base check and rebuild
    $kbStatus = Check-RebuildKnowledgeBase
    
    # 6. Start services
    $serviceStarted = Start-Services
    if (-not $serviceStarted) {
        throw "Service startup failed"
    }
    
    # 7. Health check
    $healthCheck = Test-ServiceHealth
    
    # 8. Update reports
    $reportStatus = Update-Reports
    
    # 9. Generate summary
    $summary = Generate-Summary -healthCheck $healthCheck -llmStatus $llmStatus -kbStatus $kbStatus -reportStatus $reportStatus
    
    # 10. Open UI (optional)
    if ($OpenUI) {
        Write-Log "Opening user interface..."
        Start-Process "http://127.0.0.1:$UiPort"
    }
    
    Write-Log "========================================"
    Write-Log "MAO-Wise One-Click Recovery Completed!"
    Write-Log "========================================"
    
    # Return key information for verification
    return @{
        LogFile = $logFile
        HealthCheck = $healthCheck
        ReportStatus = $reportStatus
        Success = $true
    }
}
catch {
    $errorMsg = "Recovery script execution failed: $($_.Exception.Message)"
    Write-Log $errorMsg -Level "ERROR"
    Write-Log "========================================"
    Write-Log "MAO-Wise Recovery Failed!"
    Write-Log "========================================"
    
    return @{
        LogFile = $logFile
        Error = $errorMsg
        Success = $false
    }
}