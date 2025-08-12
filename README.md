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

## 📚 推荐验证（文献对照）

MAO-Wise 提供推荐验证功能，将批量生成的实验方案与知识库文献进行对照验证，输出历史先例分析、最相近文献和参数差异摘要，确保方案的可靠性和创新性。

### 增强抽取（LLM SlotFill）

首先运行增强抽取，启用LLM SlotFill来提高文献结构化的质量：

```powershell
# 运行增强抽取（启用 LLM slotfill）
python -m maowise.dataflow.ingest --pdf_dir datasets/data_raw --out_dir datasets/versions/maowise_ds_v2 --use_llm_slotfill true

# 重新构建知识库索引
python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store
```

**增强抽取特性**：
- **规则优先**：首先使用规则抽取器处理文本
- **LLM补充**：对缺失槽位使用LLM SlotFill补充
- **来源标记**：在样本元数据中记录`extractor="rules"`或`"rules+llm"`
- **版本隔离**：输出到`maowise_ds_v2`避免覆盖原始数据

### 文献对照验证

对批量方案进行文献对照验证：

```powershell
# 基本验证
python scripts/validate_recommendations.py --plans tasks/batch_20250812_2246/plans.csv --kb datasets/index_store --topk 3

# 自定义参数验证
python scripts/validate_recommendations.py --plans tasks/batch_*/plans.csv --kb datasets/index_store --topk 5 --threshold 0.7

# 指定输出路径
python scripts/validate_recommendations.py --plans tasks/batch_20250812_2246/plans.csv --kb datasets/index_store --output custom_validation.xlsx
```

### 验证功能特性

- **🔍 智能检索**：基于体系+关键电参数构造检索查询
- **📊 相似度匹配**：使用向量相似度和内容匹配双重判断
- **📈 参数差异分析**：计算方案与最相近文献的参数差异百分比
- **📋 分类报告**：按匹配/未匹配状态分别统计和展示
- **📄 多格式导出**：支持Excel和CSV格式的详细报告
- **🎯 质量评估**：提供命中率、平均相似度等质量指标

### 验证结果解读

**输出文件结构**：
```
tasks/batch_20250812_2246/
├── validation_report.xlsx    # 验证报告（Excel格式）
│   ├── Summary              # 验证摘要统计
│   ├── Matched              # 匹配成功的方案
│   └── Unmatched            # 未匹配的方案
└── plans.csv                # 原始方案文件
```

**关键验证指标**：
- `match_found`: 是否找到历史先例（基于相似度≥0.6或体系+2个关键电参数匹配）
- `similarity_score`: 与最相近文献的向量相似度
- `nearest_citations`: 最相近的K个文献片段（包含来源、页码、相似度、摘要）
- `delta_params`: 参数差异百分比（电压、电流密度、频率、占空比、时间）

**匹配判断逻辑**：
1. **相似度阈值**：向量相似度≥0.6（可自定义）
2. **内容匹配**：同时包含体系类型+至少2个关键电参数
3. **体系识别**：
   - 硅酸盐体系：包含"silicate"或"Na2SiO3"
   - 锆盐体系：包含"zirconate"或"K2ZrF6"

### 验证质量评估

**命中率指导**：
- **≥80%**: ✅ 验证结果良好，大部分方案都有历史先例支撑
- **50-80%**: ⚠️ 验证结果一般，建议检查未匹配方案的创新性和可行性
- **<50%**: ❌ 验证结果较差，多数方案缺乏文献支撑，建议重新评估

**参数差异分析**：
- **<10%**: 参数与文献高度一致，可靠性强
- **10-30%**: 参数有一定差异，需要关注风险
- **>30%**: 参数差异较大，属于创新性尝试，需要谨慎验证

### 高级用法

**自定义检索查询**：
验证器会根据方案自动构造查询，优先级：体系类型 > 电压 > 电流密度 > 频率

**批量验证工作流**：
```powershell
# 1. 生成批量方案
python scripts/generate_batch_plans.py --system silicate --n 10 --target-alpha 0.20 --target-epsilon 0.80

# 2. 验证方案可靠性
python scripts/validate_recommendations.py --plans tasks/batch_*/plans.csv --kb datasets/index_store --topk 3

# 3. 分析验证报告
# 查看 validation_report.xlsx 中的匹配情况和参数差异

# 4. 筛选高质量方案
# 优先选择 match_found=True 且 similarity_score>0.7 的方案
```

### 测试验证

运行推荐验证功能的测试：
```powershell
# 运行完整测试套件
python -m pytest tests/test_validate_recommendations.py -v

# 测试特定功能
python -m pytest tests/test_validate_recommendations.py::TestRecommendationValidator::test_validate_batch -v
```

## 🔄 实验评估与一键调优

MAO-Wise 提供完整的实验反馈闭环，支持从实验结果回传到模型自动更新的全流程自动化。

### 快速开始

```powershell
# 1. 导入实验结果
python scripts/record_experiment_results.py --file results/round1_results.xlsx

# 2. 评估预测性能
python scripts/evaluate_predictions.py

# 3. 一键更新模型（含热加载）
powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1 -HotReload:$true
```

### 标准化结果导入

**实验结果模板**：
使用 `manifests/experiment_result_template.csv` 作为标准模板，包含完整的实验参数和测量结果：

```csv
experiment_id,batch_id,plan_id,system,substrate_alloy,electrolyte_components_json,
voltage_V,current_density_Adm2,frequency_Hz,duty_cycle_pct,time_min,temp_C,pH,post_treatment,
measured_alpha,measured_epsilon,hardness_HV,roughness_Ra_um,corrosion_rate_mmpy,notes,reviewer,timestamp
```

