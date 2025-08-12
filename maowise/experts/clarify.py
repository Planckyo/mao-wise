from __future__ import annotations

import yaml
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from ..llm.client import llm_chat
from ..llm.rag import build_context, format_context_for_prompt
from ..llm.jsonio import expect_schema
from ..utils.logger import logger
from .schemas_llm import ClarifyQuestion, ClarifyQuestions, CLARIFY_SCHEMA
from .followups import load_question_catalog, validate_mandatory_answers, gen_followups


def load_clarify_prompt() -> Dict[str, Any]:
    """加载澄清问题的提示模板"""
    prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / "clarify.yaml"
    try:
        with prompt_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load clarify prompt: {e}")
        return {}


def identify_missing_fields(current_data: Dict[str, Any], required_fields: Set[str]) -> List[str]:
    """识别缺失的关键字段"""
    missing = []
    for field in required_fields:
        value = current_data.get(field)
        if value is None or value == "" or value == 0:
            missing.append(field)
    return missing


def build_clarify_prompt(
    missing_fields: List[str],
    current_context: str,
    rag_snippets: List[str]
) -> List[Dict[str, str]]:
    """构建澄清问题的完整提示"""
    prompt_template = load_clarify_prompt()
    
    system_prompt = prompt_template.get("system", "")
    instruction = prompt_template.get("instruction", "")
    schema_info = prompt_template.get("schema", "")
    few_shot_examples = prompt_template.get("few_shot", [])
    
    # 构建上下文
    context_parts = [
        f"缺失字段: {', '.join(missing_fields)}",
        f"当前上下文: {current_context}",
    ]
    
    if rag_snippets:
        context_parts.append("检索片段:")
        for i, snippet in enumerate(rag_snippets, 1):
            context_parts.append(f"- {snippet}")
    
    context_text = "\n".join(context_parts)
    
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
    messages.append({"role": "user", "content": f"输入:\n{context_text}"})
    
    return messages


def generate_clarify_questions(
    current_data: Dict[str, Any],
    context_description: str = "",
    max_questions: int = 3,
    include_mandatory: bool = True,
    expert_answers: Optional[Dict[str, str]] = None
) -> List[ClarifyQuestion]:
    """
    生成澄清问题
    
    Args:
        current_data: 当前已有的数据
        context_description: 上下文描述
        max_questions: 最大问题数量
        include_mandatory: 是否包含必答问题
        expert_answers: 专家已有回答（用于追问检查）
        
    Returns:
        List[ClarifyQuestion]: 澄清问题列表
    """
    all_questions = []
    
    # 1. 处理必答问题
    if include_mandatory:
        mandatory_questions = _generate_mandatory_questions(expert_answers)
        all_questions.extend(mandatory_questions)
        
        # 如果有必答问题，优先处理
        if mandatory_questions:
            return mandatory_questions[:max_questions]
    
    # 2. 处理追问逻辑
    if expert_answers:
        followup_questions = _generate_followup_questions(expert_answers)
        all_questions.extend(followup_questions)
        
        # 如果有追问，优先处理
        if followup_questions:
            return followup_questions[:max_questions]
    
    # 3. 处理常规缺失字段
    # 定义关键字段（按优先级排序）
    critical_fields = [
        "voltage_V",
        "current_density_A_dm2", 
        "time_min",
        "frequency_Hz",
        "duty_cycle_pct",
        "electrolyte_family",
        "post_treatment"
    ]
    
    # 识别缺失字段
    missing_fields = identify_missing_fields(current_data, set(critical_fields))
    
    if not missing_fields:
        logger.info("No missing critical fields found")
        return all_questions[:max_questions]
    
    # 限制缺失字段数量（按优先级）
    missing_fields = missing_fields[:max_questions - len(all_questions)]
    
    try:
        # 构建 RAG 上下文
        query = f"微弧氧化实验参数 {' '.join(missing_fields)} {context_description}"
        rag_context = build_context(query, topk=3, max_tokens=800)
        rag_snippets = [snippet.text for snippet in rag_context]
        
        # 构建提示
        messages = build_clarify_prompt(missing_fields, context_description, rag_snippets)
        
        # 调用 LLM
        response = llm_chat(messages, use_cache=True, max_retries=2)
        content = response.get("content", "")
        
        if not content:
            return _generate_fallback_questions(missing_fields)
        
        # 解析 JSON 响应
        parsed = expect_schema(CLARIFY_SCHEMA, content, max_repair_attempts=1)
        
        # 转换为 Pydantic 模型
        questions_data = parsed.get("questions", [])
        questions = []
        
        for q_data in questions_data[:max_questions]:
            try:
                question = ClarifyQuestion(**q_data)
                questions.append(question)
            except Exception as e:
                logger.warning(f"Failed to parse question: {e}")
                continue
        
        logger.info(f"Generated {len(questions)} clarify questions")
        all_questions.extend(questions)
        
    except Exception as e:
        logger.error(f"Failed to generate clarify questions: {e}")
        fallback_questions = _generate_fallback_questions(missing_fields[:max_questions])
        all_questions.extend(fallback_questions)
    
    return all_questions[:max_questions]


