# MAO-Wise 真实生产环境流水线脚本
# 
# 完整流程：文献库注册 → 数据分割 → LLM增强抽取 → 泄漏检查 → KB构建 → 模型训练 → API启动
#
# 使用示例：
# powershell -ExecutionPolicy Bypass -File scripts\pipeline_real.ps1 -LibraryDir "D:\文献库" -Online
# powershell -ExecutionPolicy Bypass -File scripts\pipeline_real.ps1 -LibraryDir "C:\MAO-Papers" -UseOCR -DoTrain -Online

param(
    [Parameter(Mandatory=$true)]
    [string]$LibraryDir,
    [switch]$UseOCR = $false,
    [switch]$DoTrain = $true,
    [switch]$Online = $true
)

# 设置错误处理和编码
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null

Write-Host "`n🚀 MAO-Wise 生产环境流水线" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# 设置工作目录为仓库根目录
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

# 设置PYTHONPATH环境变量
$env:PYTHONPATH = (Get-Location).Path
Write-Host "✅ 工作目录: $(Get-Location)" -ForegroundColor Green
Write-Host "✅ PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Green

# 参数显示
Write-Host "`n📋 流水线参数:" -ForegroundColor Yellow
Write-Host "   文献库目录: $LibraryDir" -ForegroundColor Gray
Write-Host "   使用OCR: $UseOCR" -ForegroundColor Gray
Write-Host "   执行训练: $DoTrain" -ForegroundColor Gray
Write-Host "   在线模式: $Online" -ForegroundColor Gray

# 步骤1: 环境配置
Write-Host "`n📋 步骤1: 环境配置与检查..." -ForegroundColor Yellow

# 检查文献库目录
if (-not (Test-Path $LibraryDir)) {
    Write-Host "❌ 文献库目录不存在: $LibraryDir" -ForegroundColor Red
    exit 1
}

$pdfCount = (Get-ChildItem $LibraryDir -Filter "*.pdf" -Recurse).Count
Write-Host "✅ 文献库目录验证通过，发现 $pdfCount 个PDF文件" -ForegroundColor Green

# 确保.env文件存在
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env" -ErrorAction SilentlyContinue
        Write-Host "✅ 创建.env文件" -ForegroundColor Green
    } else {
        New-Item -Path ".env" -ItemType File -Force | Out-Null
        Write-Host "✅ 创建空.env文件" -ForegroundColor Green
    }
}

# 写入MAOWISE_LIBRARY_DIR
$envContent = Get-Content ".env" -Raw -ErrorAction SilentlyContinue
if (-not $envContent -or $envContent -notmatch "MAOWISE_LIBRARY_DIR=") {
    Add-Content ".env" "`nMAOWISE_LIBRARY_DIR=$LibraryDir"
    Write-Host "✅ 设置MAOWISE_LIBRARY_DIR" -ForegroundColor Green
} else {
    # 更新现有值
    $envContent = $envContent -replace "MAOWISE_LIBRARY_DIR=.*", "MAOWISE_LIBRARY_DIR=$LibraryDir"
    Set-Content ".env" $envContent
    Write-Host "✅ 更新MAOWISE_LIBRARY_DIR" -ForegroundColor Green
}

# 检查OPENAI_API_KEY（在线模式需要）
if ($Online) {
    $apiKeyExists = $false
    
    # 检查环境变量
    if ($env:OPENAI_API_KEY) {
        $apiKeyExists = $true
        Write-Host "✅ OPENAI_API_KEY 在环境变量中存在" -ForegroundColor Green
    } else {
        # 检查.env文件
        $envContent = Get-Content ".env" -Raw -ErrorAction SilentlyContinue
        if ($envContent -and $envContent -match "OPENAI_API_KEY=\w+") {
            $apiKeyExists = $true
            Write-Host "✅ OPENAI_API_KEY 在.env文件中存在" -ForegroundColor Green
        }
    }
    
    if (-not $apiKeyExists) {
        Write-Host "⚠️  在线模式需要OPENAI_API_KEY，但未检测到" -ForegroundColor Yellow
        Write-Host "请运行 scripts\set_llm_keys.ps1 交互式设置" -ForegroundColor Cyan
        Write-Host "或手动在.env文件中添加 OPENAI_API_KEY=sk-..." -ForegroundColor Gray
        Write-Host "继续执行离线模式..." -ForegroundColor Gray
        $Online = $false
    }
}

