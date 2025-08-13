#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据泄漏检查脚本 - 检查训练/验证/测试集之间是否存在重复样本

用法:
    python scripts/check_leakage.py --samples datasets/versions/maowise_ds_v2/samples.parquet
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Set
import hashlib

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import setup_logger

def calculate_content_hash(text: str) -> str:
    """计算文本内容哈希值"""
    if pd.isna(text) or not text:
        return "empty"
    # 标准化文本：去除空白、转换为小写
    normalized = ''.join(text.split()).lower()
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

def check_exact_duplicates(df: pd.DataFrame) -> Dict[str, any]:
    """检查完全重复的样本"""
    logger = setup_logger(__name__)
    
    # 基于文本内容计算哈希
    df['content_hash'] = df['text'].apply(calculate_content_hash)
    
    # 查找重复
    duplicated_mask = df.duplicated(subset=['content_hash'], keep=False)
    duplicated_df = df[duplicated_mask]
    
    result = {
        "total_samples": len(df),
        "duplicate_samples": len(duplicated_df),
        "unique_duplicates": len(duplicated_df['content_hash'].unique()),
        "duplicate_ratio": len(duplicated_df) / len(df) * 100 if len(df) > 0 else 0
    }
    
    if len(duplicated_df) > 0:
        logger.warning(f"发现 {len(duplicated_df)} 个重复样本 ({result['duplicate_ratio']:.2f}%)")
        
        # 显示重复分组
        duplicate_groups = duplicated_df.groupby('content_hash').size().sort_values(ascending=False)
        logger.warning(f"重复组数: {len(duplicate_groups)}")
        
        # 显示前5个最大的重复组
        top_duplicates = duplicate_groups.head(5)
        for hash_val, count in top_duplicates.items():
            logger.warning(f"  哈希 {hash_val[:8]}...: {count} 个重复样本")
    else:
        logger.info("未发现完全重复的样本")
    
    return result

def check_cross_split_leakage(df: pd.DataFrame) -> Dict[str, any]:
    """检查跨数据集的泄漏"""
    logger = setup_logger(__name__)
    
    if 'split' not in df.columns:
        logger.warning("数据中不包含split列，跳过跨split泄漏检查")
        return {"has_split_column": False}
    
    # 计算内容哈希
    df['content_hash'] = df['text'].apply(calculate_content_hash)
    
    splits = df['split'].unique()
    logger.info(f"检查数据集: {list(splits)}")
    
    leakage_results = {}
    total_leakage = 0
    
    # 两两检查splits之间的重复
    for i, split1 in enumerate(splits):
        for split2 in splits[i+1:]:
            split1_hashes = set(df[df['split'] == split1]['content_hash'])
            split2_hashes = set(df[df['split'] == split2]['content_hash'])
            
            overlap = split1_hashes & split2_hashes
            overlap_count = len(overlap)
            
            leakage_results[f"{split1}_vs_{split2}"] = {
                "overlap_samples": overlap_count,
                "split1_size": len(split1_hashes),
                "split2_size": len(split2_hashes),
                "leakage_ratio": overlap_count / min(len(split1_hashes), len(split2_hashes)) * 100 if min(len(split1_hashes), len(split2_hashes)) > 0 else 0
            }
            
            total_leakage += overlap_count
            
            if overlap_count > 0:
                logger.error(f"发现泄漏: {split1} <-> {split2}: {overlap_count} 个重复样本")
            else:
                logger.info(f"无泄漏: {split1} <-> {split2}")
    
    result = {
        "has_split_column": True,
        "splits": list(splits),
        "total_leakage_samples": total_leakage,
        "leakage_details": leakage_results,
        "has_leakage": total_leakage > 0
    }
    
    return result

def check_near_duplicates(df: pd.DataFrame, similarity_threshold: float = 0.9) -> Dict[str, any]:
    """检查近似重复（简化版，基于文本长度和前缀）"""
    logger = setup_logger(__name__)
    
    # 简化的近似重复检测：基于文本长度和前100字符
    df['text_length'] = df['text'].str.len()
    df['text_prefix'] = df['text'].str[:100]
    
    # 查找长度相近且前缀相似的样本
    near_duplicates = []
    
    # 按长度分组，查找相似的
    length_groups = df.groupby(pd.cut(df['text_length'], bins=20))
    
    for name, group in length_groups:
        if len(group) < 2:
            continue
            
        # 在每个长度组内查找前缀相似的
        prefix_groups = group.groupby('text_prefix')
        for prefix, prefix_group in prefix_groups:
            if len(prefix_group) > 1:
                near_duplicates.extend(prefix_group.index.tolist())
    
    result = {
        "total_samples": len(df),
        "near_duplicate_samples": len(near_duplicates),
        "near_duplicate_ratio": len(near_duplicates) / len(df) * 100 if len(df) > 0 else 0
    }
    
    if len(near_duplicates) > 0:
        logger.warning(f"发现 {len(near_duplicates)} 个可能的近似重复样本 ({result['near_duplicate_ratio']:.2f}%)")
    else:
        logger.info("未发现明显的近似重复样本")
    
    return result

