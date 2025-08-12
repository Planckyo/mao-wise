# 一键更新脚本 - 从实验反馈更新残差校正器和偏好模型
# 
# 功能：
# - 基于实验数据训练/更新残差校正器 (GP Corrector)
# - 训练/更新偏好模型 (Reward Model)
# - 前后性能对比
# - 可选热加载到运行中的API
#
# 使用示例：
# powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1
# powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1 -HotReload:$true
# powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1 -ExperimentsFile "datasets/experiments/custom.parquet"

param(
    [string]$ExperimentsFile = "datasets/experiments/experiments.parquet",
    [string]$ApiUrl = "http://localhost:8000", 
    [switch]$HotReload = $false,
    [switch]$SkipEvaluation = $false,
    [string]$OutputDir = "models_ckpt"
)

# 设置工作目录为仓库根目录
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..  # 切到仓库根

# 设置PYTHONPATH环境变量
$env:PYTHONPATH = (Get-Location).Path

Write-Host "`n🔄 MAO-Wise 一键模型更新" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan

# 参数显示
Write-Host "`n📋 更新参数:" -ForegroundColor Yellow
Write-Host "   实验数据: $ExperimentsFile" -ForegroundColor Gray
Write-Host "   API地址: $ApiUrl" -ForegroundColor Gray
Write-Host "   热加载: $HotReload" -ForegroundColor Gray
Write-Host "   输出目录: $OutputDir" -ForegroundColor Gray

# 检查实验数据文件
if (-not (Test-Path $ExperimentsFile)) {
    Write-Host "❌ 实验数据文件不存在: $ExperimentsFile" -ForegroundColor Red
    Write-Host "请先运行实验结果导入：" -ForegroundColor Yellow
    Write-Host "python scripts/record_experiment_results.py --file your_results.xlsx" -ForegroundColor Gray
    exit 1
}

