# MAO-Wise 1.0 (Micro-Arc Oxidation Thermal-Control Coating Optimizer)

![ci](https://github.com/Planckyo/mao-wise/actions/workflows/ci.yml/badge.svg)
![kb-smoke](https://github.com/Planckyo/mao-wise/actions/workflows/kb-smoke.yml/badge.svg)

MAO-Wise 是一个端到端的微弧氧化工艺知识与优化系统，包含：
- PDF → 结构化样本抽取（可追溯）
- 向量知识库（FAISS/NumPy 备选）
- 正向预测（文本→α/ε）
- 反向优化（目标→可执行多方案）
- FastAPI 服务与 Streamlit UI
- 数据/模型版本化与基础 MLOps（DVC/MLflow）

## 目录结构

```
mao-wise/
├─ apps/
│  ├─ api/                  # FastAPI 服务
│  └─ ui/                   # Streamlit 前端
├─ maowise/
│  ├─ config/               # 配置与schema
│  ├─ dataflow/             # 模块一：PDF抽取→结构化
│  ├─ kb/                   # 模块四：向量库
│  ├─ models/               # 模块二：正向模型
│  ├─ optimize/             # 模块三：反向优化
│  ├─ utils/                # 公共工具、日志、校验
│  └─ api_schemas/          # Pydantic请求/响应模型
├─ datasets/                # 本地数据区（gitignore）
│  ├─ data_raw/             # PDF/原始数据
│  ├─ data_parsed/          # 解析中间件
│  ├─ index_store/          # 向量索引/通道
│  └─ versions/             # 结构化样本&发布数据集
├─ models_ckpt/             # 训练后的模型权重（gitignore）
├─ scripts/                 # 训练/评测/构建脚本
├─ tests/                   # 单元与端到端测试
├─ requirements.txt
├─ .env.example
├─ README.md
└─ LICENSE
```

## 快速开始（本地开发）

1) 安装依赖（Windows 需额外安装 Tesseract OCR 与 Java（用于 Tabula，可选））

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) 准备数据：将 PDF 放入 `datasets/data_raw/`

3) 抽取 → 样本

```
python -m maowise.dataflow.ingest --pdf_dir datasets/data_raw --out_dir datasets/versions/maowise_ds_v1
```

4) 构建知识库

```
python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store
```

5) 训练正向模型

```
python -m maowise.models.train_fwd --samples datasets/versions/maowise_ds_v1/samples.parquet \
  --model_name bert-base-multilingual-cased --out_dir models_ckpt/fwd_v1 --epochs 8 --lr 2e-5 --batch 16
```

6) 启动 API 与 UI

```
uvicorn apps.api.main:app --reload
streamlit run apps/ui/app.py
```

### 快速命令（开发）
- 初始化依赖与钩子：`make init`
- 代码检查（格式化+lint+单测）：`make check`

### 本地库接入（Windows 中文路径）
```
chcp 65001 > $null
$env:MAOWISE_LIBRARY_DIR="D:\桌面\本地PDF文献知识库"
powershell -ExecutionPolicy Bypass -File scripts\link_local_library.ps1 -UseOCR:$false -DoTrain:$false
# 如需立即训练：
# powershell -ExecutionPolicy Bypass -File scripts\link_local_library.ps1 -UseOCR:$false -DoTrain:$true
```

## 本地一键运行（Windows + 中文路径）

> 需要安装依赖：`pip install -r requirements.txt`；若使用 OCR/Tabula，请额外安装 Tesseract/Java。

```powershell
# 1) 写入 .env（可修改路径）
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_env.ps1 -LibraryDir "D:\桌面\本地PDF文献知识库"

# 2) 一键接入库（不训练）
powershell -ExecutionPolicy Bypass -File scripts\pipeline_local.ps1 -UseOCR:$false -DoTrain:$false

# 3) （可选）开始训练与评测
powershell -ExecutionPolicy Bypass -File scripts\pipeline_local.ps1 -DoTrain:$true

# 4) 启动 API + UI 并自测
powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1

# 5) 需要时停止服务
powershell -ExecutionPolicy Bypass -File scripts\stop_services.ps1
```

常见产物：
- `manifests/manifest_{train,val,test}.csv`, `split_meta.json`
- `datasets/versions/maowise_ds_v1/samples.parquet`（带 split）
- `datasets/data_parsed/corpus.jsonl`，`datasets/index_store/`
- 训练产物：`models_ckpt/fwd_v1/`，报告在 `reports/`

### 数据与 DVC 治理
- 不要将大文件（PDF/模型权重/索引）直接提交到 Git。
- 使用 DVC 追踪数据与索引（远端地址通过 `DVC_REMOTE_URL` 配置）。

## API 端点
- POST `/api/maowise/v1/ingest`
- POST `/api/maowise/v1/predict`
- POST `/api/maowise/v1/recommend`
- POST `/api/maowise/v1/kb/search`

## 备注
- 首版优先打通端到端最小可用路径；精度与鲁棒性随数据迭代。
- 置信度来源于相似案例的相似度，仅供排序与提示。
- DVC/MLflow 钩子就绪，可按需启用。

