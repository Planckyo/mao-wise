from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from ..utils import load_config
from ..utils.logger import logger


class ConcurrencyLimiter:
    """并发请求限制器"""
    
    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        self.active_requests = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
    
    def __enter__(self):
        with self.condition:
            while self.active_requests >= self.max_concurrent:
                self.condition.wait()
            self.active_requests += 1
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.condition:
            self.active_requests -= 1
            self.condition.notify()


class TokenBucket:
    """令牌桶速率限制器"""
    
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


class UsageTracker:
    """LLM使用统计跟踪器"""
    
    def __init__(self, log_file: str):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        
        # 初始化CSV文件
        if not self.log_file.exists():
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'provider', 'model', 'prompt_tokens', 
                    'completion_tokens', 'total_tokens', 'cost_usd', 
                    'cache_hit', 'duration_ms'
                ])
    
    def log_usage(self, provider: str, model: str, usage: Dict[str, Any], 
                  cost_usd: float = 0.0, cache_hit: bool = False, 
                  duration_ms: int = 0):
        """记录使用统计"""
        with self.lock:
            try:
                with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        provider,
                        model,
                        usage.get('prompt_tokens', 0),
                        usage.get('completion_tokens', 0),
                        usage.get('total_tokens', 0),
                        cost_usd,
                        cache_hit,
                        duration_ms
                    ])
            except Exception as e:
                logger.warning(f"Failed to log usage: {e}")
    
    def get_daily_usage(self, date: datetime = None) -> Dict[str, Any]:
        """获取指定日期的使用统计"""
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime('%Y-%m-%d')
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                daily_stats = {
                    'total_requests': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'cache_hits': 0
                }
                
                for row in reader:
                    if row['timestamp'].startswith(date_str):
                        daily_stats['total_requests'] += 1
                        daily_stats['total_tokens'] += int(row['total_tokens'] or 0)
                        daily_stats['total_cost'] += float(row['cost_usd'] or 0)
                        if row['cache_hit'].lower() == 'true':
                            daily_stats['cache_hits'] += 1
                
                return daily_stats
                
        except Exception as e:
            logger.warning(f"Failed to get daily usage: {e}")
            return {'total_requests': 0, 'total_tokens': 0, 'total_cost': 0.0, 'cache_hits': 0}


class LLMCache:
    """LLM响应缓存"""
    
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
        # 创建缓存键，排除敏感信息
        safe_kwargs = {k: v for k, v in kwargs.items() if 'key' not in k.lower()}
        content = json.dumps({"messages": messages, "model": model, **safe_kwargs}, sort_keys=True)
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


# 全局实例
_cache: Optional[LLMCache] = None
_concurrency_limiter: Optional[ConcurrencyLimiter] = None
_rate_limiter: Optional[TokenBucket] = None
_token_limiter: Optional[TokenBucket] = None
_usage_tracker: Optional[UsageTracker] = None


def _get_cache() -> LLMCache:
    global _cache
    if _cache is None:
        cfg = load_config()
        cache_dir = cfg.get("llm", {}).get("cache_dir", "datasets/cache")
        _cache = LLMCache(cache_dir)
    return _cache


def _get_concurrency_limiter() -> ConcurrencyLimiter:
    global _concurrency_limiter
    if _concurrency_limiter is None:
        cfg = load_config()
        max_concurrent = cfg.get("llm", {}).get("limits", {}).get("max_concurrent_requests", 5)
        # 确保是整数类型
        if isinstance(max_concurrent, str):
            max_concurrent = int(max_concurrent) if max_concurrent.isdigit() else 5
        _concurrency_limiter = ConcurrencyLimiter(max_concurrent)
    return _concurrency_limiter


