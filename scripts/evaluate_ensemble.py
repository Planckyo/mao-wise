#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成模型评估脚本

用法:
    python scripts/evaluate_ensemble.py --samples datasets/versions/maowise_ds_v2/samples.parquet --output reports/fwd_eval_v2.json
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.models.ensemble import evaluate_ensemble
from maowise.utils.logger import setup_logger

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MAO-Wise 集成模型评估")
    
    parser.add_argument(
        "--samples",
        type=str,
        required=True,
        help="测试样本文件路径 (parquet格式)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="reports/fwd_eval_v2.json",
        help="评估报告输出路径"
    )
    
    parser.add_argument(
        "--models_dir",
        type=str,
        default="models_ckpt",
        help="模型目录"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger(__name__)
    
    try:
        # 执行评估
        logger.info("开始集成模型评估...")
        
        evaluation_report = evaluate_ensemble(
            samples_path=args.samples,
            output_path=args.output,
            models_dir=args.models_dir
        )
        
        # 检查目标达成情况
        if evaluation_report:
            epsilon_mae = evaluation_report.get('overall_metrics', {}).get('epsilon_mae', float('inf'))
            target_achieved = epsilon_mae <= 0.06
            
            if target_achieved:
                logger.info(f"🎉 目标达成！Epsilon MAE: {epsilon_mae:.4f} ≤ 0.06")
            else:
                logger.warning(f"⚠️ 未达标：Epsilon MAE: {epsilon_mae:.4f} > 0.06")
                print("未达标")  # 为脚本调用提供状态指示
        
        logger.info("集成模型评估完成")
        
    except Exception as e:
        logger.error(f"集成模型评估失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
