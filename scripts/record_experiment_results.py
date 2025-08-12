#!/usr/bin/env python3
"""
实验结果记录脚本

从CSV/Excel导入实验结果，追加到experiments.parquet，自动去重。

功能特性：
- 支持CSV和Excel格式导入
- 基于experiment_id/batch_id/plan_id三键去重
- 自动数据类型转换和验证
- 增量追加到parquet文件
- 完整的导入日志和统计

使用示例：
python scripts/record_experiment_results.py --file results/round1_results.xlsx
python scripts/record_experiment_results.py --file results/batch_results.csv --dry-run
"""

import argparse
import json
import sys
import pathlib
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

# 确保能找到maowise包
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import logger

class ExperimentRecorder:
    """实验结果记录器"""
    
    def __init__(self, experiments_dir: str = "datasets/experiments"):
        self.experiments_dir = pathlib.Path(experiments_dir)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_file = self.experiments_dir / "experiments.parquet"
        
        # 定义标准字段和数据类型
        self.required_fields = [
            'experiment_id', 'batch_id', 'plan_id', 'system',
            'measured_alpha', 'measured_epsilon'
        ]
        
        self.field_types = {
            'experiment_id': 'str',
            'batch_id': 'str', 
            'plan_id': 'str',
            'system': 'str',
            'substrate_alloy': 'str',
            'electrolyte_components_json': 'str',
            'voltage_V': 'float',
            'current_density_Adm2': 'float',
            'frequency_Hz': 'float',
            'duty_cycle_pct': 'float',
            'time_min': 'float',
            'temp_C': 'float',
            'pH': 'float',
            'post_treatment': 'str',
            'measured_alpha': 'float',
            'measured_epsilon': 'float',
            'hardness_HV': 'float',
            'roughness_Ra_um': 'float',
            'corrosion_rate_mmpy': 'float',
            'notes': 'str',
            'reviewer': 'str',
            'timestamp': 'str'
        }
    
    def _validate_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """验证和清理数据"""
        errors = []
        
        # 检查必需字段
        missing_fields = [f for f in self.required_fields if f not in df.columns]
        if missing_fields:
            errors.append(f"缺少必需字段: {missing_fields}")
            return df, errors
        
        # 数据类型转换
        for field, dtype in self.field_types.items():
            if field in df.columns:
                try:
                    if dtype == 'float':
                        df[field] = pd.to_numeric(df[field], errors='coerce')
                    elif dtype == 'str':
                        df[field] = df[field].astype(str).replace('nan', '')
                except Exception as e:
                    errors.append(f"字段 {field} 类型转换失败: {e}")
        
        # 验证关键数值范围
        if 'measured_alpha' in df.columns:
            invalid_alpha = df[(df['measured_alpha'] < 0) | (df['measured_alpha'] > 1)].index
            if len(invalid_alpha) > 0:
                errors.append(f"measured_alpha 超出范围 [0,1]: 行 {invalid_alpha.tolist()}")
        
        if 'measured_epsilon' in df.columns:
            invalid_epsilon = df[(df['measured_epsilon'] < 0) | (df['measured_epsilon'] > 2)].index
            if len(invalid_epsilon) > 0:
                errors.append(f"measured_epsilon 超出范围 [0,2]: 行 {invalid_epsilon.tolist()}")
        
        # 检查重复的主键
        key_columns = ['experiment_id', 'batch_id', 'plan_id']
        duplicates = df[df.duplicated(subset=key_columns, keep=False)]
        if len(duplicates) > 0:
            errors.append(f"发现重复记录: {len(duplicates)} 条")
        
        return df, errors
    
    def _load_existing_data(self) -> pd.DataFrame:
        """加载现有实验数据"""
        if self.parquet_file.exists():
            try:
                existing_df = pd.read_parquet(self.parquet_file)
                logger.info(f"加载现有实验数据: {len(existing_df)} 条记录")
                return existing_df
            except Exception as e:
                logger.error(f"加载现有数据失败: {e}")
                return pd.DataFrame()
        else:
            logger.info("未找到现有实验数据，将创建新文件")
            return pd.DataFrame()
    
    def _deduplicate_records(self, new_df: pd.DataFrame, existing_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
        """去重处理"""
        key_columns = ['experiment_id', 'batch_id', 'plan_id']
        
        stats = {
            'total_new': len(new_df),
            'duplicates_internal': 0,
            'duplicates_existing': 0,
            'final_new': 0
        }
        
        # 1. 去除新数据内部重复
        if len(new_df) > 0:
            duplicates_internal = new_df.duplicated(subset=key_columns, keep='first')
            stats['duplicates_internal'] = duplicates_internal.sum()
            new_df_clean = new_df[~duplicates_internal].copy()
        else:
            new_df_clean = new_df.copy()
        
        # 2. 去除与现有数据的重复
        if len(existing_df) > 0 and len(new_df_clean) > 0:
            # 创建复合键进行比较
            existing_keys = existing_df[key_columns].apply(
                lambda x: f"{x['experiment_id']}|{x['batch_id']}|{x['plan_id']}", axis=1
            ).tolist()
            
            new_keys = new_df_clean[key_columns].apply(
                lambda x: f"{x['experiment_id']}|{x['batch_id']}|{x['plan_id']}", axis=1
            )
            
            duplicates_existing = new_keys.isin(existing_keys)
            stats['duplicates_existing'] = duplicates_existing.sum()
            final_new_df = new_df_clean[~duplicates_existing].copy()
        else:
            final_new_df = new_df_clean.copy()
        
        stats['final_new'] = len(final_new_df)
        
        return final_new_df, stats
    
    def import_from_file(self, file_path: str, dry_run: bool = False) -> Dict[str, Any]:
        """从文件导入实验结果"""
        file_path = pathlib.Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 读取文件
        try:
            if file_path.suffix.lower() == '.csv':
                new_df = pd.read_csv(file_path, encoding='utf-8-sig')
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                new_df = pd.read_excel(file_path)
            else:
                raise ValueError(f"不支持的文件格式: {file_path.suffix}")
            
            logger.info(f"成功读取文件 {file_path}: {len(new_df)} 条记录")
        except Exception as e:
            raise ValueError(f"读取文件失败: {e}")
        
        # 数据验证
        new_df, validation_errors = self._validate_data(new_df)
        if validation_errors:
            logger.error("数据验证失败:")
            for error in validation_errors:
                logger.error(f"  - {error}")
            raise ValueError("数据验证失败，请检查输入文件")
        
        # 加载现有数据
        existing_df = self._load_existing_data()
        
        # 去重处理
        final_new_df, dedup_stats = self._deduplicate_records(new_df, existing_df)
        
        result = {
            'file_path': str(file_path),
            'import_time': datetime.now().isoformat(),
            'stats': dedup_stats,
            'validation_errors': validation_errors,
            'success': True
        }
        
        if dry_run:
            logger.info("DRY RUN - 不会实际写入数据")
            result['dry_run'] = True
            return result
        
        # 保存数据
        if len(final_new_df) > 0:
            try:
                if len(existing_df) > 0:
                    # 合并数据
                    combined_df = pd.concat([existing_df, final_new_df], ignore_index=True)
                else:
                    combined_df = final_new_df
                
                # 保存到parquet
                combined_df.to_parquet(self.parquet_file, index=False)
                
                # 创建备份
                backup_file = self.experiments_dir / f"experiments_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
                combined_df.to_parquet(backup_file, index=False)
                
                logger.info(f"成功保存实验数据: {len(combined_df)} 条记录")
                logger.info(f"新增记录: {len(final_new_df)} 条")
                logger.info(f"备份文件: {backup_file}")
                
                result['total_records'] = len(combined_df)
                result['backup_file'] = str(backup_file)
                
            except Exception as e:
                logger.error(f"保存数据失败: {e}")
                result['success'] = False
                result['error'] = str(e)
        else:
            logger.info("没有新记录需要导入")
            result['total_records'] = len(existing_df)
        
        return result
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """获取实验数据摘要统计"""
        if not self.parquet_file.exists():
            return {'total_records': 0, 'message': 'No experiment data found'}
        
        try:
            df = pd.read_parquet(self.parquet_file)
            
            stats = {
                'total_records': len(df),
                'unique_experiments': df['experiment_id'].nunique(),
                'unique_batches': df['batch_id'].nunique(),
                'systems': df['system'].value_counts().to_dict(),
                'date_range': {
                    'earliest': df['timestamp'].min() if 'timestamp' in df.columns else None,
                    'latest': df['timestamp'].max() if 'timestamp' in df.columns else None
                },
                'alpha_stats': {
                    'mean': float(df['measured_alpha'].mean()),
                    'std': float(df['measured_alpha'].std()),
                    'min': float(df['measured_alpha'].min()),
                    'max': float(df['measured_alpha'].max())
                } if 'measured_alpha' in df.columns else None,
                'epsilon_stats': {
                    'mean': float(df['measured_epsilon'].mean()),
                    'std': float(df['measured_epsilon'].std()),
                    'min': float(df['measured_epsilon'].min()),
                    'max': float(df['measured_epsilon'].max())
                } if 'measured_epsilon' in df.columns else None
            }
            
            return stats
        except Exception as e:
            logger.error(f"生成统计信息失败: {e}")
            return {'error': str(e)}

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="实验结果记录脚本 - 导入实验数据到parquet文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 导入Excel文件
  python scripts/record_experiment_results.py --file results/round1_results.xlsx
  
  # 导入CSV文件（预览模式）
  python scripts/record_experiment_results.py --file results/batch_results.csv --dry-run
  
  # 查看当前统计信息
  python scripts/record_experiment_results.py --stats
        """
    )
    
    parser.add_argument("--file", 
                       type=str,
                       help="实验结果文件路径 (CSV或Excel)")
    
    parser.add_argument("--dry-run", 
                       action="store_true",
                       help="预览模式，不实际写入数据")
    
    parser.add_argument("--stats", 
                       action="store_true",
                       help="显示现有实验数据统计信息")
    
    parser.add_argument("--experiments-dir", 
                       type=str,
                       default="datasets/experiments",
                       help="实验数据目录 (默认: datasets/experiments)")
    
    args = parser.parse_args()
    
    try:
        recorder = ExperimentRecorder(args.experiments_dir)
        
        if args.stats:
            # 显示统计信息
            print("📊 实验数据统计信息:")
            stats = recorder.get_summary_stats()
            
            if 'error' in stats:
                print(f"❌ 错误: {stats['error']}")
                return
            
            print(f"   - 总记录数: {stats['total_records']}")
            print(f"   - 独特实验: {stats['unique_experiments']}")
            print(f"   - 独特批次: {stats['unique_batches']}")
            
            if stats.get('systems'):
                print(f"   - 体系分布:")
                for system, count in stats['systems'].items():
                    print(f"     * {system}: {count}")
            
            if stats.get('alpha_stats'):
                alpha_stats = stats['alpha_stats']
                print(f"   - Alpha统计: 均值={alpha_stats['mean']:.3f}, 标准差={alpha_stats['std']:.3f}")
            
            if stats.get('epsilon_stats'):
                epsilon_stats = stats['epsilon_stats']
                print(f"   - Epsilon统计: 均值={epsilon_stats['mean']:.3f}, 标准差={epsilon_stats['std']:.3f}")
            
            return
        
        if not args.file:
            parser.error("需要指定 --file 或 --stats 参数")
        
        # 导入数据
        print(f"📁 开始导入实验结果...")
        print(f"   文件: {args.file}")
        print(f"   目标目录: {args.experiments_dir}")
        if args.dry_run:
            print("   模式: 预览模式 (不会实际写入)")
        
        result = recorder.import_from_file(args.file, dry_run=args.dry_run)
        
        # 显示结果
        print(f"\n📋 导入结果:")
        print(f"   - 文件记录数: {result['stats']['total_new']}")
        print(f"   - 内部重复: {result['stats']['duplicates_internal']}")
        print(f"   - 与现有重复: {result['stats']['duplicates_existing']}")
        print(f"   - 最终新增: {result['stats']['final_new']}")
        
        if result['success']:
            if not args.dry_run:
                print(f"   - 总记录数: {result.get('total_records', '?')}")
                if result.get('backup_file'):
                    print(f"   - 备份文件: {result['backup_file']}")
            print("✅ 导入成功!")
        else:
            print(f"❌ 导入失败: {result.get('error', '未知错误')}")
            sys.exit(1)
        
        # 显示更新后的统计
        if not args.dry_run and result['stats']['final_new'] > 0:
            print(f"\n📊 更新后统计:")
            stats = recorder.get_summary_stats()
            print(f"   - 总记录数: {stats['total_records']}")
            print(f"   - 独特实验: {stats['unique_experiments']}")
            print(f"   - 独特批次: {stats['unique_batches']}")
        
    except Exception as e:
        logger.error(f"导入失败: {e}")
        print(f"❌ 错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
