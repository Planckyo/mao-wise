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

## 🔐 配置 LLM 凭据

MAO-Wise 提供安全的 API Key 管理脚本，支持交互式输入、环境变量管理和连通性自检。

### 快速配置

**Windows (PowerShell)**：
```powershell
# 交互式设置 OpenAI Key（安全输入，仅当前会话 + 写入 .env）
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1 -Provider openai

# 直接传入 Key，并写入用户级环境变量（长期生效）
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1 -Provider openai -OpenAIKey "sk-xxxxx" -Scope user

# 配置 Azure OpenAI
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1 -Provider azure

# 删除所有 API Key
powershell -ExecutionPolicy Bypass -File scripts\set_llm_keys.ps1 -Unset
```

**Linux/Mac (Bash)**：
```bash
# 交互式设置 OpenAI Key
./scripts/set_llm_keys.sh --provider openai

# 直接传入 Key，写入用户级环境变量
./scripts/set_llm_keys.sh --provider openai --openai-key "sk-xxxxx" --scope user

# 配置 Azure OpenAI
./scripts/set_llm_keys.sh --provider azure --azure-key "xxx" --azure-endpoint "https://xxx.openai.azure.com/" --azure-deployment "gpt-4"

# 删除所有 API Key
./scripts/set_llm_keys.sh --unset
```

### 功能特性

**🔒 安全管理**：
- 交互式安全输入（不回显、不记录日志）
- API Key 显示时自动掩码（只显示前4后4字符）
- 自动确保 `.env` 文件被 Git 忽略
- 支持删除功能，完全清理环境变量

**⚙️ 灵活配置**：
- 支持 OpenAI 和 Azure OpenAI 两种提供商
- 可选择作用域：`process`（仅当前会话）或 `user`（长期生效）
- 自动写入项目 `.env` 文件和系统环境变量
- 配置后自动进行连通性测试

**🔍 连通性检测**：
- 自动运行 `scripts/test_llm_connectivity.py`
- 显示在线/离线状态和缓存命中情况
- 提供详细的排查建议（网络/代理/Key有效性/配额）

### 安全保证

- ✅ API Key 永不进入 Git 仓库（`.gitignore` 自动配置）
- ✅ 控制台输出仅显示掩码后的 Key
- ✅ 安全字符串处理，内存中不保留明文
- ✅ 支持完全清理，无残留敏感信息

### 环境配置

配置完成后，以下环境变量将被自动设置：

**OpenAI 配置**：
```
OPENAI_API_KEY=sk-your-api-key
LLM_PROVIDER=openai
```

**Azure OpenAI 配置**：
```
AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
LLM_PROVIDER=azure
```

**其他可选环境变量**：
```powershell
# 使用本地文献库（支持中文路径）
$env:MAOWISE_LIBRARY_DIR = "D:\桌面\本地PDF文献知识库"

# 启用详细调试日志
$env:DEBUG_LLM = "true"
```

### 离线兜底模式

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

### 管理端点

**模型状态检查**：
```http
GET /api/maowise/v1/admin/model_status
```

返回所有模型的状态信息：
```json
{
  "timestamp": "2025-08-13T15:30:00",
  "summary": {
    "total_models": 3,
    "found_models": 1,
    "missing_models": 2,
    "overall_status": "degraded"
  },
  "models": {
    "fwd_model": {
      "status": "found",
      "path": "models_ckpt/fwd_v1",
      "mtime": "2025-08-12T18:20:00",
      "size_mb": 45.2,
      "files": [...]
    },
    "gp_corrector": {
      "status": "missing",
      "path": null
    },
    "reward_model": {
      "status": "missing", 
      "path": null
    }
  }
}
```

**热加载机制**：
```http
POST /api/maowise/v1/admin/reload
Content-Type: application/json

{
  "models": ["gp_corrector", "reward_model"],
  "force": false
}
```

**智能错误处理**：
- 模型文件缺失时返回 **409 Conflict**
- 详细错误信息和建议
- `force=true` 可强制重载

