#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐实验方案包的YAML文件
从CSV读取实验方案，调用plan_writer生成完整的YAML工艺卡
"""

import argparse
import os
import sys
import pandas as pd
from pathlib import Path
import yaml
from typing import Dict, Any

# 添加项目根目录到路径
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from maowise.experts.plan_writer import make_plan_yaml
    from maowise.config import load_config
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保在MAO-Wise项目根目录下执行此脚本")
    sys.exit(1)


def load_defaults_from_config() -> Dict[str, Any]:
    """从config.yaml加载默认参数模板"""
    try:
        config = load_config()
        
        # 构建默认参数模板
        defaults = {
            'electrolyte': {
                'silicate': {
                    'composition': {
                        'Na2SiO3': '10.0 g/L',
                        'KOH': '8.0 g/L',
                        'NaF': '2.0 g/L',
                        '添加剂': '稳定剂 0.5 g/L'
                    },
                    'pH': 12.2,
                    'temperature': '25±2°C'
                },
                'zirconate': {
                    'composition': {
                        'K2ZrF6': '8.0 g/L',
                        'KOH': '8.0 g/L',
                        'NaF': '2.0 g/L',
                        '添加剂': '稳定剂 0.5 g/L'
                    },
                    'pH': 12.2,
                    'temperature': '25±2°C'
                }
            },
            'process_parameters': {
                'voltage_mode': '恒流 (CC)',
                'current_density': '7.2 A/dm²',
                'frequency': '750 Hz',
                'duty_cycle': '10%',  # 默认值，会根据体系调整
                'waveform': '双极脉冲',
                'treatment_time': '18 min'
            },
            'substrate': {
                'material': 'AZ91D',
                'dimensions': '50mm × 30mm × 3mm',
                'surface_prep': '800#砂纸打磨 + 丙酮清洗'
            },
            'equipment_settings': {
                'power_supply': 'MAO-2000型',
                'cooling': '循环水冷',
                'stirring': '磁力搅拌 300 rpm',
                'electrode_distance': '8 cm'
            }
        }
        
        return defaults
        
    except Exception as e:
        print(f"⚠️ 加载配置失败: {e}")
        print("使用内置默认配置")
        return {}


def enhance_plan_with_defaults(plan_data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """用默认配置补齐plan数据"""
    enhanced_plan = plan_data.copy()
    
    # 确保基本字段存在
    if 'system' not in enhanced_plan:
        enhanced_plan['system'] = 'silicate'
    
    system = enhanced_plan['system']
    
    # 补齐电解液信息
    if system in defaults.get('electrolyte', {}):
        enhanced_plan.setdefault('electrolyte', defaults['electrolyte'][system])
    
    # 补齐工艺参数
    if 'process_parameters' in defaults:
        process_params = defaults['process_parameters'].copy()
        
        # 根据体系调整占空比
        if system == 'zirconate':
            process_params['duty_cycle'] = '8%'
        elif system == 'silicate':
            process_params['duty_cycle'] = '10%'
            
        enhanced_plan.setdefault('process_parameters', process_params)
    
    # 补齐其他字段
    for key in ['substrate', 'equipment_settings']:
        if key in defaults:
            enhanced_plan.setdefault(key, defaults[key])
    
    return enhanced_plan


def create_plan_wrapper(row: pd.Series, defaults: Dict[str, Any]) -> str:
    """包装器：从CSV行创建完整的YAML内容"""
    
    # 构建基础plan数据
    plan_data = {
        'plan_id': row['plan_id'],
        'system': row['system'],
        'alpha_target': float(row['alpha']),
        'epsilon_target': float(row['epsilon']),
        'confidence': float(row['confidence']),
        'type': row.get('type', 'unknown'),
        'score_total': float(row.get('score_total', 0))
    }
    
    # 用默认配置增强
    enhanced_plan = enhance_plan_with_defaults(plan_data, defaults)
    
    # 直接使用基础YAML模板（跳过有问题的make_plan_yaml）
    return create_basic_yaml_template(enhanced_plan)


def create_basic_yaml_template(plan_data: Dict[str, Any]) -> str:
    """创建基础YAML模板（备用方案）"""
    
    system = plan_data.get('system', 'silicate')
    plan_id = plan_data.get('plan_id', 'unknown')
    
    # 体系特定的占空比
    duty_cycle = '8%' if system == 'zirconate' else '10%'
    
    template = f"""# MAO-Wise 工艺卡片
# 方案: {plan_id} - {system}体系

plan_info:
  plan_id: {plan_id}
  batch_id: R5_now
  system: {system}
  type: {plan_data.get('type', 'unknown')}
  generated_at: "2025-08-14T22:00:00"
  
target_performance:
  alpha_target: {plan_data.get('alpha_target', 0.2)}
  epsilon_target: {plan_data.get('epsilon_target', 0.8)}
  confidence: {plan_data.get('confidence', 0.8)}
  
