# Canvas 批量脚本配置指南

## 🚀 快速配置

### 1. 环境变量设置

**⚠️ 重要：不要直接在脚本中设置API Key！**

```powershell
# ❌ 错误做法 - 不要在脚本中硬编码Key
$env:OPENAI_API_KEY="sk-..."

# ✅ 正确做法 - 使用交互式配置脚本
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1
```

### 2. 基础环境配置

```powershell
# 设置编码和激活虚拟环境
chcp 65001 > $null
.venv\Scripts\activate

# 设置本地文献库路径
$env:MAOWISE_LIBRARY_DIR="D:\桌面\本地PDF文献知识库"
```

### 3. 推荐配置流程

#### 步骤1：交互式设置LLM凭据
```powershell
# 运行交互式配置脚本
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1 -Provider openai
```

#### 步骤2：验证配置
```powershell
# 检查连通性
python scripts/test_llm_connectivity.py
```

#### 步骤3：执行批量脚本
```powershell
# 在线Real Run
powershell -ExecutionPolicy Bypass -File scripts\real_run.ps1 -LibraryDir "D:\桌面\本地PDF文献知识库"

# 或离线模式
powershell -ExecutionPolicy Bypass -File scripts\pipeline_local.ps1 -UseOCR:$false -DoTrain:$true
```

## 🔐 安全配置原则

### 1. 凭据管理
- **永远不要**在脚本中硬编码API Key
- **永远不要**将包含Key的文件提交到Git
- 使用 `scripts\set_llm_keys.ps1` 安全设置凭据
- 凭据存储在本地 `.env` 文件中（已加入.gitignore）

### 2. 环境变量优先级
```
1. 环境变量 (最高优先级)
2. .env 文件
3. config.yaml (最低优先级)
```

### 3. 离线兜底机制
- 当检测不到API Key时，系统自动切换到离线模式
- 不会因为缺少Key而中断执行
- 提供友好的提示信息引导用户配置

## 📋 脚本配置模板

### Canvas批量执行脚本
```powershell
# Canvas批量脚本配置模板
# 文件名: canvas_batch_script.ps1

# 1. 基础环境设置
chcp 65001 > $null
.venv\Scripts\activate
$env:MAOWISE_LIBRARY_DIR="D:\桌面\本地PDF文献知识库"

# 2. 检查LLM配置
if (-not $env:OPENAI_API_KEY) {
    Write-Host "⚠️  OPENAI_API_KEY 环境变量未设置" -ForegroundColor Yellow
    Write-Host "请运行 scripts\set_llm_keys.ps1 交互式设置" -ForegroundColor Cyan
    Write-Host "继续执行离线模式..." -ForegroundColor Gray
}

# 3. 执行批量任务
Write-Host "开始执行批量任务..." -ForegroundColor Green

# 生成批量方案
python scripts/generate_batch_plans.py --system silicate --n 6 --notes "canvas_batch"
python scripts/generate_batch_plans.py --system zirconate --n 6 --notes "canvas_batch"

# 验证方案
$latestBatch = (Get-ChildItem tasks -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
python scripts/validate_recommendations.py --plans "tasks\$latestBatch\plans.csv" --kb datasets/index_store --topk 3

Write-Host "批量任务执行完成！" -ForegroundColor Green
```

### 环境检查脚本
```powershell
# 环境检查脚本
# 文件名: check_environment.ps1

Write-Host "🔍 MAO-Wise 环境检查" -ForegroundColor Cyan
Write-Host "=" * 40 -ForegroundColor Cyan

# 检查Python环境
if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "✅ Python: 已安装" -ForegroundColor Green
    $pythonVersion = python --version
    Write-Host "   版本: $pythonVersion" -ForegroundColor Gray
} else {
    Write-Host "❌ Python: 未安装" -ForegroundColor Red
}

# 检查虚拟环境
if (Test-Path ".venv\Scripts\activate") {
    Write-Host "✅ 虚拟环境: 已创建" -ForegroundColor Green
} else {
    Write-Host "❌ 虚拟环境: 未创建" -ForegroundColor Red
}

# 检查LLM配置
if ($env:OPENAI_API_KEY) {
    Write-Host "✅ OPENAI_API_KEY: 已设置" -ForegroundColor Green
} else {
    Write-Host "⚠️  OPENAI_API_KEY: 未设置" -ForegroundColor Yellow
    Write-Host "   建议: 运行 scripts\set_llm_keys.ps1" -ForegroundColor Cyan
}

# 检查文献库路径
if ($env:MAOWISE_LIBRARY_DIR) {
    if (Test-Path $env:MAOWISE_LIBRARY_DIR) {
        Write-Host "✅ MAOWISE_LIBRARY_DIR: 已设置且路径有效" -ForegroundColor Green
        Write-Host "   路径: $env:MAOWISE_LIBRARY_DIR" -ForegroundColor Gray
    } else {
        Write-Host "❌ MAOWISE_LIBRARY_DIR: 路径不存在" -ForegroundColor Red
        Write-Host "   路径: $env:MAOWISE_LIBRARY_DIR" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠️  MAOWISE_LIBRARY_DIR: 未设置" -ForegroundColor Yellow
}

Write-Host "=" * 40 -ForegroundColor Cyan
Write-Host "环境检查完成" -ForegroundColor Cyan
```

## 🚨 常见问题解决

### 1. API Key未设置
**症状**: 脚本提示"OPENAI_API_KEY环境变量未设置"
**解决**: 
```powershell
# 运行交互式配置
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1
```

### 2. 网络连接问题
**症状**: 连通性测试显示"Connection error"
**解决**:
- 检查网络代理设置
- 确认防火墙配置
- 系统会自动切换到离线兜底模式

### 3. 文献库路径错误
**症状**: 提示"Library directory does not exist"
**解决**:
```powershell
# 设置正确的文献库路径
$env:MAOWISE_LIBRARY_DIR="D:\桌面\本地PDF文献知识库"
```

### 4. 权限问题
**症状**: PowerShell执行策略错误
**解决**:
```powershell
# 临时绕过执行策略
powershell -ExecutionPolicy Bypass -File scripts\your_script.ps1

# 或永久设置（需要管理员权限）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 📚 相关文档

- [MAO-Wise 主文档](../README.md)
- [LLM凭据设置指南](../scripts/set_llm_keys.ps1)
- [连通性测试脚本](../scripts/test_llm_connectivity.py)
- [批量方案生成](../scripts/generate_batch_plans.py)

## 🔒 安全提醒

1. **永远不要**在代码中硬编码API Key
2. **永远不要**将包含敏感信息的文件提交到版本控制
3. 使用提供的安全脚本管理凭据
4. 定期轮换API Key
5. 监控API使用情况

---

*最后更新: 2025-08-13*
*版本: v2.0*
