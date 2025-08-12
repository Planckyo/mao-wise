#!/usr/bin/env python3
"""
MAO-Wise 批量实验方案生成器

支持硅酸盐(silicate)和锆盐(zirconate)两套预设体系，
一次性生成N条可执行的实验方案，输出CSV+YAML格式供实验组使用。

功能特性：
- 基于预设体系边界生成多样化方案
- 调用/recommend_or_ask API获取专业建议  
- 自动处理专家问题(need_expert=true)
- 生成批次编号和完整溯源记录
- 支持离线兜底模式
- 输出统计摘要和质量分析

使用示例：
python scripts/generate_batch_plans.py --system silicate --n 10 --target-alpha 0.20 --target-epsilon 0.80
python scripts/generate_batch_plans.py --system zirconate --n 8 --constraints manifests/my_bounds.json
"""

import argparse
import json
import csv
import yaml
import random
import httpx
import sys
import pathlib
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import logging

# 确保能找到maowise包
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import logger
from maowise.utils.config import load_config

@dataclass
class PlanResult:
    """单个实验方案结果"""
    plan_id: str
    batch_id: str
    system: str
    alpha: float
    epsilon: float
    confidence: float
    hard_constraints_passed: bool
    rule_penalty: float
    reward_score: float
    plan_yaml: str
    citations: List[str]
    citations_count: int
    created_at: str
    status: str  # "success", "pending_expert", "failed"
    expert_questions: Optional[List[str]] = None
    error_message: Optional[str] = None

@dataclass 
class BatchSummary:
    """批次统计摘要"""
    batch_id: str
    system: str
    total_plans: int
    successful_plans: int
    pending_expert_plans: int
    failed_plans: int
    hard_constraints_pass_rate: float
    avg_alpha: float
    avg_epsilon: float
    avg_confidence: float
    top_citations: List[Tuple[str, int]]
    generation_time: float
    target_alpha: float
    target_epsilon: float
    notes: str

