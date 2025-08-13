#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据分割脚本 - 将文献库manifest按比例分割为训练/验证/测试集

用法:
    python scripts/make_split.py --manifest manifests/library_manifest.csv --train_ratio 0.7 --val_ratio 0.15 --test_ratio 0.15 --output_dir manifests
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple
from sklearn.model_selection import train_test_split

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import setup_logger

def validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    """验证分割比例"""
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"分割比例总和必须为1.0，当前为{total}")
    
    if any(ratio <= 0 for ratio in [train_ratio, val_ratio, test_ratio]):
        raise ValueError("所有分割比例必须大于0")

def stratified_split(df: pd.DataFrame, train_ratio: float, val_ratio: float, test_ratio: float, 
                    random_state: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    分层分割数据，确保各集合的分布相似
    
    Args:
        df: 文件清单DataFrame
        train_ratio: 训练集比例
        val_ratio: 验证集比例
        test_ratio: 测试集比例
        random_state: 随机种子
        
    Returns:
        (train_df, val_df, test_df)
    """
    logger = setup_logger(__name__)
    
    # 简单的分层策略：按文件大小区间分层
    df_copy = df.copy()
    
    # 按文件大小创建分层标签
    size_quantiles = df_copy['size_mb'].quantile([0.33, 0.67])
    df_copy['size_stratum'] = pd.cut(
        df_copy['size_mb'], 
        bins=[-np.inf, size_quantiles[0.33], size_quantiles[0.67], np.inf],
        labels=['small', 'medium', 'large']
    )
    
    # 先分出测试集
    train_val_df, test_df = train_test_split(
        df_copy,
        test_size=test_ratio,
        stratify=df_copy['size_stratum'],
        random_state=random_state
    )
    
    # 再从训练+验证集中分出验证集
    adjusted_val_ratio = val_ratio / (train_ratio + val_ratio)
    train_df, val_df = train_test_split(
        train_val_df,
        test_size=adjusted_val_ratio,
        stratify=train_val_df['size_stratum'],
        random_state=random_state
    )
    
    # 移除辅助列
    for df_split in [train_df, val_df, test_df]:
        df_split.drop('size_stratum', axis=1, inplace=True)
    
    logger.info(f"数据分割完成:")
    logger.info(f"  训练集: {len(train_df)} 文件 ({len(train_df)/len(df)*100:.1f}%)")
    logger.info(f"  验证集: {len(val_df)} 文件 ({len(val_df)/len(df)*100:.1f}%)")
    logger.info(f"  测试集: {len(test_df)} 文件 ({len(test_df)/len(df)*100:.1f}%)")
    
    return train_df, val_df, test_df

def export_splits(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame, 
                 output_dir: str) -> None:
    """
    导出分割后的manifest文件
    
    Args:
        train_df: 训练集DataFrame
        val_df: 验证集DataFrame  
        test_df: 测试集DataFrame
        output_dir: 输出目录
    """
    logger = setup_logger(__name__)
    
    # 确保输出目录存在
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 导出各个split
    splits = {
        'train': train_df,
        'val': val_df,
        'test': test_df
    }
    
    for split_name, df in splits.items():
        output_file = output_path / f"manifest_{split_name}.csv"
        df.to_csv(output_file, index=False, encoding='utf-8')
        logger.info(f"已导出 {split_name} 集合到: {output_file}")
        logger.info(f"  文件数: {len(df)}, 总大小: {df['size_mb'].sum():.1f} MB")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MAO-Wise 数据分割工具",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--manifest",
        type=str,
        required=True,
        help="输入manifest CSV文件路径"
    )
    
    parser.add_argument(
        "--train_ratio",
        type=float,
        default=0.7,
        help="训练集比例 (默认: 0.7)"
    )
    
    parser.add_argument(
        "--val_ratio", 
        type=float,
        default=0.15,
        help="验证集比例 (默认: 0.15)"
    )
    
    parser.add_argument(
        "--test_ratio",
        type=float,
        default=0.15,
        help="测试集比例 (默认: 0.15)"
    )
    
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="输出目录路径"
    )
    
    parser.add_argument(
        "--random_state",
        type=int,
        default=42,
        help="随机种子 (默认: 42)"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger(__name__)
    
    try:
        # 验证参数
        validate_ratios(args.train_ratio, args.val_ratio, args.test_ratio)
        
        # 读取manifest
        if not os.path.exists(args.manifest):
            raise FileNotFoundError(f"Manifest文件不存在: {args.manifest}")
        
        df = pd.read_csv(args.manifest)
        logger.info(f"读取manifest文件: {args.manifest}")
        logger.info(f"总文件数: {len(df)}")
        
        if len(df) == 0:
            raise ValueError("Manifest文件为空")
        
        # 执行分割
        train_df, val_df, test_df = stratified_split(
            df, args.train_ratio, args.val_ratio, args.test_ratio, args.random_state
        )
        
        # 导出结果
        export_splits(train_df, val_df, test_df, args.output_dir)
        
        logger.info("数据分割完成")
        
    except Exception as e:
        logger.error(f"数据分割失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()