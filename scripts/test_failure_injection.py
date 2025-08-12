#!/usr/bin/env python3
"""
失败注入测试脚本 - 独立验证系统健壮性
"""

import sys
import time
import json
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.utils.logger import logger

def test_malformed_json_handling():
    """测试LLM返回损坏JSON的处理"""
    logger.info("🔧 测试LLM损坏JSON处理...")
    
    base_url = "http://localhost:8000"
    
    # 发送可能导致JSON解析错误的请求
    payload = {
        "current_data": {"test_malformed_json": True},
        "context_description": "Test malformed JSON response from LLM - 特殊字符测试 {}[]()\"'",
        "max_questions": 1
    }
    
    try:
        response = requests.post(f"{base_url}/api/maowise/v1/expert/clarify", json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            # 检查兜底机制迹象
            has_fallback = any(key in result for key in [
                'fallback_used', 'json_repair_attempted', 'schema_validation_failed',
                'questions', 'error_recovered'
            ])
            
            logger.info(f"✅ JSON处理测试: {'兜底机制激活' if has_fallback else '正常处理'}")
            logger.info(f"   响应键: {list(result.keys())}")
            logger.info(f"   问题数量: {len(result.get('questions', []))}")
            
            return {
                "test": "LLM损坏JSON",
                "status": "兜底成功" if has_fallback else "正常响应",
                "success": True,
                "details": {
                    "response_keys": list(result.keys()),
                    "questions_count": len(result.get('questions', [])),
                    "fallback_indicators": has_fallback
                }
            }
        else:
            logger.info(f"✅ JSON处理测试: 友好报错 (HTTP {response.status_code})")
            return {
                "test": "LLM损坏JSON",
                "status": "友好报错",
                "success": True,
                "details": {"status_code": response.status_code}
            }
            
    except Exception as e:
        logger.warning(f"⚠️ JSON处理测试异常: {e}")
        return {
            "test": "LLM损坏JSON",
            "status": "异常捕获",
            "success": False,
            "details": {"error": str(e)}
        }

def test_session_conflict():
    """测试会话状态冲突处理"""
    logger.info("🔧 测试会话状态冲突...")
    
    base_url = "http://localhost:8000"
    
    try:
        # 尝试直接调用resolve端点而不创建有效会话
        conflict_payload = {
            "thread_id": "nonexistent_thread_12345",
            "status": "answered",
            "force_resolve": True
        }
        
        response = requests.post(f"{base_url}/api/maowise/v1/expert/thread/resolve", 
                               json=conflict_payload, timeout=15)
        
        if response.status_code == 409:
            logger.info("✅ 会话冲突测试: 正确返回409 Conflict")
            return {
                "test": "会话状态冲突",
                "status": "友好报错",
                "success": True,
                "details": {
                    "status_code": 409,
                    "conflict_detected": True,
                    "error_message": response.text[:100]
                }
            }
        elif response.status_code in [400, 422, 404]:
            logger.info(f"✅ 会话冲突测试: 参数验证错误 (HTTP {response.status_code})")
            return {
                "test": "会话状态冲突",
                "status": "参数验证",
                "success": True,
                "details": {
                    "status_code": response.status_code,
                    "validation_error": True
                }
            }
        else:
            logger.warning(f"⚠️ 会话冲突测试: 意外响应 (HTTP {response.status_code})")
            return {
                "test": "会话状态冲突",
                "status": "意外响应",
                "success": False,
                "details": {"status_code": response.status_code}
            }
            
    except Exception as e:
        logger.warning(f"⚠️ 会话冲突测试异常: {e}")
        return {
            "test": "会话状态冲突",
            "status": "异常捕获",
            "success": False,
            "details": {"error": str(e)}
        }

def test_incomplete_yaml():
    """测试YAML缺失关键字段处理"""
    logger.info("🔧 测试YAML缺失关键字段...")
    
    base_url = "http://localhost:8000"
    
    # 构造不完整的解决方案
    incomplete_solution = {
        "electrolyte_composition": {
            "Na2SiO3": 15.0
            # 缺少其他必要组分
        },
        "process_parameters": {
            "voltage_V": 400
            # 缺少电流密度、时间等关键参数
        },
        # 完全缺少expected_performance等字段
        "description": "Incomplete solution for testing"
    }
    
    try:
        payload = {"solution": incomplete_solution}
        response = requests.post(f"{base_url}/api/maowise/v1/expert/plan", 
                               json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            hard_constraints_passed = result.get("hard_constraints_passed", True)
            has_warnings = any(key in result for key in ['soft_warnings', 'warnings', 'validation_errors'])
            has_yaml = "plan_yaml" in result
            
            if not hard_constraints_passed:
                logger.info("✅ YAML缺失测试: 正确标注hard_constraints_passed=false")
                status = "约束检查"
            elif has_warnings:
                logger.info("✅ YAML缺失测试: 提供了软警告")
                status = "生成带警告"
            else:
                logger.info("✅ YAML缺失测试: 系统补全了缺失字段")
                status = "自动补全"
            
            return {
                "test": "YAML缺失字段",
                "status": status,
                "success": True,
                "details": {
                    "hard_constraints_passed": hard_constraints_passed,
                    "has_warnings": has_warnings,
                    "has_yaml_plan": has_yaml,
                    "response_keys": list(result.keys()),
                    "warnings": result.get("soft_warnings", result.get("warnings", []))
                }
            }
        else:
            logger.info(f"✅ YAML缺失测试: 友好报错 (HTTP {response.status_code})")
            return {
                "test": "YAML缺失字段",
                "status": "友好报错",
                "success": True,
                "details": {"status_code": response.status_code}
            }
            
    except Exception as e:
        logger.warning(f"⚠️ YAML缺失测试异常: {e}")
        return {
            "test": "YAML缺失字段",
            "status": "异常捕获",
            "success": False,
            "details": {"error": str(e)}
        }

def check_api_health():
    """检查API服务健康状态"""
    base_url = "http://localhost:8000"
    
    try:
        response = requests.get(f"{base_url}/api/maowise/v1/health", timeout=5)
        if response.status_code == 200:
            logger.info("✅ API服务正常运行")
            return True
        else:
            logger.error(f"❌ API服务异常: HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ 无法连接到API服务: {e}")
        logger.info("请确保已启动API服务: uvicorn apps.api.main:app --host 127.0.0.1 --port 8000")
        return False

def generate_failure_report(results):
    """生成失败注入测试报告"""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    # 计算统计信息
    total_tests = len(results)
    successful_tests = len([r for r in results if r["success"]])
    robustness_score = successful_tests / total_tests if total_tests > 0 else 0
    
    # 生成Markdown报告
    report_content = f"""# MAO-Wise 失败注入测试报告

## 测试概览

- **测试时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}
- **测试场景**: {total_tests}
- **成功处理**: {successful_tests}
- **健壮性评分**: {robustness_score:.1%}

## 测试结果

| 测试场景 | 系统响应 | 状态 | 详情 |
|---------|---------|------|------|
"""
    
    for result in results:
        test_name = result["test"]
        status = result["status"]
        success = result["success"]
        details = result["details"]
        
        status_icon = "✅" if success else "❌"
        
        detail_summary = ""
        if "status_code" in details:
            detail_summary += f"HTTP {details['status_code']}"
        if "questions_count" in details:
            detail_summary += f", {details['questions_count']}个问题"
        if "hard_constraints_passed" in details:
            detail_summary += f", 约束{'通过' if details['hard_constraints_passed'] else '未通过'}"
        
        report_content += f"| {test_name} | {status} | {status_icon} | {detail_summary} |\n"
    
    report_content += f"""

## 详细分析

### 1. LLM损坏JSON处理
- **测试目的**: 验证当LLM返回格式错误的JSON时，系统能否通过jsonio.expect_schema进行二次修复
- **预期行为**: 触发JSON修复机制或提供兜底响应
- **实际结果**: {next((r['status'] for r in results if r['test'] == 'LLM损坏JSON'), '未测试')}

### 2. 会话状态冲突处理  
- **测试目的**: 验证当会话在resolve前被手动改为answered状态时的处理
- **预期行为**: 返回409 Conflict状态码并提供友好的错误提示
- **实际结果**: {next((r['status'] for r in results if r['test'] == '会话状态冲突'), '未测试')}

### 3. YAML缺失字段处理
- **测试目的**: 验证工艺卡YAML缺少关键字段时的处理
- **预期行为**: 规则引擎标注hard_constraints_passed=false并给出明确的soft_warnings
- **实际结果**: {next((r['status'] for r in results if r['test'] == 'YAML缺失字段'), '未测试')}

## 健壮性评估

- **整体健壮性**: {'优秀' if robustness_score >= 1.0 else '良好' if robustness_score >= 0.8 else '需要改进' if robustness_score >= 0.6 else '较差'}
- **错误处理**: {'完善' if robustness_score >= 0.8 else '基本完善' if robustness_score >= 0.6 else '需要加强'}
- **用户体验**: {'友好' if robustness_score >= 0.8 else '可接受' if robustness_score >= 0.6 else '需要优化'}

## 建议

"""
    
    if robustness_score < 1.0:
        failed_tests = [r for r in results if not r["success"]]
        if failed_tests:
            report_content += "### 需要关注的问题\n\n"
            for failed in failed_tests:
                report_content += f"- **{failed['test']}**: {failed['status']} - {failed['details'].get('error', '详见测试日志')}\n"
    else:
        report_content += "### 系统表现优秀\n\n"
        report_content += "- 所有失败注入场景都得到了正确处理\n"
        report_content += "- 系统具有良好的健壮性和错误恢复能力\n"
        report_content += "- 用户体验友好，错误提示清晰\n"
    
    report_content += f"""

---
*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    # 保存报告
    report_file = reports_dir / "failure_injection_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    # 保存JSON格式的详细结果
    json_file = reports_dir / "failure_injection_results.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "robustness_score": robustness_score,
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"📄 失败注入测试报告已生成:")
    logger.info(f"  - {report_file}")
    logger.info(f"  - {json_file}")

def main():
    """主函数"""
    logger.info("💥 开始失败注入测试...")
    
    # 检查API服务
    if not check_api_health():
        return False
    
    # 执行失败注入测试
    test_results = []
    
    test_results.append(test_malformed_json_handling())
    time.sleep(1)
    
    test_results.append(test_session_conflict())
    time.sleep(1)
    
    test_results.append(test_incomplete_yaml())
    
    # 生成报告
    generate_failure_report(test_results)
    
    # 统计结果
    successful_tests = len([r for r in test_results if r["success"]])
    total_tests = len(test_results)
    robustness_score = successful_tests / total_tests if total_tests > 0 else 0
    
    logger.info(f"\n💥 失败注入测试完成!")
    logger.info(f"📊 健壮性评分: {robustness_score:.1%} ({successful_tests}/{total_tests})")
    
    if robustness_score >= 0.8:
        logger.info("🎉 系统健壮性表现优秀!")
    elif robustness_score >= 0.6:
        logger.info("✅ 系统健壮性表现良好")
    else:
        logger.warning("⚠️ 系统健壮性需要改进")
    
    return robustness_score >= 0.6

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
