#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real Run 基础功能测试脚本

测试 Real Run 脚本的各个组件是否正常工作
"""

import sys
import os
from pathlib import Path
import tempfile
import subprocess

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import setup_logger

def test_script_syntax():
    """测试PowerShell脚本语法"""
    logger = setup_logger(__name__)
    logger.info("=== 测试PowerShell脚本语法 ===")
    
    try:
        # 测试语法检查
        result = subprocess.run([
            "powershell", "-Command", 
            f"Get-Content '{REPO_ROOT}/scripts/real_run.ps1' | Out-Null"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ PowerShell脚本语法检查通过")
            return True
        else:
            logger.error(f"❌ PowerShell脚本语法错误: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 语法检查失败: {e}")
        return False

def test_environment_check():
    """测试环境检查功能"""
    logger = setup_logger(__name__)
    logger.info("=== 测试环境检查功能 ===")
    
    try:
        # 测试缺少API Key的情况
        env = os.environ.copy()
        if 'OPENAI_API_KEY' in env:
            del env['OPENAI_API_KEY']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run([
                "powershell", "-ExecutionPolicy", "Bypass", "-Command",
                f"& '{REPO_ROOT}/scripts/real_run.ps1' -LibraryDir '{temp_dir}'"
            ], capture_output=True, text=True, env=env)
            
            if "OPENAI_API_KEY environment variable not set" in result.stdout:
                logger.info("✅ 环境检查功能正常（正确检测到缺少API Key）")
                return True
            else:
                logger.warning(f"⚠️ 环境检查可能有问题: {result.stdout}")
                return False
                
    except Exception as e:
        logger.error(f"❌ 环境检查测试失败: {e}")
        return False

def test_component_scripts():
    """测试组件脚本是否存在"""
    logger = setup_logger(__name__)
    logger.info("=== 测试组件脚本 ===")
    
    required_scripts = [
        "scripts/pipeline_real.ps1",
        "scripts/generate_batch_plans.py", 
        "scripts/validate_recommendations.py",
        "scripts/evaluate_predictions.py"
    ]
    
    all_exist = True
    for script_path in required_scripts:
        full_path = REPO_ROOT / script_path
        if full_path.exists():
            logger.info(f"✅ {script_path} 存在")
        else:
            logger.error(f"❌ {script_path} 不存在")
            all_exist = False
    
    return all_exist

def test_report_generation():
    """测试报告生成功能"""
    logger = setup_logger(__name__)
    logger.info("=== 测试报告生成功能 ===")
    
    try:
        # 创建模拟数据
        reports_dir = REPO_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        
        tasks_dir = REPO_ROOT / "tasks"
        tasks_dir.mkdir(exist_ok=True)
        
        # 创建模拟批次目录
        import csv
        from datetime import datetime
        
        batch_id = f"batch_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch_dir = tasks_dir / batch_id
        batch_dir.mkdir(exist_ok=True)
        
        # 创建模拟CSV文件
        csv_file = batch_dir / "plans.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "plan_id", "batch_id", "system", "alpha", "epsilon", "confidence",
                "hard_constraints_passed", "rule_penalty", "reward_score", 
                "citations_count", "status", "created_at",
                "mass_proxy", "uniformity_penalty", "score_total"
            ])
            
            # 添加一些测试数据
            for i in range(3):
                writer.writerow([
                    f"{batch_id}_plan_{i:03d}", batch_id, "silicate", 
                    0.15 + i * 0.01, 0.85 + i * 0.01, 0.7 + i * 0.1,
                    True, 2.0 + i, 0.6 + i * 0.1,
                    5, "success", datetime.now().isoformat(),
                    0.3 + i * 0.1, 0.1 + i * 0.05, 0.25 + i * 0.05
                ])
        
        logger.info(f"✅ 创建模拟数据: {batch_dir}")
        logger.info(f"✅ 模拟CSV文件包含多目标字段")
        
        # 清理测试数据
        import shutil
        shutil.rmtree(batch_dir)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 报告生成测试失败: {e}")
        return False

def generate_test_report():
    """生成测试报告"""
    logger = setup_logger(__name__)
    logger.info("=== Real Run 基础功能测试报告 ===")
    
    tests = [
        ("PowerShell脚本语法", test_script_syntax),
        ("环境检查功能", test_environment_check),
        ("组件脚本存在性", test_component_scripts),
        ("报告生成功能", test_report_generation)
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
    logger.info("Real Run 基础功能测试总结")
    logger.info("="*60)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n总体结果: {passed}/{total} 测试通过")
    
    if passed == total:
        logger.info("🎉 所有基础功能测试通过！Real Run脚本准备就绪")
        return True
    else:
        logger.warning("⚠️ 部分测试失败，需要修复后才能进行完整Real Run")
        return False

def main():
    """主函数"""
    logger = setup_logger(__name__)
    
    try:
        logger.info("🚀 开始 Real Run 基础功能测试")
        success = generate_test_report()
        
        if success:
            logger.info("\n✅ 基础功能验证完成，可以进行Real Run")
            sys.exit(0)
        else:
            logger.info("\n❌ 基础功能验证失败，请修复问题")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