def _get_rate_limiter() -> TokenBucket:
    global _rate_limiter
    if _rate_limiter is None:
        cfg = load_config()
        rpm = cfg.get("llm", {}).get("limits", {}).get("max_requests_per_minute", 100)
        # 确保是数值类型
        if isinstance(rpm, str):
            rpm = int(rpm) if rpm.isdigit() else 100
        _rate_limiter = TokenBucket(capacity=rpm, refill_rate=rpm / 60.0)
    return _rate_limiter


def _get_token_limiter() -> TokenBucket:
    global _token_limiter
    if _token_limiter is None:
        cfg = load_config()
        tpm = cfg.get("llm", {}).get("limits", {}).get("max_tokens_per_minute", 50000)
        # 确保是数值类型
        if isinstance(tpm, str):
            tpm = int(tpm) if tpm.isdigit() else 50000
        _token_limiter = TokenBucket(capacity=tpm, refill_rate=tpm / 60.0)
    return _token_limiter


def _get_usage_tracker() -> UsageTracker:
    global _usage_tracker
    if _usage_tracker is None:
        cfg = load_config()
        log_file = cfg.get("llm", {}).get("usage_tracking", {}).get("log_file", "datasets/cache/llm_usage.csv")
        _usage_tracker = UsageTracker(log_file)
    return _usage_tracker


def _calculate_cost(provider: str, model: str, usage: Dict[str, Any]) -> float:
    """计算API调用成本（美元）"""
    prompt_tokens = usage.get('prompt_tokens', 0)
    completion_tokens = usage.get('completion_tokens', 0)
    
    # OpenAI pricing (approximate, as of 2024)
    pricing = {
        'gpt-4': {'prompt': 0.03/1000, 'completion': 0.06/1000},
        'gpt-4-turbo': {'prompt': 0.01/1000, 'completion': 0.03/1000},
        'gpt-4o': {'prompt': 0.005/1000, 'completion': 0.015/1000},
        'gpt-4o-mini': {'prompt': 0.00015/1000, 'completion': 0.0006/1000},
        'gpt-3.5-turbo': {'prompt': 0.001/1000, 'completion': 0.002/1000},
    }
    
    if provider in ['openai', 'azure'] and model in pricing:
        rates = pricing[model]
        return prompt_tokens * rates['prompt'] + completion_tokens * rates['completion']
    
    return 0.0


def _check_daily_limits() -> bool:
    """检查每日成本限制"""
    cfg = load_config()
    cost_limit = cfg.get("llm", {}).get("limits", {}).get("cost_limit_per_day_usd", 10.0)
    
    # 确保是数值类型
    if isinstance(cost_limit, str):
        try:
            cost_limit = float(cost_limit)
        except ValueError:
            cost_limit = 10.0
    
    tracker = _get_usage_tracker()
    daily_usage = tracker.get_daily_usage()
    
    if daily_usage['total_cost'] >= cost_limit:
        logger.warning(f"Daily cost limit reached: ${daily_usage['total_cost']:.4f} >= ${cost_limit}")
        return False
    
    return True


def _sanitize_for_logging(text: str) -> str:
    """日志脱敏：移除敏感信息"""
    if not text:
        return text
    
    # 移除API密钥模式
    import re
    
    # OpenAI keys
    text = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[API_KEY_REDACTED]', text)
    # Azure keys  
    text = re.sub(r'[a-f0-9]{32}', '[API_KEY_REDACTED]', text)
    # 其他常见密钥模式
    text = re.sub(r'(?:api[_-]?key|secret|token|password)["\s]*[:=]["\s]*[^\s"]+', '[SECRET_REDACTED]', text, flags=re.IGNORECASE)
    
    # 移除文件系统绝对路径
    text = re.sub(r'[A-Za-z]:\\[^\\/:*?"<>|\r\n]+', '[PATH_REDACTED]', text)  # Windows
    text = re.sub(r'/[^/\s:*?"<>|\r\n]+(?:/[^/\s:*?"<>|\r\n]+)*', '[PATH_REDACTED]', text)  # Unix
    
    return text


