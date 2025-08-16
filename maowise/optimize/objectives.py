from __future__ import annotations

import numpy as np
from typing import Dict, Any
from ..models.infer_fwd import get_model
from ..models.dataset_builder import compose_input_text_from_slots
from ..utils.config import load_config


def charge_density(params: Dict[str, Any]) -> float:
    """
    计算电荷密度
    
    Args:
        params: 工艺参数字典
        
    Returns:
        电荷密度 (A·min/dm²)
    """
    current_density_Adm2 = float(params.get('current_density_A_dm2', 8))
    duty_cycle_pct = float(params.get('duty_cycle_pct', 25))
    time_min = float(params.get('time_min', 15))
    
    return current_density_Adm2 * (duty_cycle_pct / 100.0) * time_min


def thickness_proxy(params: Dict[str, Any]) -> float:
    """
    计算厚度代理值
    
    Args:
        params: 工艺参数字典
        
    Returns:
        厚度代理值 (µm)
    """
    config = load_config()
    system = params.get('system', 'silicate')
    
    # 从配置获取转换系数
    k_charge_to_thickness = config.get('optimize', {}).get('mass_proxy', {}).get('k_charge_to_thickness', {
        'silicate': 0.015,
        'zirconate': 0.018
    })
    
    k = k_charge_to_thickness.get(system, 0.015)
    charge_dens = charge_density(params)
    
    return k * charge_dens


def mass_proxy(params: Dict[str, Any]) -> float:
    """
    质量代理指标
    
    Args:
        params: 工艺参数字典
        
    Returns:
        归一化的质量代理值 [0,1]，越小越好（薄/轻）
    """
    config = load_config()
    system = params.get('system', 'silicate')
    
    # 从配置获取参数
    mass_config = config.get('optimize', {}).get('mass_proxy', {})
    rho_coating_g_cm3 = mass_config.get('rho_coating_g_cm3', {
        'silicate': 3.2,
        'zirconate': 4.6
    })
    charge_limits = mass_config.get('charge_limits', {'min': 3.0, 'max': 60.0})
    
    # 计算电荷密度
    charge_dens = charge_density(params)
    
    # 归一化到[0,1]，以 charge_limits 的 min/max 做线性缩放
    z = (charge_dens - charge_limits['min']) / (charge_limits['max'] - charge_limits['min'])
    z = np.clip(z, 0, 1)
    
    # 获取当前体系的密度
    rho = rho_coating_g_cm3.get(system, 3.2)
    max_rho = max(rho_coating_g_cm3.values())
    
    mass_proxy_val = np.clip(z * (rho / max_rho), 0, 1)
    
    return float(mass_proxy_val)


def uniformity_penalty(params: Dict[str, Any]) -> float:
    """
    均匀性惩罚函数（三角惩罚 + 双极波形加分）
    
    Args:
        params: 工艺参数字典
        
    Returns:
        均匀性惩罚值 [0,1]，越小越好（均匀）
    """
    config = load_config()
    system = params.get('system', 'silicate')
    
    # 从配置获取参数
    uniformity_config = config.get('optimize', {}).get('uniformity', {})
    freq_win_Hz = uniformity_config.get('freq_win_Hz', {
        'silicate': [700, 1100],
        'zirconate': [600, 1000]
    })
    duty_win_pct = uniformity_config.get('duty_win_pct', {
        'silicate': [20, 35],
        'zirconate': [18, 32]
    })
    soft_margin = uniformity_config.get('soft_margin', 0.15)
    freq_weight = uniformity_config.get('freq_weight', 0.6)
    duty_weight = uniformity_config.get('duty_weight', 0.4)
    bipolar_bonus = uniformity_config.get('bipolar_bonus', 0.15)
    
    # 获取参数值
    freq_Hz = float(params.get('frequency_Hz', 1000))
    duty_pct = float(params.get('duty_cycle_pct', 25))
    waveform = params.get('waveform', 'unipolar')
    
    # 获取体系特定的窗口
    freq_lo, freq_hi = freq_win_Hz.get(system, [700, 1100])
    duty_lo, duty_hi = duty_win_pct.get(system, [20, 35])
    
    def tri_penalty(val: float, lo: float, hi: float, soft: float) -> float:
        """三角惩罚函数"""
        if lo <= val <= hi:
            return 0.0
        d = (lo - val) / ((hi - lo) * soft) if val < lo else (val - hi) / ((hi - lo) * soft)
        return np.clip(d, 0, 1)
    
    # 计算频率和占空比惩罚
    pf = tri_penalty(freq_Hz, freq_lo, freq_hi, soft_margin)
    pd = tri_penalty(duty_pct, duty_lo, duty_hi, soft_margin)
    
    # 基础惩罚
    base = freq_weight * pf + duty_weight * pd
    
    # 双极波形加分
    bonus = bipolar_bonus if waveform in {"bipolar", "双极"} else 0.0
    
    uniformity_penalty_val = np.clip(base - bonus, 0, 1)
    
    return float(uniformity_penalty_val)


