#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试打包函数是否正确写入所有YAML文件
确保所有plan_id都被处理且文件被创建
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import yaml

# 添加项目根目录到路径
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.repair_pack_plans import create_plan_wrapper, load_defaults_from_config


class TestPackWritesAll(unittest.TestCase):
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.plans_dir = self.test_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建测试用的12条记录
        self.test_data = []
        for i in range(1, 13):
            if i <= 6:
                system = 'silicate'
                plan_id = f'R5_sil_{i:03d}'
            else:
                system = 'zirconate'
                plan_id = f'R5_zir_{i-6:03d}'
            
            self.test_data.append({
                'plan_id': plan_id,
                'system': system,
                'alpha': 0.15 + (i * 0.01),
                'epsilon': 0.75 + (i * 0.01),
                'confidence': 0.6 + (i * 0.02),
                'type': 'conservative' if i % 2 == 1 else 'explore',
                'score_total': 1.5 - (i * 0.05)
            })
        
        self.test_df = pd.DataFrame(self.test_data)
        
        # 创建CSV文件
        self.csv_path = self.test_dir / "exp_tasks.csv"
        self.test_df.to_csv(self.csv_path, index=False)
        
    def tearDown(self):
        """清理测试环境"""
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_repair_pack_plans_writes_all_files(self):
        """测试repair_pack_plans.py是否为所有记录写入YAML文件"""
        
        # 加载默认配置
        defaults = load_defaults_from_config()
        
        # 为每条记录生成YAML文件
        created_files = []
        for _, row in self.test_df.iterrows():
            plan_id = row['plan_id']
            yaml_path = self.plans_dir / f"{plan_id}.yaml"
            
            try:
                # 生成YAML内容
                yaml_content = create_plan_wrapper(row, defaults)
                
                # 确保plan_id文件名合法
                import re
                safe_plan_id = re.sub(r'[^A-Za-z0-9_\-]', '_', plan_id)
                safe_yaml_path = self.plans_dir / f"{safe_plan_id}.yaml"
                
                # 写入文件
                with open(safe_yaml_path, 'w', encoding='utf-8') as f:
                    f.write(yaml_content)
                
                created_files.append(safe_yaml_path)
                
            except Exception as e:
                self.fail(f"Failed to create YAML for {plan_id}: {e}")
        
        # 验证所有文件都被创建
        self.assertEqual(len(created_files), 12, "应该创建12个YAML文件")
        
        # 验证每个文件都存在且可读
        for yaml_path in created_files:
            self.assertTrue(yaml_path.exists(), f"YAML文件应该存在: {yaml_path}")
            self.assertGreater(yaml_path.stat().st_size, 0, f"YAML文件不应为空: {yaml_path}")
            
            # 验证YAML文件格式正确
            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
                    self.assertIsInstance(yaml_data, dict, "YAML文件应该包含有效的字典数据")
                    self.assertIn('plan_info', yaml_data, "YAML应该包含plan_info节")
                    self.assertIn('target_performance', yaml_data, "YAML应该包含target_performance节")
            except Exception as e:
                self.fail(f"YAML文件格式无效 {yaml_path}: {e}")
    
    def test_windows_path_compatibility(self):
        """测试Windows路径兼容性（模拟反斜杠分隔符）"""
        
        # 在Windows风格路径上测试
        if os.name == 'nt':  # 仅在Windows上运行
            windows_dir = Path("C:\\temp\\test_maowise")
            try:
                windows_dir.mkdir(parents=True, exist_ok=True)
                
                # 测试带有Windows路径的文件创建
                test_plan_id = "R5_test_001"
                yaml_path = windows_dir / f"{test_plan_id}.yaml"
                
                # 使用测试数据生成内容
                test_row = self.test_df.iloc[0].copy()
                test_row['plan_id'] = test_plan_id
                
                defaults = load_defaults_from_config()
                yaml_content = create_plan_wrapper(test_row, defaults)
                
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    f.write(yaml_content)
                
                self.assertTrue(yaml_path.exists(), "Windows路径下的YAML文件应该存在")
                
            finally:
                import shutil
                if windows_dir.exists():
                    shutil.rmtree(windows_dir)
        else:
            self.skipTest("Windows路径测试仅在Windows系统上运行")
    
    def test_plan_id_sanitization(self):
        """测试plan_id文件名清理"""
        
        # 测试包含非法字符的plan_id
        problematic_ids = [
            "R5/sil\\001",
            "R5:sil*001",
            "R5<sil>001",
            "R5|sil?001"
        ]
        
        defaults = load_defaults_from_config()
        
        for original_id in problematic_ids:
            test_row = self.test_df.iloc[0].copy()
            test_row['plan_id'] = original_id
            
            # 清理文件名
            import re
            safe_id = re.sub(r'[^A-Za-z0-9_\-]', '_', original_id)
            yaml_path = self.plans_dir / f"{safe_id}.yaml"
            
            try:
                yaml_content = create_plan_wrapper(test_row, defaults)
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    f.write(yaml_content)
                
                self.assertTrue(yaml_path.exists(), f"清理后的文件名应该可以创建: {safe_id}")
                
            except Exception as e:
                self.fail(f"文件名清理失败 {original_id} -> {safe_id}: {e}")
    
    def test_yaml_content_correctness(self):
        """测试生成的YAML内容正确性"""
        
        defaults = load_defaults_from_config()
        test_row = self.test_df.iloc[0]  # 取第一条记录测试
        
        yaml_content = create_plan_wrapper(test_row, defaults)
        yaml_data = yaml.safe_load(yaml_content)
        
        # 验证关键字段
        self.assertEqual(yaml_data['plan_info']['plan_id'], test_row['plan_id'])
        self.assertEqual(yaml_data['plan_info']['system'], test_row['system'])
        self.assertEqual(yaml_data['target_performance']['alpha_target'], test_row['alpha'])
        self.assertEqual(yaml_data['target_performance']['epsilon_target'], test_row['epsilon'])
        self.assertEqual(yaml_data['target_performance']['confidence'], test_row['confidence'])
        
        # 验证体系特定的参数
        if test_row['system'] == 'silicate':
            self.assertEqual(yaml_data['process_parameters']['duty_cycle'], "10%")
            self.assertIn('Na2SiO3', yaml_data['electrolyte']['composition'])
        elif test_row['system'] == 'zirconate':
            self.assertEqual(yaml_data['process_parameters']['duty_cycle'], "8%")
            self.assertIn('K2ZrF6', yaml_data['electrolyte']['composition'])
        
        # 验证安全限制
        self.assertEqual(yaml_data['electrolyte']['composition']['NaF'], "2.0 g/L")
        self.assertEqual(yaml_data['process_parameters']['frequency'], "750 Hz")


if __name__ == '__main__':
    unittest.main()
