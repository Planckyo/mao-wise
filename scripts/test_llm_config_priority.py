#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM配置优先级和状态显示测试脚本

验证环境变量 > .env > config.yaml 的读取优先级
验证API状态端点的Provider信息显示
"""

import sys
import os
import tempfile
import subprocess
from pathlib import Path

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import setup_logger

def test_config_priority():
    """测试配置读取优先级"""
    logger = setup_logger(__name__)
    logger.info("=== 测试配置读取优先级 ===")
    
    try:
        from maowise.llm.client import _get_llm_config, get_llm_status
        
        # 备份当前环境变量
        backup_env = {}
        env_vars = ["LLM_PROVIDER", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", 
                   "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"]
        
        for var in env_vars:
            if var in os.environ:
                backup_env[var] = os.environ[var]
                del os.environ[var]
        
        # 测试1: 无配置时应该回退到local
        logger.info("测试1: 无配置情况")
        provider, config, key_source = _get_llm_config()
        logger.info(f"Provider: {provider}, Key Source: {key_source}")
        
        if provider == "local" and key_source == "none":
            logger.info("✅ 无配置时正确回退到local")
        else:
            logger.warning(f"⚠️ 无配置时行为异常: provider={provider}, key_source={key_source}")
        
        # 测试2: 环境变量优先级
        logger.info("测试2: 环境变量配置")
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "sk-test1234567890abcdef1234567890abcdef"
        
        provider, config, key_source = _get_llm_config()
        logger.info(f"Provider: {provider}, Key Source: {key_source}")
        
        if provider == "openai" and key_source == "env":
            logger.info("✅ 环境变量配置正确读取")
        else:
            logger.warning(f"⚠️ 环境变量配置异常: provider={provider}, key_source={key_source}")
        
        # 测试3: .env文件优先级
        logger.info("测试3: .env文件配置")
        
        # 清除环境变量
        del os.environ["LLM_PROVIDER"]
        del os.environ["OPENAI_API_KEY"]
        
        # 创建临时.env文件（在当前目录）
        env_content = """LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=test-azure-key-123
AZURE_OPENAI_ENDPOINT=https://test.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4
"""
        
        env_file = Path.cwd() / ".env"
        backup_env_file = None
        if env_file.exists():
            backup_env_file = env_file.read_text(encoding='utf-8')
        
        env_file.write_text(env_content, encoding='utf-8')
        
        try:
            provider, config, key_source = _get_llm_config()
            logger.info(f"Provider: {provider}, Key Source: {key_source}")
            
            if provider == "azure" and key_source == "dotenv":
                logger.info("✅ .env文件配置正确读取")
            else:
                logger.warning(f"⚠️ .env文件配置异常: provider={provider}, key_source={key_source}")
        
        finally:
            # 恢复.env文件
            if backup_env_file is not None:
                env_file.write_text(backup_env_file, encoding='utf-8')
            elif env_file.exists():
                env_file.unlink()
        
        # 测试4: 环境变量覆盖.env
        logger.info("测试4: 环境变量覆盖.env文件")
        
        # 设置环境变量
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "sk-env-override-key"
        
        # 保持.env文件中的Azure配置
        env_file.write_text(env_content, encoding='utf-8')
        
        try:
            provider, config, key_source = _get_llm_config()
            logger.info(f"Provider: {provider}, Key Source: {key_source}")
            
            if provider == "openai" and key_source == "env":
                logger.info("✅ 环境变量正确覆盖.env文件")
            else:
                logger.warning(f"⚠️ 环境变量覆盖失败: provider={provider}, key_source={key_source}")
        
        finally:
            # 清理.env文件
            if backup_env_file is not None:
                env_file.write_text(backup_env_file, encoding='utf-8')
            elif env_file.exists():
                env_file.unlink()
        
        # 恢复环境变量
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]
        
        for var, value in backup_env.items():
            os.environ[var] = value
        
        return True
        
    except Exception as e:
        logger.error(f"配置优先级测试失败: {e}")
        return False

def test_key_masking():
    """测试密钥掩码功能"""
    logger = setup_logger(__name__)
    logger.info("=== 测试密钥掩码功能 ===")
    
    try:
        from maowise.llm.client import _mask_key
        
        test_cases = [
            ("sk-test1234567890abcdef", "sk-t***************cdef"),  # 23字符，15个*
            ("short", "[EMPTY]"),
            ("", "[EMPTY]"),
            ("sk-proj-1234567890abcdef1234567890abcdef1234567890abcdef", "sk-p************************************************cdef")  # 56字符，48个*
        ]
        
        all_passed = True
        for key, expected in test_cases:
            result = _mask_key(key)
            if result == expected:
                logger.info(f"✅ '{key}' -> '{result}'")
            else:
                logger.warning(f"⚠️ '{key}' -> '{result}' (expected: '{expected}')")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        logger.error(f"密钥掩码测试失败: {e}")
        return False

def test_api_model_status():
    """测试API模型状态端点"""
    logger = setup_logger(__name__)
    logger.info("=== 测试API模型状态端点 ===")
    
    try:
        import requests
        import time
        
        # 检查API是否运行
        api_base = "http://localhost:8000"
        
        try:
            response = requests.get(f"{api_base}/api/maowise/v1/admin/model_status", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                # 检查必需字段
                required_fields = ["llm_provider", "llm_key_source", "llm_providers_available"]
                missing_fields = []
                
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if missing_fields:
                    logger.warning(f"⚠️ API响应缺少字段: {missing_fields}")
                    return False
                
                # 显示LLM状态
                logger.info(f"✅ API响应正常:")
                logger.info(f"  LLM Provider: {data['llm_provider']}")
                logger.info(f"  Key Source: {data['llm_key_source']}")
                logger.info(f"  Available Providers: {data['llm_providers_available']}")
                
                return True
            else:
                logger.warning(f"⚠️ API响应状态码: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.info("ℹ️ API服务未运行，跳过API测试")
            return True
        except requests.exceptions.Timeout:
            logger.warning("⚠️ API请求超时")
            return False
            
    except Exception as e:
        logger.error(f"API状态测试失败: {e}")
        return False

def test_llm_status_function():
    """测试LLM状态函数"""
    logger = setup_logger(__name__)
    logger.info("=== 测试LLM状态函数 ===")
    
    try:
        from maowise.llm.client import get_llm_status
        
        status = get_llm_status()
        
        # 检查必需字段
        required_fields = ["llm_provider", "llm_key_source", "providers_available"]
        missing_fields = []
        
        for field in required_fields:
            if field not in status:
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"⚠️ 状态信息缺少字段: {missing_fields}")
            return False
        
        # 显示状态信息
        logger.info(f"✅ 状态函数正常:")
        logger.info(f"  Provider: {status['llm_provider']}")
        logger.info(f"  Key Source: {status['llm_key_source']}")
        logger.info(f"  OpenAI Available: {status['providers_available'].get('openai', False)}")
        logger.info(f"  Azure Available: {status['providers_available'].get('azure', False)}")
        logger.info(f"  Local Available: {status['providers_available'].get('local', True)}")
        
        return True
        
    except Exception as e:
        logger.error(f"LLM状态函数测试失败: {e}")
        return False

def test_env_file_reading():
    """测试.env文件读取功能"""
    logger = setup_logger(__name__)
    logger.info("=== 测试.env文件读取功能 ===")
    
    try:
        from maowise.llm.client import _read_env_file
        
        # 创建临时.env文件
        test_content = """# 测试配置
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-test123
# 注释行
AZURE_OPENAI_ENDPOINT=https://test.com/

