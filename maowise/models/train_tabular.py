#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
表格模型训练模块 - 基于LightGBM/XGBoost的分体系回归器

主要功能：
1. 分体系训练（silicate/zirconate独立模型）
2. 5折交叉验证
3. 分位回归估计不确定度
4. OOF预测保存
5. 模型评估和保存
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from sklearn.model_selection import KFold, GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib
import json
from pathlib import Path
import argparse
import sys

# 尝试导入机器学习后端（优先级顺序）
ML_BACKEND = None
try:
    import lightgbm as lgb
    ML_BACKEND = 'lightgbm'
except ImportError:
    try:
        import xgboost as xgb
        ML_BACKEND = 'xgboost'
    except ImportError:
        try:
            import catboost as cb
            ML_BACKEND = 'catboost'
        except ImportError:
            ML_BACKEND = None

# 添加项目根目录到Python路径
REPO_ROOT = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))

from maowise.models.features import create_features, FeatureEngineering
from maowise.utils.logger import setup_logger

class TabularModel:
    """表格模型类"""
    
    def __init__(self, backend: str = None, quantiles: List[float] = None):
        """
        初始化表格模型
        
        Args:
            backend: 机器学习后端 ('lightgbm', 'xgboost', 'catboost')
            quantiles: 分位回归分位数 [0.1, 0.5, 0.9]
        """
        self.backend = backend or ML_BACKEND
        self.quantiles = quantiles or [0.1, 0.5, 0.9]
        self.models = {}  # 存储不同系统和目标的模型
        self.feature_importance = {}
        self.logger = setup_logger(__name__)
        
        if self.backend is None:
            raise ImportError("未找到支持的机器学习后端（LightGBM/XGBoost/CatBoost）")
        
        self.logger.info(f"使用机器学习后端: {self.backend}")
    
    def _create_model(self, task_type: str = 'regression', quantile: float = None) -> Any:
        """创建单个模型实例"""
        if self.backend == 'lightgbm':
            params = {
                'objective': 'regression' if quantile is None else 'quantile',
                'metric': 'mae',
                'boosting_type': 'gbdt',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'feature_fraction': 0.9,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1,
                'random_state': 42
            }
            if quantile is not None:
                params['alpha'] = quantile
            
            return lgb.LGBMRegressor(**params)
            
        elif self.backend == 'xgboost':
            params = {
                'objective': 'reg:squarederror',
                'eval_metric': 'mae',
                'max_depth': 6,
                'learning_rate': 0.05,
                'subsample': 0.8,
                'colsample_bytree': 0.9,
                'random_state': 42,
                'verbosity': 0
            }
            if quantile is not None:
                params['objective'] = 'reg:quantileerror'
                params['quantile_alpha'] = quantile
            
            return xgb.XGBRegressor(**params)
            
        elif self.backend == 'catboost':
            params = {
                'loss_function': 'MAE',
                'depth': 6,
                'learning_rate': 0.05,
                'random_seed': 42,
                'verbose': False
            }
            if quantile is not None:
                params['loss_function'] = f'Quantile:alpha={quantile}'
            
            return cb.CatBoostRegressor(**params)
        
        else:
            raise ValueError(f"不支持的后端: {self.backend}")
    
    def train_system_models(self, X: np.ndarray, y: np.ndarray, system_labels: np.ndarray,
                           target_name: str, n_folds: int = 5) -> Dict[str, Any]:
        """
        为特定系统训练模型
        
        Args:
            X: 特征矩阵
            y: 目标变量
            system_labels: 系统标签
            target_name: 目标名称 ('alpha' or 'epsilon')
            n_folds: 交叉验证折数
            
        Returns:
            训练结果字典
        """
        results = {
            'systems': {},
            'oof_predictions': np.full(len(y), np.nan),
            'cv_scores': {},
            'feature_importance': {}
        }
        
        unique_systems = np.unique(system_labels)
        self.logger.info(f"训练 {target_name} 模型，系统: {unique_systems}")
        
        for system in unique_systems:
            if system in ['silicate', 'zirconate']:  # 只训练主要系统
                self.logger.info(f"训练 {system} 系统的 {target_name} 模型")
                
                # 过滤系统数据
                system_mask = system_labels == system
                X_sys = X[system_mask]
                y_sys = y[system_mask]
                
                if len(y_sys) < 10:  # 样本太少，跳过
                    self.logger.warning(f"{system} 系统样本太少 ({len(y_sys)})，跳过训练")
                    continue
                
                # 交叉验证
                kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)
                fold_scores = []
                fold_models = []
                oof_pred = np.zeros(len(y_sys))
                
                for fold, (train_idx, val_idx) in enumerate(kf.split(X_sys)):
                    self.logger.info(f"  折 {fold+1}/{n_folds}")
                    
                    X_train, X_val = X_sys[train_idx], X_sys[val_idx]
                    y_train, y_val = y_sys[train_idx], y_sys[val_idx]
                    
                    # 训练主模型（中位数回归）
                    model = self._create_model(quantile=0.5)
                    model.fit(X_train, y_train)
                    
                    # 预测并评估
                    y_pred = model.predict(X_val)
                    oof_pred[val_idx] = y_pred
                    
                    mae = mean_absolute_error(y_val, y_pred)
                    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
                    fold_scores.append({'mae': mae, 'rmse': rmse})
                    fold_models.append(model)
                    
                    self.logger.info(f"    MAE: {mae:.4f}, RMSE: {rmse:.4f}")
                
                # 训练分位回归模型（用于不确定度估计）
                quantile_models = {}
                for q in self.quantiles:
                    q_model = self._create_model(quantile=q)
                    q_model.fit(X_sys, y_sys)
                    quantile_models[f'q{int(q*100)}'] = q_model
                
                # 保存系统结果
                results['systems'][system] = {
                    'models': fold_models,
                    'quantile_models': quantile_models,
                    'cv_scores': fold_scores,
                    'mean_mae': np.mean([s['mae'] for s in fold_scores]),
                    'mean_rmse': np.mean([s['rmse'] for s in fold_scores]),
                    'std_mae': np.std([s['mae'] for s in fold_scores])
                }
                
                # 保存OOF预测
                global_indices = np.where(system_mask)[0]
                results['oof_predictions'][global_indices] = oof_pred
                
                # 特征重要性
                if hasattr(fold_models[0], 'feature_importances_'):
                    importance = np.mean([m.feature_importances_ for m in fold_models], axis=0)
                    results['feature_importance'][system] = importance.tolist()
                
                self.logger.info(f"  {system} CV MAE: {results['systems'][system]['mean_mae']:.4f} ± {results['systems'][system]['std_mae']:.4f}")
        
        # 计算总体CV分数
        valid_mask = ~np.isnan(results['oof_predictions'])
        if np.sum(valid_mask) > 0:
            overall_mae = mean_absolute_error(y[valid_mask], results['oof_predictions'][valid_mask])
            overall_rmse = np.sqrt(mean_squared_error(y[valid_mask], results['oof_predictions'][valid_mask]))
            results['cv_scores']['overall'] = {'mae': overall_mae, 'rmse': overall_rmse}
            
            self.logger.info(f"总体 CV MAE: {overall_mae:.4f}, RMSE: {overall_rmse:.4f}")
        
        return results
    
    def save_models(self, results: Dict[str, Any], output_dir: str, target_name: str):
        """保存模型到磁盘"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for system, system_results in results['systems'].items():
            system_dir = output_path / system
            system_dir.mkdir(exist_ok=True)
            
            target_dir = system_dir / target_name
            target_dir.mkdir(exist_ok=True)
            
            # 保存CV模型
            for i, model in enumerate(system_results['models']):
                joblib.dump(model, target_dir / f'fold_{i}.pkl')
            
            # 保存分位回归模型
            for q_name, q_model in system_results['quantile_models'].items():
                joblib.dump(q_model, target_dir / f'{q_name}.pkl')
            
            # 保存元数据
            metadata = {
                'backend': self.backend,
                'cv_scores': system_results['cv_scores'],
                'mean_mae': system_results['mean_mae'],
                'mean_rmse': system_results['mean_rmse'],
                'std_mae': system_results['std_mae'],
                'feature_importance': system_results.get('feature_importance', []),
                'quantiles': self.quantiles
            }
            
            with open(target_dir / 'metadata.json', 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # 保存OOF预测
        np.save(output_path / f'oof_{target_name}.npy', results['oof_predictions'])
        
        self.logger.info(f"{target_name} 模型已保存到: {output_dir}")

def load_tabular_models(model_dir: str) -> Dict[str, Any]:
    """
    加载表格模型
    
    Args:
        model_dir: 模型目录
        
    Returns:
        加载的模型字典
    """
    model_path = Path(model_dir)
    if not model_path.exists():
        return {}
    
    models = {}
    
    for system_dir in model_path.iterdir():
        if system_dir.is_dir() and system_dir.name in ['silicate', 'zirconate']:
            system_name = system_dir.name
            models[system_name] = {}
            
            for target_dir in system_dir.iterdir():
                if target_dir.is_dir() and target_dir.name in ['alpha', 'epsilon']:
                    target_name = target_dir.name
                    target_models = {}
                    
                    # 加载CV模型
                    fold_models = []
                    for fold_file in sorted(target_dir.glob('fold_*.pkl')):
                        fold_models.append(joblib.load(fold_file))
                    target_models['cv_models'] = fold_models
                    
                    # 加载分位回归模型
                    quantile_models = {}
                    for q_file in target_dir.glob('q*.pkl'):
                        q_name = q_file.stem
                        quantile_models[q_name] = joblib.load(q_file)
                    target_models['quantile_models'] = quantile_models
                    
                    # 加载元数据
                    metadata_file = target_dir / 'metadata.json'
                    if metadata_file.exists():
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            target_models['metadata'] = json.load(f)
                    
                    models[system_name][target_name] = target_models
    
    return models

def predict_tabular(models: Dict[str, Any], X: np.ndarray, system_labels: np.ndarray,
                   target_name: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    使用表格模型进行预测
    
    Args:
        models: 加载的模型字典
        X: 特征矩阵
        system_labels: 系统标签
        target_name: 目标名称
        
    Returns:
        (predictions, uncertainties)
    """
    predictions = np.full(len(X), np.nan)
    uncertainties = np.full(len(X), np.nan)
    
    unique_systems = np.unique(system_labels)
    
    for system in unique_systems:
        if system in models and target_name in models[system]:
            system_mask = system_labels == system
            X_sys = X[system_mask]
            
            system_models = models[system][target_name]
            
            # CV模型集成预测
            if 'cv_models' in system_models and system_models['cv_models']:
                cv_preds = []
                for model in system_models['cv_models']:
                    cv_preds.append(model.predict(X_sys))
                
                # 平均预测
                pred_mean = np.mean(cv_preds, axis=0)
                predictions[system_mask] = pred_mean
                
                # 基于CV模型变异性的不确定度
                pred_std = np.std(cv_preds, axis=0)
                uncertainties[system_mask] = pred_std
            
            # 如果有分位回归模型，使用更精确的不确定度估计
            if 'quantile_models' in system_models:
                q_models = system_models['quantile_models']
                if 'q10' in q_models and 'q90' in q_models:
                    q10_pred = q_models['q10'].predict(X_sys)
                    q90_pred = q_models['q90'].predict(X_sys)
                    
                    # 使用90%-10%分位数间距作为不确定度
                    uncertainties[system_mask] = (q90_pred - q10_pred) / 2.0
    
    return predictions, uncertainties

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MAO-Wise 表格模型训练")
    
    parser.add_argument(
        "--samples",
        type=str,
        required=True,
        help="样本数据文件路径 (parquet格式)"
    )
    
    parser.add_argument(
        "--out_dir",
        type=str,
        default="models_ckpt/tabular_v2",
        help="输出目录"
    )
    
    parser.add_argument(
        "--backend",
        type=str,
        choices=['lightgbm', 'xgboost', 'catboost'],
        help="机器学习后端"
    )
    
    parser.add_argument(
        "--n_folds",
        type=int,
        default=5,
        help="交叉验证折数"
    )
    
    parser.add_argument(
        "--quantiles",
        type=str,
        default="0.1,0.5,0.9",
        help="分位回归分位数，逗号分隔"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger(__name__)
    
    try:
        # 解析分位数
        quantiles = [float(q.strip()) for q in args.quantiles.split(',')]
        
        # 创建特征
        logger.info("创建特征...")
        X, y_alpha, y_epsilon, feature_engine = create_features(
            args.samples, args.out_dir
        )
        
        # 读取系统标签
        df = pd.read_parquet(args.samples)
        valid_mask = (df['alpha_150_2600'].notna() & df['epsilon_3000_30000'].notna())
        system_labels = df[valid_mask]['system'].fillna('unknown').values
        
        # 创建表格模型
        tabular_model = TabularModel(backend=args.backend, quantiles=quantiles)
        
        # 训练Alpha模型
        logger.info("="*60)
        logger.info("训练 Alpha 模型")
        logger.info("="*60)
        alpha_results = tabular_model.train_system_models(
            X, y_alpha, system_labels, 'alpha', args.n_folds
        )
        tabular_model.save_models(alpha_results, args.out_dir, 'alpha')
        
        # 训练Epsilon模型
        logger.info("="*60)
        logger.info("训练 Epsilon 模型")
        logger.info("="*60)
        epsilon_results = tabular_model.train_system_models(
            X, y_epsilon, system_labels, 'epsilon', args.n_folds
        )
        tabular_model.save_models(epsilon_results, args.out_dir, 'epsilon')
        
        # 生成评估报告
        report = {
            'model_type': 'tabular',
            'backend': tabular_model.backend,
            'n_samples': len(X),
            'n_features': X.shape[1],
            'quantiles': quantiles,
            'alpha_results': {
                'cv_scores': alpha_results.get('cv_scores', {}),
                'systems': {
                    system: {
                        'mean_mae': results['mean_mae'],
                        'std_mae': results['std_mae']
                    }
                    for system, results in alpha_results['systems'].items()
                }
            },
            'epsilon_results': {
                'cv_scores': epsilon_results.get('cv_scores', {}),
                'systems': {
                    system: {
                        'mean_mae': results['mean_mae'],
                        'std_mae': results['std_mae']
                    }
                    for system, results in epsilon_results['systems'].items()
                }
            }
        }
        
        # 保存报告
        report_path = Path(args.out_dir) / 'training_report.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"训练报告已保存到: {report_path}")
        
        # 打印总结
        logger.info("="*60)
        logger.info("训练总结")
        logger.info("="*60)
        
        for target, results in [('Alpha', alpha_results), ('Epsilon', epsilon_results)]:
            logger.info(f"\n{target} 模型:")
            overall_scores = results.get('cv_scores', {}).get('overall')
            if overall_scores:
                logger.info(f"  总体 MAE: {overall_scores['mae']:.4f}")
                logger.info(f"  总体 RMSE: {overall_scores['rmse']:.4f}")
            
            for system, sys_results in results['systems'].items():
                logger.info(f"  {system}: MAE {sys_results['mean_mae']:.4f} ± {sys_results['std_mae']:.4f}")
        
        logger.info(f"\n模型已保存到: {args.out_dir}")
        
    except Exception as e:
        logger.error(f"表格模型训练失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