def _mask_key(key: str) -> str:
    """掩码API Key，只显示前4后4字符"""
    if not key or len(key) < 8:
        return "[EMPTY]"
    
    prefix = key[:4]
    suffix = key[-4:]
    masked_length = max(0, len(key) - 8)
    masked = "*" * masked_length
    
    return f"{prefix}{masked}{suffix}"


def _read_env_file() -> Dict[str, str]:
    """读取.env文件内容"""
    env_vars = {}
    
    # 查找项目根目录的.env文件
    current_dir = Path.cwd()
    while current_dir.parent != current_dir:
        env_file = current_dir / ".env"
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
                break
            except Exception as e:
                logger.debug(f"Failed to read .env file {env_file}: {e}")
        current_dir = current_dir.parent
    
    return env_vars


def _get_llm_config() -> Tuple[str, Dict[str, Any], str]:
    """
    获取LLM配置，按优先级读取：环境变量 > .env > config.yaml
    
    Returns:
        (provider, config_dict, key_source)
    """
    # 读取.env文件
    env_vars = _read_env_file()
    
    # 初始化配置
    config = {
        "provider": "local",
        "openai": {},
        "azure": {},
        "timeout_s": 60,
        "max_tokens": 1024,
        "temperature": 0.2
    }
    
    key_source = "none"
    
    # 1. 先从环境变量读取
    provider = os.getenv("LLM_PROVIDER")
    openai_key = os.getenv("OPENAI_API_KEY")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    
    if provider or openai_key or azure_key:
        key_source = "env"
    
    # 2. 如果环境变量没有，从.env文件读取
    if not provider and "LLM_PROVIDER" in env_vars:
        provider = env_vars["LLM_PROVIDER"]
        if key_source == "none":
            key_source = "dotenv"
    
    if not openai_key and "OPENAI_API_KEY" in env_vars:
        openai_key = env_vars["OPENAI_API_KEY"]
        if key_source == "none":
            key_source = "dotenv"
    
    if not azure_key and "AZURE_OPENAI_API_KEY" in env_vars:
        azure_key = env_vars["AZURE_OPENAI_API_KEY"]
        if key_source == "none":
            key_source = "dotenv"
        
    if not azure_endpoint and "AZURE_OPENAI_ENDPOINT" in env_vars:
        azure_endpoint = env_vars["AZURE_OPENAI_ENDPOINT"]
        
    if not azure_deployment and "AZURE_OPENAI_DEPLOYMENT" in env_vars:
        azure_deployment = env_vars["AZURE_OPENAI_DEPLOYMENT"]
    
    # 3. 最后从config.yaml读取（作为fallback）
    try:
        cfg = load_config()
        llm_cfg = cfg.get("llm", {})
        
        if not provider:
            provider = llm_cfg.get("provider", "local")
            # 处理环境变量替换语法 ${VAR:-default}
            if isinstance(provider, str) and provider.startswith("${") and provider.endswith("}"):
                var_expr = provider[2:-1]  # 移除 ${ }
                if ":-" in var_expr:
                    var_name, default_value = var_expr.split(":-", 1)
                    provider = os.getenv(var_name, default_value)
                else:
                    provider = os.getenv(var_expr, "local")
            
            if provider and provider != "local" and key_source == "none":
                key_source = "config"
        
        if not openai_key:
            openai_key = llm_cfg.get("openai", {}).get("api_key")
            # 处理环境变量替换语法
            if isinstance(openai_key, str) and openai_key.startswith("${") and openai_key.endswith("}"):
                var_expr = openai_key[2:-1]  # 移除 ${ }
                if ":-" in var_expr:
                    var_name, default_value = var_expr.split(":-", 1)
                    openai_key = os.getenv(var_name, default_value if default_value else None)
                else:
                    openai_key = os.getenv(var_expr)
            
            if openai_key and key_source == "none":
                key_source = "config"
        
        # 合并其他配置
        config.update({
            "timeout_s": llm_cfg.get("timeout_s", 60),
            "max_tokens": llm_cfg.get("max_tokens", 1024),
            "temperature": llm_cfg.get("temperature", 0.2),
            "openai": {
                **llm_cfg.get("openai", {}),
                "api_key": openai_key
            }
        })
        
    except Exception as e:
        logger.debug(f"Failed to load config: {e}")
    
    # 设置provider
    config["provider"] = provider or "local"
    
    # 配置OpenAI
    if openai_key:
        config["openai"]["api_key"] = openai_key
    
    # 配置Azure
    if azure_key or azure_endpoint or azure_deployment:
        config["azure"] = {
            "api_key": azure_key,
            "endpoint": azure_endpoint, 
            "deployment": azure_deployment
        }
    
    # 根据可用密钥自动推断provider
    if config["provider"] == "local":
        if openai_key:
            config["provider"] = "openai"
            if key_source == "none":
                key_source = "env" if os.getenv("OPENAI_API_KEY") else "dotenv"
        elif azure_key:
            config["provider"] = "azure"
            if key_source == "none":
                key_source = "env" if os.getenv("AZURE_OPENAI_API_KEY") else "dotenv"
    
    # 日志记录（安全）
    masked_openai = _mask_key(openai_key) if openai_key else "[NONE]"
    masked_azure = _mask_key(azure_key) if azure_key else "[NONE]"
    
    logger.debug(f"LLM Config - Provider: {config['provider']}, "
                f"OpenAI Key: {masked_openai}, Azure Key: {masked_azure}, "
                f"Key Source: {key_source}")
    
    return config["provider"], config, key_source


