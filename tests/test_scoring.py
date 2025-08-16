#!/usr/bin/env python3
"""
测试多目标评分函数

验证mass_proxy、uniformity_penalty、score_total函数的正确性
"""

import pytest
import numpy as np
from maowise.optimize.objectives import (
    charge_density, 
    thickness_proxy, 
    mass_proxy, 
    uniformity_penalty, 
    score_total
)


class TestScoringFunctions:
    """评分函数测试类"""
    
    def test_charge_density(self):
        """测试电荷密度计算"""
        params = {
            "current_density_A_dm2": 10.0,
            "duty_cycle_pct": 25.0,
            "time_min": 20.0
        }
        
        expected = 10.0 * (25.0 / 100.0) * 20.0  # 50.0
        result = charge_density(params)
        
        assert result == 50.0
        
    def test_thickness_proxy(self):
        """测试厚度代理值计算"""
        params = {
            "system": "silicate",
            "current_density_A_dm2": 10.0,
            "duty_cycle_pct": 25.0,
            "time_min": 20.0
        }
        
        result = thickness_proxy(params)
        
        # 应该 = 0.015 * 50.0 = 0.75
        assert result == pytest.approx(0.75, rel=1e-3)
        
    def test_mass_proxy_range(self):
        """测试质量代理值范围"""
        # 测试样本1：低电荷密度 (silicate)
        params1 = {
            "system": "silicate",
            "current_density_A_dm2": 2.0,
            "duty_cycle_pct": 10.0,
            "time_min": 5.0
        }
        
        # 测试样本2：高电荷密度 (zirconate)
        params2 = {
            "system": "zirconate",
            "current_density_A_dm2": 20.0,
            "duty_cycle_pct": 50.0,
            "time_min": 30.0
        }
        
        # 测试样本3：中等参数 (silicate)
        params3 = {
            "system": "silicate",
            "current_density_A_dm2": 8.0,
            "duty_cycle_pct": 25.0,
            "time_min": 15.0
        }
        
        result1 = mass_proxy(params1)
        result2 = mass_proxy(params2)
        result3 = mass_proxy(params3)
        
        # 验证范围 [0, 1]
        assert 0 <= result1 <= 1
        assert 0 <= result2 <= 1
        assert 0 <= result3 <= 1
        
        # 验证不同系统和参数产生不同结果
        assert result1 != result2
        assert result1 != result3
        assert result2 != result3
        
        print(f"Mass proxy results: {result1:.3f}, {result2:.3f}, {result3:.3f}")
        
    def test_uniformity_penalty_range(self):
        """测试均匀性惩罚范围"""
        # 测试样本1：在推荐窗口内 (silicate)
        params1 = {
            "system": "silicate",
            "frequency_Hz": 900.0,    # 在 [700, 1100] 范围内
            "duty_cycle_pct": 25.0,   # 在 [20, 35] 范围内
            "waveform": "bipolar"     # 有加分
        }
        
        # 测试样本2：偏离推荐窗口 (zirconate)
        params2 = {
            "system": "zirconate",
            "frequency_Hz": 1500.0,   # 超出 [600, 1000] 范围
            "duty_cycle_pct": 50.0,   # 超出 [18, 32] 范围
            "waveform": "unipolar"    # 无加分
        }
        
        # 测试样本3：边界参数 (silicate)
        params3 = {
            "system": "silicate",
            "frequency_Hz": 700.0,    # 边界值
            "duty_cycle_pct": 35.0,   # 边界值
            "waveform": "unipolar"
        }
        
        result1 = uniformity_penalty(params1)
        result2 = uniformity_penalty(params2)
        result3 = uniformity_penalty(params3)
        
        # 验证范围 [0, 1]
        assert 0 <= result1 <= 1
        assert 0 <= result2 <= 1
        assert 0 <= result3 <= 1
        
        # 验证窗口内的惩罚应该比窗口外的小
        assert result1 < result2
        
        # 验证不同参数产生不同结果（至少有一个不同）
        assert len(set([result1, result2, result3])) > 1, f"所有结果相同: {result1:.3f}, {result2:.3f}, {result3:.3f}"
        
        print(f"Uniformity penalty results: {result1:.3f}, {result2:.3f}, {result3:.3f}")
        
    def test_score_total_discrimination(self):
        """测试综合得分的区分性"""
        # 测试样本1：优秀方案 (低alpha, 高epsilon, 低质量, 低惩罚)
        params1 = {
            "system": "silicate",
            "current_density_A_dm2": 5.0,
            "duty_cycle_pct": 20.0,
            "time_min": 10.0,
            "frequency_Hz": 900.0,
            "waveform": "bipolar"
        }
        pred1 = {"alpha": 0.15, "epsilon": 0.85}
        confidence1 = 0.8
        
        # 测试样本2：一般方案 (中等参数)
        params2 = {
            "system": "zirconate",
            "current_density_A_dm2": 12.0,
            "duty_cycle_pct": 30.0,
            "time_min": 20.0,
            "frequency_Hz": 800.0,
            "waveform": "unipolar"
        }
        pred2 = {"alpha": 0.25, "epsilon": 0.75}
        confidence2 = 0.6
        
        # 测试样本3：差方案 (高alpha, 低epsilon, 高质量, 高惩罚)
        params3 = {
            "system": "zirconate",
            "current_density_A_dm2": 25.0,
            "duty_cycle_pct": 60.0,
            "time_min": 40.0,
            "frequency_Hz": 1500.0,
            "waveform": "unipolar"
        }
        pred3 = {"alpha": 0.35, "epsilon": 0.65}
        confidence3 = 0.3
        
        result1 = score_total(params1, pred1, confidence1, 0)
        result2 = score_total(params2, pred2, confidence2, 0)
        result3 = score_total(params3, pred3, confidence3, 0)
        
        # 验证得分具有区分性（不全相等）
        scores = [result1, result2, result3]
        assert len(set(scores)) > 1, "所有得分相同，缺乏区分性"
        
        # 验证优秀方案得分更高
        assert result1 > result3, "优秀方案得分应该比差方案高"
        
        print(f"Score total results: {result1:.3f}, {result2:.3f}, {result3:.3f}")
        
    def test_edge_cases(self):
        """测试边界情况"""
        # 最小参数
        params_min = {
            "system": "silicate",
            "current_density_A_dm2": 1.0,
            "duty_cycle_pct": 5.0,
            "time_min": 1.0,
            "frequency_Hz": 50.0,
            "waveform": "unipolar"
        }
        
        # 最大参数
        params_max = {
            "system": "zirconate",
            "current_density_A_dm2": 40.0,
            "duty_cycle_pct": 80.0,
            "time_min": 120.0,
            "frequency_Hz": 2000.0,
            "waveform": "bipolar"
        }
        
        # 测试所有函数都能处理边界情况
        assert 0 <= mass_proxy(params_min) <= 1
        assert 0 <= mass_proxy(params_max) <= 1
        assert 0 <= uniformity_penalty(params_min) <= 1
        assert 0 <= uniformity_penalty(params_max) <= 1
        
        pred_min = {"alpha": 0.0, "epsilon": 0.0}
        pred_max = {"alpha": 1.0, "epsilon": 1.0}
        
        score_min = score_total(params_min, pred_min, 0.0, 0)
        score_max = score_total(params_max, pred_max, 1.0, 10)
        
        # 验证得分合理
        assert isinstance(score_min, float)
        assert isinstance(score_max, float)
        assert score_min != score_max
        
    def test_system_differences(self):
        """测试不同体系产生不同结果"""
        # 相同参数，不同体系
        base_params = {
            "current_density_A_dm2": 10.0,
            "duty_cycle_pct": 25.0,
            "time_min": 15.0,
            "frequency_Hz": 800.0,
            "waveform": "unipolar"
        }
        
        params_silicate = {**base_params, "system": "silicate"}
        params_zirconate = {**base_params, "system": "zirconate"}
        
        mass_sil = mass_proxy(params_silicate)
        mass_zir = mass_proxy(params_zirconate)
        
        uniform_sil = uniformity_penalty(params_silicate)
        uniform_zir = uniformity_penalty(params_zirconate)
        
        # 不同体系应该产生不同结果（质量代理必须不同，均匀性可能相同）
        assert mass_sil != mass_zir, "不同体系的质量代理值应该不同"
        # 均匀性惩罚可能在某些参数下相同，但至少质量代理不同表明体系差异
        
        print(f"Silicate vs Zirconate - Mass: {mass_sil:.3f} vs {mass_zir:.3f}")
        print(f"Silicate vs Zirconate - Uniformity: {uniform_sil:.3f} vs {uniform_zir:.3f}")


if __name__ == "__main__":
    # 直接运行测试
    test = TestScoringFunctions()
    
    print("=== 评分函数测试 ===")
    
    print("\n1. 测试电荷密度计算...")
    test.test_charge_density()
    print("✅ 电荷密度计算测试通过")
    
    print("\n2. 测试厚度代理值计算...")
    test.test_thickness_proxy()
    print("✅ 厚度代理值计算测试通过")
    
    print("\n3. 测试质量代理值范围...")
    test.test_mass_proxy_range()
    print("✅ 质量代理值范围测试通过")
    
    print("\n4. 测试均匀性惩罚范围...")
    test.test_uniformity_penalty_range()
    print("✅ 均匀性惩罚范围测试通过")
    
    print("\n5. 测试综合得分区分性...")
    test.test_score_total_discrimination()
    print("✅ 综合得分区分性测试通过")
    
    print("\n6. 测试边界情况...")
    test.test_edge_cases()
    print("✅ 边界情况测试通过")
    
    print("\n7. 测试体系差异...")
    test.test_system_differences()
    print("✅ 体系差异测试通过")
    
    print("\n🎉 所有测试通过！评分函数工作正常。")
