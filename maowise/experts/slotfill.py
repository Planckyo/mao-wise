from __future__ import annotations

import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..llm.client import llm_chat
from ..llm.jsonio import expect_schema
from ..utils.logger import logger
from .schemas_llm import SlotFillResult, SLOTFILL_SCHEMA


def load_slotfill_prompt() -> Dict[str, Any]:
    """加载槽位填充的提示模板"""
    prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / "slotfill.yaml"
    try:
        with prompt_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load slotfill prompt: {e}")
        return {}


def build_slotfill_prompt(expert_answer: str, current_context: str = "") -> list:
    """构建槽位填充的完整提示"""
    prompt_template = load_slotfill_prompt()
    
    system_prompt = prompt_template.get("system", "")
    instruction = prompt_template.get("instruction", "")
    schema_info = prompt_template.get("schema", "")
    few_shot_examples = prompt_template.get("few_shot", [])
    
    # 构建消息
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加指令和 Schema
    instruction_text = f"{instruction}\n\nSchema:\n{schema_info}"
    messages.append({"role": "user", "content": instruction_text})
    
    # 添加 few-shot 例子
    for example in few_shot_examples:
        if "input" in example and "output" in example:
            messages.append({"role": "user", "content": f"输入:\n{example['input']}"})
            messages.append({"role": "assistant", "content": example["output"]})
    
    # 构建实际输入
    input_text = f"专家回答: {expert_answer}"
    if current_context:
        input_text += f"\n上下文: {current_context}"
    
    messages.append({"role": "user", "content": f"输入:\n{input_text}"})
    
    return messages


def normalize_units(data: Dict[str, Any]) -> Dict[str, Any]:
    """单位归一化处理"""
    normalized = data.copy()
    
    # 电压单位归一化 (V)
    if "voltage_V" in normalized and normalized["voltage_V"] is not None:
        voltage = normalized["voltage_V"]
        if isinstance(voltage, (int, float)):
            # 已经是V，无需转换
            pass
        elif isinstance(voltage, str):
            # 尝试解析字符串中的数值
            import re
            match = re.search(r'(\d+\.?\d*)', str(voltage))
            if match:
                normalized["voltage_V"] = float(match.group(1))
    
    # 电流密度单位归一化 (A/dm²)
    if "current_density_Adm2" in normalized and normalized["current_density_Adm2"] is not None:
        current = normalized["current_density_Adm2"]
        if isinstance(current, str):
            import re
            match = re.search(r'(\d+\.?\d*)', str(current))
            if match:
                normalized["current_density_Adm2"] = float(match.group(1))
    
    # 频率单位归一化 (Hz)
    if "frequency_Hz" in normalized and normalized["frequency_Hz"] is not None:
        freq = normalized["frequency_Hz"]
        if isinstance(freq, str):
            import re
            # 处理 kHz -> Hz
            if "khz" in freq.lower() or "k" in freq.lower():
                match = re.search(r'(\d+\.?\d*)', str(freq))
                if match:
                    normalized["frequency_Hz"] = float(match.group(1)) * 1000
            else:
                match = re.search(r'(\d+\.?\d*)', str(freq))
                if match:
                    normalized["frequency_Hz"] = float(match.group(1))
    
    # 占空比单位归一化 (%)
    if "duty_cycle_pct" in normalized and normalized["duty_cycle_pct"] is not None:
        duty = normalized["duty_cycle_pct"]
        if isinstance(duty, str):
            import re
            match = re.search(r'(\d+\.?\d*)', str(duty))
            if match:
                value = float(match.group(1))
                # 如果值在0-1之间，转换为百分比
                if 0 < value < 1:
                    normalized["duty_cycle_pct"] = value * 100
                else:
                    normalized["duty_cycle_pct"] = value
    
    # 时间单位归一化 (min)
    if "time_min" in normalized and normalized["time_min"] is not None:
        time_val = normalized["time_min"]
        if isinstance(time_val, str):
            import re
            # 处理小时 -> 分钟
            if "小时" in time_val or "hour" in time_val.lower() or "h" in time_val.lower():
                match = re.search(r'(\d+\.?\d*)', str(time_val))
                if match:
                    normalized["time_min"] = float(match.group(1)) * 60
            # 处理秒 -> 分钟
            elif "秒" in time_val or "sec" in time_val.lower() or "s" in time_val.lower():
                match = re.search(r'(\d+\.?\d*)', str(time_val))
                if match:
                    normalized["time_min"] = float(match.group(1)) / 60
            else:
                match = re.search(r'(\d+\.?\d*)', str(time_val))
                if match:
                    normalized["time_min"] = float(match.group(1))
    
    # 温度单位归一化 (°C)
    if "temp_C" in normalized and normalized["temp_C"] is not None:
        temp = normalized["temp_C"]
        if isinstance(temp, str):
            import re
            match = re.search(r'(\d+\.?\d*)', str(temp))
            if match:
                normalized["temp_C"] = float(match.group(1))
    
    return normalized


