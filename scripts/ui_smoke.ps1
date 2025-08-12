# MAO-Wise UI 手工验证清单 - 自动截图脚本
# 功能：启动服务、打开UI、自动截图、生成验收材料

# Set UTF-8 encoding for PowerShell session
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

Write-Host "🚀 启动MAO-Wise UI验证与截图..." -ForegroundColor Green

# 设置工作目录为仓库根目录
Write-Host "`n📁 设置工作环境..." -ForegroundColor Yellow
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..  # 切到仓库根

# 设置PYTHONPATH环境变量
$env:PYTHONPATH = (Get-Location).Path
Write-Host "工作目录: $(Get-Location)" -ForegroundColor Cyan
Write-Host "PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Cyan

# 检查Python环境
Write-Host "`n🔍 检查Python环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python已安装: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Python未安装或不在PATH中" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ 无法检测Python版本" -ForegroundColor Red
    exit 1
}

# 检查必要的Python包
Write-Host "`n📦 检查必要的Python包..." -ForegroundColor Yellow
$requiredPackages = @("selenium", "requests")
$missingPackages = @()

foreach ($package in $requiredPackages) {
    try {
        $result = python -c "import $package; print('OK')" 2>&1
        if ($LASTEXITCODE -eq 0 -and $result -eq "OK") {
            Write-Host "✅ $package 已安装" -ForegroundColor Green
        } else {
            $missingPackages += $package
        }
    } catch {
        $missingPackages += $package
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host "⚠️ 缺少必要的包，正在安装..." -ForegroundColor Yellow
    foreach ($package in $missingPackages) {
        Write-Host "📦 安装 $package..." -ForegroundColor Cyan
        pip install $package
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ 安装 $package 失败" -ForegroundColor Red
            exit 1
        }
    }
}

# 检查Chrome浏览器
Write-Host "`n🌐 检查Chrome浏览器..." -ForegroundColor Yellow
$chromeExists = $false
$chromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)

foreach ($path in $chromePaths) {
    if (Test-Path $path) {
        Write-Host "✅ Chrome浏览器已找到: $path" -ForegroundColor Green
        $chromeExists = $true
        break
    }
}

if (-not $chromeExists) {
    Write-Host "⚠️ 未找到Chrome浏览器，尝试安装ChromeDriver..." -ForegroundColor Yellow
    pip install webdriver-manager
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ ChromeDriver安装失败，请手动安装Chrome浏览器" -ForegroundColor Red
        Write-Host "下载地址: https://www.google.com/chrome/" -ForegroundColor Cyan
    }
}

# 确保reports目录存在
Write-Host "`n📁 准备reports目录..." -ForegroundColor Yellow
if (-not (Test-Path "reports")) {
    New-Item -ItemType Directory -Path "reports" -Force | Out-Null
    Write-Host "✅ 已创建reports目录" -ForegroundColor Green
} else {
    Write-Host "✅ reports目录已存在" -ForegroundColor Green
}

# 启动服务
Write-Host "`n🚀 启动MAO-Wise服务..." -ForegroundColor Green
if (Test-Path "scripts\start_services.ps1") {
    Write-Host "执行 start_services.ps1..." -ForegroundColor Cyan
    
    # 在后台启动服务
    $serviceJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        .\scripts\start_services.ps1
    }
    
    Write-Host "✅ 服务启动任务已创建 (Job ID: $($serviceJob.Id))" -ForegroundColor Green
    
    # 等待服务启动
    Write-Host "⏳ 等待服务启动..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15
    
} else {
    Write-Host "❌ 未找到 start_services.ps1，尝试手动启动..." -ForegroundColor Red
    
    # 手动启动API服务
    Write-Host "🔧 手动启动API服务..." -ForegroundColor Cyan
    $apiJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
    }
    
    # 手动启动Streamlit服务
    Write-Host "🔧 手动启动Streamlit服务..." -ForegroundColor Cyan
    $streamlitJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        streamlit run apps/ui/app.py --server.port 8501 --server.address 127.0.0.1
    }
    
    Write-Host "✅ 服务已手动启动" -ForegroundColor Green
    Start-Sleep -Seconds 20
}

# 检查服务状态
Write-Host "`n🔍 检查服务状态..." -ForegroundColor Yellow

