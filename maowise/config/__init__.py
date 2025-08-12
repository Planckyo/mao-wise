"""
Configuration module for MAO-Wise
"""

try:
    from maowise.utils.config import load_config
except ImportError:
    # Fallback for direct import
    try:
        from ..utils.config import load_config
    except ImportError:
        def load_config():
            """Fallback config loader"""
            return {"dummy": True}

__all__ = ["load_config"]
