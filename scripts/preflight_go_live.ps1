# MAO-Wise Go-Live 预检脚本
# 生成自检报告，逐项检查系统准备状态

param(
    [switch]$SkipServices,
    [switch]$QuickMode,
    [string]$OutputDir = "reports"
)

# 统一编码设置
chcp 65001 > $null
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# 全局变量
$script:CheckResults = @()
$script:OverallStatus = "PASS"
$script:RepoRoot = Split-Path -Parent $PSScriptRoot

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN"  { Write-Host $logEntry -ForegroundColor Yellow }
        "INFO"  { Write-Host $logEntry -ForegroundColor Green }
        default { Write-Host $logEntry }
    }
}

function Add-CheckResult {
    param(
        [string]$Category,
        [string]$Item,
        [string]$Status,  # PASS/WARN/FAIL
        [string]$Details,
        [string]$Suggestion = ""
    )
    
    $script:CheckResults += @{
        Category = $Category
        Item = $Item
        Status = $Status
        Details = $Details
        Suggestion = $Suggestion
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }
    
    # 更新整体状态
    if ($Status -eq "FAIL" -and $script:OverallStatus -ne "FAIL") {
        $script:OverallStatus = "FAIL"
    } elseif ($Status -eq "WARN" -and $script:OverallStatus -eq "PASS") {
        $script:OverallStatus = "WARN"
    }
    
    Write-Log "$Category - $Item: $Status - $Details" $Status
}

function Test-EnvironmentFiles {
    Write-Log "检查环境配置文件..." "INFO"
    
    # 检查.env文件
    $envPath = Join-Path $script:RepoRoot ".env"
    if (Test-Path $envPath) {
        $envContent = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
        
        # 检查必需的环境变量
        $requiredVars = @("OPENAI_API_KEY", "LLM_PROVIDER", "MAOWISE_LIBRARY_DIR")
        $missingVars = @()
        
        foreach ($var in $requiredVars) {
            $found = $false
            if ($envContent -match "^$var\s*=") {
                $found = $true
            }
            if (-not $found) {
                $missingVars += $var
            }
        }
        
        if ($missingVars.Count -eq 0) {
            Add-CheckResult "环境配置" ".env必需变量" "PASS" "所有必需环境变量已配置"
        } else {
            Add-CheckResult "环境配置" ".env必需变量" "FAIL" "缺少变量: $($missingVars -join ', ')" "运行 scripts/set_llm_keys.ps1 设置缺失变量"
        }
    } else {
        Add-CheckResult "环境配置" ".env文件" "FAIL" "未找到.env文件" "运行 scripts/set_llm_keys.ps1 创建环境配置"
    }
    
    # 检查.gitignore
    $gitignorePath = Join-Path $script:RepoRoot ".gitignore"
    if (Test-Path $gitignorePath) {
        $gitignoreContent = Get-Content $gitignorePath -Raw -ErrorAction SilentlyContinue
        if ($gitignoreContent -match "\.env") {
            Add-CheckResult "环境配置" ".gitignore覆盖" "PASS" ".env文件已在.gitignore中"
        } else {
            Add-CheckResult "环境配置" ".gitignore覆盖" "WARN" ".env未在.gitignore中" "将.env添加到.gitignore以保护敏感信息"
        }
    } else {
        Add-CheckResult "环境配置" ".gitignore文件" "WARN" "未找到.gitignore文件" "创建.gitignore并添加.env"
    }
}

function Test-LLMConnectivity {
    Write-Log "检查LLM连通性..." "INFO"
    
    try {
        $testScript = Join-Path $script:RepoRoot "scripts/test_llm_connectivity.py"
        if (Test-Path $testScript) {
            $result = & python -X utf8 $testScript 2>&1
            $exitCode = $LASTEXITCODE
            
            # 脱敏处理
            $sanitizedResult = $result -replace "sk-[a-zA-Z0-9-_]+", "sk-***MASKED***"
            
            if ($exitCode -eq 0) {
                Add-CheckResult "LLM连通性" "API连接测试" "PASS" "LLM连接正常"
            } else {
                $suggestion = "检查API密钥和网络连接"
                if ($sanitizedResult -match "ImportError|ModuleNotFoundError") {
                    $suggestion += "; 运行 pip install openai tiktoken"
                }
                Add-CheckResult "LLM连通性" "API连接测试" "WARN" "连接失败但可降级运行" $suggestion
            }
        } else {
            Add-CheckResult "LLM连通性" "测试脚本" "FAIL" "test_llm_connectivity.py不存在" "检查scripts目录完整性"
        }
    } catch {
        Add-CheckResult "LLM连通性" "执行测试" "WARN" "测试执行异常: $($_.Exception.Message)" "检查Python环境和依赖"
    }
}