# 检查API服务
try {
    $apiResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/maowise/v1/health" -TimeoutSec 5 -UseBasicParsing
    if ($apiResponse.StatusCode -eq 200) {
        Write-Host "✅ API服务正常运行 (端口8000)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ API服务响应异常" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ API服务未响应，继续尝试..." -ForegroundColor Yellow
}

# 检查Streamlit服务
try {
    $streamlitResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8501" -TimeoutSec 5 -UseBasicParsing
    if ($streamlitResponse.StatusCode -eq 200) {
        Write-Host "✅ Streamlit服务正常运行 (端口8501)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Streamlit服务响应异常" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Streamlit服务未响应，请检查服务状态" -ForegroundColor Red
    Write-Host "尝试手动访问: http://127.0.0.1:8501" -ForegroundColor Cyan
}

# 打开浏览器（可选）
Write-Host "`n🌐 打开浏览器..." -ForegroundColor Yellow
try {
    Start-Process "http://127.0.0.1:8501"
    Write-Host "✅ 浏览器已打开 http://127.0.0.1:8501" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 无法自动打开浏览器，请手动访问 http://127.0.0.1:8501" -ForegroundColor Yellow
}

# 等待用户确认服务就绪
Write-Host "`n⏳ 等待服务完全启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# 执行自动截图
Write-Host "`n📸 开始自动截图..." -ForegroundColor Green
Write-Host "执行 ui_snapshots.py..." -ForegroundColor Cyan

try {
    $screenshotResult = python scripts/ui_snapshots.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 自动截图完成" -ForegroundColor Green
        Write-Host $screenshotResult
    } else {
        Write-Host "⚠️ 截图过程有警告，但已完成" -ForegroundColor Yellow
        Write-Host $screenshotResult
    }
} catch {
    Write-Host "❌ 自动截图失败: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "请检查Chrome浏览器和Selenium配置" -ForegroundColor Yellow
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
    Write-Host "⚠️ 未找到截图文件，可能截图过程失败" -ForegroundColor Yellow
    Write-Host "请检查以下内容:" -ForegroundColor Cyan
    Write-Host "  1. Streamlit服务是否正常运行" -ForegroundColor White
    Write-Host "  2. Chrome浏览器是否已安装" -ForegroundColor White
    Write-Host "  3. Selenium是否正确配置" -ForegroundColor White
}

# 生成验收报告
Write-Host "`n📝 生成验收报告..." -ForegroundColor Yellow
$reportPath = "reports/ui_smoke_report.md"
$reportContent = @"
# MAO-Wise UI 验证报告

生成时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

## 服务状态
- API服务 (8000端口): $(if (Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet) { "✅ 正常" } else { "❌ 异常" })
- Streamlit服务 (8501端口): $(if (Test-NetConnection -ComputerName 127.0.0.1 -Port 8501 -InformationLevel Quiet) { "✅ 正常" } else { "❌ 异常" })

## 截图文件
$(if ($screenshots) {
    $screenshots | ForEach-Object {
        $sizeKB = [math]::Round($_.Length / 1024, 1)
        "- [OK] $($_.Name) ($sizeKB KB)"
    }
} else {
    "- [FAIL] 未生成截图文件"
})

## 验收标准
- [$(if (Test-Path "reports/ui_predict.png") { "OK" } else { "FAIL" })] 预测页面截图 (ui_predict.png)
- [$(if (Test-Path "reports/ui_recommend.png") { "OK" } else { "FAIL" })] 优化页面截图 (ui_recommend.png) 
- [$(if (Test-Path "reports/ui_expert.png") { "OK" } else { "FAIL" })] 专家指导页面截图 (ui_expert.png)

## 使用说明
1. 查看生成的截图文件
2. 确认UI中包含中文标签
3. 验证各模块功能正常显示
4. 如需重新截图，请重新运行此脚本

---
*由 MAO-Wise UI 自动化验证脚本生成*
"@

Set-Content -Path $reportPath -Value $reportContent -Encoding UTF8
Write-Host "✅ 验收报告已生成: $reportPath" -ForegroundColor Green

# 打开reports目录
Write-Host "`n📁 打开reports目录..." -ForegroundColor Green
try {
    Invoke-Item "reports"
    Write-Host "✅ reports目录已打开" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 无法自动打开目录，请手动查看 'reports/' 文件夹" -ForegroundColor Yellow
}

# 清理后台任务
Write-Host "`n🧹 清理后台任务..." -ForegroundColor Yellow
Get-Job | Where-Object { $_.State -eq "Running" } | ForEach-Object {
    Write-Host "停止任务: $($_.Name) (ID: $($_.Id))" -ForegroundColor Gray
    Stop-Job $_ -PassThru | Remove-Job
}

Write-Host "`n🎉 UI验证与截图完成！" -ForegroundColor Green
Write-Host "请查看 reports/ 目录下的截图文件和验收报告。" -ForegroundColor Cyan

# 最终状态检查
$finalCheck = @{
    "预测页面截图" = Test-Path "reports/ui_predict.png"
    "优化页面截图" = Test-Path "reports/ui_recommend.png"
    "专家页面截图" = Test-Path "reports/ui_expert.png"
    "验收报告" = Test-Path "reports/ui_smoke_report.md"
}

Write-Host "`n📋 最终验收状态:" -ForegroundColor Cyan
foreach ($item in $finalCheck.GetEnumerator()) {
    $status = if ($item.Value) { "[OK]" } else { "[FAIL]" }
    Write-Host "  $status $($item.Key)" -ForegroundColor $(if ($item.Value) { "Green" } else { "Red" })
}

$successCount = ($finalCheck.Values | Where-Object { $_ }).Count
Write-Host "`n📊 验收通过率: $successCount/4 ($([math]::Round($successCount/4*100))%)" -ForegroundColor $(if ($successCount -eq 4) { "Green" } else { "Yellow" })

if ($successCount -eq 4) {
    Write-Host "🎉 所有验收项目均已完成！" -ForegroundColor Green
} else {
    Write-Host "⚠️ 部分验收项目未完成，请检查上述状态。" -ForegroundColor Yellow
}
