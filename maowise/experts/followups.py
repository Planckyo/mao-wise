from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..llm.client import llm_chat
from ..llm.rag import build_context
from ..llm.jsonio import expect_schema
from ..utils.logger import logger


def load_question_catalog() -> Dict[str, Any]:
    """加载问题目录配置"""
    catalog_path = Path(__file__).parent / "question_catalog.yaml"
    try:
        with catalog_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load question catalog: {e}")
        return {}


def is_answer_vague(answer: str, question_config: Dict[str, Any]) -> bool:
    """
    检查回答是否含糊
    
    Args:
        answer: 专家回答
        question_config: 问题配置
        
    Returns:
        bool: 是否含糊
    """
    if not answer or not answer.strip():
        return True
    
    answer_lower = answer.lower().strip()
    
    # 检查问题特定的含糊指标
    vague_indicators = question_config.get("vague_indicators", [])
    for indicator in vague_indicators:
        if indicator.lower() in answer_lower:
            return True
    
    # 检查全局含糊模式
    catalog = load_question_catalog()
    global_vague = catalog.get("answer_quality_check", {}).get("vague_patterns", [])
    for pattern in global_vague:
        if pattern.lower() in answer_lower:
            return True
    
    # 检查是否过短（少于3个字符，可能是"是"、"否"等）
    if len(answer_lower) < 3:
        return True
    
    return False


def has_specific_content(answer: str) -> bool:
    """检查回答是否包含具体内容"""
    catalog = load_question_catalog()
    specific_indicators = catalog.get("answer_quality_check", {}).get("specific_indicators", [])
    
    answer_lower = answer.lower()
    for indicator in specific_indicators:
        if indicator.lower() in answer_lower:
            return True
    
    # 检查是否包含数字
    import re
    if re.search(r'\d+', answer):
        return True
    
    # 检查是否包含单位
    units = ["μm", "mm", "g/m²", "mg/cm²", "v", "a/dm²", "hz", "%", "min", "°c"]
    for unit in units:
        if unit.lower() in answer_lower:
            return True
    
    return False


def gen_followups(
    question_id: str,
    original_answer: str,
    question_config: Dict[str, Any],
    max_followups: int = 1
) -> List[Dict[str, Any]]:
    """
    生成追问问题
    
    Args:
        question_id: 原问题ID
        original_answer: 原始回答
        question_config: 问题配置
        max_followups: 最大追问次数
        
    Returns:
        List[Dict]: 追问问题列表
    """
    if not is_answer_vague(original_answer, question_config):
        logger.info("Answer is specific enough, no followup needed")
        return []
    
    try:
        # 获取追问模板
        catalog = load_question_catalog()
        followup_templates = catalog.get("followup_templates", {})
        
        # 根据问题类别选择模板
        category = question_config.get("category", "general")
        template_key = _get_template_key(question_id, category)
        
        if template_key not in followup_templates:
            return _generate_generic_followup(question_id, original_answer, question_config)
        
        template = followup_templates[template_key]
        
        # 构建RAG上下文
        followup_context = question_config.get("followup_context", "")
        context_snippets = build_context(followup_context, topk=3, max_tokens=800)
        
        # 生成追问
        followup_question = _generate_specific_followup(
            template, original_answer, context_snippets
        )
        
        if followup_question:
            return [{
                "id": f"{question_id}_followup_1",
                "question": followup_question,
                "kind": "text",
                "rationale": f"原回答'{original_answer}'过于含糊，需要更具体的信息",
                "is_followup": True,
                "parent_question_id": question_id,
                "max_attempts": 1  # 只追问一次
            }]
        
    except Exception as e:
        logger.error(f"Failed to generate followup for {question_id}: {e}")
    
    return _generate_generic_followup(question_id, original_answer, question_config)


def _get_template_key(question_id: str, category: str) -> str:
    """根据问题ID和类别获取模板键"""
    template_mapping = {
        "fluoride_additives": "fluoride_safety",
        "thickness_limits": "thickness_specification", 
        "substrate_surface": "surface_roughness",
        "performance_priorities": "performance_priority"
    }
    
    return template_mapping.get(question_id, category)


def _generate_specific_followup(
    template: Dict[str, str],
    original_answer: str,
    context_snippets: List
) -> Optional[str]:
    """使用LLM生成特定的追问"""
    try:
        system_prompt = template.get("system", "")
        question_template = template.get("question_template", "")
        
        # 格式化问题模板
        formatted_question = question_template.format(original_answer=original_answer)
        
        # 构建RAG上下文
        context_text = ""
        if context_snippets:
            context_parts = []
            for i, snippet in enumerate(context_snippets, 1):
                context_parts.append(f"[参考{i}] {snippet.text}")
            context_text = "\n".join(context_parts)
        
        # 构建LLM消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""基于以下信息生成一个具体的追问：