function Test-DataSplitAndLeakage {
    Write-Log "检查数据分割与泄漏..." "INFO"
    
    # 检查manifests目录
    $manifestsPath = Join-Path $script:RepoRoot "manifests"
    if (Test-Path $manifestsPath) {
        $manifestFiles = Get-ChildItem $manifestsPath -Filter "*.csv" | Measure-Object
        Add-CheckResult "数据质量" "manifests目录" "PASS" "找到 $($manifestFiles.Count) 个manifest文件"
    } else {
        Add-CheckResult "数据质量" "manifests目录" "WARN" "manifests目录不存在" "检查数据准备流程"
    }
    
    # 检查泄漏检测
    $leakageScript = Join-Path $script:RepoRoot "scripts/check_leakage.py"
    if (Test-Path $leakageScript) {
        try {
            & python -X utf8 $leakageScript 2>&1 | Out-Null
            $exitCode = $LASTEXITCODE
            if ($exitCode -eq 0) {
                Add-CheckResult "数据质量" "泄漏检测" "PASS" "无数据泄漏风险"
            } else {
                Add-CheckResult "数据质量" "泄漏检测" "WARN" "检测到潜在泄漏风险" "审查数据分割策略"
            }
        } catch {
            Add-CheckResult "数据质量" "泄漏检测" "WARN" "无法执行泄漏检测" "检查check_leakage.py脚本"
        }
    } else {
        Add-CheckResult "数据质量" "泄漏检测脚本" "WARN" "check_leakage.py不存在" "实现数据泄漏检测"
    }
}

function Test-SamplesAndSplit {
    Write-Log "检查样本数据..." "INFO"
    
    $samplesPath = Join-Path $script:RepoRoot "datasets/versions/maowise_ds_v1/samples.parquet"
    if (Test-Path $samplesPath) {
        try {
            $pythonCode = @"
import pandas as pd
import sys
sys.path.append('.')

try:
    df = pd.read_parquet('$($samplesPath.Replace('\', '/'))')
    print(f'TOTAL:{len(df)}')
    
    if 'split' in df.columns:
        counts = df['split'].value_counts()
        for split, count in counts.items():
            print(f'{split.upper()}:{count}')
    else:
        print('NO_SPLIT_COLUMN')
        
except Exception as e:
    print(f'ERROR:{str(e)}')
"@
            
            $result = python -X utf8 -c $pythonCode 2>&1
            
            if ($result -match "TOTAL:(\d+)") {
                $totalSamples = $matches[1]
                $splitInfo = ($result | Where-Object { $_ -match "^(TRAIN|VAL|TEST):" }) -join ", "
                
                if ($splitInfo) {
                    Add-CheckResult "数据集" "样本分割" "PASS" "总样本: $totalSamples, 分割: $splitInfo"
                } else {
                    Add-CheckResult "数据集" "样本分割" "WARN" "总样本: $totalSamples, 未发现split列" "添加数据分割信息"
                }
            } else {
                Add-CheckResult "数据集" "样本文件" "FAIL" "无法读取samples.parquet" "检查数据文件完整性"
            }
        } catch {
            Add-CheckResult "数据集" "样本分析" "FAIL" "样本分析失败: $($_.Exception.Message)" "检查Python环境和pandas依赖"
        }
    } else {
        Add-CheckResult "数据集" "样本文件" "FAIL" "samples.parquet不存在" "运行数据准备流程生成样本文件"
    }
}

