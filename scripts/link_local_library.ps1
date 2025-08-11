# scripts/link_local_library.ps1
param(
  [string]$LibraryDir = $env:MAOWISE_LIBRARY_DIR,
  [string]$Ratio = "0.7,0.15,0.15",
  [int]$Seed = 42,
  [string]$VersionDir = "datasets/versions/maowise_ds_v1",
  [string]$CorpusPath = "datasets/data_parsed/corpus.jsonl",
  [switch]$UseOCR = $false,
  [switch]$DoTrain = $false
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null

function OK($m){ Write-Host "✅ $m" -ForegroundColor Green }
function INFO($m){ Write-Host "ℹ️  $m" -ForegroundColor Cyan }
function DIE($m){ Write-Host "❌ $m" -ForegroundColor Red; exit 1 }

if (-not $LibraryDir) { DIE "缺少 LibraryDir。可在 .env 设置 MAOWISE_LIBRARY_DIR 或通过参数传入。" }
$LibraryDir = (Resolve-Path $LibraryDir).Path

# 1) 生成清单
INFO "注册本地库：$LibraryDir"
python scripts/register_library.py --pdf_dir "$LibraryDir" --out manifests/library_manifest.csv
OK "manifest: manifests/library_manifest.csv"

# 2) 分割
$r = $Ratio.Split(",") | ForEach-Object { $_.Trim() }
if ($r.Length -ne 3) { DIE "Ratio 需为 '0.7,0.15,0.15' 格式" }
python scripts/make_split.py --manifest manifests/library_manifest.csv --ratio $r[0] $r[1] $r[2] --seed $Seed --out_dir manifests
OK "split: manifests/manifest_train.csv / val.csv / test.csv"

# 3) ingest（三次，写入 split）
$ocr = if ($UseOCR) { "true" } else { "false" }
python -m maowise.dataflow.ingest --manifest manifests/manifest_train.csv --split_name train --out_dir $VersionDir --use_ocr $ocr
python -m maowise.dataflow.ingest --manifest manifests/manifest_val.csv   --split_name val   --out_dir $VersionDir --use_ocr $ocr
python -m maowise.dataflow.ingest --manifest manifests/manifest_test.csv  --split_name test  --out_dir $VersionDir --use_ocr $ocr
OK "ingest done -> $VersionDir"

# 4) 泄漏检查
python scripts/check_leakage.py --samples "$VersionDir/samples.parquet"
OK "leakage check passed"

# 5) 构建 KB
python -m maowise.kb.build_index --corpus "$CorpusPath" --out_dir datasets/index_store
OK "KB built: datasets/index_store"

# 6) （可选）训练与评测
if ($DoTrain) {
  INFO "开始训练（DoTrain）"
  python -m maowise.models.train_fwd --samples "$VersionDir/samples.parquet" `
    --model_name bert-base-multilingual-cased --out_dir models_ckpt/fwd_v1 `
    --epochs 8 --lr 2e-5 --batch 16
  OK "训练完成 -> models_ckpt/fwd_v1"
}

OK "全部完成。"

