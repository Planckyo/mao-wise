# MAO-Wise 端到端测试一键运行脚本
# 支持 Windows 中文路径和环境变量配置

# 设置控制台编码为UTF-8
chcp 65001 > $null

# 设置错误处理
$ErrorActionPreference = "Continue"

Write-Host "🚀 MAO-Wise 端到端测试启动" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

# 检查Python环境
Write-Host "`n🐍 检查Python环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python环境: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Python未安装或不在PATH中" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ 无法检测Python环境: $_" -ForegroundColor Red
    exit 1
}

# 检查必要的Python包
Write-Host "`n📦 检查Python依赖..." -ForegroundColor Yellow
$requiredPackages = @("requests", "pyyaml", "uvicorn", "fastapi")

foreach ($package in $requiredPackages) {
    try {
        python -c "import $package" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ $package 已安装" -ForegroundColor Green
        } else {
            Write-Host "⚠️ $package 未安装，尝试安装..." -ForegroundColor Yellow
            pip install $package --quiet
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ $package 安装成功" -ForegroundColor Green
            } else {
                Write-Host "❌ $package 安装失败" -ForegroundColor Red
            }
        }
    } catch {
        Write-Host "❌ 检查 $package 时出错: $_" -ForegroundColor Red
    }
}

# 可选：设置环境变量
Write-Host "`n🔧 配置环境变量..." -ForegroundColor Yellow

# 检查是否有本地库路径配置
if (-not $env:MAOWISE_LIBRARY_DIR) {
    Write-Host "ℹ️ MAOWISE_LIBRARY_DIR 未设置，将使用最小数据夹具" -ForegroundColor Cyan
    # 用户可以取消注释下面的行来设置库路径
    # $env:MAOWISE_LIBRARY_DIR = "D:\桌面\本地PDF文献知识库"
} else {
    Write-Host "✅ MAOWISE_LIBRARY_DIR: $env:MAOWISE_LIBRARY_DIR" -ForegroundColor Green
}

# 检查API密钥
if (-not $env:OPENAI_API_KEY) {
    Write-Host "ℹ️ OPENAI_API_KEY 未设置，将使用离线兜底模式" -ForegroundColor Cyan
    # 用户可以取消注释下面的行来设置API密钥
    # $env:OPENAI_API_KEY = "sk-your-api-key-here"
} else {
    $maskedKey = $env:OPENAI_API_KEY.Substring(0, [Math]::Min(7, $env:OPENAI_API_KEY.Length)) + "..."
    Write-Host "✅ OPENAI_API_KEY: $maskedKey" -ForegroundColor Green
}

# 设置调试模式（可选）
if (-not $env:DEBUG_LLM) {
    $env:DEBUG_LLM = "false"
}
Write-Host "🐛 DEBUG_LLM: $env:DEBUG_LLM" -ForegroundColor Cyan

# 步骤1：数据准备
Write-Host "`n📋 步骤1：数据准备..." -ForegroundColor Yellow
Write-Host "执行: python scripts/e2e_data_prep.py" -ForegroundColor Gray

try {
    python scripts/e2e_data_prep.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 数据准备完成" -ForegroundColor Green
    } else {
        Write-Host "❌ 数据准备失败 (退出码: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "继续执行测试，可能使用离线模式..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ 数据准备异常: $_" -ForegroundColor Red
    Write-Host "继续执行测试..." -ForegroundColor Yellow
}

# 短暂等待
Start-Sleep -Seconds 2

# 步骤2：端到端测试
Write-Host "`n🧪 步骤2：端到端测试..." -ForegroundColor Yellow
Write-Host "执行: python scripts/e2e_validate.py" -ForegroundColor Gray

try {
    python scripts/e2e_validate.py
    $testExitCode = $LASTEXITCODE
    
    if ($testExitCode -eq 0) {
        Write-Host "✅ 端到端测试完成，所有测试通过！" -ForegroundColor Green
    } else {
        Write-Host "⚠️ 端到端测试完成，但存在失败项目 (退出码: $testExitCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ 端到端测试异常: $_" -ForegroundColor Red
    $testExitCode = 1
}

# 步骤3：打开报告
Write-Host "`n📊 步骤3：查看测试报告..." -ForegroundColor Yellow

$reportsDir = "reports"
$markdownReport = Join-Path $reportsDir "e2e_report.md"
$htmlReport = Join-Path $reportsDir "e2e_report.html"

if (Test-Path $reportsDir) {
    Write-Host "✅ 报告目录存在: $reportsDir" -ForegroundColor Green
    
    if (Test-Path $markdownReport) {
        Write-Host "✅ Markdown报告: $markdownReport" -ForegroundColor Green
    } else {
        Write-Host "❌ Markdown报告未找到" -ForegroundColor Red
    }
    
    if (Test-Path $htmlReport) {
        Write-Host "✅ HTML报告: $htmlReport" -ForegroundColor Green
    } else {
        Write-Host "❌ HTML报告未找到" -ForegroundColor Red
    }
    
    # 尝试打开报告目录
    try {
        Write-Host "`n🔗 打开报告目录..." -ForegroundColor Yellow
        Invoke-Item $reportsDir
        Write-Host "✅ 报告目录已打开" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ 无法自动打开报告目录: $_" -ForegroundColor Yellow
        Write-Host "请手动打开: $reportsDir" -ForegroundColor Cyan
    }
} else {
    Write-Host "❌ 报告目录不存在" -ForegroundColor Red
}

# 总结
Write-Host "`n" + "="*50 -ForegroundColor Green
Write-Host "📋 端到端测试总结" -ForegroundColor Green
Write-Host "="*50 -ForegroundColor Green

if ($testExitCode -eq 0) {
    Write-Host "🎉 状态: 全部通过" -ForegroundColor Green
    Write-Host "✅ MAO-Wise 系统各项功能正常运行" -ForegroundColor Green
} else {
    Write-Host "⚠️ 状态: 部分失败" -ForegroundColor Yellow
    Write-Host "📋 请查看详细报告了解失败原因" -ForegroundColor Yellow
}

Write-Host "`n📂 报告文件:" -ForegroundColor Cyan
Write-Host "  • Markdown: $markdownReport" -ForegroundColor White
Write-Host "  • HTML: $htmlReport" -ForegroundColor White

Write-Host "`n🔧 运行模式:" -ForegroundColor Cyan
if ($env:OPENAI_API_KEY) {
    Write-Host "  • LLM: 在线模式 (OpenAI)" -ForegroundColor White
} else {
    Write-Host "  • LLM: 离线兜底模式" -ForegroundColor White
}

if ($env:MAOWISE_LIBRARY_DIR) {
    Write-Host "  • 数据: 本地文献库" -ForegroundColor White
} else {
    Write-Host "  • 数据: 最小测试夹具" -ForegroundColor White
}

Write-Host "`n💡 提示:" -ForegroundColor Cyan
Write-Host "  • 设置 OPENAI_API_KEY 启用在线LLM功能" -ForegroundColor White
Write-Host "  • 设置 MAOWISE_LIBRARY_DIR 使用本地文献库" -ForegroundColor White
Write-Host "  • 设置 DEBUG_LLM=true 查看详细日志" -ForegroundColor White

Write-Host "`n🏁 端到端测试完成！" -ForegroundColor Green

# 等待用户按键（可选）
if ($env:E2E_WAIT_FOR_KEY -eq "true") {
    Write-Host "`n按任意键退出..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# 返回测试结果作为退出码
exit $testExitCode