function Test-KnowledgeBase {
    Write-Log "检查知识库..." "INFO"
    
    # 检查corpus.jsonl
    $corpusPath = Join-Path $script:RepoRoot "datasets/data_parsed/corpus.jsonl"
    if (Test-Path $corpusPath) {
        try {
            $lineCount = (Get-Content $corpusPath | Measure-Object -Line).Lines
            Add-CheckResult "知识库" "语料库" "PASS" "corpus.jsonl包含 $lineCount 条记录"
        } catch {
            Add-CheckResult "知识库" "语料库" "WARN" "无法统计corpus.jsonl行数" "检查文件权限"
        }
    } else {
        Add-CheckResult "知识库" "语料库" "FAIL" "corpus.jsonl不存在" "运行知识库构建流程"
    }
    
    # 检查index_store
    $indexPath = Join-Path $script:RepoRoot "datasets/index_store"
    if (Test-Path $indexPath) {
        $metaPath = Join-Path $indexPath "meta.json"
        if (Test-Path $metaPath) {
            try {
                $metaContent = Get-Content $metaPath -Raw | ConvertFrom-Json
                $backend = $metaContent.backend
                $totalVectors = $metaContent.total_vectors
                Add-CheckResult "知识库" "向量索引" "PASS" "后端: $backend, 向量数: $totalVectors"
            } catch {
                Add-CheckResult "知识库" "向量索引" "WARN" "meta.json解析失败" "检查索引元信息"
            }
        } else {
            Add-CheckResult "知识库" "索引元信息" "WARN" "meta.json不存在" "重建向量索引"
        }
    } else {
        Add-CheckResult "知识库" "索引目录" "FAIL" "index_store目录不存在" "运行知识库索引构建"
    }
    
    # 检查是否有未入库的lab_feedback
    $experimentsPath = Join-Path $script:RepoRoot "datasets/experiments/experiments.parquet"
    if (Test-Path $experimentsPath) {
        try {
            $pythonCode = @"
import pandas as pd
import sys, os
sys.path.append('.')

try:
    # 检查experiments中的lab_feedback
    df_exp = pd.read_parquet('$($experimentsPath.Replace('\', '/'))')
    lab_feedback_count = 0
    if 'source' in df_exp.columns:
        lab_feedback_count = df_exp['source'].str.contains('lab_feedback', na=False).sum()
    
    # 检查corpus中的lab_feedback
    corpus_path = '$($corpusPath.Replace('\', '/'))'
    corpus_lab_count = 0
    if os.path.exists(corpus_path):
        with open(corpus_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'lab_feedback' in line or 'LAB-FEEDBACK' in line:
                    corpus_lab_count += 1
    
    print(f'EXP_LAB:{lab_feedback_count}')
    print(f'CORPUS_LAB:{corpus_lab_count}')
    
except Exception as e:
    print(f'ERROR:{str(e)}')
"@
            
            $result = python -X utf8 -c $pythonCode 2>&1
            
            if ($result -match "EXP_LAB:(\d+)" -and $result -match "CORPUS_LAB:(\d+)") {
                $expLabCount = [int]$matches[1]
                $corpusLabCount = [int]$matches[2]
                
                if ($expLabCount -gt $corpusLabCount) {
                    Add-CheckResult "知识库" "实验反馈入库" "WARN" "发现 $($expLabCount - $corpusLabCount) 条未入库的lab_feedback" "运行 scripts/append_feedback_to_kb.py 进行增量入库"
                } else {
                    Add-CheckResult "知识库" "实验反馈入库" "PASS" "所有lab_feedback已入库"
                }
            }
        } catch {
            Add-CheckResult "知识库" "反馈检查" "WARN" "无法检查lab_feedback状态" "手动检查实验反馈数据"
        }
    }
}

function Test-ModelsAndCorrectors {
    Write-Log "检查模型与校正器..." "INFO"
    
    # 检查主模型
    $modelPaths = @(
        "models_ckpt/fwd_v2/model.joblib",
        "models_ckpt/fwd_v1/model.joblib",
        "tabular_model/ensemble/model.joblib"
    )
    
    $foundModel = $false
    foreach ($modelPath in $modelPaths) {
        $fullPath = Join-Path $script:RepoRoot $modelPath
        if (Test-Path $fullPath) {
            $size = (Get-Item $fullPath).Length / 1MB
            Add-CheckResult "模型文件" "主模型" "PASS" "找到模型: $modelPath (${size:F1} MB)"
            $foundModel = $true
            break
        }
    }
    
    if (-not $foundModel) {
        Add-CheckResult "模型文件" "主模型" "FAIL" "未找到主模型文件" "运行模型训练流程"
    }
    
    # 检查GP校正器
    $gpPattern = Join-Path $script:RepoRoot "models_ckpt/fwd_v2/gp_epsilon_*.pkl"
    $gpFiles = Get-ChildItem $gpPattern -ErrorAction SilentlyContinue
    if ($gpFiles) {
        $gpCount = $gpFiles.Count
        $totalSize = ($gpFiles | Measure-Object -Property Length -Sum).Sum / 1MB
        Add-CheckResult "模型文件" "GP校正器" "PASS" "找到 $gpCount 个GP校正器 (${totalSize:F1} MB)"
    } else {
        Add-CheckResult "模型文件" "GP校正器" "WARN" "未找到GP校正器" "运行校正器训练"
    }
    
    # 检查等温校准器
    $calibPattern = Join-Path $script:RepoRoot "models_ckpt/fwd_v2/calib_epsilon_*.pkl"
    $calibFiles = Get-ChildItem $calibPattern -ErrorAction SilentlyContinue
    if ($calibFiles) {
        $calibCount = $calibFiles.Count
        Add-CheckResult "模型文件" "等温校准器" "PASS" "找到 $calibCount 个等温校准器"
    } else {
        Add-CheckResult "模型文件" "等温校准器" "WARN" "未找到等温校准器" "运行校准器训练"
    }
}

function Test-ConfigurationFiles {
    Write-Log "检查配置文件..." "INFO"
    
    # 检查config.yaml
    $configPath = Join-Path $script:RepoRoot "maowise/config/config.yaml"
    if (Test-Path $configPath) {
        try {
            $pythonCode = @"
import yaml
import sys
sys.path.append('.')

try:
    with open('$($configPath.Replace('\', '/'))', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 检查关键字段
    checks = []
    if 'fwd_model' in config:
        checks.append('fwd_model')
    if 'optimize' in config:
        checks.append('optimize')
    if 'kb' in config:
        checks.append('kb')
    
    print(f'CONFIG_SECTIONS:{",".join(checks)}')
    
except Exception as e:
    print(f'ERROR:{str(e)}')
"@
            
            $result = python -X utf8 -c $pythonCode 2>&1
            
            if ($result -match "CONFIG_SECTIONS:(.+)") {
                $sections = $matches[1]
                Add-CheckResult "配置文件" "config.yaml" "PASS" "配置完整，包含: $sections"
            } else {
                Add-CheckResult "配置文件" "config.yaml" "FAIL" "配置文件解析失败" "检查YAML语法"
            }
        } catch {
            Add-CheckResult "配置文件" "config.yaml解析" "FAIL" "无法解析配置文件" "检查Python环境和PyYAML依赖"
        }
    } else {
        Add-CheckResult "配置文件" "config.yaml" "FAIL" "配置文件不存在" "创建基础配置文件"
    }
    
    # 检查constraints.yaml
    $constraintsPath = Join-Path $script:RepoRoot "datasets/constraints/lab_constraints.yaml"
    if (Test-Path $constraintsPath) {
        try {
            $pythonCode = @"
import yaml

try:
    with open('$($constraintsPath.Replace('\', '/'))', 'r', encoding='utf-8') as f:
        constraints = yaml.safe_load(f)
    
    required_fields = ['targets', 'preferences', 'penalties', 'search_space_overrides']
    found_fields = [field for field in required_fields if field in constraints]
    
    print(f'CONSTRAINT_FIELDS:{",".join(found_fields)}')
    
except Exception as e:
    print(f'ERROR:{str(e)}')
"@
            
            $result = python -X utf8 -c $pythonCode 2>&1
            
            if ($result -match "CONSTRAINT_FIELDS:(.+)") {
                $fields = $matches[1]
                Add-CheckResult "配置文件" "约束配置" "PASS" "约束配置完整，包含: $fields"
            } else {
                Add-CheckResult "配置文件" "约束配置" "WARN" "约束配置解析失败" "检查约束文件格式"
            }
        } catch {
            Add-CheckResult "配置文件" "约束解析" "WARN" "无法解析约束文件" "检查约束文件语法"
        }
    } else {
        Add-CheckResult "配置文件" "约束配置" "WARN" "lab_constraints.yaml不存在" "创建实验约束配置"
    }
}

function Test-ServicesAndAPI {
    Write-Log "检查API和UI服务..." "INFO"
    
    if ($SkipServices) {
        Add-CheckResult "服务状态" "API检查" "SKIP" "跳过服务检查（-SkipServices参数）"
        return
    }
    
    # 检查服务是否已运行
    $apiRunning = $false
    $uiRunning = $false
    
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $apiRunning = $true
        }
    } catch {
        # API未运行
    }
    
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8501" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $uiRunning = $true
        }
    } catch {
        # UI未运行
    }
    
    if (-not $apiRunning) {
        # 尝试启动服务
        Write-Log "尝试启动API服务..." "INFO"
        
        $startScript = Join-Path $script:RepoRoot "scripts/start_services.ps1"
        if (Test-Path $startScript) {
            try {
                # 后台启动服务
                Start-Process -FilePath "powershell.exe" -ArgumentList "-File", $startScript -WindowStyle Hidden
                Start-Sleep -Seconds 10
                
                # 重新检查
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Add-CheckResult "服务状态" "API服务" "PASS" "API服务已启动"
                    $apiRunning = $true
                } else {
                    Add-CheckResult "服务状态" "API服务" "WARN" "API服务启动失败" "手动运行 scripts/start_services.ps1"
                }
            } catch {
                Add-CheckResult "服务状态" "API服务" "WARN" "无法启动API服务" "检查端口占用和依赖"
            }
        } else {
            Add-CheckResult "服务状态" "启动脚本" "WARN" "start_services.ps1不存在" "创建服务启动脚本"
        }
    } else {
        Add-CheckResult "服务状态" "API服务" "PASS" "API服务正在运行"
    }
    
    # 检查API端点
    if ($apiRunning) {
        try {
            $modelStatus = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/maowise/v1/admin/model_status" -TimeoutSec 10
            if ($modelStatus) {
                Add-CheckResult "服务状态" "模型状态API" "PASS" "模型状态API响应正常"
            }
        } catch {
            Add-CheckResult "服务状态" "模型状态API" "WARN" "模型状态API异常" "检查API服务日志"
        }
        
        # 检查专家问答API
        try {
            $expertQuestions = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/maowise/v1/expert/mandatory" -TimeoutSec 10
            if ($expertQuestions -and $expertQuestions.Count -ge 5) {
                Add-CheckResult "服务状态" "专家问答API" "PASS" "专家问答返回 $($expertQuestions.Count) 个必答问题"
            } else {
                Add-CheckResult "服务状态" "专家问答API" "WARN" "专家问答返回问题数不足" "检查专家问答配置"
            }
        } catch {
            Add-CheckResult "服务状态" "专家问答API" "WARN" "专家问答API异常" "检查专家问答服务"
        }
    }
}

