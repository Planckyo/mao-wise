#!/usr/bin/env python3
"""
A/B对照与缓存命中测试脚本
"""

import sys
import time
import json
import os
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.utils.logger import logger

def test_ab_cache(mode="offline", repeat_count=2):
    """测试A/B对照和缓存命中"""
    
    # 设置环境
    if mode == "online":
        if not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing"
        logger.info("🌐 在线模式已启用")
    else:
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        logger.info("📴 离线模式已启用")
    
    base_url = "http://localhost:8000"
    session = requests.Session()
    
    # 检查服务状态
    try:
        response = session.get(f"{base_url}/api/maowise/v1/health")
        if response.status_code != 200:
            logger.error("API服务未运行，请先启动服务")
            return False
        logger.info("✅ API服务正常运行")
    except Exception as e:
        logger.error(f"无法连接到API服务: {e}")
        return False
    
    # 获取测试前的使用统计
    try:
        stats_response = session.get(f"{base_url}/api/maowise/v1/stats/usage")
        stats_before = stats_response.json() if stats_response.status_code == 200 else {}
        logger.info("✅ 获取使用统计")
    except Exception as e:
        logger.warning(f"获取使用统计失败: {e}")
        stats_before = {}
    
    # 准备测试数据
    test_description = ("AZ91 substrate; silicate electrolyte: Na2SiO3 10 g/L, KOH 2 g/L; "
                      "bipolar 500 Hz 30% duty; current density 12 A/dm2; time 10 min; "
                      "post-treatment none.")
    
    results = []
    
    # 执行多次相同的clarify调用
    for i in range(repeat_count):
        logger.info(f"📞 执行第 {i+1} 次clarify调用...")
        
        payload = {
            "current_data": {},
            "context_description": test_description,
            "max_questions": 3,
            "include_mandatory": True
        }
        
        start_time = time.time()
        response = session.post(f"{base_url}/api/maowise/v1/expert/clarify", json=payload)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        if response.status_code != 200:
            logger.error(f"第 {i+1} 次调用失败: {response.status_code}")
            continue
        
        result = response.json()
        
        # 检测缓存命中
        cache_hit = False
        cache_info = {}
        
        # 检查响应头
        if hasattr(response, 'headers'):
            cache_hit = response.headers.get('X-Cache-Hit', 'false').lower() == 'true'
            cache_info['header_cache_hit'] = cache_hit
        
        # 检查响应JSON中的缓存标记
        try:
            if isinstance(result, dict):
                json_cache_hit = result.get('cache_hit', False)
                cache_info['json_cache_hit'] = json_cache_hit
                cache_hit = cache_hit or json_cache_hit
                
                # 检查LLM相关的缓存信息
                if 'llm_cache_hit' in result:
                    cache_info['llm_cache_hit'] = result['llm_cache_hit']
                    cache_hit = cache_hit or result['llm_cache_hit']
        except:
            pass
        
        # 记录结果
        call_result = {
            "call_number": i + 1,
            "response_time": response_time,
            "cache_hit": cache_hit,
            "cache_info": cache_info,
            "questions_count": len(result.get("questions", [])),
            "status_code": response.status_code,
            "mode": mode
        }
        
        results.append(call_result)
        logger.info(f"第 {i+1} 次调用完成: 响应时间={response_time:.3f}s, 缓存命中={cache_hit}, 问题数={len(result.get('questions', []))}")
        
        # 短暂延迟
        if i < repeat_count - 1:
            time.sleep(0.5)
    
    # 获取测试后的使用统计
    try:
        stats_response = session.get(f"{base_url}/api/maowise/v1/stats/usage")
        stats_after = stats_response.json() if stats_response.status_code == 200 else {}
    except Exception as e:
        logger.warning(f"获取测试后统计失败: {e}")
        stats_after = {}
    
    # 计算统计差异
    token_diff = 0
    cost_diff = 0.0
    requests_diff = 0
    
    if stats_after and stats_before:
        token_diff = stats_after.get("total", {}).get("tokens", 0) - stats_before.get("total", {}).get("tokens", 0)
        cost_diff = stats_after.get("total", {}).get("cost", 0.0) - stats_before.get("total", {}).get("cost", 0.0)
        requests_diff = stats_after.get("total", {}).get("requests", 0) - stats_before.get("total", {}).get("requests", 0)
    
    # 分析结果
    cache_hits = [r["cache_hit"] for r in results]
    cache_hit_rate = sum(cache_hits) / len(cache_hits) if cache_hits else 0
    response_times = [r["response_time"] for r in results]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    # 生成报告
    logger.info(f"\n📊 A/B对照测试报告 (模式: {mode})")
    logger.info("="*50)
    logger.info(f"调用次数: {len(results)}")
    logger.info(f"缓存命中率: {cache_hit_rate:.1%}")
    logger.info(f"缓存命中序列: {cache_hits}")
    logger.info(f"平均响应时间: {avg_response_time:.3f}s")
    logger.info(f"响应时间序列: {[f'{t:.3f}s' for t in response_times]}")
    logger.info(f"Token消耗差异: {token_diff}")
    logger.info(f"成本差异: ${cost_diff:.4f}")
    logger.info(f"请求数差异: {requests_diff}")
    
    if len(cache_hits) >= 2:
        second_call_cached = cache_hits[1] if len(cache_hits) > 1 else False
        logger.info(f"第二次调用缓存命中: {'✅ 是' if second_call_cached else '❌ 否'}")
        
        if len(response_times) >= 2:
            time_improvement = response_times[0] - response_times[1]
            improvement_pct = (time_improvement / response_times[0] * 100) if response_times[0] > 0 else 0
            logger.info(f"响应时间改善: {time_improvement:.3f}s ({improvement_pct:.1f}%)")
    
    # 保存详细结果到文件
    report_data = {
        "mode": mode,
        "repeat_count": repeat_count,
        "results": results,
        "cache_hit_rate": cache_hit_rate,
        "avg_response_time": avg_response_time,
        "token_diff": token_diff,
        "cost_diff": cost_diff,
        "requests_diff": requests_diff,
        "stats_before": stats_before,
        "stats_after": stats_after
    }
    
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    report_file = reports_dir / f"ab_cache_test_{mode}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"📄 详细报告已保存到: {report_file}")
    
    return True

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="A/B对照与缓存测试")
    parser.add_argument("--mode", choices=["offline", "online"], default="offline", help="测试模式")
    parser.add_argument("--repeat", type=int, default=2, help="重复次数")
    
    args = parser.parse_args()
    
    logger.info(f"🚀 开始A/B对照缓存测试")
    logger.info(f"模式: {args.mode}, 重复: {args.repeat}次")
    
    success = test_ab_cache(args.mode, args.repeat)
    
    if success:
        logger.info("🎉 A/B对照测试完成")
    else:
        logger.error("❌ A/B对照测试失败")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