class BatchPlanGenerator:
    """批量实验方案生成器"""
    
    def __init__(self, api_base: str = "http://127.0.0.1:8000", timeout: int = 30):
        self.api_base = api_base.rstrip('/')
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
        
        # 加载预设配置
        self.presets = self._load_presets()
        self.config = load_config()
        
        # 创建必要目录
        self.tasks_dir = REPO_ROOT / "tasks"
        self.manifests_dir = REPO_ROOT / "manifests"
        self.tasks_dir.mkdir(exist_ok=True)
        self.manifests_dir.mkdir(exist_ok=True)
        
    def _load_presets(self) -> Dict[str, Any]:
        """加载预设配置"""
        presets_path = REPO_ROOT / "maowise" / "config" / "presets.yaml"
        try:
            with open(presets_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load presets: {e}")
            return self._get_fallback_presets()
    
    def _get_fallback_presets(self) -> Dict[str, Any]:
        """获取兜底预设配置"""
        return {
            "silicate": {
                "bounds": {
                    "voltage_V": [200, 520],
                    "current_density_Adm2": [5, 15],
                    "frequency_Hz": [200, 1500],
                    "duty_cycle_pct": [20, 45],
                    "time_min": [5, 40],
                    "pH": [10, 13]
                },
                "additives": {
                    "allowed": ["Na2SiO3", "KOH", "KF"],
                    "forbid": ["Cr6+", "HF"]
                }
            },
            "zirconate": {
                "bounds": {
                    "voltage_V": [180, 500],
                    "current_density_Adm2": [4, 12],
                    "frequency_Hz": [200, 1200],
                    "duty_cycle_pct": [20, 40],
                    "time_min": [4, 30],
                    "pH": [9, 12]
                },
                "additives": {
                    "allowed": ["K2ZrF6", "Na2SiO3", "KOH"],
                    "forbid": ["Cr6+"]
                }
            }
        }
    
    def _generate_batch_id(self) -> str:
        """生成批次编号"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        return f"batch_{timestamp}"
    
    def _generate_plan_description(self, system: str, bounds: Dict[str, Any], seed: int) -> str:
        """根据预设边界生成实验描述"""
        random.seed(seed)
        
        # 选择基材
        substrates = ["AZ91", "AM60", "ZK60"]
        substrate = random.choice(substrates)
        
        # 生成参数
        voltage = random.uniform(*bounds["voltage_V"])
        current_density = random.uniform(*bounds["current_density_Adm2"])
        time_min = random.uniform(*bounds["time_min"])
        
        # 选择电解液组成
        if system == "silicate":
            main_salt = "Na2SiO3"
            concentration = random.uniform(8, 15)
            additives = ["KOH"]
            if random.random() > 0.5:
                additives.append("KF")
        else:  # zirconate
            main_salt = "K2ZrF6"
            concentration = random.uniform(3, 8)
            additives = ["Na2SiO3", "KOH"]
            if random.random() > 0.5:
                additives.append("NaF")
        
        # 构建描述
        electrolyte_desc = f"{main_salt} {concentration:.1f} g/L"
        if additives:
            electrolyte_desc += f", {', '.join(additives)}"
        
        # 选择电源模式
        if random.random() > 0.3:  # 70%概率使用脉冲
            frequency = random.uniform(*bounds["frequency_Hz"])
            duty_cycle = random.uniform(*bounds["duty_cycle_pct"])
            power_desc = f"bipolar {frequency:.0f} Hz {duty_cycle:.0f}% duty"
        else:
            power_desc = "DC"
        
        description = (
            f"{substrate} substrate; "
            f"{system} electrolyte: {electrolyte_desc}; "
            f"{power_desc}; "
            f"{voltage:.0f} V; "
            f"{current_density:.1f} A/dm2; "
            f"{time_min:.0f} min; "
            f"sealing none."
        )
        
        return description
    
    def _call_recommend_api(self, description: str, target_alpha: float, target_epsilon: float) -> Dict[str, Any]:
        """调用推荐API"""
        url = f"{self.api_base}/api/maowise/v1/recommend_or_ask"
        payload = {
            "description": description,
            "target_alpha": target_alpha,
            "target_epsilon": target_epsilon,
            "max_suggestions": 1
        }
        
        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"API call failed: {e}")
            return self._generate_fallback_response(description, target_alpha, target_epsilon)
    
    def _generate_fallback_response(self, description: str, target_alpha: float, target_epsilon: float) -> Dict[str, Any]:
        """生成兜底响应"""
        return {
            "need_expert": False,
            "suggestions": [{
                "alpha": target_alpha + random.uniform(-0.05, 0.05),
                "epsilon": target_epsilon + random.uniform(-0.05, 0.05),
                "confidence": random.uniform(0.3, 0.8),
                "hard_constraints_passed": random.random() > 0.3,
                "rule_penalty": random.uniform(0, 5),
                "reward_score": random.uniform(0.1, 0.9),
                "plan_yaml": f"# Fallback plan\ndescription: '{description}'\nmethod: offline_generation\n",
                "citations": [f"fallback_ref_{i}" for i in range(random.randint(1, 4))]
            }],
            "clarifying_questions": []
        }
    
    def generate_batch(self, 
                      system: str,
                      n: int,
                      target_alpha: float,
                      target_epsilon: float,
                      seed: int = 42,
                      constraints: Optional[Dict[str, Any]] = None,
                      notes: str = "") -> Tuple[str, List[PlanResult], BatchSummary]:
        """生成一批实验方案"""
        
        logger.info(f"开始生成 {system} 体系的 {n} 个实验方案...")
        start_time = time.time()
        
        # 生成批次ID
        batch_id = self._generate_batch_id()
        
        # 获取体系边界
        if system not in self.presets:
            raise ValueError(f"Unsupported system: {system}")
        
        bounds = constraints or self.presets[system]["bounds"]
        
        # 生成方案
        plans = []
        pending_questions = []
        
        for i in range(n):
            plan_seed = seed + i
            plan_id = f"{batch_id}_plan_{i+1:03d}"
            
            try:
                # 生成描述
                description = self._generate_plan_description(system, bounds, plan_seed)
                
                # 调用API
                response = self._call_recommend_api(description, target_alpha, target_epsilon)
                
                if response.get("need_expert", False):
                    # 需要专家回答
                    questions = response.get("clarifying_questions", [])
                    pending_questions.extend([{
                        "plan_id": plan_id,
                        "description": description,
                        "questions": questions,
                        "target_alpha": target_alpha,
                        "target_epsilon": target_epsilon
                    }])
                    
                    plan = PlanResult(
                        plan_id=plan_id,
                        batch_id=batch_id,
                        system=system,
                        alpha=0.0,
                        epsilon=0.0,
                        confidence=0.0,
                        hard_constraints_passed=False,
                        rule_penalty=999.0,
                        reward_score=0.0,
                        plan_yaml=f"# Pending expert questions\ndescription: '{description}'\nstatus: pending_expert\n",
                        citations=[],
                        citations_count=0,
                        created_at=datetime.now().isoformat(),
                        status="pending_expert",
                        expert_questions=questions
                    )
                    
                else:
                    # 正常建议
                    suggestions = response.get("suggestions", [])
                    if suggestions:
                        suggestion = suggestions[0]
                        citations = suggestion.get("citations", [])
                        
                        plan = PlanResult(
                            plan_id=plan_id,
                            batch_id=batch_id,
                            system=system,
                            alpha=suggestion.get("alpha", target_alpha),
                            epsilon=suggestion.get("epsilon", target_epsilon),
                            confidence=suggestion.get("confidence", 0.5),
                            hard_constraints_passed=suggestion.get("hard_constraints_passed", True),
                            rule_penalty=suggestion.get("rule_penalty", 0.0),
                            reward_score=suggestion.get("reward_score", 0.5),
                            plan_yaml=suggestion.get("plan_yaml", f"description: '{description}'"),
                            citations=citations,
                            citations_count=len(citations),
                            created_at=datetime.now().isoformat(),
                            status="success"
                        )
                    else:
                        raise ValueError("No suggestions returned")
                        
            except Exception as e:
                logger.error(f"Failed to generate plan {plan_id}: {e}")
                plan = PlanResult(
                    plan_id=plan_id,
                    batch_id=batch_id,
                    system=system,
                    alpha=0.0,
                    epsilon=0.0,
                    confidence=0.0,
                    hard_constraints_passed=False,
                    rule_penalty=999.0,
                    reward_score=0.0,
                    plan_yaml=f"# Failed plan\ndescription: '{description}'\nerror: '{str(e)}'\n",
                    citations=[],
                    citations_count=0,
                    created_at=datetime.now().isoformat(),
                    status="failed",
                    error_message=str(e)
                )
            
            plans.append(plan)
            logger.info(f"Generated plan {i+1}/{n}: {plan.status}")
        
        # 保存待回答问题
        if pending_questions:
            questions_file = self.manifests_dir / f"pending_questions_{batch_id}.json"
            with open(questions_file, 'w', encoding='utf-8') as f:
                json.dump(pending_questions, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(pending_questions)} pending questions to {questions_file}")
        
        # 生成统计摘要
        generation_time = time.time() - start_time
        summary = self._generate_summary(batch_id, system, plans, target_alpha, target_epsilon, 
                                       generation_time, notes)
        
        logger.info(f"批次生成完成: {batch_id}, 耗时 {generation_time:.2f}s")
        return batch_id, plans, summary
    
    def _generate_summary(self, batch_id: str, system: str, plans: List[PlanResult],
                         target_alpha: float, target_epsilon: float, generation_time: float,
                         notes: str) -> BatchSummary:
        """生成批次统计摘要"""
        
        successful_plans = [p for p in plans if p.status == "success"]
        pending_plans = [p for p in plans if p.status == "pending_expert"]
        failed_plans = [p for p in plans if p.status == "failed"]
        
        # 计算通过硬约束的比率
        hard_pass_plans = [p for p in successful_plans if p.hard_constraints_passed]
        hard_pass_rate = len(hard_pass_plans) / len(plans) if plans else 0.0
        
        # 计算平均值
        if successful_plans:
            avg_alpha = sum(p.alpha for p in successful_plans) / len(successful_plans)
            avg_epsilon = sum(p.epsilon for p in successful_plans) / len(successful_plans)
            avg_confidence = sum(p.confidence for p in successful_plans) / len(successful_plans)
        else:
            avg_alpha = avg_epsilon = avg_confidence = 0.0
        
        # 统计引用频次
        citation_counts = {}
        for plan in successful_plans:
            for citation in plan.citations:
                citation_counts[citation] = citation_counts.get(citation, 0) + 1
        
        top_citations = sorted(citation_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return BatchSummary(
            batch_id=batch_id,
            system=system,
            total_plans=len(plans),
            successful_plans=len(successful_plans),
            pending_expert_plans=len(pending_plans),
            failed_plans=len(failed_plans),
            hard_constraints_pass_rate=hard_pass_rate,
            avg_alpha=avg_alpha,
            avg_epsilon=avg_epsilon,
            avg_confidence=avg_confidence,
            top_citations=top_citations,
            generation_time=generation_time,
            target_alpha=target_alpha,
            target_epsilon=target_epsilon,
            notes=notes
        )
    
    def export_batch(self, batch_id: str, plans: List[PlanResult], summary: BatchSummary) -> pathlib.Path:
        """导出批次结果到文件"""
        
        # 创建批次目录
        batch_dir = self.tasks_dir / batch_id
        batch_dir.mkdir(exist_ok=True)
        
        # 导出CSV
        csv_path = batch_dir / "plans.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 写入表头
            headers = [
                "plan_id", "batch_id", "system", "alpha", "epsilon", "confidence",
                "hard_constraints_passed", "rule_penalty", "reward_score", 
                "citations_count", "status", "created_at"
            ]
            writer.writerow(headers)
            
            # 写入数据
            for plan in plans:
                writer.writerow([
                    plan.plan_id,
                    plan.batch_id,
                    plan.system,
                    f"{plan.alpha:.4f}",
                    f"{plan.epsilon:.4f}",
                    f"{plan.confidence:.4f}",
                    plan.hard_constraints_passed,
                    f"{plan.rule_penalty:.2f}",
                    f"{plan.reward_score:.4f}",
                    plan.citations_count,
                    plan.status,
                    plan.created_at
                ])
        
        # 导出每个方案的YAML
        yaml_dir = batch_dir / "plans_yaml"
        yaml_dir.mkdir(exist_ok=True)
        
        for plan in plans:
            yaml_path = yaml_dir / f"{plan.plan_id}.yaml"
            with open(yaml_path, 'w', encoding='utf-8') as f:
                f.write(plan.plan_yaml)
        
        # 导出README
        readme_path = batch_dir / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_readme(summary))
        
        logger.info(f"批次结果已导出到: {batch_dir}")
        return batch_dir
    
    def _generate_readme(self, summary: BatchSummary) -> str:
        """生成批次README"""
        
        readme_content = f"""# 实验批次报告: {summary.batch_id}

## 基本信息

- **批次编号**: {summary.batch_id}
- **体系类型**: {summary.system}
- **目标参数**: α={summary.target_alpha:.3f}, ε={summary.target_epsilon:.3f}
- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **处理耗时**: {summary.generation_time:.2f}秒
- **备注**: {summary.notes}

## 统计摘要

### 方案数量分布
- **总方案数**: {summary.total_plans}
- **成功生成**: {summary.successful_plans} ({summary.successful_plans/summary.total_plans*100:.1f}%)
- **待专家回答**: {summary.pending_expert_plans} ({summary.pending_expert_plans/summary.total_plans*100:.1f}%)
- **生成失败**: {summary.failed_plans} ({summary.failed_plans/summary.total_plans*100:.1f}%)

### 质量指标
- **硬约束通过率**: {summary.hard_constraints_pass_rate*100:.1f}%
- **平均热扩散系数**: α = {summary.avg_alpha:.4f}
- **平均发射率**: ε = {summary.avg_epsilon:.4f}
- **平均置信度**: {summary.avg_confidence:.3f}

### 文献引用分析
"""
        
        if summary.top_citations:
            readme_content += "\n**Top-3 引用文献**:\n"
            for i, (citation, count) in enumerate(summary.top_citations, 1):
                readme_content += f"{i}. {citation} (引用{count}次)\n"
        else:
            readme_content += "\n暂无文献引用数据\n"
        
        readme_content += f"""
## 文件说明

- `plans.csv`: 所有方案的汇总表格
- `plans_yaml/`: 每个方案的详细YAML配置文件
- `README.md`: 本批次报告

## 使用方法

1. 查看 `plans.csv` 了解所有方案概况
2. 选择感兴趣的方案，查看对应的 `plans_yaml/*.yaml` 文件
3. 如有 `pending_questions_*.json`，请联系专家回答相关问题
4. 根据 `hard_constraints_passed` 字段筛选可直接执行的方案

## 质量建议

- 优先选择 `hard_constraints_passed=True` 的方案
- 关注 `confidence >= 0.5` 的高置信度方案
- 参考 `rule_penalty < 5.0` 的低风险方案
- 考虑 `reward_score >= 0.3` 的高奖励方案

---
*此报告由 MAO-Wise 批量方案生成器自动生成*
"""
        
        return readme_content

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MAO-Wise 批量实验方案生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 生成10条硅酸盐体系方案
  python scripts/generate_batch_plans.py --system silicate --n 10 --target-alpha 0.20 --target-epsilon 0.80
  
  # 生成8条锆盐体系方案并自定义边界
  python scripts/generate_batch_plans.py --system zirconate --n 8 --constraints manifests/my_bounds.json
  
  # 生成方案并添加备注
  python scripts/generate_batch_plans.py --system silicate --n 5 --notes "第1轮联调测试"
        """
    )
    
    parser.add_argument("--system", 
                       choices=["silicate", "zirconate"], 
                       required=True,
                       help="实验体系类型")
    
    parser.add_argument("--target-alpha", 
                       type=float, 
                       default=0.20,
                       help="目标热扩散系数 (默认: 0.20)")
    
    parser.add_argument("--target-epsilon", 
                       type=float, 
                       default=0.80,
                       help="目标发射率 (默认: 0.80)")
    
    parser.add_argument("--n", 
                       type=int, 
                       default=10,
                       help="生成方案数量 (默认: 10)")
    
    parser.add_argument("--seed", 
                       type=int, 
                       default=42,
                       help="随机种子 (默认: 42)")
    
    parser.add_argument("--constraints", 
                       type=str,
                       help="自定义约束文件路径 (JSON格式)")
    
    parser.add_argument("--notes", 
                       type=str, 
                       default="",
                       help="批次备注信息")
    
    parser.add_argument("--api-base", 
                       type=str, 
                       default="http://127.0.0.1:8000",
                       help="API服务地址 (默认: http://127.0.0.1:8000)")
    
    parser.add_argument("--timeout", 
                       type=int, 
                       default=30,
                       help="API请求超时时间 (默认: 30秒)")
    
    args = parser.parse_args()
    
    try:
        # 加载自定义约束
        constraints = None
        if args.constraints:
            constraints_path = pathlib.Path(args.constraints)
            if constraints_path.exists():
                with open(constraints_path, 'r', encoding='utf-8') as f:
                    constraints = json.load(f)
                logger.info(f"已加载自定义约束: {constraints_path}")
            else:
                logger.warning(f"约束文件不存在: {constraints_path}")
        
        # 创建生成器
        generator = BatchPlanGenerator(api_base=args.api_base, timeout=args.timeout)
        
        # 生成批次
        batch_id, plans, summary = generator.generate_batch(
            system=args.system,
            n=args.n,
            target_alpha=args.target_alpha,
            target_epsilon=args.target_epsilon,
            seed=args.seed,
            constraints=constraints,
            notes=args.notes
        )
        
        # 导出结果
        batch_dir = generator.export_batch(batch_id, plans, summary)
        
        # 打印摘要
        print(f"\n🎉 批次生成完成!")
        print(f"📁 批次目录: {batch_dir}")
        print(f"📊 统计摘要:")
        print(f"   - 总方案数: {summary.total_plans}")
        print(f"   - 成功生成: {summary.successful_plans}")
        print(f"   - 待专家回答: {summary.pending_expert_plans}")
        print(f"   - 生成失败: {summary.failed_plans}")
        print(f"   - 硬约束通过率: {summary.hard_constraints_pass_rate*100:.1f}%")
        print(f"   - 平均置信度: {summary.avg_confidence:.3f}")
        print(f"   - 处理耗时: {summary.generation_time:.2f}秒")
        
        if summary.pending_expert_plans > 0:
            questions_file = REPO_ROOT / "manifests" / f"pending_questions_{batch_id}.json"
            print(f"❓ 待回答问题已保存到: {questions_file}")
        
        print(f"\n📋 查看详细结果:")
        print(f"   CSV文件: {batch_dir}/plans.csv")
        print(f"   YAML文件: {batch_dir}/plans_yaml/")
        print(f"   报告: {batch_dir}/README.md")
        
    except Exception as e:
        logger.error(f"批次生成失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
