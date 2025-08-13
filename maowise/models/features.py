#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
特征工程模块 - 从样本数据生成机器学习特征

主要功能：
1. 系统和材料特征（one-hot编码、目标编码）
2. 电解液组分特征（统计、化学特性）
3. 工艺参数特征（标准化、缺失值处理）
4. 后处理特征编码
5. 特征标准化和缺失值填充
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import KFold
import joblib
import json
import re
from pathlib import Path
import warnings

from maowise.utils.logger import setup_logger

warnings.filterwarnings('ignore')

class FeatureEngineering:
    """特征工程类"""
    
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.scalers = {}
        self.encoders = {}
        self.target_encoders = {}
        self.feature_names = []
        self.fitted = False
        
    def extract_electrolyte_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取电解液特征
        
        Args:
            df: 包含electrolyte_components的DataFrame
            
        Returns:
            电解液特征DataFrame
        """
        electrolyte_features = pd.DataFrame(index=df.index)
        
        # 解析电解液组分
        if 'electrolyte_components' in df.columns:
            # 处理电解液组分列表
            components_series = df['electrolyte_components'].fillna('[]')
            
            # 统计特征
            electrolyte_features['n_components'] = components_series.apply(
                lambda x: len(eval(x)) if isinstance(x, str) and x.strip() else 0
            )
            
            # 化学特性检测
            def check_chemical_features(components_str):
                try:
                    if isinstance(components_str, str) and components_str.strip():
                        components = eval(components_str)
                        if isinstance(components, list):
                            components_text = ' '.join(str(comp) for comp in components).upper()
                        else:
                            components_text = str(components).upper()
                    else:
                        components_text = ''
                    
                    features = {
                        'has_fluoride': any(x in components_text for x in ['F', 'FLUORIDE', 'KF', 'NAF', 'HF']),
                        'has_zirconium': any(x in components_text for x in ['ZR', 'ZIRCONIUM', 'ZRF', 'K2ZRF6']),
                        'has_silicate': any(x in components_text for x in ['SIO3', 'SILICATE', 'NA2SIO3', 'K2SIO3']),
                        'has_phosphate': any(x in components_text for x in ['PO4', 'PHOSPHATE', 'NA3PO4']),
                        'has_hydroxide': any(x in components_text for x in ['OH', 'HYDROXIDE', 'KOH', 'NAOH']),
                        'has_organic': any(x in components_text for x in ['EDTA', 'CITRIC', 'GLYCOL', 'ALCOHOL']),
                        'has_rare_earth': any(x in components_text for x in ['Y2O3', 'CEO2', 'LA', 'ND', 'Y', 'CE'])
                    }
                    return features
                except:
                    return {key: False for key in ['has_fluoride', 'has_zirconium', 'has_silicate', 
                                                  'has_phosphate', 'has_hydroxide', 'has_organic', 'has_rare_earth']}
            
            # 应用化学特性检测
            chemical_features = components_series.apply(check_chemical_features)
            chemical_df = pd.DataFrame(chemical_features.tolist(), index=df.index)
            electrolyte_features = pd.concat([electrolyte_features, chemical_df], axis=1)
        else:
            # 如果没有electrolyte_components列，设置默认值
            default_features = ['n_components', 'has_fluoride', 'has_zirconium', 'has_silicate', 
                              'has_phosphate', 'has_hydroxide', 'has_organic', 'has_rare_earth']
            for feature in default_features:
                electrolyte_features[feature] = 0 if feature == 'n_components' else False
        
        return electrolyte_features
    
    def extract_waveform_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取波形参数特征
        
        Args:
            df: 包含波形参数的DataFrame
            
        Returns:
            波形特征DataFrame
        """
        waveform_features = pd.DataFrame(index=df.index)
        
        # 基础波形参数
        waveform_params = ['frequency_Hz', 'duty_cycle_pct', 'voltage_V', 'current_density_A_dm2']
        for param in waveform_params:
            if param in df.columns:
                waveform_features[param] = pd.to_numeric(df[param], errors='coerce')
            else:
                waveform_features[param] = np.nan
        
        # 衍生特征
        if 'frequency_Hz' in waveform_features.columns and 'duty_cycle_pct' in waveform_features.columns:
            waveform_features['effective_frequency'] = (
                waveform_features['frequency_Hz'] * waveform_features['duty_cycle_pct'] / 100
            )
        
        if 'voltage_V' in waveform_features.columns and 'current_density_A_dm2' in waveform_features.columns:
            waveform_features['power_density'] = (
                waveform_features['voltage_V'] * waveform_features['current_density_A_dm2']
            )
        
        # 波形类型检测（基于文本字段）
        waveform_features['is_bipolar'] = False
        waveform_features['is_unipolar'] = False
        waveform_features['is_ac'] = False
        waveform_features['is_dc'] = False
        
        if 'text' in df.columns:
            text_lower = df['text'].fillna('').str.lower()
            waveform_features['is_bipolar'] = text_lower.str.contains('双极|bipolar')
            waveform_features['is_unipolar'] = text_lower.str.contains('单极|unipolar')
            waveform_features['is_ac'] = text_lower.str.contains('交流|ac')
            waveform_features['is_dc'] = text_lower.str.contains('直流|dc')
        
        return waveform_features
    
    def extract_process_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取工艺条件特征
        
        Args:
            df: 包含工艺参数的DataFrame
            
        Returns:
            工艺特征DataFrame
        """
        process_features = pd.DataFrame(index=df.index)
        
        # 基础工艺参数
        process_params = ['time_min', 'temp_C', 'pH']
        for param in process_params:
            if param in df.columns:
                process_features[param] = pd.to_numeric(df[param], errors='coerce')
            else:
                process_features[param] = np.nan
        
        # pH分类
        if 'pH' in process_features.columns:
            process_features['pH_acidic'] = (process_features['pH'] < 7).astype(int)
            process_features['pH_neutral'] = ((process_features['pH'] >= 7) & (process_features['pH'] <= 8)).astype(int)
            process_features['pH_alkaline'] = (process_features['pH'] > 8).astype(int)
        else:
            process_features['pH_acidic'] = 0
            process_features['pH_neutral'] = 0  
            process_features['pH_alkaline'] = 0
        
        # 温度分类
        if 'temp_C' in process_features.columns:
            process_features['temp_low'] = (process_features['temp_C'] < 25).astype(int)
            process_features['temp_normal'] = ((process_features['temp_C'] >= 25) & (process_features['temp_C'] <= 35)).astype(int)
            process_features['temp_high'] = (process_features['temp_C'] > 35).astype(int)
        else:
            process_features['temp_low'] = 0
            process_features['temp_normal'] = 0
            process_features['temp_high'] = 0
        
        # 时间分类
        if 'time_min' in process_features.columns:
            process_features['time_short'] = (process_features['time_min'] < 15).astype(int)
            process_features['time_medium'] = ((process_features['time_min'] >= 15) & (process_features['time_min'] <= 25)).astype(int)
            process_features['time_long'] = (process_features['time_min'] > 25).astype(int)
        else:
            process_features['time_short'] = 0
            process_features['time_medium'] = 0
            process_features['time_long'] = 0
        
        return process_features
    
    def extract_material_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取材料系统特征
        
        Args:
            df: 包含材料信息的DataFrame
            
        Returns:
            材料特征DataFrame
        """
        material_features = pd.DataFrame(index=df.index)
        
        # 系统类型 (one-hot编码)
        if 'system' in df.columns:
            system_dummies = pd.get_dummies(df['system'].fillna('unknown'), prefix='system')
            material_features = pd.concat([material_features, system_dummies], axis=1)
        
        # 基体合金 (hash特征 + one-hot)
        if 'substrate_alloy' in df.columns:
            substrate_clean = df['substrate_alloy'].fillna('unknown').str.upper()
            
            # 常见合金的one-hot
            common_alloys = ['AZ91D', 'AZ31B', 'AZ91', 'AZ31', 'AM60', 'ZK60']
            for alloy in common_alloys:
                material_features[f'alloy_{alloy}'] = (substrate_clean == alloy).astype(int)
            
            # 合金族特征
            material_features['is_AZ_series'] = substrate_clean.str.contains('AZ').astype(int)
            material_features['is_AM_series'] = substrate_clean.str.contains('AM').astype(int)
            material_features['is_ZK_series'] = substrate_clean.str.contains('ZK').astype(int)
            
            # Hash特征（用于处理稀有合金）
            material_features['alloy_hash'] = substrate_clean.apply(
                lambda x: hash(x) % 100 if x != 'UNKNOWN' else 0
            )
        
        # 电解液族
        if 'electrolyte_family' in df.columns:
            family_dummies = pd.get_dummies(df['electrolyte_family'].fillna('unknown'), prefix='family')
            material_features = pd.concat([material_features, family_dummies], axis=1)
        
        return material_features
    
    def extract_postprocess_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取后处理特征
        
        Args:
            df: 包含后处理信息的DataFrame
            
        Returns:
            后处理特征DataFrame
        """
        postprocess_features = pd.DataFrame(index=df.index)
        
        # 从文本中检测后处理类型
        postprocess_features['has_annealing'] = False
        postprocess_features['has_sealing'] = False
        postprocess_features['has_coating'] = False
        postprocess_features['no_postprocess'] = False
        
        if 'text' in df.columns:
            text_lower = df['text'].fillna('').str.lower()
            
            # 退火处理
            postprocess_features['has_annealing'] = text_lower.str.contains(
                '退火|annealing|热处理|heat.?treat'
            )
            
            # 封孔处理  
            postprocess_features['has_sealing'] = text_lower.str.contains(
                '封孔|sealing|密封|封闭'
            )
            
            # 涂层处理
            postprocess_features['has_coating'] = text_lower.str.contains(
                '涂层|coating|镀层|表面处理'
            )
            
            # 无后处理
            postprocess_features['no_postprocess'] = text_lower.str.contains(
                '无后处理|无|none|no.?post|不处理'
            )
        
        return postprocess_features
    
    def fit_transform(self, df: pd.DataFrame, target_cols: List[str] = None) -> np.ndarray:
        """
        拟合并转换特征
        
        Args:
            df: 输入DataFrame
            target_cols: 目标列（用于目标编码）
            
        Returns:
            特征矩阵
        """
        self.logger.info("开始特征工程：拟合并转换")
        
        # 提取各类特征
        material_features = self.extract_material_features(df)
        electrolyte_features = self.extract_electrolyte_features(df)
        waveform_features = self.extract_waveform_features(df)
        process_features = self.extract_process_features(df)
        postprocess_features = self.extract_postprocess_features(df)
        
        # 合并所有特征
        all_features = pd.concat([
            material_features,
            electrolyte_features, 
            waveform_features,
            process_features,
            postprocess_features
        ], axis=1)
        
        # 确保没有重复列
        all_features = all_features.loc[:, ~all_features.columns.duplicated()]
        
        self.feature_names = list(all_features.columns)
        self.logger.info(f"生成 {len(self.feature_names)} 个特征")
        
        # 分离数值特征和类别特征
        numeric_features = all_features.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = all_features.select_dtypes(include=['object', 'bool']).columns.tolist()
        
        # 处理数值特征
        if numeric_features:
            # 缺失值填充（中位数）
            numeric_data = all_features[numeric_features].copy()
            for col in numeric_features:
                median_val = numeric_data[col].median()
                numeric_data[col] = numeric_data[col].fillna(median_val)
                self.scalers[f'{col}_median'] = median_val
            
            # 标准化
            scaler = StandardScaler()
            numeric_scaled = scaler.fit_transform(numeric_data)
            self.scalers['numeric_scaler'] = scaler
            
            all_features[numeric_features] = numeric_scaled
        
        # 处理类别特征
        for col in categorical_features:
            # 缺失值填充
            all_features[col] = all_features[col].fillna('UNK')
            
            # 标签编码
            encoder = LabelEncoder()
            all_features[col] = encoder.fit_transform(all_features[col].astype(str))
            self.encoders[col] = encoder
        
        # 目标编码（如果提供了目标列）
        if target_cols:
            for target_col in target_cols:
                if target_col in df.columns:
                    self._fit_target_encoding(all_features, df[target_col], categorical_features)
        
        self.fitted = True
        
        # 转换为numpy数组
        X = all_features.values.astype(np.float32)
        
        self.logger.info(f"特征工程完成，输出形状: {X.shape}")
        return X
    
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        转换特征（已拟合）
        
        Args:
            df: 输入DataFrame
            
        Returns:
            特征矩阵
        """
        if not self.fitted:
            raise ValueError("FeatureEngineering未拟合，请先调用fit_transform")
        
        # 提取各类特征（使用相同的方法）
        material_features = self.extract_material_features(df)
        electrolyte_features = self.extract_electrolyte_features(df)
        waveform_features = self.extract_waveform_features(df)
        process_features = self.extract_process_features(df)
        postprocess_features = self.extract_postprocess_features(df)
        
        # 合并所有特征
        all_features = pd.concat([
            material_features,
            electrolyte_features,
            waveform_features, 
            process_features,
            postprocess_features
        ], axis=1)
        
        # 确保列顺序一致
        all_features = all_features.reindex(columns=self.feature_names, fill_value=0)
        
        # 分离数值特征和类别特征
        numeric_features = []
        categorical_features = []
        
        for col in self.feature_names:
            if col in self.encoders:
                categorical_features.append(col)
            else:
                numeric_features.append(col)
        
        # 处理数值特征
        if numeric_features:
            # 缺失值填充
            for col in numeric_features:
                if f'{col}_median' in self.scalers:
                    all_features[col] = all_features[col].fillna(self.scalers[f'{col}_median'])
            
            # 标准化
            if 'numeric_scaler' in self.scalers:
                numeric_data = all_features[numeric_features]
                numeric_scaled = self.scalers['numeric_scaler'].transform(numeric_data)
                all_features[numeric_features] = numeric_scaled
        
        # 处理类别特征
        for col in categorical_features:
            # 缺失值填充
            all_features[col] = all_features[col].fillna('UNK')
            
            # 标签编码
            encoder = self.encoders[col]
            # 处理未见过的类别
            col_values = all_features[col].astype(str)
            known_classes = set(encoder.classes_)
            col_values = col_values.apply(lambda x: x if x in known_classes else 'UNK')
            all_features[col] = encoder.transform(col_values)
        
        # 转换为numpy数组
        X = all_features.values.astype(np.float32)
        
        return X
    
    def _fit_target_encoding(self, X: pd.DataFrame, y: pd.Series, categorical_features: List[str]):
        """拟合目标编码"""
        # 这里可以实现目标编码，暂时跳过以保持简单
        pass
    
    def save(self, filepath: str):
        """保存特征工程器"""
        save_data = {
            'scalers': self.scalers,
            'encoders': self.encoders,
            'target_encoders': self.target_encoders,
            'feature_names': self.feature_names,
            'fitted': self.fitted
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(save_data, filepath)
        self.logger.info(f"特征工程器已保存到: {filepath}")
    
    def load(self, filepath: str):
        """加载特征工程器"""
        save_data = joblib.load(filepath)
        
        self.scalers = save_data['scalers']
        self.encoders = save_data['encoders']
        self.target_encoders = save_data['target_encoders']
        self.feature_names = save_data['feature_names']
        self.fitted = save_data['fitted']
        
        self.logger.info(f"特征工程器已从 {filepath} 加载")

def create_features(samples_path: str, output_dir: str = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray, FeatureEngineering]:
    """
    便捷函数：从样本文件创建特征
    
    Args:
        samples_path: 样本文件路径
        output_dir: 输出目录（保存特征工程器）
        
    Returns:
        (X, y_alpha, y_epsilon, feature_engine)
    """
    logger = setup_logger(__name__)
    
    # 读取数据
    logger.info(f"读取样本数据: {samples_path}")
    df = pd.read_parquet(samples_path)
    
    # 过滤有效样本
    valid_mask = (
        df['alpha_150_2600'].notna() & 
        df['epsilon_3000_30000'].notna()
    )
    df_valid = df[valid_mask].copy()
    logger.info(f"有效样本数: {len(df_valid)} / {len(df)}")
    
    # 创建特征
    feature_engine = FeatureEngineering()
    X = feature_engine.fit_transform(df_valid, ['alpha_150_2600', 'epsilon_3000_30000'])
    
    # 提取目标
    y_alpha = df_valid['alpha_150_2600'].values.astype(np.float32)
    y_epsilon = df_valid['epsilon_3000_30000'].values.astype(np.float32)
    
    # 保存特征工程器
    if output_dir:
        feature_engine.save(f"{output_dir}/feature_engine.pkl")
    
    logger.info(f"特征创建完成: X={X.shape}, y_alpha={y_alpha.shape}, y_epsilon={y_epsilon.shape}")
    
    return X, y_alpha, y_epsilon, feature_engine
