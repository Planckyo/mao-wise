# scripts/push_to_github.ps1
# One-click push to GitHub (Windows PowerShell)
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\push_to_github.ps1 -Org Planckyo -Repo mao-wise -Branch main -Visibility public

param(
  [string]$Org        = "Planckyo",
  [string]$Repo       = "mao-wise",
  [string]$Branch     = "main",
  [ValidateSet("public","private")] [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"

function Info($m){ Write-Host "ℹ️  $m" -ForegroundColor Cyan }
function Ok($m){ Write-Host "✅ $m" -ForegroundColor Green }
function Warn($m){ Write-Host "⚠️ $m" -ForegroundColor Yellow }
function Die($m){ Write-Host "❌ $m" -ForegroundColor Red; exit 1 }

# 0) 预检工具
foreach($cmd in @("git","gh")){
  if(-not (Get-Command $cmd -ErrorAction SilentlyContinue)){ Die "未找到命令：$cmd" }
}

# 1) GH 登录检测（使用 SSH 协议）
try {
  gh auth status 1>$null 2>$null
} catch {
  Info "检测到未登录 GitHub CLI，将启动登录向导（SSH，浏览器授权）…"
  gh auth login -h github.com -p ssh -w
}

# 2) 初始化 Git 仓库（若尚未初始化）
if(-not (Test-Path .git)){
  Info "初始化 git 仓库…"
  git init
}
# 基础文件（只在缺失时创建，防止把大文件推上去）
if(-not (Test-Path .gitignore)){
@'
__pycache__/
*.pyc
.venv/
.env
.DS_Store
datasets/data_parsed/
datasets/index_store/
models_ckpt/
.cache/
.tmp/
'@ | Set-Content -Encoding UTF8 .gitignore
}
if(-not (Test-Path README.md)){
@'
# MAO-Wise

This repository contains MAO-Wise (Micro-Arc Oxidation Thermal-Control Coating Optimizer).
'@ | Set-Content -Encoding UTF8 README.md
}

# 若还没有任何提交，做一次初始提交
$hasHead = $true
try { git rev-parse --verify HEAD 1>$null 2>$null } catch { $hasHead = $false }
git add .
if(-not $hasHead){
  try { git commit -m "feat: initial commit (MAO-Wise bootstrap)" } catch { }
} else {
  try { git commit -m "chore: bootstrap updates" } catch { }
}

# 3) 创建/绑定远程仓库（避免 --remote=origin 的兼容问题）
$full = "$Org/$Repo"
Info "检查远程仓库：$full"
$exists = $false
try { gh repo view $full 1>$null 2>$null; $exists = ($LASTEXITCODE -eq 0) } catch { $exists = $false }

if(-not $exists){
  Info "创建 GitHub 仓库（$Visibility）…"
  gh repo create $full --$Visibility --source=. --description "MAO-Wise: Micro-Arc Oxidation Thermal-Control Coating Optimizer"
} else {
  Ok "GitHub 仓库已存在：$full"
}

# 4) 绑定/更新 origin 到 SSH 地址
$sshUrl = "git@github.com:$full.git"
$hasOrigin = $true
try { git remote get-url origin 1>$null 2>$null } catch { $hasOrigin = $false }
if($hasOrigin){
  git remote set-url origin $sshUrl
} else {
  git remote add origin $sshUrl
}
Ok "origin => $sshUrl"

# 5) 推送分支（不依赖 ssh-agent 服务；若你已通过 gh 配置 SSH，直接可推）
git branch -M $Branch
Info "推送 $Branch 到远程…"
git push -u origin $Branch

# 6) 校验与摘要
git ls-remote --heads origin $Branch | Out-Null
Ok  "仓库地址：https://github.com/$full"
Ok  "默认分支：$Branch"
git --no-pager log --oneline -3
Param(
  [string]$ORG_NAME = $env:ORG_NAME,
  [string]$REPO_NAME = $(if ($env:REPO_NAME) { $env:REPO_NAME } else { "mao-wise" }),
  [string]$DEFAULT_BRANCH = $(if ($env:DEFAULT_BRANCH) { $env:DEFAULT_BRANCH } else { "main" }),
  [string]$PRIVATE_REPO = $(if ($env:PRIVATE_REPO) { $env:PRIVATE_REPO } else { "true" })
)

function Print-Step($title) {
  Write-Host "==== $title ====" -ForegroundColor Cyan
}

function Print-OK($msg) { Write-Host "✅ $msg" -ForegroundColor Green }
function Print-Warn($msg) { Write-Host "⚠️ $msg" -ForegroundColor Yellow }
function Print-Err($msg) { Write-Host "❌ $msg" -ForegroundColor Red }

try {
  Print-Step "0) 变量与前置"
  if (-not $ORG_NAME -or $ORG_NAME -eq "") {
    # 尝试从 gh 获取登录用户
    try {
      $login = (gh api user -q ".login" 2>$null)
      if ($login) { $ORG_NAME = $login; Print-Warn "未提供 ORG_NAME，使用 gh 当前登录：$ORG_NAME" }
    } catch {}
  }
  if (-not $ORG_NAME -or $ORG_NAME -eq "") {
    $ORG_NAME = "your-org"
    Print-Warn "未提供 ORG_NAME，使用占位 your-org。请设置 ORG_NAME 环境变量或传参。"
  }
  $REPO_VISIBILITY = if ($PRIVATE_REPO -eq "true") { "private" } else { "public" }
  git --version | Write-Host
  gh --version 2>$null | Write-Host
  try { gh auth status | Write-Host } catch { Print-Warn "gh 未登录。请运行: gh auth login (优先 SSH)" }
  Print-OK "前置检查完成"

  Print-Step "1) 预检 与 基础文件"
  $gi = @"
__pycache__/
*.pyc
.venv/
.env
.DS_Store
datasets/data_parsed/
datasets/index_store/
models_ckpt/
.cache/
.tmp/
"@
  if (-not (Test-Path .gitignore)) { $gi | Out-File -Encoding utf8 .gitignore; Print-OK ".gitignore 已创建" } else { Print-Warn ".gitignore 已存在，跳过" }
  if (-not (Test-Path README.md)) { "# $REPO_NAME`n`n本仓库用于 MAO-Wise，运行:`n- uvicorn apps.api.main:app --reload`n- streamlit run apps/ui/app.py" | Out-File -Encoding utf8 README.md; Print-OK "README.md 已创建" } else { Print-Warn "README.md 已存在，跳过" }
  if (-not (Test-Path LICENSE)) {
    $year = (Get-Date).Year
    $mit = @'
MIT License

Copyright (c) $year $ORG_NAME

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'@
    $mit | Out-File -Encoding utf8 LICENSE
    Print-OK "LICENSE 已创建 (MIT)"
  } else { Print-Warn "LICENSE 已存在，跳过" }

  Print-Step "2) 初始化 Git"
  if (-not (Test-Path .git)) {
    git init | Write-Host
  } else { Print-Warn ".git 已存在，跳过 init" }
  git add . | Out-Null
  git status -s | Write-Host
  git commit -m "feat: initial commit (MAO-Wise bootstrap)" 2>$null | Write-Host
  git branch -M $DEFAULT_BRANCH | Write-Host
  Print-OK "Git 初始化完成"

  Print-Step "3) 创建/绑定 GitHub 仓库"
  $origin = (& git remote get-url origin 2>$null)
  if (-not $origin) {
    try {
      gh repo create "$ORG_NAME/$REPO_NAME" --$REPO_VISIBILITY --source=. --remote=origin --description "MAO-Wise: Micro-Arc Oxidation Thermal-Control Coating Optimizer" | Write-Host
    } catch {
      Print-Warn "gh 创建仓库失败，尝试直接设置远程。建议先 gh auth login。错误: $($_.Exception.Message)"
      try { git remote add origin "git@github.com:$ORG_NAME/$REPO_NAME.git" | Write-Host } catch { Print-Err "git remote add 失败: $($_.Exception.Message)" }
    }
  } else { Print-Warn "origin 已存在: $origin" }
  Print-OK "远程绑定步骤完成"

  Print-Step "4) 可选：LFS & DVC"
  if (Get-Command git-lfs -ErrorAction SilentlyContinue) {
    git lfs install | Write-Host
    "*.bin filter=lfs diff=lfs merge=lfs -text`n*.pt filter=lfs diff=lfs merge=lfs -text" | Out-File -Append -Encoding utf8 .gitattributes
    git add .gitattributes | Out-Null
    Print-OK "Git LFS 已初始化"
  } else { Print-Warn "git-lfs 未安装，跳过 LFS" }
  if (Get-Command dvc -ErrorAction SilentlyContinue) {
    if (-not (Test-Path .dvc)) { dvc init -q | Write-Host; git add .dvc | Out-Null; Print-OK "DVC 已初始化" } else { Print-Warn "DVC 已存在，跳过" }
  } else {
    Print-Warn "dvc 未安装，跳过 DVC"
  }

  Print-Step "5) 推送到远程"
  git add . | Out-Null
  git commit -m "chore: repo scaffolding, gitignore/license/readme" 2>$null | Write-Host
  try {
    git push -u origin $DEFAULT_BRANCH | Write-Host
    Print-OK "已推送到远程 $DEFAULT_BRANCH"
  } catch {
    Print-Err "推送失败: $($_.Exception.Message)"
    Print-Warn "建议：确保 gh 已登录且有权限；或改用 HTTPS：git remote set-url origin https://github.com/$ORG_NAME/$REPO_NAME.git 后重试。"
    throw
  }

  Print-Step "6) 基础校验与输出"
  git ls-remote --heads origin $DEFAULT_BRANCH | Write-Host
  Write-Host "仓库地址：https://github.com/$ORG_NAME/$REPO_NAME"
  Write-Host "默认分支：$DEFAULT_BRANCH"
  git --no-pager log --oneline -3 | Write-Host
  Print-OK "推送完成"
} catch {
  Print-Err "流程中断：$($_.Exception.Message)"
  Print-Warn "常见问题：gh 未登录/无权限；远程仓库已存在；分支冲突；大文件未忽略（请移入 DVC/LFS 或加到 .gitignore）。"
  exit 1
}

