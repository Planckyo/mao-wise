from __future__ import annotations

from typing import Dict, Any

from ..llm.client import llm_chat
from ..llm.jsonio import expect_schema
from ..utils.logger import logger


EXTRACTION_SCHEMA = {
    "substrate_alloy": str,
    "electrolyte_family": str,
    "mode": str,
    "voltage_V": float,
    "current_density_A_dm2": float,
    "frequency_Hz": float,
    "duty_cycle_pct": float,
    "time_min": float,
    "temp_C": float,
    "pH": float,
    "alpha_150_2600": float,
    "epsilon_3000_30000": float,
}


def try_llm_extract(chunk: str) -> Dict[str, Any]:
    """
    使用 LLM 进行信息抽取（带离线兜底）
    
    Args:
        chunk: 待抽取的文本块
        
    Returns:
        Dict[str, Any]: 抽取的字段，失败时返回空字典
    """
    if not chunk.strip():
        return {}
    
    try:
        messages = [
            {
                "role": "system",
                "content": "你是科学信息抽取助手。从文本中抽取微弧氧化实验参数，仅输出JSON格式，不要解释。"
            },
            {
                "role": "user",
                "content": f"""从以下文本中抽取微弧氧化实验的关键字段。只抽取明确出现的字段，单位统一为：
- 电压: V
- 电流密度: A/dm²
- 频率: Hz
- 占空比: %
- 时间: min
- 温度: °C
- α值: 0-1之间
- ε值: 0-1之间

文本：
{chunk}

输出JSON格式（仅包含找到的字段）："""
            }
        ]
        
        response = llm_chat(messages, use_cache=True, max_retries=1)
        content = response.get("content", "")
        
        if not content:
            return {}
        
        # 使用 JSON 解析器解析结果
        extracted = expect_schema(EXTRACTION_SCHEMA, content, max_repair_attempts=1)
        
        # 过滤掉解析错误和无效值
        result = {}
        for key, value in extracted.items():
            if key.startswith("_"):  # 跳过内部标记
                continue
            if value is not None and value != "parse_error" and value != 0:
                result[key] = value
        
        logger.debug(f"LLM extracted {len(result)} fields from chunk")
        return result
        
    except Exception as e:
        logger.warning(f"LLM extraction failed: {e}")
        return {}

