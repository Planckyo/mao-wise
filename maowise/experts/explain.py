from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..llm.client import llm_chat
from ..llm.rag import Snippet, build_context
from ..llm.jsonio import expect_schema
from ..utils.logger import logger


def load_explain_prompt() -> Dict[str, Any]:
    """加载解释生成的提示模板"""
    prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / "explain.yaml"
    try:
        with prompt_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load explain prompt: {e}")
        return {}


def format_snippets_with_citations(snippets: List[Snippet]) -> tuple[str, Dict[str, Snippet]]:
    """
    格式化文献片段并生成引用映射
    
    Returns:
        tuple: (formatted_text, citation_map)
    """
    citation_map = {}
    formatted_parts = []
    
    for i, snippet in enumerate(snippets, 1):
        citation_id = f"CIT-{i}"
        citation_map[citation_id] = snippet
        
        formatted_parts.append(f"- [{citation_id}] {snippet.text}")
    
    return "\n".join(formatted_parts), citation_map


def build_explain_prompt(
    result: Dict[str, Any],
    context_snippets: List[Snippet],
    result_type: str = "prediction"
) -> List[Dict[str, str]]:
    """构建解释生成的完整提示"""
    prompt_template = load_explain_prompt()
    
    system_prompt = prompt_template.get("system", "")
    instruction = prompt_template.get("instruction", "")
    schema_info = prompt_template.get("schema", "")
    few_shot_examples = prompt_template.get("few_shot", [])
    
    # 格式化文献片段
    snippets_text, _ = format_snippets_with_citations(context_snippets)
    
    # 构建结果描述
    if result_type == "prediction":
        result_desc = f"预测结果: α={result.get('alpha', 'N/A')}, ε={result.get('epsilon', 'N/A')}, confidence={result.get('confidence', 'N/A')}"
        if 'description' in result:
            result_desc += f"\n输入描述: {result['description']}"
    elif result_type == "recommendation":
        result_desc = "优化建议:"
        solutions = result.get('solutions', [])
        for i, sol in enumerate(solutions[:3], 1):
            result_desc += f"\n方案{i}: {sol.get('description', 'N/A')}"
        if 'target' in result:
            target = result['target']
            result_desc += f"\n目标: α*={target.get('alpha', 'N/A')}, ε*={target.get('epsilon', 'N/A')}"
    else:
        result_desc = f"结果: {result}"
    
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
    input_text = f"{result_desc}\n文献片段:\n{snippets_text}"
    messages.append({"role": "user", "content": f"输入:\n{input_text}"})
    
    return messages


def make_explanation(
    result: Dict[str, Any],
    context_snippets: Optional[List[Snippet]] = None,
    result_type: str = "prediction"
) -> Dict[str, Any]:
    """
    生成带引用的解释要点
    
    Args:
        result: 预测结果或优化建议
        context_snippets: 上下文文献片段（可选，会自动检索）
        result_type: 结果类型 ("prediction" 或 "recommendation")
        
    Returns:
        Dict: 包含解释要点和引用映射的字典
    """
    try:
        # 如果没有提供上下文，自动检索
        if context_snippets is None:
            query = ""
            if result_type == "prediction" and 'description' in result:
                query = result['description']
            elif result_type == "recommendation" and 'solutions' in result:
                # 从方案中提取关键词
                solutions = result.get('solutions', [])
                if solutions:
                    query = solutions[0].get('description', '')
            
            if query:
                context_snippets = build_context(query, topk=5, max_tokens=1200)
            else:
                context_snippets = []
        
        if not context_snippets:
            return _make_fallback_explanation(result, result_type)
        
        # 构建提示
        messages = build_explain_prompt(result, context_snippets, result_type)
        
        # 调用 LLM
        response = llm_chat(messages, use_cache=True, max_retries=2)
        content = response.get("content", "")
        
        if not content:
            return _make_fallback_explanation(result, result_type)
        
        # 解析 JSON 响应
        schema = {
            "explanations": list,
            "explanations[].point": str,
            "explanations[].citations": list
        }
        
        parsed = expect_schema(schema, content, max_repair_attempts=1)
        explanations_data = parsed.get("explanations", [])
        
        # 构建引用映射
        _, citation_map = format_snippets_with_citations(context_snippets)
        
        # 验证和清理解释
        cleaned_explanations = []
        for exp_data in explanations_data[:7]:  # 最多7条
            if isinstance(exp_data, dict) and 'point' in exp_data:
                point = exp_data['point']
                citations = exp_data.get('citations', [])
                
                # 验证引用ID
                valid_citations = [cit for cit in citations if cit in citation_map]
                
                cleaned_explanations.append({
                    "point": point,
                    "citations": valid_citations
                })
        
        logger.info(f"Generated {len(cleaned_explanations)} explanation points")
        
        return {
            "explanations": cleaned_explanations,
            "citation_map": {cid: {
                "text": snippet.text,
                "source": snippet.source,
                "page": snippet.page,
                "score": snippet.score
            } for cid, snippet in citation_map.items()},
            "total_citations": len(citation_map)
        }
        
    except Exception as e:
        logger.error(f"Failed to generate explanation: {e}")
        return _make_fallback_explanation(result, result_type)


def _make_fallback_explanation(result: Dict[str, Any], result_type: str) -> Dict[str, Any]:
    """生成离线兜底解释"""
    explanations = []
    
    if result_type == "prediction":
        alpha = result.get('alpha', 'N/A')
        epsilon = result.get('epsilon', 'N/A')
        confidence = result.get('confidence', 'N/A')
        
        explanations = [
            {
                "point": f"根据输入参数预测，太阳吸收率α预期为{alpha}",
                "citations": []
            },
            {
                "point": f"红外发射率ε预期为{epsilon}",
                "citations": []
            },
            {
                "point": f"预测置信度为{confidence}，建议结合实际工艺验证",
                "citations": []
            }
        ]
        
        if confidence != 'N/A' and isinstance(confidence, (int, float)) and confidence < 0.7:
            explanations.append({
                "point": "置信度较低，建议提供更详细的工艺参数以提高预测准确性",
                "citations": []
            })
    
    elif result_type == "recommendation":
        solutions = result.get('solutions', [])
        target = result.get('target', {})
        
        explanations = [
            {
                "point": f"基于目标性能α*={target.get('alpha', 'N/A')}, ε*={target.get('epsilon', 'N/A')}生成了{len(solutions)}个候选方案",
                "citations": []
            }
        ]
        
        for i, sol in enumerate(solutions[:3], 1):
            explanations.append({
                "point": f"方案{i}通过调整关键参数来优化性能指标",
                "citations": []
            })
        
        explanations.append({
            "point": "建议根据设备条件和成本考虑选择最适合的方案",
            "citations": []
        })
    
    logger.info(f"Generated {len(explanations)} fallback explanations")
    
    return {
        "explanations": explanations,
        "citation_map": {},
        "total_citations": 0
    }
