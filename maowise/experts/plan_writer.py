from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..llm.client import llm_chat
from ..llm.rag import Snippet, build_context
from ..llm.jsonio import expect_schema
from ..utils.logger import logger


def load_plan_writer_prompt() -> Dict[str, Any]:
    """加载工艺卡生成的提示模板"""
    prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / "plan_writer.yaml"
    try:
        with prompt_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load plan_writer prompt: {e}")
        return {}


def format_solution_description(solution: Dict[str, Any]) -> str:
    """格式化方案描述"""
    parts = []
    
    # 基体信息
    if 'substrate_alloy' in solution:
        parts.append(f"{solution['substrate_alloy']}基体")
    
    # 电解液信息
    if 'electrolyte_family' in solution:
        parts.append(f"{solution['electrolyte_family']}电解液")
    
    # 电解液成分
    if 'electrolyte_components_json' in solution:
        components = solution['electrolyte_components_json']
        if isinstance(components, dict):
            comp_parts = [f"{k} {v}" for k, v in components.items()]
            parts.append(f"({', '.join(comp_parts)})")
    
    # 电压
    if 'voltage_V' in solution:
        parts.append(f"{solution['voltage_V']}V")
    
    # 电流密度
    if 'current_density_A_dm2' in solution:
        parts.append(f"{solution['current_density_A_dm2']}A/dm²")
    
    # 脉冲参数
    mode_parts = []
    if 'mode' in solution:
        mode_parts.append(solution['mode'])
    if 'frequency_Hz' in solution:
        mode_parts.append(f"{solution['frequency_Hz']}Hz")
    if 'duty_cycle_pct' in solution:
        mode_parts.append(f"{solution['duty_cycle_pct']}%占空比")
    if mode_parts:
        parts.append(' '.join(mode_parts))
    
    # 时间
    if 'time_min' in solution:
        parts.append(f"处理时间{solution['time_min']}分钟")
    
    # 后处理
    if 'post_treatment' in solution and solution['post_treatment'] != '无':
        parts.append(solution['post_treatment'])
    
    return "，".join(parts)


def build_plan_writer_prompt(
    solution: Dict[str, Any],
    context_snippets: List[Snippet]
) -> List[Dict[str, str]]:
    """构建工艺卡生成的完整提示"""
    prompt_template = load_plan_writer_prompt()
    
    system_prompt = prompt_template.get("system", "")
    instruction = prompt_template.get("instruction", "")
    schema_info = prompt_template.get("schema", "")
    few_shot_examples = prompt_template.get("few_shot", [])
    
    # 格式化方案描述
    solution_desc = format_solution_description(solution)
    
    # 格式化文献片段
    snippets_parts = []
    for i, snippet in enumerate(context_snippets, 1):
        snippets_parts.append(f"- [CIT-{i}] {snippet.text}")
    snippets_text = "\n".join(snippets_parts)
    
    # 构建完整消息
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加指令和 Schema
    instruction_text = f"{instruction}\n\nSchema:\n{schema_info}"
    messages.append({"role": "user", "content": instruction_text})
    
    # 添加 few-shot 例子
    for example in few_shot_examples:
        if "input" in example and "output" in example:
            messages.append({"role": "user", "content": f"输入:\n{example['input']}"})
            messages.append({"role": "assistant", "content": example["output"]})
    
    # 添加实际输入
    input_text = f"候选方案: {solution_desc}\n文献片段:\n{snippets_text}"
    messages.append({"role": "user", "content": f"输入:\n{input_text}"})
    
    return messages