**导入实验数据**：
```powershell
# 导入Excel文件
python scripts/record_experiment_results.py --file results/batch_results.xlsx

# 导入CSV文件（预览模式）
python scripts/record_experiment_results.py --file results/round2_results.csv --dry-run

# 查看当前实验数据统计
python scripts/record_experiment_results.py --stats
```

**导入特性**：
- **智能去重**：基于 experiment_id/batch_id/plan_id 三键自动去重
- **数据验证**：自动检查字段完整性和数值范围
- **增量更新**：支持多次导入，自动合并到 `datasets/experiments/experiments.parquet`
- **备份保护**：每次导入自动创建带时间戳的备份文件
- **格式兼容**：支持 CSV 和 Excel (.xlsx/.xls) 格式

### 预测性能评估

**标准评估**：
```powershell
# 基本评估（调用API）
python scripts/evaluate_predictions.py

# 指定API地址
python scripts/evaluate_predictions.py --api-url http://localhost:8000

# 使用自定义实验数据
python scripts/evaluate_predictions.py --experiments-file custom_experiments.parquet
```

**评估指标体系**：
- **回归指标**：MAE (平均绝对误差)、MAPE (平均百分比误差)、RMSE (均方根误差)
- **命中率**：±0.03 和 ±0.05 容差范围内的预测准确率
- **置信度分析**：平均置信度、低置信度样本比例
- **相关性**：预测值与实测值的皮尔逊相关系数
- **分体系统计**：按 silicate/zirconate 体系分别统计性能

**评估输出**：
```
reports/
├── eval_experiments_20250812_1530.json    # 详细评估报告
├── eval_experiments_20250812_1530_pred_vs_true.png      # 预测vs实测散点图
└── eval_experiments_20250812_1530_error_distribution.png # 误差分布直方图
```

### 一键模型更新

**基本更新**：
```powershell
# 标准更新流程
powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1

# 带热加载的更新
powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1 -HotReload:$true

# 自定义参数更新
powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1 -ExperimentsFile "custom.parquet" -ApiUrl "http://prod:8000"
```

**更新流程**：
1. **更新前评估**：生成基线性能报告
2. **残差校正器训练**：使用GP回归校正预测偏差
3. **偏好模型训练**：基于实验质量评分训练奖励模型
4. **更新后评估**：生成改进后性能报告
5. **性能对比**：自动计算前后指标差异
6. **热加载**（可选）：向运行中的API发送模型重载信号

**更新特性**：
- **双模型更新**：同时更新残差校正器和偏好模型
- **性能跟踪**：自动对比更新前后的MAE、命中率等关键指标
- **安全备份**：所有模型文件带时间戳保存到 `models_ckpt/`
- **热加载支持**：无需重启API即可使用新模型
- **错误恢复**：单个模型更新失败不影响其他模型

### 热加载机制

**API端点**：
```http
POST /api/maowise/v1/admin/reload
Content-Type: application/json

{
  "models": ["gp_corrector", "reward_model"],
  "force": false
}
```

**PowerShell调用**：
```powershell
# 手动触发热加载
$body = @{
    models = @("gp_corrector", "reward_model")
    force = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/maowise/v1/admin/reload" -Method POST -Body $body -ContentType "application/json"
```

### 质量评估与改进指导

**性能基准**：
- **优秀**：Alpha MAE < 0.02, Epsilon MAE < 0.05, 命中率(±0.03) > 80%
- **良好**：Alpha MAE < 0.03, Epsilon MAE < 0.08, 命中率(±0.03) > 70%
- **需改进**：Alpha MAE > 0.05, Epsilon MAE > 0.10, 命中率(±0.03) < 60%

**改进策略**：
- **低置信度高**（>30%）：增加训练数据多样性，优化特征工程
- **某体系性能差**：针对性收集该体系实验数据
- **整体MAE偏高**：检查实验数据质量，考虑异常值处理
- **命中率低但相关性高**：调整校正器参数，增强残差建模

### 高级用法

**批量实验工作流**：
```powershell
# 1. 生成实验方案
python scripts/generate_batch_plans.py --system silicate --n 20

# 2. 执行实验（人工）
# ... 实验团队按方案执行实验 ...

# 3. 导入实验结果
python scripts/record_experiment_results.py --file lab_results_batch1.xlsx

# 4. 评估当前模型性能
python scripts/evaluate_predictions.py --output reports/eval_before_round2.json

# 5. 更新模型
powershell -ExecutionPolicy Bypass -File scripts\update_from_feedback.ps1 -HotReload:$true

# 6. 验证改进效果
python scripts/evaluate_predictions.py --output reports/eval_after_round2.json
```

**持续改进循环**：
```powershell
# 设置定期评估任务
$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
$action = New-ScheduledTaskAction -Execute "python" -Argument "scripts/evaluate_predictions.py --output reports/daily_eval.json"
Register-ScheduledTask -TaskName "MAOWise_DailyEval" -Trigger $trigger -Action $action
```

### 测试验证

运行实验反馈流程的完整测试：
```powershell
# 运行完整测试套件
python -m pytest tests/test_eval_and_update.py -v

# 测试特定功能
python -m pytest tests/test_eval_and_update.py::TestExperimentFeedbackFlow::test_end_to_end_workflow -v

# 测试性能指标计算
python -m pytest tests/test_eval_and_update.py::TestPerformanceMetrics::test_metrics_calculation -v
```

**测试覆盖**：
- 实验数据导入和去重
- 预测评估和指标计算
- 模型更新流程模拟
- API热加载端点
- 端到端工作流验证

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

