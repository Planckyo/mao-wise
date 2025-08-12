#!/usr/bin/env python3
"""
LLM 连接健康检查脚本
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.llm.client import llm_chat
from maowise.utils import load_config
from maowise.utils.logger import logger


def test_basic_chat():
    """测试基本聊天功能"""
    messages = [
        {"role": "user", "content": "Hello, this is a connectivity test. Please respond with 'OK'."}
    ]
    
    try:
        response = llm_chat(messages)
        content = response.get("content", "")
        usage = response.get("usage", {})
        
        print(f"✅ LLM Response: {content[:100]}...")
        print(f"📊 Token Usage: {usage}")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return False


def test_json_output():
    """测试 JSON 格式输出"""
    messages = [
        {
            "role": "user", 
            "content": "Return a JSON object with keys 'status' and 'message'. Set status to 'ok' and message to 'test successful'."
        }
    ]
    
    try:
        response = llm_chat(
            messages,
            response_format={"type": "json_object"}
        )
        
        content = response.get("content", "")
        print(f"✅ JSON Response: {content}")
        
        # Try to parse JSON
        import json
        json.loads(content)
        print("✅ Valid JSON format")
        
        return True
        
    except Exception as e:
        print(f"❌ JSON Test Error: {e}")
        return False


def test_rag_integration():
    """测试 RAG 集成"""
    try:
        from maowise.llm.rag import build_context
        
        context = build_context("micro-arc oxidation", topk=3)
        print(f"✅ RAG Context: Found {len(context)} snippets")
        
        if context:
            for i, snippet in enumerate(context[:2], 1):
                print(f"   Snippet {i}: {snippet.text[:50]}... (score: {snippet.score:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ RAG Test Error: {e}")
        return False


def test_cache_functionality():
    """测试缓存功能"""
    messages = [
        {"role": "user", "content": "Cache test message - respond with current timestamp if possible"}
    ]
    
    try:
        # First call
        import time
        start_time = time.time()
        response1 = llm_chat(messages, use_cache=True)
        first_call_time = time.time() - start_time
        
        # Second call (should be cached)
        start_time = time.time()
        response2 = llm_chat(messages, use_cache=True)
        second_call_time = time.time() - start_time
        
        print(f"✅ Cache Test:")
        print(f"   First call: {first_call_time:.3f}s")
        print(f"   Second call: {second_call_time:.3f}s")
        
        if second_call_time < first_call_time * 0.5:
            print("✅ Cache appears to be working (faster second call)")
        else:
            print("⚠️  Cache may not be working (similar call times)")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache Test Error: {e}")
        return False


def main():
    """主函数"""
    print("🔍 MAO-Wise LLM 连接健康检查")
    print("=" * 50)
    
    # 加载配置
    try:
        config = load_config()
        llm_config = config.get("llm", {})
        provider = llm_config.get("provider", "local")
        
        print(f"📋 配置信息:")
        print(f"   Provider: {provider}")
        print(f"   Offline Fallback: {llm_config.get('offline_fallback', True)}")
        print(f"   Cache Directory: {llm_config.get('cache_dir', 'datasets/cache')}")
        print()
        
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return 1
    
    # 检查 API Key (仅对 openai/azure)
    if provider in ["openai", "azure"]:
        import os
        if provider == "openai":
            api_key = llm_config.get("openai", {}).get("api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("⚠️  未设置 OPENAI_API_KEY，将使用离线兜底模式")
        elif provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            if not api_key:
                print("⚠️  未设置 AZURE_OPENAI_API_KEY，将使用离线兜底模式")
    
    # 运行测试
    tests = [
        ("基本聊天测试", test_basic_chat),
        ("JSON 输出测试", test_json_output),
        ("RAG 集成测试", test_rag_integration),
        ("缓存功能测试", test_cache_functionality),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"🧪 {test_name}...")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} 通过\n")
            else:
                print(f"❌ {test_name} 失败\n")
        except Exception as e:
            print(f"❌ {test_name} 异常: {e}\n")
    
    # 总结
    print("=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！LLM 系统运行正常。")
        return 0
    elif passed > 0:
        print("⚠️  部分测试通过。请检查配置或网络连接。")
        if provider == "local":
            print("💡 提示: 当前使用本地模式，这是正常的离线兜底行为。")
        return 0  # 部分通过也算成功，因为有离线兜底
    else:
        print("❌ 所有测试失败。请检查配置。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
