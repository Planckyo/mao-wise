#!/usr/bin/env python3
"""测试GP校正器功能"""

from maowise.models.infer_fwd import get_model

def test_gp_corrector():
    # 测试不同体系的校正器效果
    model = get_model()

    # 测试silicate体系
    print('=== Silicate 体系测试 ===')
    result_sil = model.predict('silicate system MAO 300V 10A/dm2 800Hz 25% 15min KOH+Na2SiO3')
    print(f'Alpha: {result_sil["alpha"]:.3f}, Epsilon: {result_sil["epsilon"]:.3f}')
    print(f'System: {result_sil["system"]}, Corrected: {result_sil["corrected"]}')

    # 测试zirconate体系
    print('\n=== Zirconate 体系测试 ===')
    result_zir = model.predict('zirconate system MAO 350V 12A/dm2 900Hz 30% 20min KOH+K2ZrF6')
    print(f'Alpha: {result_zir["alpha"]:.3f}, Epsilon: {result_zir["epsilon"]:.3f}')
    print(f'System: {result_zir["system"]}, Corrected: {result_zir["corrected"]}')

    # 测试default体系（无校正器）
    print('\n=== Default 体系测试 ===')
    result_def = model.predict('unknown MAO 250V 8A/dm2 600Hz 20% 10min')
    print(f'Alpha: {result_def["alpha"]:.3f}, Epsilon: {result_def["epsilon"]:.3f}')
    print(f'System: {result_def["system"]}, Corrected: {result_def["corrected"]}')

    print(f'\n已加载GP校正器数量: {len(model.gp_correctors)}')
    print(f'已加载等温校准器数量: {len(model.isotonic_calibrators)}')
    print(f'支持的体系: {list(model.gp_correctors.keys())}')
    
    return {
        'gp_correctors_loaded': len(model.gp_correctors),
        'isotonic_calibrators_loaded': len(model.isotonic_calibrators),
        'supported_systems': list(model.gp_correctors.keys()),
        'test_results': {
            'silicate': result_sil,
            'zirconate': result_zir,
            'default': result_def
        }
    }

if __name__ == "__main__":
    test_gp_corrector()
