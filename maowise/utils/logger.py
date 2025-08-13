from loguru import logger as _logger
import sys

_logger.remove()
_logger.add(sys.stderr, level="INFO", backtrace=True, diagnose=False, enqueue=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

logger = _logger

def setup_logger(name: str = None):
    """
    设置日志器
    
    Args:
        name: 日志器名称
        
    Returns:
        配置好的日志器
    """
    return _logger

