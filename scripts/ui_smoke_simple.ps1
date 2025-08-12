# MAO-Wise UI 手工验证清单 - 简化版自动截图脚本

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "🚀 启动MAO-Wise UI验证与截图..." -ForegroundColor Green

# 检查Python环境
Write-Host "`n🔍 检查Python环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python已安装: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Python未安装" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ 无法检测Python版本" -ForegroundColor Red
    exit 1
}

# 检查必要的包
Write-Host "`n📦 检查必要的Python包..." -ForegroundColor Yellow
$packages = @("selenium", "requests", "streamlit")
foreach ($package in $packages) {
    try {
        $result = python -c "import $package; print('OK')" 2>&1
        if ($LASTEXITCODE -eq 0 -and $result -eq "OK") {
            Write-Host "✅ $package 已安装" -ForegroundColor Green
        } else {
            Write-Host "⚠️ 正在安装 $package..." -ForegroundColor Yellow
            pip install $package | Out-Null
        }
    } catch {
        Write-Host "⚠️ 正在安装 $package..." -ForegroundColor Yellow
        pip install $package | Out-Null
    }
}

# 确保reports目录存在
Write-Host "`n📁 准备reports目录..." -ForegroundColor Yellow
if (-not (Test-Path "reports")) {
    New-Item -ItemType Directory -Path "reports" -Force | Out-Null
}
Write-Host "✅ reports目录已准备" -ForegroundColor Green

# 启动Streamlit服务
Write-Host "`n🚀 启动Streamlit服务..." -ForegroundColor Green
$streamlitJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    streamlit run apps/ui/app.py --server.port 8501 --server.address 127.0.0.1
}

Write-Host "✅ Streamlit服务启动中... (Job ID: $($streamlitJob.Id))" -ForegroundColor Green
Write-Host "⏳ 等待服务启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# 检查服务状态
Write-Host "`n🔍 检查服务状态..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8501" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Streamlit服务正常运行" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Streamlit服务响应异常" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Streamlit服务检查失败，继续尝试截图" -ForegroundColor Yellow
}

# 打开浏览器
Write-Host "`n🌐 打开浏览器..." -ForegroundColor Yellow
try {
    Start-Process "http://127.0.0.1:8501"
    Write-Host "✅ 浏览器已打开" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 无法自动打开浏览器" -ForegroundColor Yellow
}

# 等待用户确认
Write-Host "`n⏳ 等待服务完全启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 执行自动截图
Write-Host "`n📸 开始自动截图..." -ForegroundColor Green
try {
    python scripts/ui_snapshots.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 自动截图完成" -ForegroundColor Green
    } else {
        Write-Host "⚠️ 截图过程有警告" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ 自动截图失败" -ForegroundColor Red
}

# 检查生成的截图
Write-Host "`n📊 检查生成的截图..." -ForegroundColor Yellow
$screenshots = Get-ChildItem -Path "reports" -Filter "ui_*.png" -ErrorAction SilentlyContinue

if ($screenshots) {
    Write-Host "✅ 发现截图文件:" -ForegroundColor Green
    foreach ($screenshot in $screenshots) {
        $sizeKB = [math]::Round($screenshot.Length / 1024, 1)
        Write-Host "  📸 $($screenshot.Name) ($sizeKB KB)" -ForegroundColor Cyan
    }
} else {
    Write-Host "⚠️ 未找到截图文件" -ForegroundColor Yellow
}

# 生成简单报告
Write-Host "`n📝 生成验收报告..." -ForegroundColor Yellow
$reportContent = @"
# MAO-Wise UI 验证报告

生成时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

## 截图文件状态
- 预测页面: $(if (Test-Path "reports/ui_predict.png") { "✅ 已生成" } else { "❌ 未生成" })
- 优化页面: $(if (Test-Path "reports/ui_recommend.png") { "✅ 已生成" } else { "❌ 未生成" })
- 专家页面: $(if (Test-Path "reports/ui_expert.png") { "✅ 已生成" } else { "❌ 未生成" })

## 文件列表
$(if ($screenshots) {
    $screenshots | ForEach-Object {
        $sizeKB = [math]::Round($_.Length / 1024, 1)
        "- $($_.Name) ($sizeKB KB)"
    }
} else {
    "- 未生成截图文件"
})

## 验收说明
请查看reports目录下的截图文件，确认：
1. UI界面显示正常
2. 中文标签清晰可见
3. 各模块功能展示完整

---
*由 MAO-Wise UI 验证脚本生成*
"@

Set-Content -Path "reports/ui_smoke_report.md" -Value $reportContent -Encoding UTF8
Write-Host "✅ 验收报告已生成" -ForegroundColor Green

# 打开reports目录
Write-Host "`n📁 打开reports目录..." -ForegroundColor Green
try {
    Invoke-Item "reports"
    Write-Host "✅ reports目录已打开" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 请手动查看 reports 文件夹" -ForegroundColor Yellow
}

# 清理后台任务
Write-Host "`n🧹 清理后台任务..." -ForegroundColor Yellow
Get-Job | Stop-Job -PassThru | Remove-Job

# 最终状态
Write-Host "`n🎉 UI验证与截图完成！" -ForegroundColor Green
$predictExists = Test-Path "reports/ui_predict.png"
$recommendExists = Test-Path "reports/ui_recommend.png"
$expertExists = Test-Path "reports/ui_expert.png"

Write-Host "`n📋 验收状态:" -ForegroundColor Cyan
Write-Host "  $(if ($predictExists) { "✅" } else { "❌" }) 预测页面截图" -ForegroundColor $(if ($predictExists) { "Green" } else { "Red" })
Write-Host "  $(if ($recommendExists) { "✅" } else { "❌" }) 优化页面截图" -ForegroundColor $(if ($recommendExists) { "Green" } else { "Red" })
Write-Host "  $(if ($expertExists) { "✅" } else { "❌" }) 专家页面截图" -ForegroundColor $(if ($expertExists) { "Green" } else { "Red" })

$successCount = @($predictExists, $recommendExists, $expertExists) | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count
Write-Host "`n📊 验收通过率: $successCount/3 ($([math]::Round($successCount/3*100))%)" -ForegroundColor $(if ($successCount -eq 3) { "Green" } else { "Yellow" })

if ($successCount -eq 3) {
    Write-Host "🎉 所有截图均已生成！" -ForegroundColor Green
} else {
    Write-Host "⚠️ 部分截图未生成，请检查服务状态" -ForegroundColor Yellow
}