def extract_slot_values(
    expert_answer: str,
    current_context: str = "",
    current_data: Optional[Dict[str, Any]] = None
) -> SlotFillResult:
    """
    从专家自由文本中抽取结构化槽位
    
    Args:
        expert_answer: 专家的自由文本回答
        current_context: 当前实验上下文
        current_data: 当前已有数据（可选）
        
    Returns:
        SlotFillResult: 抽取的槽位数据
    """
    if not expert_answer.strip():
        logger.warning("Empty expert answer provided")
        return SlotFillResult()
    
    try:
        # 构建提示
        messages = build_slotfill_prompt(expert_answer, current_context)
        
        # 调用 LLM
        response = llm_chat(messages, use_cache=True, max_retries=2)
        content = response.get("content", "")
        
        if not content:
            return _extract_fallback_values(expert_answer)
        
        # 解析 JSON 响应
        parsed = expect_schema(SLOTFILL_SCHEMA, content, max_repair_attempts=1)
        
        # 单位归一化
        normalized = normalize_units(parsed)
        
        # 过滤无效值
        cleaned = {}
        for key, value in normalized.items():
            if value is not None and value != "parse_error" and value != "":
                # 特殊处理数值字段的0值
                if key in ["voltage_V", "current_density_Adm2", "frequency_Hz", "duty_cycle_pct", "time_min", "temp_C"]:
                    if isinstance(value, (int, float)) and value > 0:
                        cleaned[key] = value
                else:
                    cleaned[key] = value
        
        # 创建结果对象
        result = SlotFillResult(**cleaned)
        
        logger.info(f"Extracted {len(cleaned)} slot values from expert answer")
        return result
        
    except Exception as e:
        logger.error(f"Failed to extract slot values: {e}")
        return _extract_fallback_values(expert_answer)


def _extract_fallback_values(expert_answer: str) -> SlotFillResult:
    """离线兜底的槽位抽取"""
    import re
    
    result_data = {}
    text = expert_answer.lower()
    
    # 简单的正则表达式抽取
    patterns = {
        "voltage_V": [
            r'(\d+\.?\d*)\s*v(?:olt)?',
            r'电压.*?(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*伏'
        ],
        "current_density_Adm2": [
            r'(\d+\.?\d*)\s*a/dm',
            r'电流密度.*?(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*安培'
        ],
        "frequency_Hz": [
            r'(\d+\.?\d*)\s*hz',
            r'频率.*?(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*赫兹'
        ],
        "time_min": [
            r'(\d+\.?\d*)\s*分钟',
            r'(\d+\.?\d*)\s*min',
            r'时间.*?(\d+\.?\d*)'
        ],
        "duty_cycle_pct": [
            r'占空比.*?(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*%'
        ]
    }
    
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            matches = re.findall(pattern, text)
            if matches:
                try:
                    value = float(matches[0])
                    if value > 0:
                        result_data[field] = value
                        break
                except ValueError:
                    continue
    
    # 简单的电解液成分抽取
    if any(word in text for word in ["na2sio3", "硅酸钠", "koh", "氢氧化钾"]):
        components = {}
        
        # Na2SiO3 浓度
        na_pattern = r'na2sio3.*?(\d+\.?\d*)\s*g/l'
        na_matches = re.findall(na_pattern, text)
        if na_matches:
            components["Na2SiO3"] = f"{na_matches[0]} g/L"
        
        # KOH 浓度  
        koh_pattern = r'koh.*?(\d+\.?\d*)\s*g/l'
        koh_matches = re.findall(koh_pattern, text)
        if koh_matches:
            components["KOH"] = f"{koh_matches[0]} g/L"
        
        if components:
            result_data["electrolyte_components_json"] = components
    
    # 后处理检测
    if any(word in text for word in ["封孔", "sealing", "后处理", "post"]):
        if "水热" in text:
            result_data["post_treatment"] = "水热封孔"
        elif "有机" in text:
            result_data["post_treatment"] = "有机封孔"
        elif "无" in text or "没有" in text:
            result_data["post_treatment"] = "无"
        else:
            result_data["post_treatment"] = "其他后处理"
    
    logger.info(f"Fallback extracted {len(result_data)} values")
    return SlotFillResult(**result_data)
