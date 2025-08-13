# MAO-Wise 一键试运行脚本
# 
# 完整流水线：环境准备 → KB构建 → 批量方案生成 → 文献对照 → 服务启动 → API测试 → 评估更新 → 报告生成
#
# 使用示例：
# powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1
# powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1 -Online
# powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1 -LibraryDir "D:\桌面\本地PDF文献知识库" -Online

param(
    [string]$LibraryDir = $env:MAOWISE_LIBRARY_DIR,
    [switch]$Online = $false   # 有 OPENAI_API_KEY 则加上 -Online
)

# 设置错误处理和编码
$ErrorActionPreference = "Stop"
chcp 65001 > $null

Write-Host "`n🧪 MAO-Wise 一键试运行" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# 设置工作目录为仓库根目录
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

# 设置PYTHONPATH环境变量
$env:PYTHONPATH = (Get-Location).Path
Write-Host "✅ 工作目录: $(Get-Location)" -ForegroundColor Green
Write-Host "✅ PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Green

# 环境与路径准备
Write-Host "`n📋 步骤1: 环境与路径准备..." -ForegroundColor Yellow

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

# 设置库目录
if ($LibraryDir) {
    $envContent = Get-Content ".env" -Raw -ErrorAction SilentlyContinue
    if (-not $envContent -or $envContent -notmatch "MAOWISE_LIBRARY_DIR=") {
        Add-Content ".env" "`nMAOWISE_LIBRARY_DIR=$LibraryDir"
        Write-Host "✅ 设置文献库目录: $LibraryDir" -ForegroundColor Green
    }
}

# 检查运行模式
$mode = if ($Online.IsPresent) { "online" } else { "offline" }
Write-Host "✅ 运行模式: $mode" -ForegroundColor Green

# 备最小语料 & 建库
Write-Host "`n📚 步骤2: 构建/校验知识库..." -ForegroundColor Yellow

try {
    # 确保有最小数据
    python scripts/e2e_data_prep.py
    Write-Host "✅ 数据准备完成" -ForegroundColor Green
    
    # 构建KB（若不存在）
    if (-not (Test-Path "datasets/index_store")) {
        python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store
        Write-Host "✅ 知识库构建完成" -ForegroundColor Green
    } else {
        Write-Host "✅ 知识库已存在，跳过构建" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ 知识库准备失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 生成批量方案
Write-Host "`n🔬 步骤3: 批量方案生成..." -ForegroundColor Yellow

try {
    # 生成silicate方案（6条）
    python scripts/generate_batch_plans.py --system silicate --n 6 --target-alpha 0.20 --target-epsilon 0.80 --notes "trial_run"
    Write-Host "✅ Silicate方案生成完成" -ForegroundColor Green
    
    # 生成zirconate方案（6条）
    python scripts/generate_batch_plans.py --system zirconate --n 6 --target-alpha 0.20 --target-epsilon 0.80 --notes "trial_run"
    Write-Host "✅ Zirconate方案生成完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 批量方案生成失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 文献对照验证
Write-Host "`n📖 步骤4: 文献对照验证..." -ForegroundColor Yellow

try {
    # 获取最新批次目录
    $latestBatch = Get-ChildItem "tasks" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestBatch) {
        $batchPath = $latestBatch.FullName
        Write-Host "✅ 最新批次: $($latestBatch.Name)" -ForegroundColor Green
        
        # 执行验证
        python scripts/validate_recommendations.py --plans "$batchPath\plans.csv" --kb datasets/index_store --topk 3
        Write-Host "✅ 文献对照验证完成" -ForegroundColor Green
    } else {
        Write-Host "⚠️ 未找到批次目录，跳过验证" -ForegroundColor Yellow
        $batchPath = ""
    }
} catch {
    Write-Host "❌ 文献对照验证失败: $($_.Exception.Message)" -ForegroundColor Red
    # 不终止，继续执行
    $batchPath = ""
}

# 启动服务
Write-Host "`n🚀 步骤5: 启动API与UI服务..." -ForegroundColor Yellow

try {
    # 检查端口是否已被占用
    $apiRunning = $false
    $uiRunning = $false
    
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
            exit 1
        }
    }
    
    # 检查UI是否运行
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8501" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $uiRunning = $true
            Write-Host "✅ UI服务已运行" -ForegroundColor Green
        }
    } catch {
        # UI未运行
    }
    
    if (-not $uiRunning) {
        # 启动UI服务
        Start-Process powershell -ArgumentList "-NoProfile", "-WindowStyle", "Minimized", "-Command", "Set-Location '$((Get-Location).Path)'; `$env:PYTHONPATH='$((Get-Location).Path)'; streamlit run apps/ui/app.py --server.address 127.0.0.1 --server.port 8501" -WindowStyle Minimized
        Write-Host "✅ UI服务启动中..." -ForegroundColor Green
        Start-Sleep -Seconds 8
        
        # 验证UI启动
        $retries = 0
        while ($retries -lt 5) {
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:8501" -TimeoutSec 3
                if ($response.StatusCode -eq 200) {
                    Write-Host "✅ UI服务启动成功" -ForegroundColor Green
                    break
                }
            } catch {
                $retries++
                Start-Sleep -Seconds 2
            }
        }
        
        if ($retries -eq 5) {
            Write-Host "⚠️ UI服务启动可能失败，继续执行" -ForegroundColor Yellow
        }
    }
    
} catch {
    Write-Host "❌ 服务启动失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 进入试运行主逻辑
Write-Host "`n🔍 步骤6: 执行API测试与验收..." -ForegroundColor Yellow

try {
    # 调用Python脚本执行详细测试
    python scripts/trial_run.py --mode $mode --batch "$batchPath"
    Write-Host "✅ 试运行主逻辑完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 试运行主逻辑失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 完成总结
Write-Host "`n🎉 试运行完成!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green

Write-Host "`n📁 生成的文件:" -ForegroundColor Cyan
Write-Host "   - 批量方案: tasks/batch_*/plans.csv" -ForegroundColor Gray
Write-Host "   - 验证报告: tasks/batch_*/validation_report.xlsx" -ForegroundColor Gray
Write-Host "   - UI截图: reports/ui_*.png" -ForegroundColor Gray
Write-Host "   - 试运行报告: reports/trial_run_report.md/html" -ForegroundColor Gray

Write-Host "`n🌐 服务地址:" -ForegroundColor Cyan
Write-Host "   - API: http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host "   - UI: http://127.0.0.1:8501" -ForegroundColor Gray

Write-Host "`n💡 后续操作:" -ForegroundColor Cyan
Write-Host "   1. 查看试运行报告了解详细结果" -ForegroundColor Gray
Write-Host "   2. 访问UI界面进行交互式操作" -ForegroundColor Gray
Write-Host "   3. 如需停止服务，运行: scripts\stop_services.ps1" -ForegroundColor Gray

# 自动打开报告目录
try {
    if (Test-Path "reports/trial_run_report.html") {
        Write-Host "`n📊 正在打开报告目录..." -ForegroundColor Yellow
        Start-Process "explorer.exe" -ArgumentList "reports"
    }
} catch {
    # 忽略错误
}

Write-Host "`n试运行流程完成！" -ForegroundColor Green