**PowerShell调用**：
```powershell
# 检查模型状态
$status = Invoke-RestMethod -Uri "http://localhost:8000/api/maowise/v1/admin/model_status"
Write-Host "模型状态: $($status.summary.overall_status)"

# 手动触发热加载
$body = @{
    models = @("gp_corrector", "reward_model")
    force = $true
} | ConvertTo-Json

try {
    $result = Invoke-RestMethod -Uri "http://localhost:8000/api/maowise/v1/admin/reload" -Method POST -Body $body -ContentType "application/json"
    Write-Host "热加载成功: $($result.status)"
} catch {
    if ($_.Exception.Response.StatusCode -eq 409) {
        Write-Host "模型文件缺失，请先训练模型"
    } else {
        Write-Host "热加载失败: $($_.Exception.Message)"
    }
}
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

## 🚀 生产环境流水线

完整的生产级流水线，支持大规模文献库处理、LLM增强抽取、模型训练。

### 完整流水线

```powershell
# 生产环境完整流水线（需要OpenAI API Key）
powershell -ExecutionPolicy Bypass -File scripts\pipeline_real.ps1 -LibraryDir "D:\文献库" -Online

# 带OCR增强的完整流水线
powershell -ExecutionPolicy Bypass -File scripts\pipeline_real.ps1 -LibraryDir "C:\MAO-Papers" -UseOCR -Online

# 跳过模型训练（仅数据处理和KB构建）
powershell -ExecutionPolicy Bypass -File scripts\pipeline_real.ps1 -LibraryDir "D:\文献库" -DoTrain:$false -Online
```

**流水线步骤**：
1. **环境配置**：OPENAI_API_KEY 检测、文献库验证
2. **文献库注册**：扫描PDF文件，生成 manifest
3. **数据分割**：70/15/15 训练/验证/测试集分割  
4. **LLM增强抽取**：三轮 SlotFill 处理，可选OCR
5. **泄漏检查**：确保数据集间无重复
6. **KB构建**：向量索引构建
7. **模型训练**：BERT多语言基线模型
8. **API启动**：自动服务启动和健康检查
9. **统计报告**：样本数、覆盖率、KB条目数、训练耗时

## 🧪 试运行（20 分钟搞定）

MAO-Wise 提供一键试运行脚本，快速验证系统完整功能并生成详细报告。

### 快速开始

```powershell
# 基础试运行（仅离线模式）
powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1

# 在线模式试运行（需要OpenAI API Key）
powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1 -Online

# 指定本地文献库路径
powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1 -LibraryDir "D:\桌面\本地PDF文献知识库" -Online
```

### 完整流水线

试运行脚本自动执行以下完整流程：

**1. 环境与路径准备**
- 设置UTF-8编码和PYTHONPATH
- 检查/创建.env配置文件
- 配置本地文献库路径（可选）

**2. 构建/校验知识库**
- 准备最小语料数据（如不存在）
- 构建向量索引（如不存在则自动创建）
- 验证KB搜索功能正常

**3. 批量方案生成**
- Silicate体系：生成6条实验方案
- Zirconate体系：生成6条实验方案
- 目标性能：Alpha=0.20, Epsilon=0.80
- 导出到`tasks/batch_*/plans.csv`

**4. 文献对照验证**
- 对最新批次进行Top-3文献匹配
- 生成`validation_report.xlsx`验证报告
- 分析方案的历史先例和参数差异

**5. 服务启动与检查**
- 自动启动API服务（端口8000）
- 自动启动UI服务（端口8501）
- 健康状态检查和服务可用性验证

**6. API功能验证**
- **Clarify流程**：故意缺失电压参数 → 触发专家询问 → 回答"电压420V" → 获得预测结果
- **必答+追问**：缺质量上限约束 → 触发必答问题 → 模糊回答"看情况" → 追问 → 具体回答"≤50g/m²" → 获得带plan_yaml的推荐方案
- **RAG引用验证**：检查解释≤7条且包含[CIT-]引用格式

**7. 实验反馈闭环**
- 创建2条假实验结果（基于最新批次方案）
- 导入到`experiments.parquet`数据库
- 执行预测性能评估（更新前基线）
- 一键模型更新（GP校正器+偏好模型）
- API热加载新模型
- 再次评估生成性能对比报告

**8. UI界面验证**
- 自动截图：预测页、优化页、专家问答页
- 保存到`reports/ui_*.png`
- 验证界面加载和交互正常

**9. 汇总报告生成**
- 详细的Markdown报告：`reports/trial_run_report.md`
- 交互式HTML报告：`reports/trial_run_report.html`
- 包含每步骤耗时、状态、错误信息和成功率统计

### 运行参数

**PowerShell脚本参数**：
```powershell
# 基本参数
-LibraryDir <path>    # 本地文献库目录路径
-Online               # 启用在线模式（需要OPENAI_API_KEY）

