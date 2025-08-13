#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成模型演示脚本

展示集成模型的基础功能和性能报告生成
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.models.ensemble import infer_ensemble, EnsembleModel
from maowise.utils.logger import setup_logger

def create_demo_samples():
    """创建演示样本数据"""
    samples = [
        {
            "system": "silicate",
            "substrate_alloy": "AZ91D",
            "electrolyte_family": "alkaline",
            "voltage_V": 400,
            "current_density_A_dm2": 8,
            "frequency_Hz": 1000,
            "duty_cycle_pct": 20,
            "time_min": 15,
            "temp_C": 25,
            "pH": 11.5,
            "text": "硅酸盐体系微弧氧化处理",
            "alpha_150_2600": 0.15,
            "epsilon_3000_30000": 0.82
        },
        {
            "system": "zirconate",
            "substrate_alloy": "AZ91D",
            "electrolyte_family": "fluoride",
            "voltage_V": 300,
            "current_density_A_dm2": 10,
            "frequency_Hz": 600,
            "duty_cycle_pct": 35,
            "time_min": 18,
            "temp_C": 22,
            "pH": 10.8,
            "text": "锆盐体系双极脉冲MAO处理",
            "alpha_150_2600": 0.12,
            "epsilon_3000_30000": 0.88
        },
        {
            "system": "silicate",
            "substrate_alloy": "AZ31B",
            "electrolyte_family": "alkaline",
            "voltage_V": 420,
            "current_density_A_dm2": 12,
            "frequency_Hz": 800,
            "duty_cycle_pct": 25,
            "time_min": 20,
            "temp_C": 28,
            "pH": 12.0,
            "text": "硅酸盐高性能体系处理",
            "alpha_150_2600": 0.18,
            "epsilon_3000_30000": 0.85
        }
    ]
    return samples

def demo_basic_inference():
    """演示基础推理功能"""
    logger = setup_logger(__name__)
    logger.info("=== 集成模型基础推理演示 ===")
    
    samples = create_demo_samples()
    
    for i, sample in enumerate(samples):
        logger.info(f"\n样本 {i+1}: {sample['system']} 系统")
        
        # 移除真实值，只保留输入特征
        input_payload = {k: v for k, v in sample.items() 
                        if k not in ['alpha_150_2600', 'epsilon_3000_30000']}
        
        # 预测
        result = infer_ensemble(input_payload)
        
        logger.info(f"预测结果:")
        logger.info(f"  Alpha: {result['pred_alpha']:.3f} (真实: {sample['alpha_150_2600']:.3f})")
        logger.info(f"  Epsilon: {result['pred_epsilon']:.3f} (真实: {sample['epsilon_3000_30000']:.3f})")
        logger.info(f"  置信度: {result['confidence']:.3f}")
        logger.info(f"  不确定度: α={result['uncertainty']['alpha']:.3f}, ε={result['uncertainty']['epsilon']:.3f}")
        logger.info(f"  使用模型: {result['model_used']}")
        logger.info(f"  组件: {result['components_used']}")

def demo_system_comparison():
    """演示不同系统的对比"""
    logger = setup_logger(__name__)
    logger.info("\n=== 不同系统对比演示 ===")
    
    # 创建标准化输入
    base_payload = {
        "substrate_alloy": "AZ91D",
        "voltage_V": 350,
        "current_density_A_dm2": 9,
        "frequency_Hz": 800,
        "duty_cycle_pct": 25,
        "time_min": 17,
        "temp_C": 25,
        "pH": 11.0
    }
    
    systems = ["silicate", "zirconate", "unknown"]
    results = {}
    
    for system in systems:
        payload = base_payload.copy()
        payload["system"] = system
        payload["text"] = f"{system} 系统微弧氧化处理"
        
        result = infer_ensemble(payload)
        results[system] = result
        
        logger.info(f"{system:10} - α: {result['pred_alpha']:.3f}, ε: {result['pred_epsilon']:.3f}, "
                   f"置信度: {result['confidence']:.3f}, 模型: {result['model_used']}")
    
    return results