def get_llm_status() -> Dict[str, Any]:
    """获取LLM配置状态信息"""
    provider, config, key_source = _get_llm_config()
    
    # 检查密钥是否可用
    has_openai_key = bool(config.get("openai", {}).get("api_key"))
    has_azure_key = bool(config.get("azure", {}).get("api_key"))
    
    status = {
        "llm_provider": provider,
        "llm_key_source": key_source,
        "providers_available": {
            "openai": has_openai_key,
            "azure": has_azure_key and bool(config.get("azure", {}).get("endpoint")),
            "local": True  # 本地模式总是可用
        }
    }
    
    return status


def _openai_chat(messages: List[Dict], tools: Optional[Dict] = None, response_format: Optional[Dict] = None) -> Dict:
    """OpenAI provider implementation"""
    try:
        import openai
    except ImportError:
        raise ImportError("openai package required for openai provider")
    
    # 使用新的配置读取逻辑
    provider, config, key_source = _get_llm_config()
    openai_cfg = config.get("openai", {})
    
    # 检查API密钥（脱敏日志）
    api_key = openai_cfg.get("api_key")
    if not api_key:
        raise ValueError(f"OpenAI API key not configured (checked source: {key_source})")
    
    # 脱敏日志
    cfg = load_config()
    debug_enabled = cfg.get("llm", {}).get("debug", {}).get("print_full_prompts", False)
    if debug_enabled:
        logger.debug(f"OpenAI request: {json.dumps(messages, indent=2)}")
    else:
        model = openai_cfg.get("model", "gpt-4o-mini")
        logger.debug(f"OpenAI request to model {model} with {len(messages)} messages (key from {key_source})")
    
    client = openai.OpenAI(
        api_key=api_key,
        base_url=openai_cfg.get("base_url"),
        timeout=config.get("timeout_s", 60)
    )
    
    kwargs = {
        "model": openai_cfg.get("model", "gpt-4o-mini"),
        "messages": messages,
        "temperature": config.get("temperature", 0.2),
        "max_tokens": config.get("max_tokens", 1024),
    }
    
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    
    response = client.chat.completions.create(**kwargs)
    
    result = {
        "content": response.choices[0].message.content,
        "role": response.choices[0].message.role,
        "finish_reason": response.choices[0].finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
    }
    
    # 脱敏日志
    if debug_enabled:
        logger.debug(f"OpenAI response: {json.dumps(result, indent=2)}")
    else:
        logger.debug(f"OpenAI response: {result['usage']['total_tokens']} tokens, finish_reason={result['finish_reason']}")
    
    return result