# 示例
powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1 -LibraryDir "C:\文献库" -Online
```

**预期耗时**：
- **离线模式**：10-15分钟（无需外部API调用）
- **在线模式**：15-20分钟（包含LLM调用）
- **首次运行**：+5分钟（KB构建和依赖下载）

### 验收标准

试运行成功后将生成以下文件：

**✅ 批量方案**：
- `tasks/batch_*/plans.csv` - Silicate和Zirconate各6条方案
- `tasks/batch_*/validation_report.xlsx` - 文献对照验证报告

**✅ 实验数据**：
- `datasets/experiments/experiments.parquet` - 新增2条实验记录
- `results/trial_results.xlsx` - 假实验数据源文件

**✅ 评估报告**：
- `reports/eval_experiments_*.json` - 更新前后性能评估
- `reports/eval_experiments_*.png` - 预测vs实测图表

**✅ UI截图**：
- `reports/ui_predict.png` - 预测页面截图
- `reports/ui_recommend.png` - 优化页面截图  
- `reports/ui_expert.png` - 专家问答页面截图

**✅ 试运行报告**：
- `reports/trial_run_report.md` - Markdown格式详细报告
- `reports/trial_run_report.html` - HTML格式交互式报告

### 功能验证清单

**🔍 API端点测试**：
- ✅ `/api/maowise/v1/health` - 健康检查
- ✅ `/api/maowise/v1/predict_or_ask` - Clarify缺字段流程
- ✅ `/api/maowise/v1/recommend_or_ask` - 必答+追问流程
- ✅ `/api/maowise/v1/expert/thread/resolve` - QA会话解决
- ✅ `/api/maowise/v1/admin/reload` - 模型热加载

**🧠 智能问答链路**：
- ✅ 缺失关键参数自动生成问题
- ✅ 必答问题红标提示和验证
- ✅ 模糊回答触发追问机制
- ✅ SlotFill结构化信息抽取
- ✅ RAG引用格式和数量控制

**🔄 实验反馈流程**：
- ✅ 实验结果导入和去重
- ✅ 预测性能评估和指标计算
- ✅ GP校正器和偏好模型更新
- ✅ 热加载和性能对比分析

**🖥️ 用户界面**：
- ✅ 预测页面加载和参数输入
- ✅ 优化页面方案生成和显示
- ✅ 专家问答页面交互流程

### 故障排除

**常见问题**：

1. **服务启动失败**
   ```powershell
   # 检查端口占用
   netstat -ano | findstr :8000
   netstat -ano | findstr :8501
   
   # 手动停止服务
   powershell -ExecutionPolicy Bypass -File scripts\stop_services.ps1
   ```

2. **API调用超时**
   - 检查防火墙设置
   - 确认PYTHONPATH和工作目录正确
   - 查看API服务日志

3. **UI截图失败**
   - 安装Chrome浏览器和对应驱动
   - 检查UI服务是否正常启动
   - 网络代理可能影响webdriver下载

4. **模型更新异常**
   - 确保有足够的实验数据（≥2条）
   - 检查模型目录权限
   - 查看PowerShell执行策略设置

**日志查看**：
```powershell
# 查看详细日志
Get-Content .\.logs\*.log -Tail 50

# 实时监控
Get-Content .\.logs\*.log -Wait
```

### 持续集成

将试运行集成到CI/CD流程：

```yaml
# .github/workflows/trial-run.yml
name: Trial Run Test
on: [push, pull_request]

jobs:
  trial-run:
    runs-on: windows-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: pip install -r requirements.txt
    
    - name: Run trial test (offline mode)
      run: |
        powershell -ExecutionPolicy Bypass -File scripts\trial_run.ps1
    
    - name: Upload reports
      uses: actions/upload-artifact@v3
      with:
        name: trial-run-reports
        path: reports/
```

---

## 🚀 Real Run（在线真实试运行）

MAO-Wise 提供完整的在线真实试运行脚本，执行端到端的数据流水线、模型训练、批量方案生成和综合评估，适用于生产环境验证和实际项目部署。

### 核心功能

**完整数据流水线**：
- 本地PDF文献库扫描和注册
- 数据分割（70%训练/15%验证/15%测试）
- LLM增强的结构化抽取
- 数据泄漏检查和质量验证
- 向量知识库构建和索引

**模型训练与评估**：
- 基线文本模型训练（BERT多语言）
- 集成模型状态检查
- 预测性能评估（MAE/RMSE/命中率）
- 模型热加载和状态监控

**批量方案生成**：
- Silicate + Zirconate 双体系各6条方案
- 多目标优化（性能+薄轻+均匀性）
- 文献验证和历史先例分析
- CSV + YAML + README完整导出

### 快速开始

```powershell
# 执行在线真实试运行（需要先设置LLM凭据）
powershell -ExecutionPolicy Bypass -File scripts\real_run.ps1 -LibraryDir "D:\桌面\本地PDF文献知识库"

