# MAO-Wise R4 一键上线脚本
# 完整流程：预检 → 增量入库 → 生成R4 → 打包 → 报告 → 交付

param(
    [switch]$SkipPrecheck,
    [switch]$SkipUI,
    [switch]$QuickMode,
    [string]$OutputDir = "outputs/lab_package_R4"
)

# 统一编码设置
chcp 65001 > $null
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# 全局变量
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:StartTime = Get-Date

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN"  { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        "INFO"  { Write-Host $logEntry -ForegroundColor Cyan }
        default { Write-Host $logEntry }
    }
}

function Write-Step {
    param([string]$StepName, [int]$StepNumber = 0)
    
    $separator = "=" * 80
    Write-Host ""
    Write-Host $separator -ForegroundColor Blue
    if ($StepNumber -gt 0) {
        Write-Host "步骤 $StepNumber : $StepName" -ForegroundColor Blue
    } else {
        Write-Host $StepName -ForegroundColor Blue
    }
    Write-Host $separator -ForegroundColor Blue
    Write-Host ""
}

function Test-PreflightChecks {
    Write-Step "执行预检" 1
    
    if ($SkipPrecheck) {
        Write-Log "跳过预检（-SkipPrecheck 参数）" "WARN"
        return $true
    }
    
    try {
        $preflightScript = Join-Path $script:RepoRoot "scripts/preflight_go_live.ps1"
        if (-not (Test-Path $preflightScript)) {
            Write-Log "预检脚本不存在: $preflightScript" "ERROR"
            return $false
        }
        
        Write-Log "运行预检脚本..." "INFO"
        
        # 执行预检
        if ($QuickMode) {
            & powershell -ExecutionPolicy Bypass -File $preflightScript -SkipServices -QuickMode
        } else {
            & powershell -ExecutionPolicy Bypass -File $preflightScript
        }
        
        # 检查预检报告
        $checklistPath = Join-Path $script:RepoRoot "reports/go_live_checklist.txt"
        if (Test-Path $checklistPath) {
            $checklistContent = Get-Content $checklistPath -Raw -ErrorAction SilentlyContinue
            
            # 检查是否有FAIL项
            if ($checklistContent -match "✗.*FAIL") {
                Write-Log "预检发现严重问题，不能继续上线！" "ERROR"
                Write-Host ""
                Write-Host "修复建议:" -ForegroundColor Red
                
                # 提取FAIL项的修复建议
                $lines = Get-Content $checklistPath
                $inFailSection = $false
                foreach ($line in $lines) {
                    if ($line -match "✗.*FAIL") {
                        Write-Host "  $line" -ForegroundColor Red
                        $inFailSection = $true
                    } elseif ($inFailSection -and $line -match "建议:") {
                        Write-Host "  $line" -ForegroundColor Yellow
                        $inFailSection = $false
                    }
                }
                
                Write-Host ""
                Write-Host "请修复所有FAIL项后重新运行此脚本。" -ForegroundColor Red
                return $false
            }
            
            # 检查整体状态
            if ($checklistContent -match "整体状态:\s*PASS") {
                Write-Log "预检通过！系统准备就绪" "SUCCESS"
                return $true
            } elseif ($checklistContent -match "整体状态:\s*WARN") {
                Write-Log "预检基本通过，存在警告项但可以继续" "WARN"
                return $true
            } else {
                Write-Log "预检状态不明确，谨慎继续" "WARN"
                return $true
            }
        } else {
            Write-Log "预检报告文件不存在，假设通过" "WARN"
            return $true
        }
    } catch {
        Write-Log "预检执行失败: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Invoke-IncrementalKBUpdate {
    Write-Step "增量入库实验反馈" 2
    
    try {
        $appendScript = Join-Path $script:RepoRoot "scripts/append_feedback_to_kb.py"
        if (-not (Test-Path $appendScript)) {
            Write-Log "增量入库脚本不存在，跳过此步骤" "WARN"
            return $true
        }
        
        Write-Log "检查并增量入库实验反馈..." "INFO"
        
        # 执行增量入库
        $result = & python -X utf8 $appendScript --min_delta 1 2>&1
        $exitCode = $LASTEXITCODE
        
        if ($exitCode -eq 0) {
            # 解析输出获取统计信息
            if ($result -match "旧向量数:\s*(\d+)") {
                $oldVecs = $matches[1]
            } else { $oldVecs = "unknown" }
            
            if ($result -match "新向量数:\s*(\d+)") {
                $newVecs = $matches[1]
            } else { $newVecs = "unknown" }
            
            if ($result -match "总向量数:\s*(\d+)") {
                $totalVecs = $matches[1]
            } else { $totalVecs = "unknown" }
            
            Write-Log "KB更新完成: $oldVecs → $totalVecs (+$newVecs)" "SUCCESS"
            return $true
        } else {
            Write-Log "KB更新失败，但继续执行（可能无新数据）" "WARN"
            return $true
        }
    } catch {
        Write-Log "KB更新异常: $($_.Exception.Message)" "WARN"
        return $true
    }
}

function Generate-R4Batches {
    Write-Step "生成R4候选方案" 3
    
    try {
        $generateScript = Join-Path $script:RepoRoot "scripts/generate_batch_plans.py"
        if (-not (Test-Path $generateScript)) {
            Write-Log "批次生成脚本不存在: $generateScript" "ERROR"
            return $false
        }
        
        # 检查约束文件
        $constraintsPath = Join-Path $script:RepoRoot "datasets/constraints/lab_constraints.yaml"
        $useConstraints = ""
        if (Test-Path $constraintsPath) {
            $useConstraints = "--constraints $constraintsPath"
            Write-Log "使用约束文件: lab_constraints.yaml" "INFO"
        } else {
            Write-Log "约束文件不存在，使用默认配置" "WARN"
        }
        
        # 生成硅酸盐体系
        Write-Log "生成硅酸盐体系候选..." "INFO"
        $silicateResult = & python -X utf8 $generateScript --system silicate --notes "R4-自动上线-硅酸盐" --n 15 $useConstraints 2>&1
        $silicateExitCode = $LASTEXITCODE
        
        if ($silicateExitCode -ne 0) {
            Write-Log "硅酸盐方案生成失败" "ERROR"
            return $false
        }
        
        # 提取硅酸盐批次ID
        $silicateBatchId = ""
        if ($silicateResult -match "batch_(\d{8}_\d{4})") {
            $silicateBatchId = "batch_$($matches[1])"
            Write-Log "硅酸盐批次: $silicateBatchId" "SUCCESS"
        }
        
        # 生成锆酸盐体系
        Write-Log "生成锆酸盐体系候选..." "INFO"
        $zirconateResult = & python -X utf8 $generateScript --system zirconate --notes "R4-自动上线-锆酸盐" --n 15 $useConstraints 2>&1
        $zirconateExitCode = $LASTEXITCODE
        
        if ($zirconateExitCode -ne 0) {
            Write-Log "锆酸盐方案生成失败" "ERROR"
            return $false
        }
        
        # 提取锆酸盐批次ID
        $zirconateBatchId = ""
        if ($zirconateResult -match "batch_(\d{8}_\d{4})") {
            $zirconateBatchId = "batch_$($matches[1])"
            Write-Log "锆酸盐批次: $zirconateBatchId" "SUCCESS"
        }
        
        # 保存批次信息供后续使用
        $script:SilicateBatch = $silicateBatchId
        $script:ZirconateBatch = $zirconateBatchId
        
        Write-Log "R4候选方案生成完成" "SUCCESS"
        return $true
        
    } catch {
        Write-Log "R4生成异常: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Package-ExperimentPlans {
    Write-Step "打包实验清单" 4
    
    try {
        $packageScript = Join-Path $script:RepoRoot "scripts/select_and_package_for_lab.py"
        if (-not (Test-Path $packageScript)) {
            Write-Log "打包脚本不存在，手动创建实验清单" "WARN"
            return Invoke-ManualPackaging
        }
        
        # 找到最新的批次文件
        $latestBatch = Get-ChildItem (Join-Path $script:RepoRoot "tasks") -Filter "batch_*" | 
                      Sort-Object LastWriteTime -Descending | 
                      Select-Object -First 1
        
        if (-not $latestBatch) {
            Write-Log "未找到批次文件" "ERROR"
            return $false
        }
        
        $plansFile = Join-Path $latestBatch.FullName "plans.csv"
        if (-not (Test-Path $plansFile)) {
            Write-Log "批次plans.csv不存在: $plansFile" "ERROR"
            return $false
        }
        
        Write-Log "使用批次文件: $($latestBatch.Name)" "INFO"
        Write-Log "打包实验清单..." "INFO"
        
        # 确保输出目录存在
        $fullOutputDir = Join-Path $script:RepoRoot $OutputDir
        if (-not (Test-Path $fullOutputDir)) {
            New-Item -Path $fullOutputDir -ItemType Directory -Force | Out-Null
        }
        
        # 执行打包
        $packageResult = & python -X utf8 $packageScript `
            --plans $plansFile `
            --alpha_max 0.25 `
            --epsilon_min 0.75 `
            --conf_min 0.5 `
            --mass_max 0.8 `
            --uniform_max 0.3 `
            --k_explore 8 `
            --n_top 12 `
            --min_per_system 6 `
            --outdir $fullOutputDir 2>&1
        
        $packageExitCode = $LASTEXITCODE
        
        if ($packageExitCode -eq 0) {
            Write-Log "实验清单打包完成" "SUCCESS"
            
            # 防呆检查：验证YAML文件数量
            Write-Log "执行YAML文件计数检查..." "INFO"
            $checkScript = Join-Path $script:RepoRoot "scripts/yaml_count_check.ps1"
            $expTasksPath = Join-Path $script:RepoRoot "$OutputDir/exp_tasks.csv"
            $plansDir = Join-Path $script:RepoRoot "$OutputDir/plans"
            
            if (Test-Path $checkScript) {
                $checkResult = & powershell -ExecutionPolicy Bypass -File $checkScript -PlansDir $plansDir -ExpTasksCsv $expTasksPath
                
                if ($LASTEXITCODE -ne 0) {
                    Write-Log "YAML文件计数检查失败，可能存在打包问题" "ERROR"
                    return $false
                } else {
                    Write-Log "YAML文件计数检查通过" "SUCCESS"
                }
            } else {
                Write-Log "YAML计数检查脚本不存在，跳过检查" "WARN"
            }
            
            return $true
        } else {
            Write-Log "打包失败，尝试手动创建" "WARN"
            return Invoke-ManualPackaging
        }
    } catch {
        Write-Log "打包异常: $($_.Exception.Message)" "WARN"
        return Invoke-ManualPackaging
    }
}

function Invoke-ManualPackaging {
    Write-Log "执行手动打包..." "INFO"
    
    try {
        # 找到最新的批次文件
        $batchDirs = Get-ChildItem (Join-Path $script:RepoRoot "tasks") -Filter "batch_*" | 
                    Sort-Object LastWriteTime -Descending
        
        $combinedPlans = @()
        $successCount = 0
        
        foreach ($batchDir in $batchDirs | Select-Object -First 3) {
            $plansFile = Join-Path $batchDir.FullName "plans.csv"
            if (Test-Path $plansFile) {
                $plans = Import-Csv $plansFile
                $combinedPlans += $plans
                $successCount++
                Write-Log "合并批次: $($batchDir.Name) (${plans.Count} 条)" "INFO"
            }
        }
        
        if ($successCount -eq 0) {
            Write-Log "未找到有效的批次文件" "ERROR"
            return $false
        }
        
        # 筛选优质方案
        $selectedPlans = $combinedPlans | Where-Object {
            $_.alpha -le 0.25 -and 
            $_.epsilon -ge 0.75 -and 
            $_.confidence -ge 0.5
        } | Select-Object -First 20
        
        # 确保输出目录存在
        $fullOutputDir = Join-Path $script:RepoRoot $OutputDir
        if (-not (Test-Path $fullOutputDir)) {
            New-Item -Path $fullOutputDir -ItemType Directory -Force | Out-Null
        }
        
        # 保存实验清单
        $expTasksFile = Join-Path $fullOutputDir "exp_tasks.csv"
        $selectedPlans | Export-Csv -Path $expTasksFile -NoTypeInformation -Encoding UTF8
        
        Write-Log "手动打包完成: $($selectedPlans.Count) 条实验任务" "SUCCESS"
        Write-Log "保存到: $expTasksFile" "INFO"
        
        return $true
    } catch {
        Write-Log "手动打包失败: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Update-Reports {
    Write-Step "刷新报告" 5
    
    try {
        $reportScript = Join-Path $script:RepoRoot "scripts/make_html_report.py"
        if (-not (Test-Path $reportScript)) {
            Write-Log "报告脚本不存在，跳过报告生成" "WARN"
            return $true
        }
        
        Write-Log "生成HTML报告..." "INFO"
        
        $reportResult = & python -X utf8 $reportScript 2>&1
        $reportExitCode = $LASTEXITCODE
        
        if ($reportExitCode -eq 0) {
            Write-Log "HTML报告生成完成" "SUCCESS"
            
            # 检查报告文件
            $htmlReport = Join-Path $script:RepoRoot "reports/real_run_report.html"
            if (Test-Path $htmlReport) {
                $reportSize = (Get-Item $htmlReport).Length / 1KB
                Write-Log "报告文件大小: ${reportSize:F1} KB" "INFO"
            }
            return $true
        } else {
            Write-Log "报告生成失败，但继续执行" "WARN"
            return $true
        }
    } catch {
        Write-Log "报告生成异常: $($_.Exception.Message)" "WARN"
        return $true
    }
}

function Show-DeliverySummary {
    Write-Step "R4 交付摘要" 6
    
    try {
        # 检查实验清单文件
        $expTasksFile = Join-Path $script:RepoRoot "$OutputDir/exp_tasks.csv"
        if (-not (Test-Path $expTasksFile)) {
            Write-Log "实验清单文件不存在: $expTasksFile" "ERROR"
            return $false
        }
        
        Write-Log "分析R4交付清单..." "INFO"
        
        # 分析实验清单
        $analysisResult = & python -X utf8 -c @"
import pandas as pd
import sys

try:
    df = pd.read_csv('$($expTasksFile.Replace('\', '/'))')
    
    print(f'📊 R4总实验数: {len(df)}')
    
    # 体系分布
    if 'system' in df.columns:
        system_counts = df['system'].value_counts()
        print('\\n📋 体系分布:')
        for system, count in system_counts.items():
            print(f'  {system}: {count} 条')
    
    # 性能达标统计
    if 'alpha' in df.columns and 'epsilon' in df.columns:
        target_mask = (df['alpha'] <= 0.22) & (df['epsilon'] >= 0.80)
        target_count = target_mask.sum()
        
        approaching_mask = (df['alpha'] <= 0.25) & (df['epsilon'] >= 0.75)
        approaching_count = approaching_mask.sum()
        
        print(f'\\n🎯 性能统计:')
        print(f'  α≤0.22 & ε≥0.80 (达标): {target_count} 条')
        print(f'  α≤0.25 & ε≥0.75 (逼近): {approaching_count} 条')
    
    # Top-5 方案
    if 'alpha' in df.columns and 'epsilon' in df.columns:
        print(f'\\n🏆 Top-5 优选方案:')
        print('=' * 60)
        
        # 按综合性能排序
        df_sorted = df.copy()
        if 'score_total' in df.columns:
            df_sorted = df_sorted.sort_values('score_total', ascending=False)
        else:
            # 简单评分：epsilon高 + alpha低
            df_sorted['simple_score'] = df_sorted['epsilon'] - df_sorted['alpha']
            df_sorted = df_sorted.sort_values('simple_score', ascending=False)
        
        for i, (idx, row) in enumerate(df_sorted.head(5).iterrows(), 1):
            system = row.get('system', 'unknown')
            alpha = row.get('alpha', 0)
            epsilon = row.get('epsilon', 0)
            conf = row.get('confidence', 0)
            print(f'  {i}. {system:>10} | α={alpha:.3f} ε={epsilon:.3f} conf={conf:.3f}')
    
except Exception as e:
    print(f'分析失败: {e}')
    sys.exit(1)
"@ 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host $analysisResult
            Write-Log "R4交付摘要生成完成" "SUCCESS"
            return $true
        } else {
            Write-Log "摘要分析失败" "ERROR"
            return $false
        }
    } catch {
        Write-Log "摘要生成异常: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Open-UIAndReports {
    Write-Step "打开界面和报告" 7
    
    if ($SkipUI) {
        Write-Log "跳过UI打开（-SkipUI 参数）" "INFO"
        return
    }
    
    try {
        # 打开HTML报告
        $htmlReport = Join-Path $script:RepoRoot "reports/real_run_report.html"
        if (Test-Path $htmlReport) {
            Write-Log "打开HTML报告..." "INFO"
            Start-Process $htmlReport
        }
        
        # 打开Go-Live报告
        $goLiveReport = Join-Path $script:RepoRoot "reports/go_live_checklist.html"
        if (Test-Path $goLiveReport) {
            Write-Log "打开Go-Live报告..." "INFO"
            Start-Process $goLiveReport
        }
        
        # 尝试打开UI
        Write-Log "尝试打开Streamlit UI..." "INFO"
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8501" -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Start-Process "http://localhost:8501"
                Write-Log "UI已打开" "SUCCESS"
            } else {
                Write-Log "UI服务未运行" "WARN"
            }
        } catch {
            Write-Log "UI连接失败，可能服务未启动" "WARN"
        }
    } catch {
        Write-Log "打开界面异常: $($_.Exception.Message)" "WARN"
    }
}

function Show-FinalSummary {
    $endTime = Get-Date
    $duration = $endTime - $script:StartTime
    
    Write-Step "上线完成摘要"
    
    Write-Host ""
    Write-Host "🎉 MAO-Wise R4 上线流程完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "⏱️  执行时间: $($duration.TotalMinutes.ToString('F1')) 分钟" -ForegroundColor Cyan
    Write-Host "📁 输出目录: $OutputDir" -ForegroundColor Cyan
    
    # 检查关键文件
    $expTasksFile = Join-Path $script:RepoRoot "$OutputDir/exp_tasks.csv"
    if (Test-Path $expTasksFile) {
        $taskCount = (Import-Csv $expTasksFile).Count
        Write-Host "📊 实验任务: $taskCount 条" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "📋 关键文件:" -ForegroundColor Yellow
    Write-Host "  - 实验清单: $OutputDir/exp_tasks.csv" -ForegroundColor White
    Write-Host "  - HTML报告: reports/real_run_report.html" -ForegroundColor White
    Write-Host "  - 预检报告: reports/go_live_checklist.html" -ForegroundColor White
    
    Write-Host ""
    Write-Host "🚀 系统已准备就绪，可以开始R4实验！" -ForegroundColor Green
    Write-Host ""
}

function Main {
    Write-Host ""
    Write-Host "🚀 MAO-Wise R4 一键上线脚本" -ForegroundColor Green
    Write-Host "   自动化流程：预检 → 入库 → 生成 → 打包 → 报告 → 交付" -ForegroundColor Gray
    Write-Host ""
    
    # 切换到仓库根目录
    Set-Location $script:RepoRoot
    
    # 激活虚拟环境
    $venvPath = Join-Path $script:RepoRoot ".venv/Scripts/activate.ps1"
    if (Test-Path $venvPath) {
        & $venvPath
        Write-Log "虚拟环境已激活" "INFO"
    } else {
        Write-Log "虚拟环境不存在，使用系统Python" "WARN"
    }
    
    # 执行流程步骤
    $steps = @(
        { Test-PreflightChecks },
        { Invoke-IncrementalKBUpdate },
        { Generate-R4Batches },
        { Package-ExperimentPlans },
        { Update-Reports },
        { Show-DeliverySummary },
        { Open-UIAndReports }
    )
    
    $stepNames = @(
        "预检",
        "增量入库",
        "生成R4",
        "打包实验",
        "刷新报告",
        "交付摘要",
        "打开界面"
    )
    
    for ($i = 0; $i -lt $steps.Count; $i++) {
        $stepResult = & $steps[$i]
        
        if (-not $stepResult -and $i -lt 4) {  # 前4步是关键步骤
            Write-Log "$($stepNames[$i])失败，中止流程" "ERROR"
            exit 1
        }
    }
    
    # 显示最终摘要
    Show-FinalSummary
    
    Write-Log "R4上线流程成功完成！" "SUCCESS"
}

# 执行主函数
try {
    Main
} catch {
    Write-Log "上线流程失败: $($_.Exception.Message)" "ERROR"
    exit 1
}