def demo_uncertainty_analysis():
    """演示不确定度分析"""
    logger = setup_logger(__name__)
    logger.info("\n=== 不确定度分析演示 ===")
    
    # 不同复杂度的输入
    test_cases = [
        {
            "name": "详细输入",
            "payload": {
                "system": "silicate",
                "substrate_alloy": "AZ91D",
                "electrolyte_family": "alkaline",
                "voltage_V": 400,
                "current_density_A_dm2": 8,
                "frequency_Hz": 1000,
                "duty_cycle_pct": 20,
                "time_min": 15,
                "temp_C": 25,
                "pH": 11.5,
                "text": "硅酸盐体系AZ91D镁合金微弧氧化，电压400V，电流密度8A/dm2"
            }
        },
        {
            "name": "简单输入",
            "payload": {
                "system": "silicate",
                "text": "硅酸盐微弧氧化"
            }
        },
        {
            "name": "未知系统",
            "payload": {
                "text": "微弧氧化处理"
            }
        }
    ]
    
    for case in test_cases:
        result = infer_ensemble(case["payload"])
        
        logger.info(f"{case['name']:10} - 置信度: {result['confidence']:.3f}, "
                   f"不确定度: α={result['uncertainty']['alpha']:.3f}, ε={result['uncertainty']['epsilon']:.3f}")

def generate_performance_report():
    """生成性能报告"""
    logger = setup_logger(__name__)
    logger.info("\n=== 生成性能报告 ===")
    
    samples = create_demo_samples()
    
    # 预测所有样本
    predictions = []
    true_alphas = []
    true_epsilons = []
    
    for sample in samples:
        input_payload = {k: v for k, v in sample.items() 
                        if k not in ['alpha_150_2600', 'epsilon_3000_30000']}
        
        result = infer_ensemble(input_payload)
        predictions.append(result)
        true_alphas.append(sample['alpha_150_2600'])
        true_epsilons.append(sample['epsilon_3000_30000'])
    
    # 计算指标
    pred_alphas = [p['pred_alpha'] for p in predictions]
    pred_epsilons = [p['pred_epsilon'] for p in predictions]
    
    alpha_mae = np.mean(np.abs(np.array(pred_alphas) - np.array(true_alphas)))
    epsilon_mae = np.mean(np.abs(np.array(pred_epsilons) - np.array(true_epsilons)))
    
    # 生成报告
    model_status = EnsembleModel().get_model_status()
    
    # 转换boolean为JSON兼容格式
    def make_json_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_json_serializable(v) for v in obj]
        elif isinstance(obj, bool):
            return bool(obj)
        else:
            return obj
    
    report = {
        'model_type': 'ensemble_v2_demo',
        'evaluation_time': pd.Timestamp.now().isoformat(),
        'n_test_samples': len(samples),
        'overall_metrics': {
            'alpha_mae': float(alpha_mae),
            'epsilon_mae': float(epsilon_mae)
        },
        'target_achieved': {
            'epsilon_mae_le_006': bool(epsilon_mae <= 0.06)
        },
        'model_components': make_json_serializable(model_status)
    }
    
    # 保存报告
    report_path = Path("reports/fwd_eval_v2.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"性能报告已保存到: {report_path}")
    logger.info(f"Alpha MAE: {alpha_mae:.4f}")
    logger.info(f"Epsilon MAE: {epsilon_mae:.4f}")
    logger.info(f"目标达成 (ε MAE ≤ 0.06): {'✅' if epsilon_mae <= 0.06 else '❌'}")
    
    if epsilon_mae > 0.06:
        print("未达标")
    else:
        print("达标")
    
    return report

def main():
    """主函数"""
    logger = setup_logger(__name__)
    
    try:
        logger.info("🚀 MAO-Wise 集成模型演示开始")
        
        # 基础推理演示
        demo_basic_inference()
        
        # 系统对比演示
        demo_system_comparison()
        
        # 不确定度分析演示
        demo_uncertainty_analysis()
        
        # 生成性能报告
        generate_performance_report()
        
        logger.info("\n🎉 集成模型演示完成！")
        
    except Exception as e:
        logger.error(f"演示失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