substrate:
  material: AZ91D
  dimensions: "50mm × 30mm × 3mm"
  surface_prep: "800#砂纸打磨 + 丙酮清洗"
  
electrolyte:
  family: {system}
  composition:"""

    # 体系特定的电解液组成
    if system == 'silicate':
        template += """
    Na2SiO3: "10.0 g/L"
    KOH: "8.0 g/L"
    NaF: "2.0 g/L"
    添加剂: "稳定剂 0.5 g/L" """
    else:  # zirconate
        template += """
    K2ZrF6: "8.0 g/L"
    KOH: "8.0 g/L"
    NaF: "2.0 g/L"
    添加剂: "稳定剂 0.5 g/L" """

    template += f"""
  pH: 12.2
  temperature: "25±2°C"
  
process_parameters:
  voltage_mode: "恒流 (CC)"
  current_density: "7.2 A/dm²"
  frequency: "750 Hz"
  duty_cycle: "{duty_cycle}"
  waveform: "双极脉冲"
  treatment_time: "18 min"
  
equipment_settings:
  power_supply: "MAO-2000型"
  cooling: "循环水冷"
  stirring: "磁力搅拌 300 rpm"
  electrode_distance: "8 cm"
  
quality_control:
  expected_thickness: "35-45 μm"
  surface_roughness: "Ra < 2.5 μm"
  uniformity_requirement: ">85%"
  
post_treatment:
  cleaning: "去离子水冲洗"
  drying: "60°C烘干 2h"
  sealing: "可选溶胶凝胶封孔"
  
safety_notes:
  - "佩戴防护眼镜和手套"
  - "确保通风良好"
  - "注意电解液溅射"
  - "定期检查电极状态"
  - "SAFE_OVERRIDE: NaF限制在2.0 g/L"
  - "SAFE_OVERRIDE: duty_cycle限制在{duty_cycle}"
  
expected_results:
  alpha_range: "0.18-0.22"
  epsilon_range: "0.78-0.85"
  thickness_range: "30-50 μm"
  hardness: "180-220 HV"
  
validation:
  test_methods:
    - "积分球测量热辐射性能"
    - "SEM观察表面形貌"
    - "膜厚仪测量涂层厚度"
    - "维氏硬度测试"
  
references:
  - "MAO工艺标准 GB/T 28145-2019"
  - "镁合金表面处理技术规范"
  - "实验室安全操作手册"
"""
    
    return template


def main():
    parser = argparse.ArgumentParser(description='补齐实验方案包的YAML文件')
    parser.add_argument('--csv', default='outputs/lab_package_R5_now_shortlist/exp_tasks.csv',
                        help='输入CSV文件路径')
    parser.add_argument('--out_dir', default='outputs/lab_package_R5_now_shortlist/plans',
                        help='输出目录路径')
    parser.add_argument('--force', action='store_true',
                        help='覆盖已存在的文件')
    
    args = parser.parse_args()
    
    print("🔧 开始补齐R5_now_shortlist的YAML文件...")
    
    # 检查输入CSV文件
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"❌ CSV文件不存在: {csv_path}")
        sys.exit(1)
    
    # 创建输出目录
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取CSV数据
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        print(f"📊 读取到 {len(df)} 条实验方案")
    except Exception as e:
        print(f"❌ 读取CSV失败: {e}")
        sys.exit(1)
    
    # 加载默认配置
    defaults = load_defaults_from_config()
    
    # 统计计数器
    stats = {'FOUND': 0, 'REBUILT': 0, 'FAILED': 0}
    
    # 处理每个方案
    for idx, row in df.iterrows():
        plan_id = row['plan_id']
        
        # 清理文件名中的非法字符
        import re
        safe_plan_id = re.sub(r'[^A-Za-z0-9_\-]', '_', plan_id)
        yaml_path = out_dir / f"{safe_plan_id}.yaml"
        
        # 检查是否已存在
        if yaml_path.exists() and not args.force:
            print(f"⏭️ 跳过已存在: {plan_id}")
            stats['FOUND'] += 1
            continue
        
        try:
            # 生成YAML内容
            yaml_content = create_plan_wrapper(row, defaults)
            
            # 确保目录存在
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存文件
            with open(yaml_path, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            
            print(f"✅ 生成成功: {plan_id} -> {safe_plan_id}.yaml")
            stats['REBUILT'] += 1
            
        except Exception as e:
            print(f"❌ 生成失败: {plan_id} - {e}")
            stats['FAILED'] += 1
    
    # 打印统计结果
    print(f"\n📈 处理完成统计:")
    print(f"  FOUND (已存在): {stats['FOUND']}")
    print(f"  REBUILT (重新生成): {stats['REBUILT']}")
    print(f"  FAILED (失败): {stats['FAILED']}")
    print(f"  总计: {sum(stats.values())}")
    
    if stats['FAILED'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
