#!/usr/bin/env python3
"""
预测评估脚本

对实验数据进行预测评估，生成详细报告和可视化图表。

功能特性：
- 读取experiments.parquet实验数据
- 调用/predict API或本地推理管线生成预测
- 计算多种评估指标：MAE/MAPE/RMSE、命中率、置信度分析
- 生成JSON报告和可视化图表
- 按体系分组的详细分析
- 支持干运行模式用于模型对比

使用示例：
python scripts/evaluate_predictions.py
python scripts/evaluate_predictions.py --dry-run --output reports/eval_before_update.json
python scripts/evaluate_predictions.py --api-url http://localhost:8000
"""

import argparse
import json
import sys
import pathlib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import requests
import logging

# 确保能找到maowise包
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import logger

class PredictionEvaluator:
    """预测评估器"""
    
    def __init__(self, experiments_file: str = "datasets/samples.parquet", 
                 api_url: str = "http://localhost:8000",
                 split: str = "all"):
        self.experiments_file = pathlib.Path(experiments_file)
        self.api_url = api_url.rstrip('/')
        self.reports_dir = pathlib.Path("reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.split = split
        
        # 设置matplotlib中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
    def _load_experiment_data(self) -> pd.DataFrame:
        """加载实验数据并按split过滤"""
        if not self.experiments_file.exists():
            raise FileNotFoundError(f"实验数据文件不存在: {self.experiments_file}")
        
        try:
            df = pd.read_parquet(self.experiments_file)
            logger.info(f"加载实验数据: {len(df)} 条记录")
            
            # 按split过滤数据
            if self.split != "all" and "split" in df.columns:
                df_split = df[df['split'] == self.split].copy()
                logger.info(f"按split='{self.split}'过滤: {len(df_split)} 条记录")
            else:
                df_split = df.copy()
                if self.split != "all" and "split" not in df.columns:
                    logger.warning(f"数据中无'split'列，忽略split参数，使用全部数据")
            
            # 验证必需字段
            required_fields = ['measured_alpha', 'measured_epsilon']
            missing_fields = [f for f in required_fields if f not in df_split.columns]
            if missing_fields:
                raise ValueError(f"缺少必需字段: {missing_fields}")
            
            # 过滤有效数据
            valid_mask = (
                df_split['measured_alpha'].notna() & 
                df_split['measured_epsilon'].notna() &
                (df_split['measured_alpha'] >= 0) & (df_split['measured_alpha'] <= 1) &
                (df_split['measured_epsilon'] >= 0) & (df_split['measured_epsilon'] <= 2)
            )
            
            df_valid = df_split[valid_mask].copy()
            logger.info(f"有效数据: {len(df_valid)} 条记录")
            
            if len(df_valid) == 0:
                raise ValueError("没有有效的实验数据")
            
            return df_valid
            
        except Exception as e:
            raise ValueError(f"加载实验数据失败: {e}")
    
    def _prepare_prediction_input(self, row: pd.Series) -> Dict[str, Any]:
        """准备预测输入"""
        # 构造预测输入，优先使用实验参数，否则使用默认值
        input_data = {
            "substrate_alloy": row.get('substrate_alloy', 'AZ91D'),
            "electrolyte_family": self._infer_electrolyte_family(row.get('system', 'mixed')),
            "electrolyte_components": self._parse_electrolyte_components(row.get('electrolyte_components_json', '[]')),
            "mode": "ac",  # 假设大多数是交流模式
            "voltage_V": float(row.get('voltage_V', 300.0)),
            "current_density_A_dm2": float(row.get('current_density_Adm2', row.get('current_density_A_dm2', 10.0))),
            "frequency_Hz": float(row.get('frequency_Hz', 1000.0)),
            "duty_cycle_pct": float(row.get('duty_cycle_pct', 30.0)),
            "time_min": float(row.get('time_min', 20.0)),
            "temp_C": float(row.get('temp_C', 25.0)) if pd.notna(row.get('temp_C')) else 25.0,
            "pH": float(row.get('pH', 11.0)) if pd.notna(row.get('pH')) else 11.0,
            "sealing": row.get('post_treatment', 'none') if row.get('post_treatment') != 'none' else 'none'
        }
        
        return input_data
    
    def _infer_electrolyte_family(self, system: str) -> str:
        """根据体系推断电解液族"""
        system = str(system).lower()
        if 'silicate' in system:
            return 'alkaline'
        elif 'zirconate' in system:
            return 'fluoride'
        else:
            return 'mixed'
    
    def _parse_electrolyte_components(self, components_json: str) -> List[str]:
        """解析电解液组分"""
        try:
            if pd.isna(components_json) or components_json == '':
                return []
            return json.loads(components_json)
        except:
            return []
    
    def _predict_via_api(self, input_data: Dict[str, Any]) -> Dict[str, float]:
        """通过API进行预测"""
        try:
            response = requests.post(
                f"{self.api_url}/api/maowise/v1/predict",
                json=input_data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                'pred_alpha': result.get('alpha_150_2600', 0.0),
                'pred_epsilon': result.get('epsilon_3000_30000', 0.0),
                'confidence': result.get('confidence', 0.5)
            }
        except Exception as e:
            logger.warning(f"API预测失败: {e}")
            return self._predict_local_fallback(input_data)
    
    def _predict_local_fallback(self, input_data: Dict[str, Any]) -> Dict[str, float]:
        """本地预测降级方案"""
        try:
            # 尝试导入本地推理模块
            from maowise.models.infer_fwd import predict_properties
            result = predict_properties(input_data)
            
            return {
                'pred_alpha': result.get('alpha_150_2600', 0.0),
                'pred_epsilon': result.get('epsilon_3000_30000', 0.0),
                'confidence': result.get('confidence', 0.5)
            }
        except Exception as e:
            logger.warning(f"本地预测也失败: {e}")
            # 最终降级：基于经验的简单预测
            return self._simple_baseline_prediction(input_data)
    
    def _simple_baseline_prediction(self, input_data: Dict[str, Any]) -> Dict[str, float]:
        """简单基线预测（基于经验规律）"""
        # 基于电压和电流密度的简单经验公式
        voltage = input_data.get('voltage_V', 300)
        current = input_data.get('current_density_A_dm2', 10)
        
        # 简化的经验公式
        pred_alpha = 0.15 + (voltage - 200) * 0.0001 + (current - 5) * 0.005
        pred_epsilon = 0.7 + (voltage - 200) * 0.0003 + (current - 5) * 0.01
        
        # 限制在合理范围内
        pred_alpha = np.clip(pred_alpha, 0.05, 0.4)
        pred_epsilon = np.clip(pred_epsilon, 0.5, 1.2)
        
        return {
            'pred_alpha': pred_alpha,
            'pred_epsilon': pred_epsilon,
            'confidence': 0.3  # 低置信度
        }
    
    def _calculate_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算评估指标"""
        # 基本回归指标
        alpha_mae = np.mean(np.abs(df['measured_alpha'] - df['pred_alpha']))
        alpha_mape = np.mean(np.abs((df['measured_alpha'] - df['pred_alpha']) / df['measured_alpha'])) * 100
        alpha_rmse = np.sqrt(np.mean((df['measured_alpha'] - df['pred_alpha']) ** 2))
        
        epsilon_mae = np.mean(np.abs(df['measured_epsilon'] - df['pred_epsilon']))
        epsilon_mape = np.mean(np.abs((df['measured_epsilon'] - df['pred_epsilon']) / df['measured_epsilon'])) * 100
        epsilon_rmse = np.sqrt(np.mean((df['measured_epsilon'] - df['pred_epsilon']) ** 2))
        
        # 命中率指标
        alpha_hit_003 = np.mean(np.abs(df['measured_alpha'] - df['pred_alpha']) <= 0.03) * 100
        alpha_hit_005 = np.mean(np.abs(df['measured_alpha'] - df['pred_alpha']) <= 0.05) * 100
        
        epsilon_hit_003 = np.mean(np.abs(df['measured_epsilon'] - df['pred_epsilon']) <= 0.03) * 100
        epsilon_hit_005 = np.mean(np.abs(df['measured_epsilon'] - df['pred_epsilon']) <= 0.05) * 100
        
        # 置信度分析
        low_confidence_ratio = np.mean(df['confidence'] < 0.5) * 100
        avg_confidence = np.mean(df['confidence'])
        
        # 相关性
        alpha_corr = np.corrcoef(df['measured_alpha'], df['pred_alpha'])[0, 1]
        epsilon_corr = np.corrcoef(df['measured_epsilon'], df['pred_epsilon'])[0, 1]
        
        # 返回标准键名格式，保持向后兼容
        result = {
            # ===== 标准键名 (新格式) =====
            'alpha_mae': float(alpha_mae),
            'epsilon_mae': float(epsilon_mae),
            'alpha_rmse': float(alpha_rmse),
            'epsilon_rmse': float(epsilon_rmse),
            'alpha_hit_pm_0.03': float(alpha_hit_003),
            'epsilon_hit_pm_0.03': float(epsilon_hit_003),
            'alpha_hit_pm_0.05': float(alpha_hit_005),
            'epsilon_hit_pm_0.05': float(epsilon_hit_005),
            'confidence_mean': float(avg_confidence),
            'confidence_low_ratio': float(low_confidence_ratio),
            'sample_size': len(df),
            
            # ===== 向后兼容 (旧格式) =====
            'alpha_metrics': {
                'mae': float(alpha_mae),
                'mape': float(alpha_mape),
                'rmse': float(alpha_rmse),
                'hit_rate_003': float(alpha_hit_003),
                'hit_rate_005': float(alpha_hit_005),
                'correlation': float(alpha_corr)
            },
            'epsilon_metrics': {
                'mae': float(epsilon_mae),
                'mape': float(epsilon_mape),
                'rmse': float(epsilon_rmse),
                'hit_rate_003': float(epsilon_hit_003),
                'hit_rate_005': float(epsilon_hit_005),
                'correlation': float(epsilon_corr)
            },
            'confidence_metrics': {
                'average': float(avg_confidence),
                'low_confidence_ratio': float(low_confidence_ratio)
            }
        }
        
        return result
    
    def _normalize_legacy_json(self, file_path: pathlib.Path) -> bool:
        """规范化历史JSON文件的键名"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查是否需要规范化
            needs_update = False
            
            # 递归规范化函数
            def normalize_metrics(metrics_dict):
                nonlocal needs_update
                if not isinstance(metrics_dict, dict):
                    return metrics_dict
                
                # 如果已经有标准键名，跳过
                if 'alpha_mae' in metrics_dict:
                    return metrics_dict
                
                # 提取旧格式的值
                alpha_metrics = metrics_dict.get('alpha_metrics', {})
                epsilon_metrics = metrics_dict.get('epsilon_metrics', {})
                confidence_metrics = metrics_dict.get('confidence_metrics', {})
                
                if alpha_metrics or epsilon_metrics or confidence_metrics:
                    needs_update = True
                    
                    # 添加标准键名
                    metrics_dict.update({
                        'alpha_mae': alpha_metrics.get('mae', 0.0),
                        'epsilon_mae': epsilon_metrics.get('mae', 0.0),
                        'alpha_rmse': alpha_metrics.get('rmse', 0.0),
                        'epsilon_rmse': epsilon_metrics.get('rmse', 0.0),
                        'alpha_hit_pm_0.03': alpha_metrics.get('hit_rate_003', 0.0),
                        'epsilon_hit_pm_0.03': epsilon_metrics.get('hit_rate_003', 0.0),
                        'alpha_hit_pm_0.05': alpha_metrics.get('hit_rate_005', 0.0),
                        'epsilon_hit_pm_0.05': epsilon_metrics.get('hit_rate_005', 0.0),
                        'confidence_mean': confidence_metrics.get('average', 0.0),
                        'confidence_low_ratio': confidence_metrics.get('low_confidence_ratio', 0.0)
                    })
                
                return metrics_dict
            
            # 规范化整体指标
            if 'overall_metrics' in data:
                data['overall_metrics'] = normalize_metrics(data['overall_metrics'])
            
            # 规范化体系指标
            if 'system_metrics' in data:
                for system, metrics in data['system_metrics'].items():
                    data['system_metrics'][system] = normalize_metrics(metrics)
            
            # 如果需要更新，写回文件
            if needs_update:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"规范化历史JSON文件: {file_path}")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"规范化JSON文件失败 {file_path}: {e}")
            return False
    
    def _generate_plots(self, df: pd.DataFrame, output_prefix: str) -> List[str]:
        """生成评估图表"""
        plot_files = []
        
        # 图1: Pred vs True 散点图
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Alpha散点图
        ax1.scatter(df['measured_alpha'], df['pred_alpha'], alpha=0.6, c=df['confidence'], 
                   cmap='viridis', s=50)
        ax1.plot([df['measured_alpha'].min(), df['measured_alpha'].max()], 
                [df['measured_alpha'].min(), df['measured_alpha'].max()], 
                'r--', alpha=0.8, label='Perfect Prediction')
        ax1.set_xlabel('实测 Alpha')
        ax1.set_ylabel('预测 Alpha')
        ax1.set_title('Alpha 预测 vs 实测')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Epsilon散点图
        scatter = ax2.scatter(df['measured_epsilon'], df['pred_epsilon'], alpha=0.6, 
                             c=df['confidence'], cmap='viridis', s=50)
        ax2.plot([df['measured_epsilon'].min(), df['measured_epsilon'].max()], 
                [df['measured_epsilon'].min(), df['measured_epsilon'].max()], 
                'r--', alpha=0.8, label='Perfect Prediction')
        ax2.set_xlabel('实测 Epsilon')
        ax2.set_ylabel('预测 Epsilon')
        ax2.set_title('Epsilon 预测 vs 实测')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 添加颜色条
        plt.colorbar(scatter, ax=ax2, label='置信度')
        
        plt.tight_layout()
        pred_vs_true_file = self.reports_dir / f"{output_prefix}_pred_vs_true.png"
        plt.savefig(pred_vs_true_file, dpi=300, bbox_inches='tight')
        plt.close()
        plot_files.append(str(pred_vs_true_file))
        
        # 图2: 误差分布直方图
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Alpha误差分布
        alpha_errors = df['measured_alpha'] - df['pred_alpha']
        ax1.hist(alpha_errors, bins=20, alpha=0.7, color='skyblue', edgecolor='black')
        ax1.axvline(0, color='red', linestyle='--', alpha=0.8, label='零误差')
        ax1.axvline(alpha_errors.mean(), color='orange', linestyle='-', alpha=0.8, 
                   label=f'平均误差: {alpha_errors.mean():.4f}')
        ax1.set_xlabel('预测误差 (实测 - 预测)')
        ax1.set_ylabel('频次')
        ax1.set_title('Alpha 预测误差分布')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Epsilon误差分布
        epsilon_errors = df['measured_epsilon'] - df['pred_epsilon']
        ax2.hist(epsilon_errors, bins=20, alpha=0.7, color='lightcoral', edgecolor='black')
        ax2.axvline(0, color='red', linestyle='--', alpha=0.8, label='零误差')
        ax2.axvline(epsilon_errors.mean(), color='orange', linestyle='-', alpha=0.8, 
                   label=f'平均误差: {epsilon_errors.mean():.4f}')
        ax2.set_xlabel('预测误差 (实测 - 预测)')
        ax2.set_ylabel('频次')
        ax2.set_title('Epsilon 预测误差分布')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        error_dist_file = self.reports_dir / f"{output_prefix}_error_distribution.png"
        plt.savefig(error_dist_file, dpi=300, bbox_inches='tight')
        plt.close()
        plot_files.append(str(error_dist_file))
        
        return plot_files
    
    def evaluate(self, dry_run: bool = False, output_file: Optional[str] = None) -> Dict[str, Any]:
        """执行评估"""
        # 加载实验数据
        df = self._load_experiment_data()
        
        if dry_run:
            logger.info("DRY RUN - 使用现有预测结果或跳过预测")
        else:
            logger.info("开始生成预测...")
        
        # 生成预测
        predictions = []
        for idx, row in df.iterrows():
            if dry_run and all(col in df.columns for col in ['pred_alpha', 'pred_epsilon', 'confidence']):
                # 干运行且已有预测结果
                pred = {
                    'pred_alpha': row['pred_alpha'],
                    'pred_epsilon': row['pred_epsilon'], 
                    'confidence': row['confidence']
                }
            else:
                # 生成新预测
                input_data = self._prepare_prediction_input(row)
                pred = self._predict_via_api(input_data)
            
            predictions.append(pred)
            
            if (idx + 1) % 10 == 0:
                logger.info(f"已处理 {idx + 1}/{len(df)} 条记录")
        
        # 添加预测结果到DataFrame
        pred_data = {
            'pred_alpha': [pred['pred_alpha'] for pred in predictions],
            'pred_epsilon': [pred['pred_epsilon'] for pred in predictions],
            'confidence': [pred['confidence'] for pred in predictions]
        }
        
        for col, values in pred_data.items():
            df[col] = values
        
        # 计算总体指标
        overall_metrics = self._calculate_metrics(df)
        
        # 按体系分组计算指标
        system_metrics = {}
        if 'system' in df.columns:
            for system in df['system'].unique():
                if pd.notna(system):
                    system_df = df[df['system'] == system]
                    if len(system_df) > 0:
                        system_metrics[system] = self._calculate_metrics(system_df)
        
        # 生成图表
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_prefix = f"eval_experiments_{timestamp}"
        if output_file:
            output_prefix = pathlib.Path(output_file).stem
        
        plot_files = self._generate_plots(df, output_prefix)
        
        # 计算目标达成情况
        target_achieved = {
            'epsilon_mae_le_006': float(overall_metrics.get('epsilon_mae', 1.0) <= 0.006),
            'alpha_mae_le_003': float(overall_metrics.get('alpha_mae', 1.0) <= 0.003),
            'epsilon_hit_pm_003_ge_90': float(overall_metrics.get('epsilon_hit_pm_0.03', 0.0) >= 90.0),
            'alpha_hit_pm_003_ge_90': float(overall_metrics.get('alpha_hit_pm_0.03', 0.0) >= 90.0),
            'confidence_mean_ge_07': float(overall_metrics.get('confidence_mean', 0.0) >= 0.7)
        }
        
        # 构建评估结果
        result = {
            'evaluation_time': datetime.now().isoformat(),
            'data_info': {
                'total_records': len(df),
                'experiment_file': str(self.experiments_file),
                'split': self.split,
                'systems': df['system'].value_counts().to_dict() if 'system' in df.columns else {}
            },
            'overall_metrics': overall_metrics,
            'system_metrics': system_metrics,
            'target_achieved': target_achieved,
            'plots': plot_files,
            'dry_run': dry_run
        }
        
        # 保存结果
        if not output_file:
            output_file = self.reports_dir / f"{output_prefix}.json"
        else:
            output_file = pathlib.Path(output_file)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"评估报告已保存: {output_file}")
        
        # 规范化历史JSON文件的键名
        reports_pattern = self.reports_dir / "eval_experiments_*.json"
        import glob
        for json_file in glob.glob(str(reports_pattern)):
            json_path = pathlib.Path(json_file)
            if json_path != output_file:  # 不处理当前刚生成的文件
                self._normalize_legacy_json(json_path)
        
        return result

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="预测评估脚本 - 评估模型预测性能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 标准评估
  python scripts/evaluate_predictions.py
  
  # 干运行模式（用于模型对比）
  python scripts/evaluate_predictions.py --dry-run --output reports/eval_before_update.json
  
  # 指定API地址
  python scripts/evaluate_predictions.py --api-url http://localhost:8000
        """
    )
    
    parser.add_argument("--experiments-file", 
                       type=str, 
                       default="datasets/samples.parquet",
                       help="实验数据文件路径")
    
    parser.add_argument("--api-url", 
                       type=str,
                       default="http://localhost:8000",
                       help="API服务地址")
    
    parser.add_argument("--output", 
                       type=str,
                       help="输出文件路径")
    
    parser.add_argument("--dry-run", 
                       action="store_true",
                       help="干运行模式，使用现有预测或跳过预测")
    
    parser.add_argument("--split", 
                       choices=["val", "test", "all"],
                       default="all",
                       help="数据集分割选择 (默认: all)")
    
    args = parser.parse_args()
    
    try:
        evaluator = PredictionEvaluator(
            experiments_file=args.experiments_file,
            api_url=args.api_url,
            split=args.split
        )
        
        print("🔍 开始预测评估...")
        print(f"   实验数据: {args.experiments_file}")
        print(f"   API地址: {args.api_url}")
        if args.dry_run:
            print("   模式: 干运行")
        
        result = evaluator.evaluate(dry_run=args.dry_run, output_file=args.output)
        
        # 打印摘要
        print(f"\n📊 评估完成!")
        print(f"   - 数据记录: {result['data_info']['total_records']}")
        print(f"   - 报告文件: {args.output or 'reports/eval_experiments_*.json'}")
        print(f"   - 图表文件: {len(result['plots'])} 张")
        
        # 打印关键指标
        overall = result['overall_metrics']
        print(f"\n📈 总体性能:")
        print(f"   Alpha MAE: {overall['alpha_metrics']['mae']:.4f}")
        print(f"   Alpha 命中率(±0.03): {overall['alpha_metrics']['hit_rate_003']:.1f}%")
        print(f"   Epsilon MAE: {overall['epsilon_metrics']['mae']:.4f}")
        print(f"   Epsilon 命中率(±0.03): {overall['epsilon_metrics']['hit_rate_003']:.1f}%")
        print(f"   平均置信度: {overall['confidence_metrics']['average']:.3f}")
        print(f"   低置信度比例: {overall['confidence_metrics']['low_confidence_ratio']:.1f}%")
        
        # 按体系打印
        if result['system_metrics']:
            print(f"\n🔬 分体系性能:")
            for system, metrics in result['system_metrics'].items():
                print(f"   {system}:")
                print(f"     Alpha MAE: {metrics['alpha_metrics']['mae']:.4f}")
                print(f"     Alpha 命中率(±0.03): {metrics['alpha_metrics']['hit_rate_003']:.1f}%")
                print(f"     Epsilon MAE: {metrics['epsilon_metrics']['mae']:.4f}")
                print(f"     Epsilon 命中率(±0.03): {metrics['epsilon_metrics']['hit_rate_003']:.1f}%")
                print(f"     样本数: {metrics['sample_size']}")
        
    except Exception as e:
        logger.error(f"评估失败: {e}")
        print(f"❌ 错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