# 检查实验数据是否为空
try {
    $recordCount = python -c "import pandas as pd; df = pd.read_parquet('$ExperimentsFile'); print(len(df))" 2>$null
    if ($LASTEXITCODE -ne 0 -or [int]$recordCount -eq 0) {
        Write-Host "❌ 实验数据为空或读取失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ 发现 $recordCount 条实验记录" -ForegroundColor Green
} catch {
    Write-Host "❌ 无法读取实验数据" -ForegroundColor Red
    exit 1
}

# 步骤1: 更新前评估（基线）
if (-not $SkipEvaluation) {
    Write-Host "`n📊 步骤1: 更新前性能评估..." -ForegroundColor Yellow
    
    $beforeReportFile = "reports/eval_before_update_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    
    try {
        python scripts/evaluate_predictions.py --experiments-file $ExperimentsFile --output $beforeReportFile --api-url $ApiUrl
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ 更新前评估完成: $beforeReportFile" -ForegroundColor Green
        } else {
            Write-Host "⚠️ 更新前评估失败，继续更新流程" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️ 更新前评估出现异常，继续更新流程" -ForegroundColor Yellow
    }
}

# 步骤2: 训练残差校正器
Write-Host "`n🧮 步骤2: 训练残差校正器 (GP Corrector)..." -ForegroundColor Yellow

$gpOutputDir = "$OutputDir/gp_corrector"
New-Item -ItemType Directory -Force -Path $gpOutputDir | Out-Null

try {
    # 调用残差校正器训练脚本
    python -c "
import sys
sys.path.insert(0, '.')
from maowise.models.residual.gp_corrector import train_gp_corrector
import pandas as pd
from datetime import datetime

# 加载实验数据
df = pd.read_parquet('$ExperimentsFile')
print(f'加载实验数据: {len(df)} 条')

# 准备训练数据
train_data = []
for _, row in df.iterrows():
    # 构造输入特征
    features = {
        'voltage_V': float(row.get('voltage_V', 300.0)),
        'current_density_A_dm2': float(row.get('current_density_Adm2', row.get('current_density_A_dm2', 10.0))),
        'frequency_Hz': float(row.get('frequency_Hz', 1000.0)),
        'duty_cycle_pct': float(row.get('duty_cycle_pct', 30.0)),
        'time_min': float(row.get('time_min', 20.0)),
        'temp_C': float(row.get('temp_C', 25.0)) if pd.notna(row.get('temp_C')) else 25.0,
        'pH': float(row.get('pH', 11.0)) if pd.notna(row.get('pH')) else 11.0
    }
    
    # 目标值
    targets = {
        'alpha': float(row['measured_alpha']),
        'epsilon': float(row['measured_epsilon'])
    }
    
    train_data.append({'features': features, 'targets': targets})

print(f'准备训练数据: {len(train_data)} 条')

# 训练GP校正器
try:
    corrector = train_gp_corrector(train_data, output_dir='$gpOutputDir')
    print('✅ GP校正器训练完成')
except Exception as e:
    print(f'❌ GP校正器训练失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ GP校正器训练完成: $gpOutputDir" -ForegroundColor Green
    } else {
        Write-Host "❌ GP校正器训练失败" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ GP校正器训练出现异常" -ForegroundColor Red
    exit 1
}

# 步骤3: 训练偏好模型
Write-Host "`n🎯 步骤3: 训练偏好模型 (Reward Model)..." -ForegroundColor Yellow

$rewardOutputDir = "$OutputDir/reward_v1"
New-Item -ItemType Directory -Force -Path $rewardOutputDir | Out-Null

try {
    # 调用偏好模型训练脚本
    python -c "
import sys
sys.path.insert(0, '.')
from maowise.models.reward.train_reward import train_reward_model
import pandas as pd
import numpy as np

# 加载实验数据
df = pd.read_parquet('$ExperimentsFile')
print(f'加载实验数据: {len(df)} 条')

# 准备偏好训练数据
preference_data = []
for _, row in df.iterrows():
    # 构造样本特征
    sample = {
        'substrate_alloy': row.get('substrate_alloy', 'AZ91D'),
        'electrolyte_family': 'alkaline' if 'silicate' in str(row.get('system', '')).lower() else 'fluoride',
        'voltage_V': float(row.get('voltage_V', 300.0)),
        'current_density_A_dm2': float(row.get('current_density_Adm2', row.get('current_density_A_dm2', 10.0))),
        'frequency_Hz': float(row.get('frequency_Hz', 1000.0)),
        'duty_cycle_pct': float(row.get('duty_cycle_pct', 30.0)),
        'time_min': float(row.get('time_min', 20.0)),
        'alpha_150_2600': float(row['measured_alpha']),
        'epsilon_3000_30000': float(row['measured_epsilon'])
    }
    
    # 计算综合质量评分（基于实测结果）
    # 简化的质量评分：alpha越低越好，epsilon越高越好
    alpha_score = max(0, 1 - row['measured_alpha'] / 0.3)  # alpha<0.3为好
    epsilon_score = min(1, row['measured_epsilon'] / 0.8)  # epsilon>0.8为好
    
    # 综合评分
    quality_score = (alpha_score * 0.4 + epsilon_score * 0.6)
    
    # 添加一些噪声以增加多样性
    quality_score = np.clip(quality_score + np.random.normal(0, 0.1), 0, 1)
    
    preference_data.append({
        'sample': sample,
        'quality_score': float(quality_score),
        'metadata': {
            'experiment_id': row.get('experiment_id', ''),
            'system': row.get('system', ''),
            'reviewer': row.get('reviewer', '')
        }
    })

print(f'准备偏好数据: {len(preference_data)} 条')

# 训练偏好模型
try:
    reward_model = train_reward_model(preference_data, output_dir='$rewardOutputDir')
    print('✅ 偏好模型训练完成')
except Exception as e:
    print(f'❌ 偏好模型训练失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 偏好模型训练完成: $rewardOutputDir" -ForegroundColor Green
    } else {
        Write-Host "❌ 偏好模型训练失败" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ 偏好模型训练出现异常" -ForegroundColor Red
    exit 1
}

# 步骤4: 更新后评估
if (-not $SkipEvaluation) {
    Write-Host "`n📈 步骤4: 更新后性能评估..." -ForegroundColor Yellow
    
    $afterReportFile = "reports/eval_after_update_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    
    try {
        python scripts/evaluate_predictions.py --experiments-file $ExperimentsFile --output $afterReportFile --api-url $ApiUrl
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ 更新后评估完成: $afterReportFile" -ForegroundColor Green
            
            # 尝试比较前后性能
            if ($beforeReportFile -and (Test-Path $beforeReportFile) -and (Test-Path $afterReportFile)) {
                Write-Host "`n📊 性能对比:" -ForegroundColor Cyan
                python -c "
import json
try:
    with open('$beforeReportFile', 'r', encoding='utf-8') as f:
        before = json.load(f)
    with open('$afterReportFile', 'r', encoding='utf-8') as f:
        after = json.load(f)
    
    before_alpha_mae = before['overall_metrics']['alpha_metrics']['mae']
    after_alpha_mae = after['overall_metrics']['alpha_metrics']['mae']
    before_epsilon_mae = before['overall_metrics']['epsilon_metrics']['mae']
    after_epsilon_mae = after['overall_metrics']['epsilon_metrics']['mae']
    
    alpha_improvement = ((before_alpha_mae - after_alpha_mae) / before_alpha_mae) * 100
    epsilon_improvement = ((before_epsilon_mae - after_epsilon_mae) / before_epsilon_mae) * 100
    
    print(f'   Alpha MAE: {before_alpha_mae:.4f} → {after_alpha_mae:.4f} ({alpha_improvement:+.1f}%)')
    print(f'   Epsilon MAE: {before_epsilon_mae:.4f} → {after_epsilon_mae:.4f} ({epsilon_improvement:+.1f}%)')
    
    if alpha_improvement > 0 and epsilon_improvement > 0:
        print('✅ 两项指标均有改善')
    elif alpha_improvement > 0 or epsilon_improvement > 0:
        print('⚠️ 部分指标有改善')
    else:
        print('❌ 性能未见改善')
        
except Exception as e:
    print(f'性能对比失败: {e}')
"
            }
        } else {
            Write-Host "⚠️ 更新后评估失败" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️ 更新后评估出现异常" -ForegroundColor Yellow
    }
}

# 步骤5: 热加载（可选）
if ($HotReload) {
    Write-Host "`n🔥 步骤5: 热加载新模型到API..." -ForegroundColor Yellow
    
    try {
        $reloadUrl = "$ApiUrl/api/maowise/v1/admin/reload"
        $response = Invoke-WebRequest -Uri $reloadUrl -Method POST -ContentType "application/json" -Body '{"models":["gp_corrector","reward_model"]}' -TimeoutSec 10
        
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ API热加载成功" -ForegroundColor Green
        } else {
            Write-Host "⚠️ API热加载响应异常: $($response.StatusCode)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️ API热加载失败（API可能未运行）: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "   可以手动重启API服务以加载新模型" -ForegroundColor Gray
    }
}

# 完成总结
Write-Host "`n🎉 模型更新完成!" -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Green

Write-Host "`n📁 输出文件:" -ForegroundColor Cyan
Write-Host "   - GP校正器: $gpOutputDir" -ForegroundColor Gray
Write-Host "   - 偏好模型: $rewardOutputDir" -ForegroundColor Gray

if (-not $SkipEvaluation) {
    if ($beforeReportFile -and (Test-Path $beforeReportFile)) {
        Write-Host "   - 更新前评估: $beforeReportFile" -ForegroundColor Gray
    }
    if ($afterReportFile -and (Test-Path $afterReportFile)) {
        Write-Host "   - 更新后评估: $afterReportFile" -ForegroundColor Gray
    }
}

Write-Host "`n💡 后续建议:" -ForegroundColor Cyan
Write-Host "   1. 查看评估报告了解性能改善情况" -ForegroundColor Gray
Write-Host "   2. 如果性能提升明显，可以部署到生产环境" -ForegroundColor Gray
Write-Host "   3. 继续收集更多实验数据以进一步改进模型" -ForegroundColor Gray

if (-not $HotReload) {
    Write-Host "   4. 重启API服务以加载新模型：" -ForegroundColor Gray
    Write-Host "      powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1" -ForegroundColor DarkGray
}

Write-Host "`n🔄 更新流程完成！" -ForegroundColor Green
