from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import threading

from ..utils import load_config
from ..utils.logger import logger


class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
        self.lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class LLMCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "llm_cache.sqlite"
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def _make_key(self, messages: List[Dict], model: str, **kwargs) -> str:
        content = json.dumps({"messages": messages, "model": model, **kwargs}, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, messages: List[Dict], model: str, **kwargs) -> Optional[Dict]:
        key = self._make_key(messages, model, **kwargs)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT response FROM llm_cache WHERE cache_key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                pass
        return None
    
    def set(self, messages: List[Dict], model: str, response: Dict, **kwargs):
        key = self._make_key(messages, model, **kwargs)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, response) VALUES (?, ?)",
            (key, json.dumps(response))
        )
        conn.commit()
        conn.close()


# Global instances
_cache: Optional[LLMCache] = None
_rate_limiter: Optional[TokenBucket] = None


def _get_cache() -> LLMCache:
    global _cache
    if _cache is None:
        cfg = load_config()
        cache_dir = cfg.get("llm", {}).get("cache_dir", "datasets/cache")
        _cache = LLMCache(cache_dir)
    return _cache


def _get_rate_limiter() -> TokenBucket:
    global _rate_limiter
    if _rate_limiter is None:
        cfg = load_config()
        rpm = cfg.get("llm", {}).get("rate_limit", {}).get("requests_per_minute", 60)
        _rate_limiter = TokenBucket(capacity=rpm, refill_rate=rpm / 60.0)
    return _rate_limiter


def _openai_chat(messages: List[Dict], tools: Optional[Dict] = None, response_format: Optional[Dict] = None) -> Dict:
    """OpenAI provider implementation"""
    try:
        import openai
    except ImportError:
        raise ImportError("openai package required for openai provider")
    
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    openai_cfg = llm_cfg.get("openai", {})
    
    client = openai.OpenAI(
        api_key=openai_cfg.get("api_key"),
        base_url=openai_cfg.get("base_url"),
        timeout=llm_cfg.get("timeout_s", 60)
    )
    
    kwargs = {
        "model": openai_cfg.get("model", "gpt-4o-mini"),
        "messages": messages,
        "temperature": llm_cfg.get("temperature", 0.2),
        "max_tokens": llm_cfg.get("max_tokens", 1024),
    }
    
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    
    response = client.chat.completions.create(**kwargs)
    
    return {
        "content": response.choices[0].message.content,
        "role": response.choices[0].message.role,
        "finish_reason": response.choices[0].finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
    }


def _azure_chat(messages: List[Dict], tools: Optional[Dict] = None, response_format: Optional[Dict] = None) -> Dict:
    """Azure OpenAI provider implementation"""
    try:
        import openai
    except ImportError:
        raise ImportError("openai package required for azure provider")
    
    import os
    
    client = openai.AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )
    
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    
    kwargs = {
        "model": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4"),
        "messages": messages,
        "temperature": llm_cfg.get("temperature", 0.2),
        "max_tokens": llm_cfg.get("max_tokens", 1024),
    }
    
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    
    response = client.chat.completions.create(**kwargs)
    
    return {
        "content": response.choices[0].message.content,
        "role": response.choices[0].message.role,
        "finish_reason": response.choices[0].finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
    }


def _local_chat(messages: List[Dict], tools: Optional[Dict] = None, response_format: Optional[Dict] = None) -> Dict:
    """Local/offline fallback implementation"""
    logger.info("Using local/offline LLM fallback")
    
    # Extract user message for template response
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_msg = msg.get("content", "")
            break
    
    # Template response based on common patterns
    if "extract" in user_msg.lower() or "json" in user_msg.lower():
        content = '{"extracted": "local_fallback_mode", "confidence": 0.1}'
    elif "summarize" in user_msg.lower():
        content = "Local fallback mode: Unable to connect to LLM service. Using offline processing."
    else:
        content = "This is a local fallback response. Please configure LLM provider for full functionality."
    
    return {
        "content": content,
        "role": "assistant",
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }


def llm_chat(
    messages: List[Dict[str, str]], 
    tools: Optional[Dict] = None, 
    response_format: Optional[Dict] = None,
    use_cache: bool = True,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    统一 LLM 调用接口
    
    Args:
        messages: 对话消息列表 [{"role": "user", "content": "..."}]
        tools: 工具定义（可选）
        response_format: 响应格式（可选）
        use_cache: 是否使用缓存
        max_retries: 最大重试次数
    
    Returns:
        {"content": str, "role": str, "finish_reason": str, "usage": dict}
    """
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "local")
    
    # Check cache first
    if use_cache:
        cache = _get_cache()
        cached = cache.get(messages, provider, tools=tools, response_format=response_format)
        if cached:
            logger.debug("LLM cache hit")
            return cached
    
    # Rate limiting
    rate_limiter = _get_rate_limiter()
    if not rate_limiter.consume():
        logger.warning("Rate limit exceeded, using cached/fallback response")
        if llm_cfg.get("offline_fallback", True):
            return _local_chat(messages, tools, response_format)
        else:
            raise RuntimeError("Rate limit exceeded")
    
    # Retry logic with exponential backoff
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            if provider == "openai":
                response = _openai_chat(messages, tools, response_format)
            elif provider == "azure":
                response = _azure_chat(messages, tools, response_format)
            else:  # local or unknown
                response = _local_chat(messages, tools, response_format)
            
            # Cache successful response
            if use_cache and response.get("content"):
                cache = _get_cache()
                cache.set(messages, provider, response, tools=tools, response_format=response_format)
            
            return response
            
        except Exception as e:
            last_exception = e
            logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries:
                wait_time = (2 ** attempt) * 1.0  # exponential backoff
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                # Final fallback
                if llm_cfg.get("offline_fallback", True):
                    logger.warning("All retries failed, using offline fallback")
                    return _local_chat(messages, tools, response_format)
                else:
                    raise last_exception
    
    # Should not reach here
    raise RuntimeError("Unexpected error in llm_chat")
