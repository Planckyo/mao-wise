from __future__ import annotations

import json
import re
from typing import Dict, Any, Optional

from .client import llm_chat
from ..utils.logger import logger


def extract_json_from_text(text: str) -> Optional[str]:
    """
    从文本中提取 JSON 字符串
    
    Args:
        text: 包含 JSON 的文本
        
    Returns:
        Optional[str]: 提取的 JSON 字符串，如果没找到则返回 None
    """
    # 尝试多种模式提取 JSON
    patterns = [
        r'```json\s*(\{.*?\})\s*```',  # ```json {...} ```
        r'```\s*(\{.*?\})\s*```',      # ``` {...} ```
        r'(\{[^{}]*\{[^{}]*\}[^{}]*\})', # 嵌套大括号
        r'(\{[^{}]+\})',               # 简单大括号
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0]
    
    # 如果没找到明确的 JSON 块，尝试整个文本
    text = text.strip()
    if text.startswith('{') and text.endswith('}'):
        return text
    
    return None


def repair_json_with_llm(broken_json: str, expected_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    使用 LLM 修复损坏的 JSON
    
    Args:
        broken_json: 损坏的 JSON 字符串
        expected_schema: 期望的 schema
        
    Returns:
        Optional[Dict[str, Any]]: 修复后的 JSON 对象
    """
    schema_example = json.dumps(expected_schema, indent=2, ensure_ascii=False)
    
    messages = [
        {
            "role": "system", 
            "content": "You are a JSON repair assistant. Fix the broken JSON and return only valid JSON without any explanation."
        },
        {
            "role": "user",
            "content": f"""Fix this broken JSON to match the expected schema:

Broken JSON:
{broken_json}

Expected schema example:
{schema_example}

Return only the fixed JSON, no explanation."""
        }
    ]
    
    try:
        response = llm_chat(messages, use_cache=True, max_retries=1)
        fixed_text = response.get("content", "")
        
        # 提取并解析修复后的 JSON
        json_str = extract_json_from_text(fixed_text)
        if json_str:
            return json.loads(json_str)
            
    except Exception as e:
        logger.warning(f"LLM JSON repair failed: {e}")
    
    return None


def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    简单的 schema 验证
    
    Args:
        data: 要验证的数据
        schema: 期望的 schema
        
    Returns:
        bool: 是否符合 schema
    """
    if not isinstance(data, dict):
        return False
    
    # 检查必需的键
    for key, value_type in schema.items():
        if key not in data:
            return False
        
        # 简单类型检查
        if isinstance(value_type, type):
            if not isinstance(data[key], value_type):
                return False
        elif isinstance(value_type, str):
            # 字符串描述的类型
            if value_type == "string" and not isinstance(data[key], str):
                return False
            elif value_type == "number" and not isinstance(data[key], (int, float)):
                return False
            elif value_type == "boolean" and not isinstance(data[key], bool):
                return False
            elif value_type == "array" and not isinstance(data[key], list):
                return False
    
    return True


def expect_schema(
    schema: Dict[str, Any], 
    text: str, 
    max_repair_attempts: int = 2
) -> Dict[str, Any]:
    """
    期望特定 schema 的 JSON 解析，支持容错和修复
    
    Args:
        schema: 期望的 JSON schema
        text: 包含 JSON 的文本
        max_repair_attempts: 最大修复尝试次数
        
    Returns:
        Dict[str, Any]: 解析后的 JSON 对象
        
    Raises:
        ValueError: 如果无法解析或修复 JSON
    """
    # 首先尝试直接解析
    json_str = extract_json_from_text(text)
    if not json_str:
        # 如果没找到 JSON，尝试整个文本
        json_str = text.strip()
    
    # 尝试直接解析
    for attempt in range(max_repair_attempts + 1):
        try:
            data = json.loads(json_str)
            
            # 验证 schema
            if validate_against_schema(data, schema):
                return data
            else:
                logger.warning(f"JSON doesn't match expected schema on attempt {attempt + 1}")
                if attempt < max_repair_attempts:
                    # 尝试用 LLM 修复
                    repaired = repair_json_with_llm(json_str, schema)
                    if repaired and validate_against_schema(repaired, schema):
                        return repaired
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
            
            if attempt < max_repair_attempts:
                # 尝试用 LLM 修复
                repaired = repair_json_with_llm(json_str, schema)
                if repaired:
                    json_str = json.dumps(repaired)
                    continue
    
    # 如果所有尝试都失败，返回默认结构
    logger.error(f"Failed to parse JSON after {max_repair_attempts + 1} attempts")
    
    # 构造默认返回值
    default_data = {}
    for key, value_type in schema.items():
        if isinstance(value_type, type):
            if value_type == str:
                default_data[key] = "parse_error"
            elif value_type == int:
                default_data[key] = 0
            elif value_type == float:
                default_data[key] = 0.0
            elif value_type == bool:
                default_data[key] = False
            elif value_type == list:
                default_data[key] = []
            elif value_type == dict:
                default_data[key] = {}
        elif isinstance(value_type, str):
            if value_type == "string":
                default_data[key] = "parse_error"
            elif value_type == "number":
                default_data[key] = 0
            elif value_type == "boolean":
                default_data[key] = False
            elif value_type == "array":
                default_data[key] = []
            else:
                default_data[key] = None
    
    default_data["_parse_error"] = True
    return default_data
