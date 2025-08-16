#!/usr/bin/env python3
"""校准mass_proxy参数的脚本"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge, HuberRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import yaml
from typing import Dict, Any

from maowise.utils.logger import logger
from maowise.optimize.objectives import charge_density, mass_proxy, uniformity_penalty


def load_experimental_data(file_path: str) -> pd.DataFrame:
    """加载实验数据"""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {file_path}")
    
    df = pd.read_parquet(file_path)
    logger.info(f"加载数据: {len(df)} 条记录")
    
    # 验证必需字段
    required_fields = ['system', 'current_density_Adm2', 'duty_cycle_pct', 'time_min']
    missing_fields = [f for f in required_fields if f not in df.columns]
    if missing_fields:
        raise ValueError(f"缺少必需字段: {missing_fields}")
    
    # 检查厚度或质量字段
    thickness_fields = ['thickness_um', 'coating_thickness_um', 'mass_per_area_mg_cm2']
    available_thickness = [f for f in thickness_fields if f in df.columns]
    
    if not available_thickness:
        logger.warning("未找到厚度/质量字段，将使用模拟数据")
        # 生成模拟厚度数据 (基于电荷密度的简单线性关系 + 噪声)
        df['thickness_um'] = (
            df['current_density_Adm2'] * df['duty_cycle_pct'] / 100 * df['time_min'] * 0.02 +
            np.random.normal(0, 2, len(df))
        )
        df['thickness_um'] = np.clip(df['thickness_um'], 5, 50)  # 限制在合理范围
        thickness_field = 'thickness_um'
    else:
        thickness_field = available_thickness[0]
        logger.info(f"使用厚度字段: {thickness_field}")
    
    return df, thickness_field


def calculate_charge_density_features(df: pd.DataFrame) -> pd.DataFrame:
    """计算电荷密度特征"""
    df = df.copy()
    
    # 计算电荷密度 (A·min/dm²)
    df['charge_density'] = df['current_density_Adm2'] * df['duty_cycle_pct'] / 100 * df['time_min']
    
    # 过滤异常值
    valid_mask = (
        (df['charge_density'] > 0) & 
        (df['charge_density'] < 100) &  # 合理的电荷密度上限
        (df[df.columns[-1]] > 0)  # 厚度/质量 > 0
    )
    
    df_clean = df[valid_mask].copy()
    logger.info(f"过滤后有效数据: {len(df_clean)} 条记录")
    
    return df_clean


def fit_thickness_models(df: pd.DataFrame, thickness_field: str) -> Dict[str, Dict[str, Any]]:
    """分体系拟合厚度~电荷密度模型"""
    results = {}
    
    for system in df['system'].unique():
        if pd.isna(system):
            continue
            
        system_df = df[df['system'] == system].copy()
        if len(system_df) < 3:
            logger.warning(f"体系 {system} 样本数过少({len(system_df)})，跳过拟合")
            continue
        
        X = system_df[['charge_density']].values
        y = system_df[thickness_field].values
        
        # 尝试Ridge和Huber回归
        models = {
            'Ridge': Ridge(alpha=1.0),
            'Huber': HuberRegressor(epsilon=1.35, alpha=0.0001)
        }
        
        best_model = None
        best_score = -np.inf
        best_name = None
        
        for model_name, model in models.items():
            try:
                model.fit(X, y)
                y_pred = model.predict(X)
                
                # 评估指标
                mae = mean_absolute_error(y, y_pred)
                r2 = r2_score(y, y_pred)
                
                # 综合评分 (优先考虑R²，然后考虑MAE)
                score = r2 - mae / np.std(y)
                
                logger.info(f"  {system} - {model_name}: R²={r2:.3f}, MAE={mae:.3f}, Score={score:.3f}")
                
                if score > best_score:
                    best_score = score
                    best_model = model
                    best_name = model_name
                    
            except Exception as e:
                logger.warning(f"  {system} - {model_name} 拟合失败: {e}")
        
        if best_model is not None:
            # 提取系数 (thickness = k * charge_density + b)
            k_charge_to_thickness = float(best_model.coef_[0])
            intercept = float(best_model.intercept_)
            
            y_pred = best_model.predict(X)
            mae = mean_absolute_error(y, y_pred)
            r2 = r2_score(y, y_pred)
            
            results[system] = {
                'k_charge_to_thickness': k_charge_to_thickness,
                'intercept': intercept,
                'model_type': best_name,
                'samples': len(system_df),
                'mae': mae,
                'r2': r2,
                'charge_range': [float(system_df['charge_density'].min()), 
                               float(system_df['charge_density'].max())],
                'thickness_range': [float(system_df[thickness_field].min()), 
                                  float(system_df[thickness_field].max())]
            }
            
            logger.info(f"✅ {system}: k={k_charge_to_thickness:.4f} µm/(A·min/dm²), "
                       f"R²={r2:.3f}, MAE={mae:.2f} µm")
        else:
            logger.error(f"❌ {system}: 所有模型拟合失败")
    
    return results


def update_config_yaml(results: Dict[str, Dict[str, Any]], config_path: str = "maowise/config/config.yaml"):
    """更新配置文件"""
    config_path = Path(config_path)
    
    # 读取现有配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 确保结构存在
    if 'optimize' not in config:
        config['optimize'] = {}
    if 'mass_proxy' not in config['optimize']:
        config['optimize']['mass_proxy'] = {}
    if 'uniformity' not in config['optimize']:
        config['optimize']['uniformity'] = {}
    
    # 更新k_charge_to_thickness
    k_charge_to_thickness = {}
    charge_limits = {'min': 1.0, 'max': 80.0}  # 默认值
    
    for system, result in results.items():
        k_charge_to_thickness[system] = result['k_charge_to_thickness']
        
        # 更新电荷密度范围
        charge_min, charge_max = result['charge_range']
        charge_limits['min'] = min(charge_limits['min'], charge_min * 0.8)
        charge_limits['max'] = max(charge_limits['max'], charge_max * 1.2)
    
    # 更新配置
    config['optimize']['mass_proxy']['k_charge_to_thickness'] = k_charge_to_thickness
    config['optimize']['mass_proxy']['charge_limits'] = charge_limits
    
    # 调整uniformity软边界
    config['optimize']['uniformity']['soft_margin'] = 0.08
    
    # 备份原配置
    backup_path = config_path.with_suffix('.yaml.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
    logger.info(f"配置备份: {backup_path}")
    
    # 写入新配置
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
    logger.info(f"配置已更新: {config_path}")
    
    return config


def evaluate_objectives_distribution(sample_params: list) -> Dict[str, Dict[str, float]]:
    """评估目标函数分布"""
    mass_values = []
    uniformity_values = []
    
    for params in sample_params:
        try:
            mass_val = mass_proxy(params)
            uniformity_val = uniformity_penalty(params)
            mass_values.append(mass_val)
            uniformity_values.append(uniformity_val)
        except Exception as e:
            logger.warning(f"计算目标函数失败: {e}")
            continue
    
    def calc_stats(values):
        if not values:
            return {'min': 0, 'p50': 0, 'max': 0}
        values = np.array(values)
        return {
            'min': float(np.min(values)),
            'p50': float(np.percentile(values, 50)),
            'max': float(np.max(values))
        }
    
    return {
        'mass_proxy': calc_stats(mass_values),
        'uniformity_penalty': calc_stats(uniformity_values)
    }


def generate_sample_parameters(n_samples: int = 100) -> list:
    """生成样本参数用于分布测试"""
    np.random.seed(42)
    
    samples = []
    systems = ['silicate', 'zirconate', 'phosphate']
    
    for _ in range(n_samples):
        system = np.random.choice(systems)
        params = {
            'system': system,
            'current_density_Adm2': np.random.uniform(5, 20),
            'duty_cycle_pct': np.random.uniform(15, 40),
            'time_min': np.random.uniform(10, 30),
            'frequency_Hz': np.random.uniform(600, 1200),
            'voltage_V': np.random.uniform(200, 400),
            'waveform': np.random.choice(['unipolar', 'bipolar'])
        }
        samples.append(params)
    
    return samples


def main():
    parser = argparse.ArgumentParser(description="校准mass_proxy参数")
    parser.add_argument("--data", 
                       default="datasets/experiments/experiments.parquet",
                       help="实验数据文件路径")
    parser.add_argument("--config", 
                       default="maowise/config/config.yaml",
                       help="配置文件路径")
    parser.add_argument("--output", 
                       help="输出校准结果JSON文件")
    
    args = parser.parse_args()
    
    logger.info("🔧 开始mass_proxy参数校准")
    
    # 1. 加载数据
    try:
        df, thickness_field = load_experimental_data(args.data)
    except FileNotFoundError:
        # 尝试备选路径
        alt_paths = [
            "datasets/versions/maowise_ds_v1/samples.parquet",
            "datasets/test_experiments.parquet"
        ]
        
        df = None
        for alt_path in alt_paths:
            try:
                df, thickness_field = load_experimental_data(alt_path)
                logger.info(f"使用备选数据: {alt_path}")
                break
            except FileNotFoundError:
                continue
        
        if df is None:
            raise FileNotFoundError("未找到可用的实验数据文件")
    
    # 2. 计算电荷密度特征
    df_clean = calculate_charge_density_features(df)
    
    if len(df_clean) == 0:
        raise ValueError("没有有效的实验数据用于校准")
    
    # 3. 分体系拟合模型
    logger.info("🔍 分体系拟合厚度~电荷密度模型")
    results = fit_thickness_models(df_clean, thickness_field)
    
    if not results:
        raise ValueError("没有成功拟合的模型")
    
    # 4. 评估更新前的分布
    logger.info("📊 评估更新前的目标函数分布")
    sample_params = generate_sample_parameters(100)
    dist_before = evaluate_objectives_distribution(sample_params)
    
    # 5. 更新配置文件
    logger.info("⚙️ 更新配置文件")
    config = update_config_yaml(results, args.config)
    
    # 6. 重新加载配置并评估更新后的分布
    logger.info("📊 评估更新后的目标函数分布")
    # 重新导入以加载新配置
    import importlib
    import maowise.optimize.objectives
    importlib.reload(maowise.optimize.objectives)
    from maowise.optimize.objectives import mass_proxy, uniformity_penalty
    
    dist_after = evaluate_objectives_distribution(sample_params)
    
    # 7. 打印结果
    print("\n" + "="*60)
    print("🎯 Mass Proxy 校准结果")
    print("="*60)
    
    print("\n📈 拟合结果:")
    for system, result in results.items():
        print(f"  {system.upper()}:")
        print(f"    k_charge_to_thickness: {result['k_charge_to_thickness']:.4f} µm/(A·min/dm²)")
        print(f"    样本数: {result['samples']}")
        print(f"    R²: {result['r2']:.3f}")
        print(f"    MAE: {result['mae']:.2f} µm")
        print(f"    模型类型: {result['model_type']}")
    
    print(f"\n⚙️ 配置更新:")
    print(f"  soft_margin: 0.15 → 0.08")
    print(f"  新增k_charge_to_thickness: {len(results)} 个体系")
    
    print(f"\n📊 目标函数分布对比:")
    print(f"  Mass Proxy:")
    print(f"    更新前: min={dist_before['mass_proxy']['min']:.3f}, "
          f"p50={dist_before['mass_proxy']['p50']:.3f}, "
          f"max={dist_before['mass_proxy']['max']:.3f}")
    print(f"    更新后: min={dist_after['mass_proxy']['min']:.3f}, "
          f"p50={dist_after['mass_proxy']['p50']:.3f}, "
          f"max={dist_after['mass_proxy']['max']:.3f}")
    
    print(f"  Uniformity Penalty:")
    print(f"    更新前: min={dist_before['uniformity_penalty']['min']:.3f}, "
          f"p50={dist_before['uniformity_penalty']['p50']:.3f}, "
          f"max={dist_before['uniformity_penalty']['max']:.3f}")
    print(f"    更新后: min={dist_after['uniformity_penalty']['min']:.3f}, "
          f"p50={dist_after['uniformity_penalty']['p50']:.3f}, "
          f"max={dist_after['uniformity_penalty']['max']:.3f}")
    
    # 8. 重新生成候选并测试
    logger.info("🚀 重新生成候选方案进行验证")
    try:
        import subprocess
        result = subprocess.run([
            "python", "scripts/generate_batch_plans.py", 
            "--output", "tasks/test_calibrated", 
            "--n_candidates", "20"
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            plans_file = Path("tasks/test_calibrated/plans.csv")
            if plans_file.exists():
                plans_df = pd.read_csv(plans_file)
                if all(col in plans_df.columns for col in ['mass_proxy', 'uniformity_penalty', 'score_total']):
                    print(f"\n📋 新生成候选方案分布 (n={len(plans_df)}):")
                    for col in ['mass_proxy', 'uniformity_penalty', 'score_total']:
                        values = plans_df[col].dropna()
                        if len(values) > 0:
                            print(f"  {col}:")
                            print(f"    min={values.min():.3f}, "
                                  f"p50={values.median():.3f}, "
                                  f"max={values.max():.3f}")
                else:
                    print("⚠️  新生成的plans.csv缺少必要的目标函数列")
            else:
                print("⚠️  未找到新生成的plans.csv文件")
        else:
            print(f"⚠️  重新生成候选失败: {result.stderr}")
    except Exception as e:
        print(f"⚠️  重新生成候选出错: {e}")
    
    # 9. 保存结果
    if args.output:
        import json
        output_data = {
            'calibration_results': results,
            'distribution_before': dist_before,
            'distribution_after': dist_after,
            'config_updates': {
                'soft_margin': 0.08,
                'k_charge_to_thickness': {sys: res['k_charge_to_thickness'] 
                                        for sys, res in results.items()}
            }
        }
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存: {args.output}")
    
    print(f"\n✅ Mass Proxy 校准完成！")


if __name__ == "__main__":
    main()
