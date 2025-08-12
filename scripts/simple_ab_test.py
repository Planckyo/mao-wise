#!/usr/bin/env python3
"""
简化的A/B对照测试
"""

import requests
import time
import json
import os
from pathlib import Path

def test_clarify_cache():
    """测试clarify接口的缓存功能"""
    
    base_url = "http://localhost:8000"
    
    # 检查API服务
    try:
        response = requests.get(f"{base_url}/api/maowise/v1/health", timeout=5)
        print(f"✅ API服务状态: {response.status_code}")
    except Exception as e:
        print(f"❌ API服务不可用: {e}")
        return False
    
    # 准备测试数据
    payload = {
        "current_data": {},
        "context_description": "AZ91 substrate; silicate electrolyte: Na2SiO3 10 g/L, KOH 2 g/L; bipolar 500 Hz 30% duty; current density 12 A/dm2; time 10 min; post-treatment none.",
        "max_questions": 3,
        "include_mandatory": True
    }
    
    results = []
    
    # 执行两次相同的请求
    for i in range(2):
        print(f"\n📞 第 {i+1} 次调用...")
        
        start_time = time.time()
        response = requests.post(f"{base_url}/api/maowise/v1/expert/clarify", json=payload, timeout=30)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        if response.status_code == 200:
            result = response.json()
            questions_count = len(result.get("questions", []))
            
            # 检查缓存标记
            cache_hit = False
            if 'cache_hit' in result:
                cache_hit = result['cache_hit']
            elif response.headers.get('X-Cache-Hit'):
                cache_hit = response.headers.get('X-Cache-Hit').lower() == 'true'
            
            call_info = {
                "call": i + 1,
                "response_time": response_time,
                "questions_count": questions_count,
                "cache_hit": cache_hit,
                "status": "success"
            }
            
            print(f"  ✅ 成功: {response_time:.3f}s, 问题数: {questions_count}, 缓存: {cache_hit}")
        else:
            call_info = {
                "call": i + 1,
                "response_time": response_time,
                "status": "failed",
                "error": response.status_code
            }
            print(f"  ❌ 失败: {response.status_code}")
        
        results.append(call_info)
        
        # 短暂延迟
        if i < 1:
            time.sleep(1)
    
    # 分析结果
    print(f"\n📊 测试结果分析:")
    print(f"调用次数: {len(results)}")
    
    successful_calls = [r for r in results if r.get("status") == "success"]
    if len(successful_calls) >= 2:
        first_time = successful_calls[0]["response_time"]
        second_time = successful_calls[1]["response_time"]
        time_diff = first_time - second_time
        improvement = (time_diff / first_time * 100) if first_time > 0 else 0
        
        print(f"第一次响应时间: {first_time:.3f}s")
        print(f"第二次响应时间: {second_time:.3f}s")
        print(f"时间差异: {time_diff:.3f}s ({improvement:.1f}%)")
        
        # 检查第二次是否有缓存命中
        second_cached = successful_calls[1].get("cache_hit", False)
        print(f"第二次调用缓存命中: {'✅ 是' if second_cached else '❌ 否'}")
        
        if second_cached or improvement > 20:
            print("🎉 缓存机制工作正常!")
        else:
            print("⚠️ 缓存机制可能需要检查")
    
    # 保存结果
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    with open(reports_dir / "simple_ab_test.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 结果已保存到: reports/simple_ab_test.json")
    
    return True

if __name__ == "__main__":
    print("🚀 开始简化A/B对照测试...")
    
    # 设置离线模式
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    print("📴 离线模式已启用")
    
    success = test_clarify_cache()
    
    if success:
        print("\n🎉 测试完成!")
    else:
        print("\n❌ 测试失败!")
