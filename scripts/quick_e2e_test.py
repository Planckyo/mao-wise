#!/usr/bin/env python3
"""
快速端到端测试脚本
验证核心功能并生成简单报告
"""

import sys
import time
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.utils.logger import logger


def test_basic_imports():
    """测试基本模块导入"""
    logger.info("🔍 测试基本模块导入...")
    
    try:
        from maowise.utils.config import load_config
        from maowise.utils.sanitizer import sanitize_text
        from maowise.llm.client import llm_chat
        from maowise.experts.clarify import generate_clarify_questions
        from maowise.experts.followups import validate_mandatory_answers
        
        logger.info("✅ 所有核心模块导入成功")
        return True
    except Exception as e:
        logger.error(f"❌ 模块导入失败: {e}")
        return False


def test_config_loading():
    """测试配置加载"""
    logger.info("🔍 测试配置加载...")
    
    try:
        from maowise.utils.config import load_config
        config = load_config()
        
        if isinstance(config, dict):
            logger.info("✅ 配置文件加载成功")
            return True
        else:
            logger.error("❌ 配置格式错误")
            return False
    except Exception as e:
        logger.error(f"❌ 配置加载失败: {e}")
        return False


def test_data_sanitization():
    """测试数据脱敏"""
    logger.info("🔍 测试数据脱敏...")
    
    try:
        from maowise.utils.sanitizer import sanitize_text, sanitize_dict
        
        # 测试文本脱敏
        test_text = "API key: sk-1234567890abcdefghij"
        sanitized = sanitize_text(test_text)
        
        if "sk-1234567890abcdefghij" not in sanitized:
            logger.info("✅ 文本脱敏功能正常")
            text_ok = True
        else:
            logger.error("❌ 文本脱敏失败")
            text_ok = False
        
        # 测试字典脱敏
        test_dict = {"api_key": "secret123", "normal": "value"}
        sanitized_dict = sanitize_dict(test_dict)
        
        if sanitized_dict["api_key"] == "[REDACTED]" and sanitized_dict["normal"] == "value":
            logger.info("✅ 字典脱敏功能正常")
            dict_ok = True
        else:
            logger.error("❌ 字典脱敏失败")
            dict_ok = False
        
        return text_ok and dict_ok
        
    except Exception as e:
        logger.error(f"❌ 数据脱敏测试失败: {e}")
        return False


def test_llm_client():
    """测试LLM客户端"""
    logger.info("🔍 测试LLM客户端...")
    
    try:
        from maowise.llm.client import llm_chat
        
        messages = [{"role": "user", "content": "Hello, this is a test."}]
        response = llm_chat(messages, use_cache=False)
        
        if isinstance(response, dict) and "content" in response:
            logger.info("✅ LLM客户端功能正常（离线模式）")
            return True
        else:
            logger.error("❌ LLM客户端响应格式错误")
            return False
            
    except Exception as e:
        logger.error(f"❌ LLM客户端测试失败: {e}")
        return False


def test_expert_system():
    """测试专家系统"""
    logger.info("🔍 测试专家系统...")
    
    try:
        from maowise.experts.clarify import generate_clarify_questions
        from maowise.experts.followups import validate_mandatory_answers
        
        # 测试澄清问题生成
        questions = generate_clarify_questions(
            current_data={},
            max_questions=2,
            include_mandatory=True
        )
        
        if isinstance(questions, list):
            logger.info(f"✅ 澄清问题生成正常，生成了 {len(questions)} 个问题")
            questions_ok = True
        else:
            logger.error("❌ 澄清问题生成失败")
            questions_ok = False
        
        # 测试必答问题验证
        test_answers = {"fluoride_additives": "不允许"}
        validation = validate_mandatory_answers(test_answers)
        
        if isinstance(validation, dict) and "all_answered" in validation:
            logger.info("✅ 必答问题验证功能正常")
            validation_ok = True
        else:
            logger.error("❌ 必答问题验证失败")
            validation_ok = False
        
        return questions_ok and validation_ok
        
    except Exception as e:
        logger.error(f"❌ 专家系统测试失败: {e}")
        return False