def score_total(params: Dict[str, Any], pred: Dict[str, Any], confidence: float = 0.5, citations_count: int = 0, rule_penalty: float = 0.0) -> float:
    """
    计算综合得分
    
    Args:
        params: 工艺参数字典
        pred: 预测结果字典 (包含alpha_pred, epsilon_pred)
        confidence: 置信度
        citations_count: 引用计数
        rule_penalty: 规则惩罚分数 (越低越好)
        
    Returns:
        综合得分 (越高越好)
    """
    config = load_config()
    scoring_config = config.get('optimize', {}).get('scoring', {})
    
    # 从配置获取参数
    epsilon_floor = scoring_config.get('epsilon_floor', 0.80)
    alpha_ceiling = scoring_config.get('alpha_ceiling', 0.20)
    epsilon_scale = scoring_config.get('epsilon_scale', 0.03)
    alpha_scale = scoring_config.get('alpha_scale', 0.03)
    
    # 获取预测值
    epsilon_pred = pred.get('epsilon', 0.0)
    alpha_pred = pred.get('alpha', 0.0)
    
    # Sigmoid函数
    def sig(t):
        return 1.0 / (1.0 + np.exp(-t))
    
    # 各项得分计算
    s_eps = 3.0 * sig((epsilon_pred - epsilon_floor) / epsilon_scale)
    s_abs = 2.0 * sig((alpha_ceiling - alpha_pred) / alpha_scale)
    s_conf = 0.5 * np.clip(confidence - 0.55, 0, 1)
    s_cit = 0.2 * np.clip(citations_count / 5.0, 0, 1) if citations_count > 0 else 0.0
    
    # 薄/轻目标和均匀性目标（负分，因为是惩罚）
    s_thin = -1.0 * mass_proxy(params)
    s_uni = -1.0 * uniformity_penalty(params)
    
    # 规则奖励：将rule_penalty转换为rule_bonus（越低的penalty越高的bonus）
    # 使用指数衰减：bonus = exp(-penalty/scale) * weight
    rule_scale = scoring_config.get('rule_penalty_scale', 2.0)  # 衰减尺度
    rule_weight = scoring_config.get('rule_bonus_weight', 1.0)  # 权重
    rule_bonus = rule_weight * np.exp(-rule_penalty / rule_scale)
    
    # 总分
    total_score = s_eps + s_abs + s_conf + s_cit + s_thin + s_uni + rule_bonus
    
    return float(total_score)


def evaluate_objectives(params: Dict[str, Any], target: Dict[str, float]) -> Dict[str, Any]:
    """
    多目标评估函数
    
    包含：
    1. Alpha/Epsilon 性能目标
    2. 薄/轻目标 (mass_proxy)
    3. 均匀性目标 (uniformity_penalty)
    4. 综合得分 (score_total)
    
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
    mass_proxy_val = mass_proxy(params)
    uniform_penalty = uniformity_penalty(params)
    
    # 计算综合得分（假设置信度0.5，引用计数0）
    confidence = pred.get('confidence', 0.5)
    total_score = score_total(params, pred, confidence, 0)
    
    return {
        "f1": da,  # Alpha 误差
        "f2": de,  # Epsilon 误差  
        "f3": mass_proxy_val,  # 厚度/质量代理（最小化）
        "f4": uniform_penalty,  # 均匀性惩罚（最小化）
        "pred": pred,
        "mass_proxy": mass_proxy_val,
        "uniformity_penalty": uniform_penalty,
        "score_total": total_score
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