原始回答: "{original_answer}"
建议追问方向: {formatted_question}

参考文献:
{context_text}

请生成一个简洁、具体的追问，帮助获得更明确的回答。只返回问题文本，不要解释。"""}
        ]
        
        response = llm_chat(messages, use_cache=True, max_retries=1)
        content = response.get("content", "").strip()
        
        if content and len(content) > 10:  # 确保不是太短的回复
            return content
            
    except Exception as e:
        logger.warning(f"LLM followup generation failed: {e}")
    
    return None


def _generate_generic_followup(
    question_id: str, 
    original_answer: str, 
    question_config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """生成通用追问（离线兜底）"""
    generic_followups = {
        "fluoride_additives": "请明确说明：是否允许使用含氟添加剂？如果允许，您的设备是否具备相应的防腐蚀能力？",
        
        "thickness_limits": "请提供具体的涂层厚度要求，包括数值范围（如10-20μm）或质量限制（如50g/m²）？",
        
        "substrate_surface": "请提供具体信息：1）基体合金牌号（如AZ91）；2）表面粗糙度Ra值（如0.8μm）？",
        
        "environmental_constraints": "请明确：是否有特定的禁用物质清单或环保等级要求？",
        
        "performance_priorities": "请明确α和ε哪个指标更重要，以及可接受的性能范围？"
    }
    
    generic_question = generic_followups.get(
        question_id,
        f"您的回答'{original_answer}'不够具体，能否提供更详细的信息？"
    )
    
    return [{
        "id": f"{question_id}_followup_1",
        "question": generic_question,
        "kind": "text",
        "rationale": "需要更具体的信息以便进行准确的工艺设计",
        "is_followup": True,
        "parent_question_id": question_id,
        "max_attempts": 1
    }]


def validate_mandatory_answers(answers: Dict[str, str]) -> Dict[str, Any]:
    """
    验证必答问题的回答质量
    
    Args:
        answers: 问题ID -> 回答的映射
        
    Returns:
        Dict: 验证结果
    """
    catalog = load_question_catalog()
    mandatory_questions = catalog.get("mandatory_questions", [])
    validation_rules = catalog.get("validation_rules", {})
    
    results = {
        "all_answered": True,
        "all_specific": True,
        "missing_questions": [],
        "vague_answers": [],
        "validation_errors": [],
        "needs_followup": []
    }
    
    for question_config in mandatory_questions:
        question_id = question_config["id"]
        
        # 检查是否回答
        if question_id not in answers or not answers[question_id].strip():
            results["all_answered"] = False
            results["missing_questions"].append({
                "id": question_id,
                "question": question_config["question"],
                "priority": question_config.get("priority", "medium")
            })
            continue
        
        answer = answers[question_id]
        
        # 检查回答是否含糊
        if is_answer_vague(answer, question_config):
            results["all_specific"] = False
            results["vague_answers"].append({
                "id": question_id,
                "question": question_config["question"],
                "answer": answer
            })
            
            # 生成追问
            followups = gen_followups(question_id, answer, question_config)
            if followups:
                results["needs_followup"].extend(followups)
        
        # 应用验证规则
        if question_id in validation_rules:
            validation_errors = _apply_validation_rules(
                question_id, answer, validation_rules[question_id]
            )
            if validation_errors:
                results["validation_errors"].extend(validation_errors)
    
    return results


def _apply_validation_rules(question_id: str, answer: str, rules: List[Dict]) -> List[str]:
    """应用验证规则"""
    errors = []
    
    for rule in rules:
        rule_type = rule.get("type", "")
        
        if rule_type == "numeric_range":
            if not _validate_numeric_range(answer, rule):
                errors.append(f"{question_id}: 需要包含数值和单位")
        
        elif rule_type == "boolean_choice":
            valid_values = rule.get("valid_values", [])
            if not any(val.lower() in answer.lower() for val in valid_values):
                errors.append(f"{question_id}: 请明确选择：{', '.join(valid_values)}")
        
        elif rule_type == "composite":
            required_parts = rule.get("required_parts", [])
            missing_parts = [part for part in required_parts 
                           if part.lower() not in answer.lower()]
            if missing_parts:
                errors.append(f"{question_id}: 缺少信息：{', '.join(missing_parts)}")
    
    return errors


def _validate_numeric_range(answer: str, rule: Dict) -> bool:
    """验证数值范围"""
    import re
    
    # 检查是否包含数字
    numbers = re.findall(r'\d+\.?\d*', answer)
    if not numbers:
        return False
    
    # 检查是否包含单位
    if rule.get("unit_required", False):
        valid_units = rule.get("valid_units", [])
        if not any(unit.lower() in answer.lower() for unit in valid_units):
            return False
    
    return True