function Test-Reports {
    Write-Log "检查报告文件..." "INFO"
    
    # 检查评估报告
    $evalPattern = Join-Path $script:RepoRoot "reports/fwd_eval_*.json"
    $evalFiles = Get-ChildItem $evalPattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    if ($evalFiles) {
        $latestEval = $evalFiles[0]
        Add-CheckResult "报告文件" "评估报告" "PASS" "找到评估报告: $($latestEval.Name)"
    } else {
        Add-CheckResult "报告文件" "评估报告" "WARN" "未找到评估报告" "运行模型评估生成报告"
    }
    
    # 检查HTML报告
    $htmlReport = Join-Path $script:RepoRoot "reports/real_run_report.html"
    if (Test-Path $htmlReport) {
        $reportAge = (Get-Date) - (Get-Item $htmlReport).LastWriteTime
        if ($reportAge.TotalDays -lt 7) {
            Add-CheckResult "报告文件" "HTML报告" "PASS" "HTML报告存在且较新 ($($reportAge.TotalDays.ToString('F1'))天前)"
        } else {
            Add-CheckResult "报告文件" "HTML报告" "WARN" "HTML报告存在但过旧 ($($reportAge.TotalDays.ToString('F0'))天前)" "运行 scripts/make_html_report.py 更新报告"
        }
    } else {
        Add-CheckResult "报告文件" "HTML报告" "FAIL" "real_run_report.html不存在" "运行 scripts/make_html_report.py 生成报告"
    }
}