def check_source_overlap(df: pd.DataFrame) -> Dict[str, any]:
    """检查source_pdf字段的overlap"""
    logger = setup_logger(__name__)
    
    if 'source_pdf' not in df.columns and 'source' not in df.columns:
        logger.warning("数据中不包含source_pdf或source列，跳过源文件overlap检查")
        return {"has_source_column": False}
    
    source_col = 'source_pdf' if 'source_pdf' in df.columns else 'source'
    
    if 'split' not in df.columns:
        logger.warning("数据中不包含split列，跳过源文件split检查")
        return {"has_split_column": False}
    
    # 检查同一PDF文件是否出现在多个split中
    source_split_map = df.groupby(source_col)['split'].apply(set).reset_index()
    source_split_map['split_count'] = source_split_map['split'].apply(len)
    
    cross_split_sources = source_split_map[source_split_map['split_count'] > 1]
    
    result = {
        "has_source_column": True,
        "has_split_column": True,
        "total_sources": len(source_split_map),
        "cross_split_sources": len(cross_split_sources),
        "cross_split_ratio": len(cross_split_sources) / len(source_split_map) * 100 if len(source_split_map) > 0 else 0
    }
    
    if len(cross_split_sources) > 0:
        logger.warning(f"发现 {len(cross_split_sources)} 个PDF文件同时出现在多个数据集中")
        logger.warning("这可能导致数据泄漏，因为同一文献的不同部分可能包含相关信息")
        
        # 显示前几个问题文件
        for idx, row in cross_split_sources.head(3).iterrows():
            logger.warning(f"  {row[source_col]}: 出现在 {list(row['split'])}")
    else:
        logger.info("所有源文件都完全分离在不同的数据集中")
    
    return result

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MAO-Wise 数据泄漏检查工具",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--samples",
        type=str,
        required=True,
        help="样本数据文件路径 (parquet格式)"
    )
    
    parser.add_argument(
        "--similarity_threshold",
        type=float,
        default=0.9,
        help="近似重复检测阈值 (默认: 0.9)"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger(__name__)
    
    try:
        # 读取样本数据
        if not os.path.exists(args.samples):
            raise FileNotFoundError(f"样本文件不存在: {args.samples}")
        
        logger.info(f"读取样本数据: {args.samples}")
        df = pd.read_parquet(args.samples)
        logger.info(f"总样本数: {len(df)}")
        
        if len(df) == 0:
            logger.warning("样本文件为空")
            return
        
        # 执行各种泄漏检查
        results = {}
        
        logger.info("\n" + "="*60)
        logger.info("1. 检查完全重复样本")
        logger.info("="*60)
        results['exact_duplicates'] = check_exact_duplicates(df)
        
        logger.info("\n" + "="*60)
        logger.info("2. 检查跨数据集泄漏")
        logger.info("="*60)
        results['cross_split_leakage'] = check_cross_split_leakage(df)
        
        logger.info("\n" + "="*60)
        logger.info("3. 检查近似重复样本")
        logger.info("="*60)
        results['near_duplicates'] = check_near_duplicates(df, args.similarity_threshold)
        
        logger.info("\n" + "="*60)
        logger.info("4. 检查源文件重叠")
        logger.info("="*60)
        results['source_overlap'] = check_source_overlap(df)
        
        # 总结报告
        logger.info("\n" + "="*60)
        logger.info("泄漏检查总结报告")
        logger.info("="*60)
        
        issues_found = []
        
        if results['exact_duplicates']['duplicate_samples'] > 0:
            issues_found.append(f"完全重复: {results['exact_duplicates']['duplicate_samples']} 个")
        
        if results['cross_split_leakage'].get('has_leakage', False):
            issues_found.append(f"跨集泄漏: {results['cross_split_leakage']['total_leakage_samples']} 个")
        
        if results['near_duplicates']['near_duplicate_samples'] > 0:
            issues_found.append(f"近似重复: {results['near_duplicates']['near_duplicate_samples']} 个")
        
        if results['source_overlap'].get('cross_split_sources', 0) > 0:
            issues_found.append(f"源文件重叠: {results['source_overlap']['cross_split_sources']} 个文件")
        
        if issues_found:
            logger.error("发现以下数据质量问题:")
            for issue in issues_found:
                logger.error(f"  - {issue}")
            logger.error("建议在训练前解决这些问题")
        else:
            logger.info("✅ 未发现明显的数据泄漏问题")
            logger.info("数据集可以安全用于训练")
        
    except Exception as e:
        logger.error(f"泄漏检查失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()