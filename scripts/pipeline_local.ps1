param(
  [string]$LibraryDir = $env:MAOWISE_LIBRARY_DIR,
  [string]$Ratio = "0.7,0.15,0.15",
  [int]$Seed = 42,
  [switch]$UseOCR = $false,
  [switch]$DoTrain = $false
)
$ErrorActionPreference = "Stop"
chcp 65001 > $null
function OK($m){ Write-Host "✅ $m" -ForegroundColor Green }
function INFO($m){ Write-Host "ℹ️  $m" -ForegroundColor Cyan }
function DIE($m){ Write-Host "❌ $m" -ForegroundColor Red; exit 1 }

# 设置工作目录为仓库根目录
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..  # 切到仓库根

# 设置PYTHONPATH环境变量
$env:PYTHONPATH = (Get-Location).Path

# 检查是否需要安装开发包
if (Test-Path "pyproject.toml") {
    INFO "检测到 pyproject.toml，检查开发包安装..."
    try {
        python -c "import maowise; print('maowise package already available')" 2>$null
        if ($LASTEXITCODE -ne 0) {
            INFO "安装开发包: pip install -e ."
            pip install -e .
            if ($LASTEXITCODE -eq 0) {
                OK "开发包安装成功"
            } else {
                INFO "开发包安装失败，继续使用 PYTHONPATH 方式"
            }
        } else {
            OK "maowise 包已可用"
        }
    } catch {
        INFO "跳过开发包安装检查"
    }
}

if (-not $LibraryDir) { DIE "未设置 MAOWISE_LIBRARY_DIR。先运行 scripts/bootstrap_env.ps1 或传参 -LibraryDir" }
$LibraryDir = (Resolve-Path $LibraryDir).Path

# 1) 注册库
INFO "注册库: $LibraryDir"
python scripts/register_library.py --pdf_dir "$LibraryDir" --out manifests/library_manifest.csv
OK "manifest -> manifests/library_manifest.csv"

# 2) 分割
$r = $Ratio.Split(",") | ForEach-Object { $_.Trim() }
python scripts/make_split.py --manifest manifests/library_manifest.csv --ratio $r[0] $r[1] $r[2] --seed $Seed --out_dir manifests
OK "split -> manifests/manifest_{train,val,test}.csv"

# 3) ingest（三次）
$ocr = if ($UseOCR) { "true" } else { "false" }
python -m maowise.dataflow.ingest --manifest manifests/manifest_train.csv --split_name train --out_dir datasets/versions/maowise_ds_v1 --use_ocr $ocr
python -m maowise.dataflow.ingest --manifest manifests/manifest_val.csv   --split_name val   --out_dir datasets/versions/maowise_ds_v1 --use_ocr $ocr
python -m maowise.dataflow.ingest --manifest manifests/manifest_test.csv  --split_name test  --out_dir datasets/versions/maowise_ds_v1 --use_ocr $ocr
OK "ingest -> datasets/versions/maowise_ds_v1/samples.parquet"

# 4) 泄漏检查
python scripts/check_leakage.py --samples datasets/versions/maowise_ds_v1/samples.parquet
OK "leakage check passed"

# 5) 构建 KB
python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store
OK "KB -> datasets/index_store"

# 6) 可选训练
if ($DoTrain) {
  INFO "开始训练..."
  python -m maowise.models.train_fwd --samples datasets/versions/maowise_ds_v1/samples.parquet `
    --train_split train --val_split val --test_split test `
    --model_name bert-base-multilingual-cased --out_dir models_ckpt/fwd_v1 `
    --epochs 6 --lr 2e-5 --batch 16
  OK "训练完成 -> models_ckpt/fwd_v1; 报告见 reports/"
}
OK "全部完成。"
