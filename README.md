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

## 🧪 端到端测试（E2E）

### 一键测试验收

MAO-Wise 提供完整的端到端测试系统，自动验证所有关键功能：

**Windows 一键运行**：
```powershell
# 在项目根目录执行
.\scripts\run_e2e.ps1
```

**Linux/macOS 手动运行**：
```bash
# 数据准备
python scripts/e2e_data_prep.py

# 执行测试
python scripts/e2e_validate.py
```

### 测试覆盖范围

- ✅ **API服务启动**：自动启动并检查服务健康状态
- ✅ **预测澄清流程**：测试缺失参数时的专家咨询机制
- ✅ **必答问题系统**：验证必答清单和智能追问功能
- ✅ **规则修复引擎**：测试违规参数的自动修复
- ✅ **RAG解释系统**：验证引用生成和解释质量
- ✅ **治理与缓存**：测试速率限制、成本控制和缓存命中

### 测试报告

测试完成后自动生成详细报告：

- **Markdown报告**：`reports/e2e_report.md`
- **HTML报告**：`reports/e2e_report.html`

报告包含：
- 📊 测试通过率和耗时统计
- 📋 每个测试项的详细结果
- 🔧 系统配置和运行模式信息
- 💡 失败项目的修复建议

### 环境配置

**可选环境变量**：
```powershell
# 启用在线LLM功能
$env:OPENAI_API_KEY = "sk-your-api-key"

# 使用本地文献库（支持中文路径）
$env:MAOWISE_LIBRARY_DIR = "D:\桌面\本地PDF文献知识库"

# 启用详细调试日志
$env:DEBUG_LLM = "true"
```

**离线兜底模式**：
- 无需API密钥即可运行完整测试
- 自动使用最小数据夹具进行功能验证
- 确保核心功能在离线环境下正常工作

## 🧬 实验流程测试（批量方案生成）

MAO-Wise 提供批量实验方案生成功能，支持硅酸盐和锆盐两套预设体系，能够一次性生成多个可执行的实验方案并导出为CSV+YAML格式供实验组使用。

### 快速开始

**生成硅酸盐体系方案**：
```powershell
# 生成10条硅酸盐体系方案
python scripts/generate_batch_plans.py --system silicate --n 10 --target-alpha 0.20 --target-epsilon 0.80

# 生成方案并添加备注
python scripts/generate_batch_plans.py --system silicate --n 5 --notes "第1轮联调测试"
```

**生成锆盐体系方案**：
```powershell
# 生成8条锆盐体系方案
python scripts/generate_batch_plans.py --system zirconate --n 8 --target-alpha 0.18 --target-epsilon 0.85

# 使用自定义约束文件
python scripts/generate_batch_plans.py --system zirconate --n 8 --constraints manifests/my_bounds.json
```

### 功能特性

- **🎯 双体系支持**：预设硅酸盐(silicate)和锆盐(zirconate)两套常用体系
- **📊 批量生成**：一次生成N条多样化的实验方案
- **🤖 智能推荐**：调用`/recommend_or_ask` API获取专业建议
- **❓ 专家问答**：自动处理需要专家回答的问题(need_expert=true)
- **📁 完整导出**：生成CSV汇总表格 + 每个方案的YAML配置文件
- **🔍 质量分析**：提供统计摘要和质量评估报告
- **💾 离线兜底**：API不可用时使用模板化方案确保功能可用
- **📋 批次溯源**：自动创建批次编号和完整的生成记录

### 输出结果

生成完成后，会在`tasks/batch_{YYYYMMDD_HHMM}/`目录下创建：

```
tasks/batch_20240112_1430/
├── plans.csv              # 所有方案的汇总表格
├── plans_yaml/            # 每个方案的详细YAML配置
│   ├── batch_20240112_1430_plan_001.yaml
│   ├── batch_20240112_1430_plan_002.yaml
│   └── ...
├── README.md              # 批次统计报告
└── (如有专家问题) manifests/pending_questions_*.json
```

**CSV文件包含字段**：
- `plan_id`: 方案唯一标识
- `batch_id`: 批次编号
- `system`: 体系类型(silicate/zirconate)
- `alpha`: 预测热扩散系数
- `epsilon`: 预测发射率
- `confidence`: 置信度
- `hard_constraints_passed`: 是否通过硬约束
- `rule_penalty`: 规则惩罚分数
- `reward_score`: 奖励分数
- `citations_count`: 引用文献数量
- `status`: 状态(success/pending_expert/failed)

### 预设体系配置

系统内置两套完整的体系预设，定义在`maowise/config/presets.yaml`：

**硅酸盐体系**：
- 基于Na2SiO3的碱性电解液
- 电压范围：200-520V
- 电流密度：5-15 A/dm²
- 允许添加剂：Na2SiO3, KOH, KF等

**锆盐体系**：
- 基于K2ZrF6的氟化物电解液
- 电压范围：180-500V
- 电流密度：4-12 A/dm²
- 允许添加剂：K2ZrF6, Na2SiO3, KOH等

### 高级用法

**自定义约束边界**：
```json
{
  "voltage_V": [250, 450],
  "current_density_Adm2": [6, 12],
  "frequency_Hz": [300, 1000],
  "duty_cycle_pct": [25, 40],
  "time_min": [8, 25]
}
```

**命令行参数**：
```powershell
python scripts/generate_batch_plans.py \
  --system silicate \           # 体系类型
  --n 15 \                     # 生成方案数
  --target-alpha 0.22 \        # 目标热扩散系数
  --target-epsilon 0.85 \      # 目标发射率
  --seed 123 \                 # 随机种子
  --constraints my_bounds.json \ # 自定义约束
  --notes "优化实验第2轮" \      # 批次备注
  --api-base http://localhost:8000 \ # API地址
  --timeout 60                 # 请求超时时间
```

### 质量保障

生成的实验方案具有以下质量保障：

- **硬约束验证**：确保参数在设备和安全限制内
- **多样性保证**：使用随机种子确保方案的多样性
- **文献支撑**：每个方案都有相关文献引用
- **专家审查**：复杂问题自动标记为待专家回答
- **统计分析**：提供通过率、置信度等质量指标

### 测试验证

运行批量方案生成器的测试：
```powershell
# 运行完整测试套件
python -m pytest tests/test_generate_batch_plans.py -v

# 测试特定功能
python -m pytest tests/test_generate_batch_plans.py::TestBatchPlanGenerator::test_generate_batch_success -v
```

---

## 快速开始（本地开发）

1) 安装依赖（Windows 需额外安装 Tesseract OCR 与 Java（用于 Tabula，可选））

**方法一：开发包安装（推荐）**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -e .
```

**方法二：传统依赖安装**
```bash
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