def apply_rule_engine_fixes(solution: Dict[str, Any], rule_engine=None) -> tuple[Dict[str, Any], bool]:
    """
    应用规则引擎修正
    
    Args:
        solution: 原始方案
        rule_engine: 规则引擎实例（可选）
        
    Returns:
        tuple: (修正后的方案, 是否通过硬约束)
    """
    fixed_solution = solution.copy()
    hard_constraints_passed = True
    
    try:
        if rule_engine is not None and hasattr(rule_engine, 'apply_auto_fixes'):
            # 使用规则引擎进行修正
            result = rule_engine.apply_auto_fixes(fixed_solution)
            if isinstance(result, dict):
                fixed_solution = result
            
            # 检查硬约束
            if hasattr(rule_engine, 'check_hard_constraints'):
                hard_constraints_passed = rule_engine.check_hard_constraints(fixed_solution)
        else:
            # 简单的内置规则检查
            fixed_solution, hard_constraints_passed = _apply_builtin_rules(fixed_solution)
            
    except Exception as e:
        logger.warning(f"Rule engine application failed: {e}")
        fixed_solution, hard_constraints_passed = _apply_builtin_rules(solution)
    
    return fixed_solution, hard_constraints_passed


def _apply_builtin_rules(solution: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """内置的简单规则检查"""
    fixed = solution.copy()
    passed = True
    
    # 电压范围检查
    if 'voltage_V' in fixed:
        voltage = fixed['voltage_V']
        if isinstance(voltage, (int, float)):
            if voltage < 200:
                fixed['voltage_V'] = 200
                logger.warning("Voltage too low, adjusted to 200V")
            elif voltage > 600:
                fixed['voltage_V'] = 600
                logger.warning("Voltage too high, adjusted to 600V")
    
    # 电流密度范围检查
    if 'current_density_A_dm2' in fixed:
        current = fixed['current_density_A_dm2']
        if isinstance(current, (int, float)):
            if current < 5:
                fixed['current_density_A_dm2'] = 5
                logger.warning("Current density too low, adjusted to 5A/dm²")
            elif current > 25:
                fixed['current_density_A_dm2'] = 25
                logger.warning("Current density too high, adjusted to 25A/dm²")
    
    # 时间范围检查
    if 'time_min' in fixed:
        time_val = fixed['time_min']
        if isinstance(time_val, (int, float)):
            if time_val < 1:
                passed = False
                logger.error("Process time too short, violates hard constraint")
            elif time_val > 60:
                passed = False
                logger.error("Process time too long, violates hard constraint")
    
    return fixed, passed


def make_plan_yaml(
    solution: Dict[str, Any],
    rule_engine=None,
    context_snippets: Optional[List[Snippet]] = None
) -> Dict[str, Any]:
    """
    生成工艺卡YAML
    
    Args:
        solution: 候选方案
        rule_engine: 规则引擎实例（可选）
        context_snippets: 上下文文献片段（可选，会自动检索）
        
    Returns:
        Dict: 包含YAML文本、引用信息和约束检查结果
    """
    try:
        # 应用规则引擎修正
        fixed_solution, hard_constraints_passed = apply_rule_engine_fixes(solution, rule_engine)
        
        # 如果没有提供上下文，自动检索
        if context_snippets is None:
            query = format_solution_description(fixed_solution)
            context_snippets = build_context(query, topk=5, max_tokens=1500)
        
        if not context_snippets:
            return _make_fallback_plan_yaml(fixed_solution, hard_constraints_passed)
        
        # 构建提示
        messages = build_plan_writer_prompt(fixed_solution, context_snippets)
        
        # 调用 LLM
        response = llm_chat(messages, use_cache=True, max_retries=2)
        content = response.get("content", "")
        
        if not content:
            return _make_fallback_plan_yaml(fixed_solution, hard_constraints_passed)
        
        # 解析 JSON 响应
        schema = {
            "process_name": str,
            "substrate": str,
            "steps": list,
            "safety_notes": list,
            "expected_performance": dict,
            "quality_control": list
        }
        
        parsed = expect_schema(schema, content, max_repair_attempts=1)
        
        # 构建引用映射
        citation_map = {}
        for i, snippet in enumerate(context_snippets, 1):
            citation_id = f"CIT-{i}"
            citation_map[citation_id] = {
                "text": snippet.text,
                "source": snippet.source,
                "page": snippet.page,
                "score": snippet.score
            }
        
        # 转换为 YAML 文本
        yaml_text = yaml.dump(parsed, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        logger.info(f"Generated process plan with {len(parsed.get('steps', []))} steps")
        
        return {
            "yaml_text": yaml_text,
            "plan_data": parsed,
            "citation_map": citation_map,
            "total_citations": len(citation_map),
            "hard_constraints_passed": hard_constraints_passed,
            "rule_fixes_applied": fixed_solution != solution
        }
        
    except Exception as e:
        logger.error(f"Failed to generate plan YAML: {e}")
        return _make_fallback_plan_yaml(solution, False)


def _make_fallback_plan_yaml(solution: Dict[str, Any], hard_constraints_passed: bool) -> Dict[str, Any]:
    """生成离线兜底工艺卡"""
    
    # 基本信息
    substrate = solution.get('substrate_alloy', 'AZ91')
    process_name = f"{substrate}镁合金微弧氧化工艺"
    
    # 构建基本步骤
    steps = [
        {
            "step_id": "PREP-01",
            "name": "基体预处理",
            "description": "表面清洁处理",
            "parameters": {
                "degreasing": "丙酮超声清洗",
                "rinsing": "去离子水冲洗"
            },
            "duration": "10分钟",
            "notes": "确保表面清洁",
            "citations": []
        }
    ]
    
    # 电解液配制步骤
    if 'electrolyte_components_json' in solution:
        components = solution['electrolyte_components_json']
        if isinstance(components, dict):
            steps.append({
                "step_id": "ELEC-01",
                "name": "电解液配制",
                "description": "配制电解液",
                "parameters": components,
                "duration": "30分钟",
                "notes": "确保完全溶解",
                "citations": []
            })
    
    # 微弧氧化步骤
    mao_params = {}
    if 'voltage_V' in solution:
        mao_params['voltage'] = f"{solution['voltage_V']} V"
    if 'current_density_A_dm2' in solution:
        mao_params['current_density'] = f"{solution['current_density_A_dm2']} A/dm²"
    if 'frequency_Hz' in solution:
        mao_params['frequency'] = f"{solution['frequency_Hz']} Hz"
    if 'duty_cycle_pct' in solution:
        mao_params['duty_cycle'] = f"{solution['duty_cycle_pct']}%"
    
    duration = f"{solution.get('time_min', 10)}分钟"
    
    steps.append({
        "step_id": "MAO-01",
        "name": "微弧氧化处理",
        "description": "微弧氧化涂层制备",
        "parameters": mao_params,
        "duration": duration,
        "notes": "监控放电稳定性",
        "citations": []
    })
    
    # 后处理步骤（如有）
    if 'post_treatment' in solution and solution['post_treatment'] != '无':
        steps.append({
            "step_id": "POST-01",
            "name": "后处理",
            "description": solution['post_treatment'],
            "parameters": {},
            "duration": "根据工艺要求",
            "notes": "提高涂层性能",
            "citations": []
        })
    
    # 构建完整数据结构
    plan_data = {
        "process_name": process_name,
        "substrate": substrate,
        "steps": steps,
        "safety_notes": [
            {
                "item": "操作过程中注意用电安全",
                "citations": []
            },
            {
                "item": "佩戴适当的防护用品",
                "citations": []
            }
        ],
        "expected_performance": {
            "alpha_150_2600": solution.get('expected_alpha', 0.8),
            "epsilon_3000_30000": solution.get('expected_epsilon', 0.9),
            "coating_thickness_um": "5-20",
            "citations": []
        },
        "quality_control": [
            {
                "test": "外观检查",
                "method": "目视检查",
                "acceptance": "表面均匀，无明显缺陷",
                "citations": []
            }
        ]
    }
    
    # 转换为 YAML 文本
    yaml_text = yaml.dump(plan_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    logger.info(f"Generated fallback process plan with {len(steps)} steps")
    
    return {
        "yaml_text": yaml_text,
        "plan_data": plan_data,
        "citation_map": {},
        "total_citations": 0,
        "hard_constraints_passed": hard_constraints_passed,
        "rule_fixes_applied": False
    }