# 步骤2: 文献库注册
Write-Host "`n📋 步骤2: 文献库注册..." -ForegroundColor Yellow

try {
    $startTime = Get-Date
    python scripts/register_library.py --library_dir $LibraryDir --output manifests/library_manifest.csv
    $duration = ((Get-Date) - $startTime).TotalSeconds
    
    if (Test-Path "manifests/library_manifest.csv") {
        $manifestLines = Get-Content "manifests/library_manifest.csv" | Where-Object { $_.Trim() -ne "" }
        $registeredCount = $manifestLines.Count - 1  # 减去表头
        Write-Host "✅ 文献库注册完成: $registeredCount 个文件，耗时 $([math]::Round($duration, 1))s" -ForegroundColor Green
    } else {
        Write-Host "❌ 文献库注册失败：manifest文件未生成" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ 文献库注册失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 步骤3: 数据分割
Write-Host "`n📋 步骤3: 数据分割 (70/15/15)..." -ForegroundColor Yellow

try {
    $startTime = Get-Date
    python scripts/make_split.py --manifest manifests/library_manifest.csv --train_ratio 0.7 --val_ratio 0.15 --test_ratio 0.15 --output_dir manifests
    $duration = ((Get-Date) - $startTime).TotalSeconds
    
    # 检查分割文件
    $splitFiles = @("manifests/manifest_train.csv", "manifests/manifest_val.csv", "manifests/manifest_test.csv")
    $splitCounts = @{}
    
    foreach ($file in $splitFiles) {
        if (Test-Path $file) {
            $lines = Get-Content $file | Where-Object { $_.Trim() -ne "" }
            $count = $lines.Count - 1  # 减去表头
            $splitName = (Split-Path $file -Leaf) -replace "manifest_|\.csv", ""
            $splitCounts[$splitName] = $count
        } else {
            Write-Host "❌ 数据分割失败：$file 未生成" -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host "✅ 数据分割完成，耗时 $([math]::Round($duration, 1))s:" -ForegroundColor Green
    Write-Host "   Train: $($splitCounts['train']) 文件" -ForegroundColor Gray
    Write-Host "   Val: $($splitCounts['val']) 文件" -ForegroundColor Gray
    Write-Host "   Test: $($splitCounts['test']) 文件" -ForegroundColor Gray
} catch {
    Write-Host "❌ 数据分割失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 步骤4: 三次增强抽取
Write-Host "`n📋 步骤4: LLM增强抽取 (3个数据集)..." -ForegroundColor Yellow

$splits = @("train", "val", "test")
$extractStats = @{}

foreach ($split in $splits) {
    Write-Host "`n🔄 处理 $split 数据集..." -ForegroundColor Cyan
    
    try {
        $startTime = Get-Date
        
        $ingestArgs = @(
            "--manifest", "manifests/manifest_$split.csv",
            "--out_dir", "datasets/versions/maowise_ds_v2",
            "--split_name", $split,
            "--use_llm_slotfill", "true"
        )
        
        if ($UseOCR) {
            $ingestArgs += "--use_ocr"
        }
        
        python -m maowise.dataflow.ingest @ingestArgs
        
        $duration = ((Get-Date) - $startTime).TotalSeconds
        
        # 检查输出文件
        $samplesFile = "datasets/versions/maowise_ds_v2/samples.parquet"
        if (Test-Path $samplesFile) {
            # 获取该split的样本统计
            $sampleCount = python -c "
import pandas as pd
df = pd.read_parquet('$samplesFile')
split_df = df[df['split'] == '$split'] if 'split' in df.columns else df
print(len(split_df))
"
            $extractStats[$split] = @{
                "count" = [int]$sampleCount
                "duration" = $duration
            }
            
            Write-Host "✅ $split 抽取完成: $sampleCount 样本，耗时 $([math]::Round($duration, 1))s" -ForegroundColor Green
        } else {
            Write-Host "❌ $split 抽取失败：samples.parquet未生成" -ForegroundColor Red
        }
    } catch {
        Write-Host "❌ $split 抽取失败: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# 步骤5: 泄漏检查
Write-Host "`n📋 步骤5: 数据泄漏检查..." -ForegroundColor Yellow

try {
    $startTime = Get-Date
    python scripts/check_leakage.py --samples datasets/versions/maowise_ds_v2/samples.parquet
    $duration = ((Get-Date) - $startTime).TotalSeconds
    Write-Host "✅ 泄漏检查完成，耗时 $([math]::Round($duration, 1))s" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 泄漏检查失败，但继续流程: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 步骤6: 知识库构建
Write-Host "`n📋 步骤6: 知识库索引构建..." -ForegroundColor Yellow

try {
    $startTime = Get-Date
    python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store
    $duration = ((Get-Date) - $startTime).TotalSeconds
    
    # 检查KB条目数
    if (Test-Path "datasets/data_parsed/corpus.jsonl") {
        $kbCount = (Get-Content "datasets/data_parsed/corpus.jsonl" | Where-Object { $_.Trim() -ne "" }).Count
        Write-Host "✅ 知识库构建完成: $kbCount 条目，耗时 $([math]::Round($duration, 1))s" -ForegroundColor Green
    } else {
        Write-Host "❌ 知识库构建失败：corpus.jsonl不存在" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ 知识库构建失败: $($_.Exception.Message)" -ForegroundColor Red
}

# 步骤7: 模型训练（可选）
if ($DoTrain) {
    Write-Host "`n📋 步骤7: 基线文本模型训练..." -ForegroundColor Yellow
    
    try {
        $startTime = Get-Date
        python -m maowise.models.train_fwd --samples datasets/versions/maowise_ds_v2/samples.parquet --model_name bert-base-multilingual-cased --out_dir models_ckpt/fwd_text_v2
        $duration = ((Get-Date) - $startTime).TotalSeconds
        
        if (Test-Path "models_ckpt/fwd_text_v2") {
            Write-Host "✅ 模型训练完成，耗时 $([math]::Round($duration, 1))s" -ForegroundColor Green
        } else {
            Write-Host "❌ 模型训练失败：输出目录未生成" -ForegroundColor Red
        }
    } catch {
        Write-Host "❌ 模型训练失败: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "`n📋 步骤7: 跳过模型训练 (DoTrain=false)" -ForegroundColor Yellow
}

# 步骤8: API启动
Write-Host "`n📋 步骤8: API服务启动..." -ForegroundColor Yellow

# 检查API是否已运行
$apiRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/maowise/v1/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $apiRunning = $true
        Write-Host "✅ API服务已运行" -ForegroundColor Green
    }
} catch {
    # API未运行
}

if (-not $apiRunning) {
    # 启动API服务
    Start-Process powershell -ArgumentList "-NoProfile", "-WindowStyle", "Minimized", "-Command", "Set-Location '$((Get-Location).Path)'; `$env:PYTHONPATH='$((Get-Location).Path)'; uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload" -WindowStyle Minimized
    Write-Host "✅ API服务启动中..." -ForegroundColor Green
    Start-Sleep -Seconds 6
    
    # 验证API启动
    $retries = 0
    while ($retries -lt 5) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/maowise/v1/health" -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                Write-Host "✅ API服务启动成功" -ForegroundColor Green
                break
            }
        } catch {
            $retries++
            Start-Sleep -Seconds 2
        }
    }
    
    if ($retries -eq 5) {
        Write-Host "❌ API服务启动失败" -ForegroundColor Red
    }
}

# 在线模式LLM连接测试
if ($Online -and $apiRunning -eq $false -or $retries -lt 5) {
    Write-Host "`n📋 步骤9: LLM连接测试..." -ForegroundColor Yellow
    
    try {
        python scripts/test_llm_connectivity.py
        Write-Host "✅ LLM连接测试完成" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ LLM连接测试失败，但流程继续: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 统计汇总
Write-Host "`n📊 流水线统计汇总" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# 文献库统计
Write-Host "`n📚 文献库统计:" -ForegroundColor White
Write-Host "   文献库路径: $LibraryDir" -ForegroundColor Gray
Write-Host "   PDF文件数量: $pdfCount" -ForegroundColor Gray
Write-Host "   注册文件数量: $registeredCount" -ForegroundColor Gray

# 数据分割统计
Write-Host "`n📊 数据分割统计:" -ForegroundColor White
foreach ($split in $splitCounts.Keys) {
    Write-Host "   $split 集: $($splitCounts[$split]) 文件" -ForegroundColor Gray
}

# 抽取统计
if ($extractStats.Count -gt 0) {
    Write-Host "`n🔍 抽取统计:" -ForegroundColor White
    $totalSamples = 0
    $totalDuration = 0
    
    foreach ($split in $extractStats.Keys) {
        $stats = $extractStats[$split]
        $totalSamples += $stats.count
        $totalDuration += $stats.duration
        Write-Host "   $split 样本: $($stats.count) 个，耗时 $([math]::Round($stats.duration, 1))s" -ForegroundColor Gray
    }
    
    Write-Host "   总样本数: $totalSamples" -ForegroundColor Gray
    Write-Host "   总抽取时间: $([math]::Round($totalDuration, 1))s" -ForegroundColor Gray
    
    # 计算抽取覆盖率
    try {
        $coverage = python -c "
import pandas as pd
df = pd.read_parquet('datasets/versions/maowise_ds_v2/samples.parquet')
total = len(df)
valid = len(df[(df['alpha_150_2600'].notna()) & (df['epsilon_3000_30000'].notna())])
coverage = (valid / total * 100) if total > 0 else 0
print(f'{coverage:.1f}')
"
        Write-Host "   抽取覆盖率 (有α/ε): $coverage%" -ForegroundColor Gray
    } catch {
        Write-Host "   抽取覆盖率: 无法计算" -ForegroundColor Gray
    }
}

# KB统计
Write-Host "`n📖 知识库统计:" -ForegroundColor White
if (Test-Path "datasets/data_parsed/corpus.jsonl") {
    $kbCount = (Get-Content "datasets/data_parsed/corpus.jsonl" | Where-Object { $_.Trim() -ne "" }).Count
    Write-Host "   KB条目数: $kbCount" -ForegroundColor Gray
} else {
    Write-Host "   KB条目数: 0 (未构建)" -ForegroundColor Gray
}

# 模型统计
Write-Host "`n🤖 模型状态:" -ForegroundColor White
if (Test-Path "models_ckpt/fwd_text_v2") {
    Write-Host "   基线文本模型: ✅ 已训练" -ForegroundColor Gray
} else {
    Write-Host "   基线文本模型: ❌ 未训练" -ForegroundColor Gray
}

# 服务状态
Write-Host "`n🚀 服务状态:" -ForegroundColor White
if ($apiRunning -or $retries -lt 5) {
    Write-Host "   API服务: ✅ 运行中 (http://127.0.0.1:8000)" -ForegroundColor Gray
} else {
    Write-Host "   API服务: ❌ 未运行" -ForegroundColor Gray
}

# 完成总结
Write-Host "`n🎉 生产流水线完成!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green

Write-Host "`n💡 后续建议:" -ForegroundColor Cyan
Write-Host "   1. 检查抽取覆盖率，考虑调整LLM SlotFill策略" -ForegroundColor Gray
Write-Host "   2. 运行试运行脚本验证完整功能" -ForegroundColor Gray
Write-Host "   3. 监控API服务日志，确保在线功能正常" -ForegroundColor Gray
Write-Host "   4. 定期重新训练模型以提升性能" -ForegroundColor Gray

Write-Host "`n🔗 快速链接:" -ForegroundColor Cyan
Write-Host "   API健康: http://127.0.0.1:8000/api/maowise/v1/health" -ForegroundColor Gray
Write-Host "   模型状态: http://127.0.0.1:8000/api/maowise/v1/admin/model_status" -ForegroundColor Gray
Write-Host "   试运行: powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1 -Online" -ForegroundColor Gray

Write-Host "`n🏁 流水线执行完成！" -ForegroundColor Green