def test_data_fixtures():
    """测试数据夹具"""
    logger.info("🔍 测试数据夹具...")
    
    try:
        fixture_file = Path("tests/fixtures/min_corpus.jsonl")
        
        if fixture_file.exists():
            with open(fixture_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            valid_lines = [line for line in lines if line.strip()]
            
            if len(valid_lines) >= 3:
                logger.info(f"✅ 数据夹具正常，包含 {len(valid_lines)} 条记录")
                return True
            else:
                logger.error(f"❌ 数据夹具记录不足: {len(valid_lines)}")
                return False
        else:
            logger.error("❌ 数据夹具文件不存在")
            return False
            
    except Exception as e:
        logger.error(f"❌ 数据夹具测试失败: {e}")
        return False


def test_usage_tracking():
    """测试使用统计"""
    logger.info("🔍 测试使用统计...")
    
    try:
        from maowise.llm.client import UsageTracker
        
        # 创建测试统计文件
        test_file = Path("datasets/cache/test_usage_quick.csv")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        
        tracker = UsageTracker(str(test_file))
        
        # 记录测试数据
        test_usage = {
            "prompt_tokens": 50,
            "completion_tokens": 25,
            "total_tokens": 75
        }
        
        tracker.log_usage("test", "gpt-4o-mini", test_usage, cost_usd=0.001)
        
        # 检查文件
        if test_file.exists():
            with open(test_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if len(lines) >= 2:  # 表头 + 数据
                logger.info("✅ 使用统计功能正常")
                # 清理测试文件
                test_file.unlink()
                return True
            else:
                logger.error("❌ 使用统计文件为空")
                return False
        else:
            logger.error("❌ 使用统计文件未创建")
            return False
            
    except Exception as e:
        logger.error(f"❌ 使用统计测试失败: {e}")
        return False


def generate_quick_report(results: dict):
    """生成快速报告"""
    logger.info("📊 生成测试报告...")
    
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    total_tests = len(results)
    passed_tests = sum(1 for success in results.values() if success)
    failed_tests = total_tests - passed_tests
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    # 生成Markdown报告
    md_content = f"""# MAO-Wise 快速端到端测试报告

## 测试概览

- **测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **测试总数**: {total_tests}
- **通过数量**: {passed_tests} ✅
- **失败数量**: {failed_tests} ❌
- **通过率**: {pass_rate:.1f}%

## 测试结果

"""
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        md_content += f"- **{test_name}**: {status}\n"
    
    md_content += f"""
## 总结

"""
    
    if passed_tests == total_tests:
        md_content += """**🎉 所有测试通过！** MAO-Wise 核心功能运行正常。

### 验收达成情况

- ✅ 核心模块导入和配置加载
- ✅ 数据脱敏和安全处理
- ✅ LLM客户端离线兜底模式
- ✅ 专家系统问答机制
- ✅ 数据夹具和使用统计

"""
    else:
        md_content += f"""**⚠️ {failed_tests} 项测试失败**，需要进一步检查。

### 失败的测试项

"""
        for test_name, success in results.items():
            if not success:
                md_content += f"- ❌ {test_name}\n"
    
    md_content += f"""
---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    # 保存报告
    report_file = reports_dir / "quick_e2e_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    logger.info(f"✅ 快速测试报告已生成: {report_file}")
    return report_file


def main():
    """主函数"""
    logger.info("🚀 开始快速端到端测试")
    logger.info("="*60)
    
    test_functions = [
        ("基本模块导入", test_basic_imports),
        ("配置加载", test_config_loading),
        ("数据脱敏", test_data_sanitization),
        ("LLM客户端", test_llm_client),
        ("专家系统", test_expert_system),
        ("数据夹具", test_data_fixtures),
        ("使用统计", test_usage_tracking),
    ]
    
    results = {}
    
    for test_name, test_func in test_functions:
        logger.info(f"\n🔍 执行测试: {test_name}")
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"❌ {test_name} 测试异常: {e}")
            results[test_name] = False
        
        time.sleep(0.5)  # 短暂间隔
    
    # 生成报告
    report_file = generate_quick_report(results)
    
    # 显示总结
    logger.info("\n" + "="*60)
    logger.info("📊 快速测试总结")
    logger.info("="*60)
    
    passed = sum(1 for success in results.values() if success)
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        logger.info(f"{test_name:15} : {status}")
    
    logger.info(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        logger.info("\n🎉 所有核心功能测试通过！")
        logger.info("MAO-Wise 系统基础功能运行正常")
        success = True
    else:
        logger.warning(f"\n⚠️ {total - passed} 项测试失败")
        logger.info("请检查失败的测试项目")
        success = False
    
    logger.info(f"\n📋 报告文件: {report_file}")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