def _generate_mandatory_questions(expert_answers: Optional[Dict[str, str]] = None) -> List[ClarifyQuestion]:
    """生成必答问题"""
    catalog = load_question_catalog()
    mandatory_questions = catalog.get("mandatory_questions", [])
    
    if not expert_answers:
        expert_answers = {}
    
    questions = []
    
    for q_config in mandatory_questions:
        question_id = q_config["id"]
        
        # 检查是否已回答
        if question_id in expert_answers and expert_answers[question_id].strip():
            continue  # 已回答，跳过
        
        # 创建必答问题
        question = ClarifyQuestion(
            id=question_id,
            question=q_config["question"],
            kind=_determine_question_kind(q_config),
            options=q_config.get("expected_answers"),
            rationale=q_config["rationale"],
            is_mandatory=True,
            priority=q_config.get("priority", "medium")
        )
        
        questions.append(question)
    
    # 按优先级排序
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    questions.sort(key=lambda q: priority_order.get(getattr(q, 'priority', 'medium'), 2))
    
    logger.info(f"Generated {len(questions)} mandatory questions")
    return questions


def _generate_followup_questions(expert_answers: Dict[str, str]) -> List[ClarifyQuestion]:
    """生成追问问题"""
    catalog = load_question_catalog()
    mandatory_questions = catalog.get("mandatory_questions", [])
    
    followup_questions = []
    
    for q_config in mandatory_questions:
        question_id = q_config["id"]
        
        if question_id not in expert_answers:
            continue
        
        answer = expert_answers[question_id]
        if not answer.strip():
            continue
        
        # 生成追问
        followups = gen_followups(question_id, answer, q_config, max_followups=1)
        
        for followup_data in followups:
            followup_question = ClarifyQuestion(
                id=followup_data["id"],
                question=followup_data["question"],
                kind=followup_data.get("kind", "text"),
                rationale=followup_data["rationale"],
                is_followup=True,
                parent_question_id=followup_data["parent_question_id"]
            )
            followup_questions.append(followup_question)
    
    logger.info(f"Generated {len(followup_questions)} followup questions")
    return followup_questions


def _determine_question_kind(q_config: Dict[str, Any]) -> str:
    """确定问题类型"""
    expected_answers = q_config.get("expected_answers", [])
    
    if expected_answers and len(expected_answers) <= 5:
        return "choice"
    
    category = q_config.get("category", "")
    if "specs" in category or "limits" in category:
        return "number"
    
    return "text"


def check_mandatory_completion(expert_answers: Dict[str, str]) -> Dict[str, Any]:
    """检查必答问题完成情况"""
    return validate_mandatory_answers(expert_answers)


def _generate_fallback_questions(missing_fields: List[str]) -> List[ClarifyQuestion]:
    """生成离线兜底问题"""
    fallback_templates = {
        "voltage_V": ClarifyQuestion(
            id="voltage_fallback",
            question="请问实验使用的电压是多少V？",
            kind="number",
            unit="V",
            rationale="电压是微弧氧化的核心参数，直接决定放电强度和涂层质量"
        ),
        "current_density_A_dm2": ClarifyQuestion(
            id="current_density_fallback",
            question="请问电流密度设置为多少A/dm²？",
            kind="number", 
            unit="A/dm²",
            rationale="电流密度影响放电均匀性和涂层厚度"
        ),
        "time_min": ClarifyQuestion(
            id="time_fallback",
            question="微弧氧化处理时间是多少分钟？",
            kind="number",
            unit="min", 
            rationale="处理时间决定涂层厚度和性能"
        ),
        "frequency_Hz": ClarifyQuestion(
            id="frequency_fallback",
            question="脉冲频率是多少Hz？",
            kind="number",
            unit="Hz",
            rationale="脉冲频率影响放电特性和涂层质量"
        ),
        "duty_cycle_pct": ClarifyQuestion(
            id="duty_cycle_fallback", 
            question="占空比设置为多少%？",
            kind="number",
            unit="%",
            rationale="占空比影响能量输入和涂层结构"
        ),
        "electrolyte_family": ClarifyQuestion(
            id="electrolyte_fallback",
            question="请说明电解液的类型和主要成分？",
            kind="choice",
            options=["硅酸盐", "磷酸盐", "铝酸盐", "复合电解液", "其他"],
            rationale="电解液类型决定涂层的化学组成和性能特征"
        ),
        "post_treatment": ClarifyQuestion(
            id="post_treatment_fallback",
            question="实验是否进行了后处理？",
            kind="choice",
            options=["无后处理", "水热封孔", "有机封孔", "其他封孔"],
            rationale="后处理工艺影响涂层的最终性能，特别是耐蚀性"
        )
    }
    
    questions = []
    for field in missing_fields:
        if field in fallback_templates:
            questions.append(fallback_templates[field])
    
    logger.info(f"Generated {len(questions)} fallback questions")
    return questions
