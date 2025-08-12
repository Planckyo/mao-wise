"""
日志脱敏工具
"""

import re
import json
from typing import Any, Dict, List, Union
from pathlib import Path


def sanitize_text(text: str) -> str:
    """
    脱敏文本内容
    
    Args:
        text: 原始文本
        
    Returns:
        str: 脱敏后的文本
    """
    if not text:
        return text
    
    # API密钥模式
    patterns = [
        # OpenAI keys
        (r'sk-[a-zA-Z0-9]{20,}', '[OPENAI_KEY_REDACTED]'),
        # Azure keys  
        (r'[a-f0-9]{32}', '[AZURE_KEY_REDACTED]'),
        # Generic API keys
        (r'(?:api[_-]?key|secret|token|password|authorization)["\s]*[:=]["\s]*[^\s"]+', '[API_KEY_REDACTED]'),
        # Bearer tokens
        (r'Bearer\s+[a-zA-Z0-9\-._~+/]+=*', 'Bearer [TOKEN_REDACTED]'),
        # JWT tokens
        (r'eyJ[a-zA-Z0-9\-._~+/]+=*\.eyJ[a-zA-Z0-9\-._~+/]+=*\.[a-zA-Z0-9\-._~+/]+=*', '[JWT_REDACTED]'),
    ]
    
    # 应用密钥脱敏
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # 文件系统路径脱敏
    path_patterns = [
        # Windows绝对路径
        (r'[A-Za-z]:\\[^\\/:*?"<>|\r\n\s]+(?:\\[^\\/:*?"<>|\r\n\s]+)*', '[WINDOWS_PATH]'),
        # Unix绝对路径  
        (r'/[^/\s:*?"<>|\r\n]+(?:/[^/\s:*?"<>|\r\n]+)*', '[UNIX_PATH]'),
        # 用户目录
        (r'~[^/\s:*?"<>|\r\n]*(?:/[^/\s:*?"<>|\r\n]+)*', '[USER_PATH]'),
    ]
    
    for pattern, replacement in path_patterns:
        text = re.sub(pattern, replacement, text)
    
    # IP地址脱敏（可选）
    ip_patterns = [
        (r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', '[IP_REDACTED]'),
        (r'\b[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4}){7}\b', '[IPv6_REDACTED]'),
    ]
    
    for pattern, replacement in ip_patterns:
        text = re.sub(pattern, replacement, text)
    
    return text


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    脱敏字典数据
    
    Args:
        data: 原始字典
        
    Returns:
        Dict: 脱敏后的字典
    """
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    
    # 需要脱敏的键名（不区分大小写）
    sensitive_keys = {
        'api_key', 'apikey', 'secret', 'password', 'token', 
        'authorization', 'auth', 'key', 'credential', 'access_token',
        'refresh_token', 'session_id', 'csrf_token'
    }
    
    for key, value in data.items():
        key_lower = key.lower()
        
        # 检查是否为敏感键
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            if isinstance(value, str) and value:
                sanitized[key] = '[REDACTED]'
            else:
                sanitized[key] = '[REDACTED]'
        elif isinstance(value, str):
            sanitized[key] = sanitize_text(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        else:
            sanitized[key] = value
    
    return sanitized


def sanitize_list(data: List[Any]) -> List[Any]:
    """
    脱敏列表数据
    
    Args:
        data: 原始列表
        
    Returns:
        List: 脱敏后的列表
    """
    if not isinstance(data, list):
        return data
    
    sanitized = []
    
    for item in data:
        if isinstance(item, str):
            sanitized.append(sanitize_text(item))
        elif isinstance(item, dict):
            sanitized.append(sanitize_dict(item))
        elif isinstance(item, list):
            sanitized.append(sanitize_list(item))
        else:
            sanitized.append(item)
    
    return sanitized


def sanitize_json(json_str: str) -> str:
    """
    脱敏JSON字符串
    
    Args:
        json_str: 原始JSON字符串
        
    Returns:
        str: 脱敏后的JSON字符串
    """
    try:
        data = json.loads(json_str)
        sanitized = sanitize_dict(data) if isinstance(data, dict) else sanitize_list(data)
        return json.dumps(sanitized, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        # 如果不是有效JSON，按普通文本处理
        return sanitize_text(json_str)


def sanitize_request_body(body: Any) -> Any:
    """
    脱敏请求体
    
    Args:
        body: 请求体（可能是dict、str等）
        
    Returns:
        Any: 脱敏后的请求体
    """
    if isinstance(body, dict):
        return sanitize_dict(body)
    elif isinstance(body, str):
        # 尝试作为JSON处理
        try:
            data = json.loads(body)
            return sanitize_dict(data) if isinstance(data, dict) else sanitize_list(data)
        except json.JSONDecodeError:
            return sanitize_text(body)
    elif isinstance(body, list):
        return sanitize_list(body)
    else:
        return body


def sanitize_response(response: Any) -> Any:
    """
    脱敏响应数据
    
    Args:
        response: 响应数据
        
    Returns:
        Any: 脱敏后的响应数据
    """
    return sanitize_request_body(response)  # 使用相同的逻辑


def get_sanitized_env_info() -> Dict[str, str]:
    """
    获取脱敏的环境信息
    
    Returns:
        Dict: 脱敏的环境变量信息
    """
    import os
    
    env_info = {}
    
    # 只记录非敏感的环境变量
    safe_env_vars = [
        'PYTHONPATH', 'PATH', 'HOME', 'USER', 'USERNAME', 
        'COMPUTERNAME', 'HOSTNAME', 'OS', 'PROCESSOR_ARCHITECTURE',
        'PYTHON_VERSION', 'CUDA_VISIBLE_DEVICES'
    ]
    
    for var in safe_env_vars:
        value = os.getenv(var)
        if value:
            env_info[var] = sanitize_text(value)
    
    # LLM相关配置（脱敏）
    llm_vars = [
        'LLM_PROVIDER', 'OPENAI_MODEL', 'OPENAI_BASE_URL',
        'AZURE_OPENAI_API_VERSION', 'AZURE_OPENAI_ENDPOINT'
    ]
    
    for var in llm_vars:
        value = os.getenv(var)
        if value:
            env_info[var] = sanitize_text(value)
    
    # 敏感变量只记录是否存在
    sensitive_vars = [
        'OPENAI_API_KEY', 'AZURE_OPENAI_API_KEY', 'MAOWISE_LIBRARY_DIR'
    ]
    
    for var in sensitive_vars:
        value = os.getenv(var)
        env_info[var] = 'SET' if value else 'NOT_SET'
    
    return env_info


def create_debug_info(include_full_env: bool = False) -> Dict[str, Any]:
    """
    创建调试信息（脱敏）
    
    Args:
        include_full_env: 是否包含完整环境信息
        
    Returns:
        Dict: 脱敏的调试信息
    """
    import sys
    import platform
    from datetime import datetime
    
    debug_info = {
        'timestamp': datetime.now().isoformat(),
        'python_version': sys.version,
        'platform': platform.platform(),
        'architecture': platform.architecture(),
        'processor': platform.processor(),
        'working_directory': '[PATH_REDACTED]',  # 始终脱敏工作目录
    }
    
    if include_full_env:
        debug_info['environment'] = get_sanitized_env_info()
    
    return debug_info
