from __future__ import annotations

import numpy as np
from typing import Dict, Any
from ..models.infer_fwd import get_model
from ..models.dataset_builder import compose_input_text_from_slots


def mass_per_area_proxy(params: Dict[str, Any]) -> float:
    """
    基于文献经验的质量/面积代理指标
    
    薄/轻目标：厚度 proxy，基于工艺参数的经验公式
    - 时间、电压、电流密度正相关
    - 不同体系有不同系数
    
    Args:
        params: 工艺参数字典
        
    Returns:
        归一化的质量/面积代理值 [0,1]，越小越好（薄/轻）
    """
    # 提取关键参数
    time_min = float(params.get('time_min', 15))
    voltage_V = float(params.get('voltage_V', 350))
    current_density = float(params.get('current_density_A_dm2', 8))
    system = params.get('system', 'silicate')
    
    # 体系系数（基于文献经验）
    system_coeffs = {
        'silicate': {'k_time': 1.0, 'k_voltage': 0.8, 'k_current': 1.2, 'base': 0.1},
        'zirconate': {'k_time': 0.9, 'k_voltage': 0.9, 'k_current': 1.0, 'base': 0.15},
        'phosphate': {'k_time': 1.1, 'k_voltage': 0.7, 'k_current': 1.3, 'base': 0.08}
    }
    
    coeff = system_coeffs.get(system, system_coeffs['silicate'])
    
    # 经验公式：厚度 ∝ 时间^0.7 × 电压^0.5 × 电流密度^0.6
    thickness_proxy = (
        coeff['base'] + 
        coeff['k_time'] * (time_min / 20.0) ** 0.7 +
        coeff['k_voltage'] * (voltage_V / 400.0) ** 0.5 +
        coeff['k_current'] * (current_density / 10.0) ** 0.6
    )
    
    # 归一化到 [0, 1]
    # 典型范围：薄膜 0.1-0.3，中等 0.3-0.6，厚重 0.6-1.0
    # 调整除数以获得更合理的分布，更多薄膜方案
    normalized = np.clip(thickness_proxy / 6.0, 0.0, 1.0)
    
    return float(normalized)


def uniformity_penalty(params: Dict[str, Any]) -> float:
    """
    均匀性惩罚函数
    
    基于 duty_cycle_pct 和 frequency_Hz 是否在推荐窗口内
    
    Args:
        params: 工艺参数字典
        
    Returns:
        均匀性惩罚值 [0,1]，越小越好（均匀）
    """
    duty_cycle = float(params.get('duty_cycle_pct', 25))
    frequency = float(params.get('frequency_Hz', 1000))
    system = params.get('system', 'silicate')
    
    # 不同体系的推荐窗口（基于文献最佳实践）
    recommended_windows = {
        'silicate': {
            'duty_cycle': (15, 30),  # 15-30% 获得均匀形貌
            'frequency': (800, 1200)  # 800-1200 Hz 减少弧坑
        },
        'zirconate': {
            'duty_cycle': (20, 40),  # 20-40% 锆盐体系较宽容
            'frequency': (600, 1000)  # 600-1000 Hz 适合双极脉冲
        },
        'phosphate': {
            'duty_cycle': (10, 25),  # 10-25% 磷酸盐需低占空比
            'frequency': (1000, 1500)  # 1000-1500 Hz 高频均匀
        }
    }
    
    windows = recommended_windows.get(system, recommended_windows['silicate'])
    
    # 计算偏离度
    duty_min, duty_max = windows['duty_cycle']
    freq_min, freq_max = windows['frequency']
    
    # Duty cycle 偏离惩罚
    if duty_cycle < duty_min:
        duty_penalty = (duty_min - duty_cycle) / duty_min
    elif duty_cycle > duty_max:
        duty_penalty = (duty_cycle - duty_max) / duty_max
    else:
        duty_penalty = 0.0
    
    # Frequency 偏离惩罚
    if frequency < freq_min:
        freq_penalty = (freq_min - frequency) / freq_min
    elif frequency > freq_max:
        freq_penalty = (frequency - freq_max) / freq_max
    else:
        freq_penalty = 0.0
    
    # 组合惩罚（加权平均）
    total_penalty = 0.6 * duty_penalty + 0.4 * freq_penalty
    
    # 限制在 [0, 1] 范围
    return float(np.clip(total_penalty, 0.0, 1.0))


def evaluate_objectives(params: Dict[str, Any], target: Dict[str, float]) -> Dict[str, Any]:
    """
    多目标评估函数
    
    包含：
    1. Alpha/Epsilon 性能目标
    2. 薄/轻目标 (mass_per_area_proxy)
    3. 均匀性目标 (uniformity_penalty)
    
    Args:
        params: 工艺参数
        target: 目标性能值
        
    Returns:
        目标函数值和预测结果
    """
    # 原有性能目标
    text = compose_input_text_from_slots(params)
    model = get_model()
    pred = model.predict(text)
    da = abs(pred["alpha"] - float(target.get("alpha", 0.0)))
    de = abs(pred["epsilon"] - float(target.get("epsilon", 0.0)))
    
    # 新增目标
    mass_proxy = mass_per_area_proxy(params)
    uniform_penalty = uniformity_penalty(params)
    
    return {
        "f1": da,  # Alpha 误差
        "f2": de,  # Epsilon 误差  
        "f3": mass_proxy,  # 厚度/质量代理（最小化）
        "f4": uniform_penalty,  # 均匀性惩罚（最小化）
        "pred": pred,
        "mass_proxy": mass_proxy,
        "uniformity_penalty": uniform_penalty
    }


def calculate_weighted_score(objectives: Dict[str, float], weights: Dict[str, float] = None) -> float:
    """
    计算加权总分
    
    Args:
        objectives: 目标函数值
        weights: 权重配置
        
    Returns:
        加权总分（越小越好）
    """
    if weights is None:
        weights = {
            'alpha': 0.4,
            'epsilon': 0.4, 
            'thin_light': 0.15,
            'uniform': 0.05
        }
    
    # 归一化各目标到相同尺度
    # Alpha/Epsilon 误差通常 0-0.1 范围
    alpha_normalized = min(objectives.get('f1', 0.0) / 0.1, 1.0)
    epsilon_normalized = min(objectives.get('f2', 0.0) / 0.1, 1.0)
    
    # Mass proxy 和 uniformity penalty 已归一化到 [0,1]
    mass_normalized = objectives.get('f3', 0.0)
    uniform_normalized = objectives.get('f4', 0.0)
    
    # 加权求和
    total_score = (
        weights['alpha'] * alpha_normalized +
        weights['epsilon'] * epsilon_normalized +
        weights['thin_light'] * mass_normalized +
        weights['uniform'] * uniform_normalized
    )
    
    return float(total_score)