def _azure_chat(messages: List[Dict], tools: Optional[Dict] = None, response_format: Optional[Dict] = None) -> Dict:
    """Azure OpenAI provider implementation"""
    try:
        import openai
    except ImportError:
        raise ImportError("openai package required for azure provider")
    
    # 使用新的配置读取逻辑
    provider, config, key_source = _get_llm_config()
    azure_cfg = config.get("azure", {})
    
    api_key = azure_cfg.get("api_key")
    endpoint = azure_cfg.get("endpoint")
    deployment = azure_cfg.get("deployment")
    
    if not api_key:
        raise ValueError(f"Azure OpenAI API key not configured (checked source: {key_source})")
    if not endpoint:
        raise ValueError("Azure OpenAI endpoint not configured")
    if not deployment:
        raise ValueError("Azure OpenAI deployment not configured")
    
    cfg = load_config()
    debug_enabled = cfg.get("llm", {}).get("debug", {}).get("print_full_prompts", False)
    if debug_enabled:
        logger.debug(f"Azure request: {json.dumps(messages, indent=2)}")
    else:
        logger.debug(f"Azure request to {deployment} with {len(messages)} messages (key from {key_source})")
    
    client = openai.AzureOpenAI(
        api_key=api_key,
        api_version="2024-02-15-preview",
        azure_endpoint=endpoint,
    )
    
    kwargs = {
        "model": deployment,
        "messages": messages,
        "temperature": config.get("temperature", 0.2),
        "max_tokens": config.get("max_tokens", 1024),
    }
    
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    
    response = client.chat.completions.create(**kwargs)
    
    result = {
        "content": response.choices[0].message.content,
        "role": response.choices[0].message.role,
        "finish_reason": response.choices[0].finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
    }
    
    if debug_enabled:
        logger.debug(f"Azure response: {json.dumps(result, indent=2)}")
    else:
        logger.debug(f"Azure response: {result['usage']['total_tokens']} tokens")
    
    return result


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
    elif "question" in user_msg.lower():
        content = "请提供更具体的信息以便进行准确分析。"
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
    max_retries: int = 3,
    timeout: int = None
) -> Dict[str, Any]:
    """
    统一 LLM 调用接口
    
    Args:
        messages: 对话消息列表 [{"role": "user", "content": "..."}]
        tools: 工具定义（可选）
        response_format: 响应格式（可选）
        use_cache: 是否使用缓存
        max_retries: 最大重试次数
        timeout: 超时时间（秒）
    
    Returns:
        {"content": str, "role": str, "finish_reason": str, "usage": dict}
    """
    start_time = time.time()
    # 使用新的配置读取逻辑
    provider, config, key_source = _get_llm_config()
    
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    
    # 检查每日成本限制
    if not _check_daily_limits():
        logger.warning("Daily cost limit exceeded, using offline fallback")
        if llm_cfg.get("offline_fallback", True):
            response = _local_chat(messages, tools, response_format)
            _get_usage_tracker().log_usage(
                provider="fallback", model="local", usage=response["usage"],
                cache_hit=False, duration_ms=int((time.time() - start_time) * 1000)
            )
            return response
        else:
            raise RuntimeError("Daily cost limit exceeded")
    
    # 检查缓存
    cache_hit = False
    if use_cache:
        cache = _get_cache()
        cached = cache.get(messages, provider, tools=tools, response_format=response_format)
        if cached:
            logger.debug("LLM cache hit")
            cache_hit = True
            _get_usage_tracker().log_usage(
                provider=provider, model=llm_cfg.get("openai", {}).get("model", "unknown"),
                usage=cached.get("usage", {}), cache_hit=True,
                duration_ms=int((time.time() - start_time) * 1000)
            )
            return cached
    
    # 并发控制
    concurrency_limiter = _get_concurrency_limiter()
    
    with concurrency_limiter:
        # 速率限制
        rate_limiter = _get_rate_limiter()
        if not rate_limiter.consume():
            logger.warning("Request rate limit exceeded")
            if llm_cfg.get("offline_fallback", True):
                response = _local_chat(messages, tools, response_format)
                _get_usage_tracker().log_usage(
                    provider="fallback", model="rate_limited", usage=response["usage"],
                    cache_hit=False, duration_ms=int((time.time() - start_time) * 1000)
                )
                return response
            else:
                raise RuntimeError("Request rate limit exceeded")
        
        # Token速率限制（估算）
        estimated_tokens = sum(len(msg.get("content", "")) // 4 for msg in messages)  # 粗略估算
        token_limiter = _get_token_limiter()
        if not token_limiter.consume(estimated_tokens):
            logger.warning("Token rate limit exceeded")
            if llm_cfg.get("offline_fallback", True):
                response = _local_chat(messages, tools, response_format)
                _get_usage_tracker().log_usage(
                    provider="fallback", model="token_limited", usage=response["usage"],
                    cache_hit=False, duration_ms=int((time.time() - start_time) * 1000)
                )
                return response
            else:
                raise RuntimeError("Token rate limit exceeded")
        
        # 重试逻辑
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                if provider == "openai":
                    response = _openai_chat(messages, tools, response_format)
                elif provider == "azure":
                    response = _azure_chat(messages, tools, response_format)
                else:  # local or unknown
                    response = _local_chat(messages, tools, response_format)
                
                # 计算成本
                model = llm_cfg.get("openai", {}).get("model", "unknown")
                cost = _calculate_cost(provider, model, response.get("usage", {}))
                
                # 记录使用统计
                _get_usage_tracker().log_usage(
                    provider=provider, model=model, usage=response.get("usage", {}),
                    cost_usd=cost, cache_hit=cache_hit,
                    duration_ms=int((time.time() - start_time) * 1000)
                )
                
                # 缓存成功响应
                if use_cache and response.get("content"):
                    cache = _get_cache()
                    cache.set(messages, provider, response, tools=tools, response_format=response_format)
                
                return response
                
            except Exception as e:
                last_exception = e
                sanitized_error = _sanitize_for_logging(str(e))
                logger.warning(f"LLM call attempt {attempt + 1} failed: {sanitized_error}")
                
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 1.0  # exponential backoff
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # 最终兜底
                    if llm_cfg.get("offline_fallback", True):
                        logger.warning("All retries failed, using offline fallback")
                        response = _local_chat(messages, tools, response_format)
                        _get_usage_tracker().log_usage(
                            provider="fallback", model="error_fallback", usage=response["usage"],
                            cache_hit=False, duration_ms=int((time.time() - start_time) * 1000)
                        )
                        return response
                    else:
                        raise last_exception
    
    # 不应该到达这里
    raise RuntimeError("Unexpected error in llm_chat")


def get_usage_stats(days: int = 7) -> Dict[str, Any]:
    """获取使用统计"""
    tracker = _get_usage_tracker()
    stats = {'daily': []}
    
    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        daily = tracker.get_daily_usage(date)
        daily['date'] = date.strftime('%Y-%m-%d')
        stats['daily'].append(daily)
    
    # 总计
    stats['total'] = {
        'requests': sum(d['total_requests'] for d in stats['daily']),
        'tokens': sum(d['total_tokens'] for d in stats['daily']),
        'cost': sum(d['total_cost'] for d in stats['daily']),
        'cache_hits': sum(d['cache_hits'] for d in stats['daily'])
    }
    
    return stats