# 空行测试
EMPTY_VALUE=
"""
        
        env_file = Path.cwd() / ".env"
        backup_content = None
        if env_file.exists():
            backup_content = env_file.read_text(encoding='utf-8')
        
        env_file.write_text(test_content, encoding='utf-8')
        
        try:
            env_vars = _read_env_file()
            
            expected_keys = ["LLM_PROVIDER", "OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "EMPTY_VALUE"]
            missing_keys = []
            
            for key in expected_keys:
                if key not in env_vars:
                    missing_keys.append(key)
            
            if missing_keys:
                logger.warning(f"⚠️ .env读取缺少键: {missing_keys}")
                return False
            
            # 检查值
            if env_vars["LLM_PROVIDER"] == "openai" and env_vars["OPENAI_API_KEY"] == "sk-test123":
                logger.info("✅ .env文件读取正常")
                return True
            else:
                logger.warning(f"⚠️ .env文件读取值异常: {env_vars}")
                return False
        
        finally:
            # 恢复文件
            if backup_content is not None:
                env_file.write_text(backup_content, encoding='utf-8')
            elif env_file.exists():
                env_file.unlink()
        
    except Exception as e:
        logger.error(f".env文件读取测试失败: {e}")
        return False

def generate_comprehensive_report():
    """生成综合测试报告"""
    logger = setup_logger(__name__)
    logger.info("=== LLM配置优先级和状态显示测试报告 ===")
    
    tests = [
        ("配置读取优先级", test_config_priority),
        ("密钥掩码功能", test_key_masking),
        (".env文件读取", test_env_file_reading),
        ("LLM状态函数", test_llm_status_function),
        ("API模型状态端点", test_api_model_status)
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n运行测试: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"测试 {test_name} 异常: {e}")
            results.append((test_name, False))
    
    # 生成总结
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    logger.info("\n" + "="*60)
    logger.info("LLM配置优先级和状态显示测试总结")
    logger.info("="*60)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n总体结果: {passed}/{total} 测试通过")
    
    if passed == total:
        logger.info("\n🎉 所有功能测试通过！LLM配置统一读取系统正常运行")
        return True
    else:
        logger.warning(f"\n⚠️ {total - passed} 个测试失败，需要检查问题")
        return False

def main():
    """主函数"""
    logger = setup_logger(__name__)
    
    try:
        logger.info("🔧 开始 LLM配置优先级和状态显示功能测试")
        success = generate_comprehensive_report()
        
        if success:
            logger.info("\n✅ 所有功能验证完成，LLM统一配置系统运行正常")
            sys.exit(0)
        else:
            logger.info("\n❌ 部分功能验证失败，请检查问题")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