function Generate-Report {
    Write-Log "生成Go-Live检查报告..." "INFO"
    
    # 确保输出目录存在
    $outputPath = Join-Path $script:RepoRoot $OutputDir
    if (-not (Test-Path $outputPath)) {
        New-Item -Path $outputPath -ItemType Directory -Force | Out-Null
    }
    
    # 调用Python脚本生成详细报告
    $pythonScript = Join-Path $script:RepoRoot "scripts/preflight_go_live.py"
    if (Test-Path $pythonScript) {
        try {
            # 将检查结果转换为JSON
            $resultsJson = $script:CheckResults | ConvertTo-Json -Depth 3
            $tempFile = Join-Path $env:TEMP "preflight_results.json"
            $resultsJson | Out-File -FilePath $tempFile -Encoding UTF8
            
            # 调用Python脚本
            & python -X utf8 $pythonScript --results $tempFile --output $outputPath
            
            # 清理临时文件
            Remove-Item $tempFile -ErrorAction SilentlyContinue
            
            Write-Log "详细报告已生成到: $outputPath" "INFO"
        } catch {
            Write-Log "Python报告生成失败: $($_.Exception.Message)" "WARN"
        }
    }
    
    # 生成简单的文本报告
    $txtReport = Join-Path $outputPath "go_live_checklist.txt"
    $reportContent = @()
    
    $reportContent += "=" * 80
    $reportContent += "MAO-Wise Go-Live 预检报告"
    $reportContent += "生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $reportContent += "整体状态: $script:OverallStatus"
    $reportContent += "=" * 80
    $reportContent += ""
    
    # 按类别分组显示结果
    $categories = $script:CheckResults | Group-Object Category
    foreach ($category in $categories) {
        $reportContent += "[$($category.Name)]"
        foreach ($result in $category.Group) {
            $statusIcon = switch ($result.Status) {
                "PASS" { "✓" }
                "WARN" { "⚠" }
                "FAIL" { "✗" }
                "SKIP" { "○" }
                default { "?" }
            }
            $reportContent += "  $statusIcon $($result.Item): $($result.Status) - $($result.Details)"
            if ($result.Suggestion) {
                $reportContent += "    建议: $($result.Suggestion)"
            }
        }
        $reportContent += ""
    }
    
    # 添加总结和建议
    $reportContent += "=" * 80
    $reportContent += "总结与建议"
    $reportContent += "=" * 80
    
    $passCount = ($script:CheckResults | Where-Object { $_.Status -eq "PASS" }).Count
    $warnCount = ($script:CheckResults | Where-Object { $_.Status -eq "WARN" }).Count
    $failCount = ($script:CheckResults | Where-Object { $_.Status -eq "FAIL" }).Count
    $skipCount = ($script:CheckResults | Where-Object { $_.Status -eq "SKIP" }).Count
    $totalCount = $script:CheckResults.Count
    
    $reportContent += "检查项统计:"
    $reportContent += "  通过 (PASS): $passCount/$totalCount"
    $reportContent += "  警告 (WARN): $warnCount/$totalCount"
    $reportContent += "  失败 (FAIL): $failCount/$totalCount"
    $reportContent += "  跳过 (SKIP): $skipCount/$totalCount"
    $reportContent += ""
    
    # 下一步建议
    $reportContent += "下一步建议:"
    if ($script:OverallStatus -eq "PASS") {
        $reportContent += "  ✓ 系统准备就绪，可以上线运行"
        $reportContent += "  ✓ 建议定期运行此预检脚本确保系统健康"
    } elseif ($script:OverallStatus -eq "WARN") {
        $reportContent += "  ⚠ 系统基本可用，但存在需要关注的问题"
        $reportContent += "  ⚠ 建议修复警告项后再上线"
        $reportContent += "  ⚠ 可在受控环境下进行测试"
    } else {
        $reportContent += "  ✗ 系统存在严重问题，不建议上线"
        $reportContent += "  ✗ 必须修复所有FAIL项"
        $reportContent += "  ✗ 建议重新运行完整的系统部署流程"
    }
    
    $reportContent += ""
    $reportContent += "如需帮助，请查阅文档或联系技术支持。"
    $reportContent += "预检脚本: scripts/preflight_go_live.ps1"
    $reportContent += "=" * 80
    
    # 写入文件
    $reportContent | Out-File -FilePath $txtReport -Encoding UTF8
    
    Write-Log "文本报告已保存到: $txtReport" "INFO"
}

function Main {
    Write-Log "开始MAO-Wise Go-Live预检..." "INFO"
    
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
    
    # 执行各项检查
    if (-not $QuickMode) {
        Test-EnvironmentFiles
        Test-LLMConnectivity
        Test-DataSplitAndLeakage
    }
    
    Test-SamplesAndSplit
    Test-KnowledgeBase
    Test-ModelsAndCorrectors
    Test-ConfigurationFiles
    
    if (-not $QuickMode) {
        Test-ServicesAndAPI
        Test-Reports
    }
    
    # 生成报告
    Generate-Report
    
    Write-Log "Go-Live预检完成，整体状态: $script:OverallStatus" $script:OverallStatus
    
    # 显示最后40行
    $txtReport = Join-Path $script:RepoRoot "$OutputDir/go_live_checklist.txt"
    if (Test-Path $txtReport) {
        Write-Log "报告最后40行:" "INFO"
        Get-Content $txtReport | Select-Object -Last 40 | Write-Host
    }
}

# 执行主函数
try {
    Main
} catch {
    Write-Log "预检执行失败: $($_.Exception.Message)" "ERROR"
    exit 1
}
