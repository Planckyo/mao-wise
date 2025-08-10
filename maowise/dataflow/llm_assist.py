from __future__ import annotations

from typing import Dict, Any


LLM_PROMPT = (
    "系统：你是科学信息抽取助手。仅按Schema输出JSON，不解释。\n"
    "用户：从以下文本中抽取微弧氧化实验的关键字段（仅出现的字段才填），单位保真并统一至Schema单位。\n"
    "文本：\n{chunk}\n"
    "输出（严格JSON，键覆盖Schema，未见字段不要出现）："
)


def try_llm_extract(chunk: str) -> Dict[str, Any]:
    """
    兜底：占位实现（离线默认不调用外部 LLM）。
    可按需接入 OpenAI/Local LLM。当前返回空。
    """
    _ = LLM_PROMPT.format(chunk=chunk)
    return {}