# 强制重新训练模型
powershell -ExecutionPolicy Bypass -File scripts\real_run.ps1 -LibraryDir "D:\桌面\本地PDF文献知识库" -Force
```

### 执行流程

Real Run 脚本自动执行以下完整流程：

**1. 环境检查与配置**
- 检查 `OPENAI_API_KEY` 环境变量（未设置时提示使用 set_llm_keys.ps1）
- 检查本地PDF文献库目录
- 设置 `MAOWISE_LIBRARY_DIR` 路径

**2. 数据流水线执行**
```powershell
# 自动调用
scripts\pipeline_real.ps1 -Online:$true -DoTrain:$true -LibraryDir $LibraryDir
```
- PDF文献扫描和清单生成
- 数据分割（train/val/test）
- 三轮LLM增强抽取（`--use_llm_slotfill true`）
- 数据泄漏检查和质量验证
- 向量知识库构建
- 基线文本模型训练

**3. 批量方案生成**
```powershell
# 生成12条实验方案
python scripts/generate_batch_plans.py --system silicate --n 6 --notes "real_run"
python scripts/generate_batch_plans.py --system zirconate --n 6 --notes "real_run"
```

**4. 质量验证与评估**
```powershell
# 文献验证
python scripts/validate_recommendations.py --plans (最新batch)/plans.csv --kb datasets/index_store --topk 3

# 预测性能评估
python scripts/evaluate_predictions.py
```

**5. 综合报告生成**
- 模型状态检查（`/admin/model_status`）
- 批量方案质量统计
- 预测性能指标分析
- 生成 `reports/real_run_report.md/html`

### 验收标准

Real Run 成功后将生成以下结果：

**✅ 数据流水线输出**：
- `datasets/data_parsed/corpus.jsonl` - 结构化样本数据
- `datasets/index_store/` - 向量知识库索引
- `models_ckpt/fwd_text_v2/` - 训练完成的文本模型

**✅ 批量方案（12条）**：
- `tasks/batch_*/plans.csv` - 包含多目标字段（mass_proxy, uniformity_penalty, score_total）
- `tasks/batch_*/plans_yaml/` - 详细YAML实验方案
- `tasks/batch_*/README.md` - 批次报告和使用建议

**✅ 质量评估报告**：
- `reports/eval_experiments_*.json` - 预测性能指标
- `reports/recommendation_validation_*.json` - 文献验证结果
- `reports/real_run_report.html` - 综合试运行报告

**✅ 模型状态验证**：
```bash
GET /api/maowise/v1/admin/model_status
# 期望结果：
# - ensemble/表格模型状态显示
# - fwd_text_v2 模型已加载
# - overall_status: "healthy" 或 "degraded"
# - llm_provider: "openai" 或 "local"
# - llm_key_source: "env" 或 "dotenv" 或 "local"
```

**✅ 性能目标**：
- **Epsilon MAE ≤ 0.06** (核心指标)
- **优秀方案比例 ≥ 30%** (mass_proxy < 0.4 且 uniformity_penalty < 0.2)
- **模型加载状态正常** (至少50%模型可用)

### 报告内容

生成的 `reports/real_run_report.html` 包含：

**数据流水线统计**：
- 样本抽取覆盖率
- KB条目数和索引状态
- 模型训练时长和状态

**批量方案分析**：
- Silicate/Zirconate双体系质量对比
- 优秀方案数量和比例统计
- 薄膜/均匀方案分布情况

**预测性能评估**：
- Alpha/Epsilon MAE和命中率
- 按体系分组的详细指标
- 置信度分布和低置信预警

**改进建议**：
- 未达标项目的具体改进方案
- 下一轮优化的参数调整建议
- 数据增强和模型优化方向

### 使用场景

**生产部署验证**：
- 新环境首次部署验证
- 模型更新后的全面测试
- 系统稳定性和性能基准测试

**项目交付验收**：
- 端到端功能完整性验证
- 性能指标达标确认
- 交付物质量评估

**持续集成测试**：
- 定期系统健康检查
- 回归测试和性能监控
- 数据质量和模型性能追踪

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

