"""
MAO-Wise 数据摄取工具模块
提供通用的数据处理、解析和验证功能
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataValidator:
    """数据验证器"""
    
    @staticmethod
    def validate_system(system: str) -> bool:
        """验证体系类型"""
        valid_systems = {'silicate', 'zirconate', 'dual_step'}
        return system in valid_systems
    
    @staticmethod
    def validate_step(step: str) -> bool:
        """验证步骤类型"""
        valid_steps = {'single', 'silicate', 'zirconate'}
        return step in valid_steps
    
    @staticmethod
    def validate_numeric_range(value: float, min_val: float, max_val: float) -> bool:
        """验证数值范围"""
        return min_val <= value <= max_val
    
    @staticmethod
    def validate_alpha(alpha: float) -> bool:
        """验证alpha值"""
        return DataValidator.validate_numeric_range(alpha, 0.0, 1.0)
    
    @staticmethod
    def validate_epsilon(epsilon: float) -> bool:
        """验证epsilon值"""
        return DataValidator.validate_numeric_range(epsilon, 0.0, 1.0)
    
    @staticmethod
    def validate_thickness(thickness: float) -> bool:
        """验证厚度值（微米）"""
        return DataValidator.validate_numeric_range(thickness, 0.1, 200.0)
    
    @staticmethod
    def validate_time(time_min: float) -> bool:
        """验证时间值（分钟）"""
        return DataValidator.validate_numeric_range(time_min, 0.1, 120.0)
    
    @staticmethod
    def validate_frequency(freq_hz: float) -> bool:
        """验证频率值（Hz）"""
        return DataValidator.validate_numeric_range(freq_hz, 100, 2000)
    
    @staticmethod
    def validate_duty_cycle(duty_pct: float) -> bool:
        """验证占空比（%）"""
        return DataValidator.validate_numeric_range(duty_pct, 1, 99)


class TextExtractor:
    """文本提取器"""
    
    # 预定义的数值提取模式
    PATTERNS = {
        'alpha': [
            r'α[^\d]*(\d+\.?\d*)',
            r'alpha[^\d]*(\d+\.?\d*)',
            r'吸收率[^\d]*(\d+\.?\d*)',
            r'α值[^\d]*(\d+\.?\d*)'
        ],
        'epsilon': [
            r'ε[^\d]*(\d+\.?\d*)',
            r'epsilon[^\d]*(\d+\.?\d*)',
            r'发射率[^\d]*(\d+\.?\d*)',
            r'ε值[^\d]*(\d+\.?\d*)',
            r'emissivity[^\d]*(\d+\.?\d*)'
        ],
        'thickness': [
            r'(?:厚度|thickness)[^\d]*(\d+\.?\d*)',
            r'膜厚[^\d]*(\d+\.?\d*)',
            r'coating\s+thickness[^\d]*(\d+\.?\d*)'
        ],
        'time': [
            r'(?:时间|time)[^\d]*(\d+\.?\d*)',
            r'处理时间[^\d]*(\d+\.?\d*)',
            r'氧化时间[^\d]*(\d+\.?\d*)',
            r'oxidation\s+time[^\d]*(\d+\.?\d*)'
        ],
        'frequency': [
            r'(?:频率|frequency)[^\d]*(\d+\.?\d*)',
            r'freq[^\d]*(\d+\.?\d*)',
            r'振荡频率[^\d]*(\d+\.?\d*)'
        ],
        'current': [
            r'(?:电流|current)[^\d]*(\d+\.?\d*)',
            r'电流密度[^\d]*(\d+\.?\d*)',
            r'current\s+density[^\d]*(\d+\.?\d*)'
        ],
        'duty': [
            r'(?:占空比|duty)[^\d]*(\d+\.?\d*)',
            r'duty\s+cycle[^\d]*(\d+\.?\d*)',
            r'脉冲占空比[^\d]*(\d+\.?\d*)'
        ],
        'voltage': [
            r'(?:电压|voltage)[^\d]*(\d+\.?\d*)',
            r'工作电压[^\d]*(\d+\.?\d*)'
        ]
    }
    
    # 系统类型识别模式
    SYSTEM_PATTERNS = {
        'silicate': ['silicate', '硅酸盐', 'Na2SiO3', '钠硅酸盐'],
        'zirconate': ['zirconate', '锆酸盐', 'K2ZrF6', '氟锆酸钾'],
        'dual_step': ['dual', '双步', 'two-step', '两步']
    }
    
    @classmethod
    def extract_numeric_values(cls, text: str, pattern_key: str) -> List[float]:
        """从文本中提取指定类型的数值"""
        if pattern_key not in cls.PATTERNS:
            return []
        
        values = []
        for pattern in cls.PATTERNS[pattern_key]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    value = float(match)
                    values.append(value)
                except ValueError:
                    continue
        
        return values
    
    @classmethod
    def identify_system_type(cls, text: str) -> Optional[str]:
        """从文本中识别体系类型"""
        text_lower = text.lower()
        
        for system, keywords in cls.SYSTEM_PATTERNS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return system
        
        return None
    
    @classmethod
    def extract_waveform(cls, text: str) -> str:
        """从文本中提取波形类型"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['bipolar', '双极', '双向']):
            return 'bipolar'
        elif any(word in text_lower for word in ['pulsed', '脉冲', 'pulse']):
            return 'pulsed'
        else:
            return 'unipolar'
    
    @classmethod
    def extract_notes_keywords(cls, text: str) -> List[str]:
        """从文本中提取关键的问题描述"""
        keywords = []
        
        # 定义问题关键词
        problem_keywords = {
            '不均匀': ['不均匀', 'nonuniform', 'uneven'],
            '粉化': ['粉化', 'powdering', 'powder'],
            '开裂': ['开裂', 'cracking', 'crack'],
            '多孔': ['多孔', 'porous', 'porosity'],
            '剥离': ['剥离', 'peeling', 'delamination'],
            '氧化': ['过氧化', 'over-oxidation', 'excessive'],
            '烧蚀': ['烧蚀', 'ablation', 'burn']
        }
        
        text_lower = text.lower()
        for category, terms in problem_keywords.items():
            for term in terms:
                if term.lower() in text_lower:
                    keywords.append(category)
                    break
        
        return keywords


class ElectrolyteProcessor:
    """电解液处理器"""
    
    # 预定义的电解液配方模板
    RECIPE_TEMPLATES = {
        'silicate': {
            'family': 'silicate',
            'recipe': {
                'Na2SiO3': 10,
                'KOH': 8,
                'NaF': 8
            }
        },
        'zirconate': {
            'family': 'zirconate',
            'recipe': {
                'K2ZrF6': 12,
                'KOH': 6,
                'NaF': 4
            }
        },
        'dual_silicate': {
            'family': 'silicate',
            'recipe': {
                'Na2SiO3': 8,
                'KOH': 6,
                'NaF': 6
            }
        },
        'dual_zirconate': {
            'family': 'zirconate',
            'recipe': {
                'K2ZrF6': 10,
                'KOH': 5,
                'Y2O3': 2
            }
        }
    }
    
    @classmethod
    def generate_electrolyte_json(cls, system: str, step: str = 'single') -> str:
        """根据体系和步骤生成电解液JSON"""
        if system == 'dual_step':
            if step == 'silicate':
                template = cls.RECIPE_TEMPLATES['dual_silicate']
            else:
                template = cls.RECIPE_TEMPLATES['dual_zirconate']
        else:
            template = cls.RECIPE_TEMPLATES.get(system, cls.RECIPE_TEMPLATES['silicate'])
        
        return json.dumps(template)
    
    @classmethod
    def parse_electrolyte_from_text(cls, text: str) -> Optional[Dict[str, Any]]:
        """从文本中解析电解液配方"""
        # 查找化学成分模式
        component_patterns = [
            r'(Na2SiO3|硅酸钠)[^\d]*(\d+\.?\d*)',
            r'(K2ZrF6|氟锆酸钾)[^\d]*(\d+\.?\d*)',
            r'(KOH|氢氧化钾)[^\d]*(\d+\.?\d*)',
            r'(NaF|氟化钠)[^\d]*(\d+\.?\d*)',
            r'(Y2O3|氧化钇)[^\d]*(\d+\.?\d*)'
        ]
        
        recipe = {}
        for pattern in component_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                component = match[0]
                try:
                    concentration = float(match[1])
                    # 标准化组分名称
                    if component.lower() in ['na2sio3', '硅酸钠']:
                        recipe['Na2SiO3'] = concentration
                    elif component.lower() in ['k2zrf6', '氟锆酸钾']:
                        recipe['K2ZrF6'] = concentration
                    elif component.lower() in ['koh', '氢氧化钾']:
                        recipe['KOH'] = concentration
                    elif component.lower() in ['naf', '氟化钠']:
                        recipe['NaF'] = concentration
                    elif component.lower() in ['y2o3', '氧化钇']:
                        recipe['Y2O3'] = concentration
                except ValueError:
                    continue
        
        if recipe:
            # 判断电解液族
            if 'Na2SiO3' in recipe:
                family = 'silicate'
            elif 'K2ZrF6' in recipe:
                family = 'zirconate'
            else:
                family = 'unknown'
            
            return {
                'family': family,
                'recipe': recipe
            }
        
        return None


class RecordEnhancer:
    """记录增强器"""
    
    @staticmethod
    def add_default_fields(record: Dict[str, Any]) -> Dict[str, Any]:
        """为记录添加默认字段"""
        defaults = {
            'substrate_alloy': 'AZ91D',
            'voltage_V': 250,
            'temp_C': 25,
            'pH': 12.0,
            'post_treatment': 'none',
            'hardness_HV': 185,
            'roughness_Ra_um': 2.0,
            'corrosion_rate_mmpy': 0.04,
            'mode': 'CC',
            'waveform': 'unipolar',
            'reviewer': 'auto_parser',
            'timestamp': datetime.now().isoformat()
        }
        
        enhanced_record = record.copy()
        for key, value in defaults.items():
            if key not in enhanced_record:
                enhanced_record[key] = value
        
        return enhanced_record
    
    @staticmethod
    def validate_and_fix_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """验证并修复记录，返回修复后的记录和警告列表"""
        fixed_record = record.copy()
        warnings = []
        
        # 验证必需字段
        required_fields = ['system', 'measured_alpha', 'measured_epsilon']
        for field in required_fields:
            if field not in fixed_record:
                warnings.append(f"缺少必需字段: {field}")
        
        # 验证数值范围并修复
        if 'measured_alpha' in fixed_record:
            alpha = fixed_record['measured_alpha']
            if not DataValidator.validate_alpha(alpha):
                fixed_record['measured_alpha'] = np.clip(alpha, 0.0, 1.0)
                warnings.append(f"Alpha值超出范围，已修正: {alpha} -> {fixed_record['measured_alpha']}")
        
        if 'measured_epsilon' in fixed_record:
            epsilon = fixed_record['measured_epsilon']
            if not DataValidator.validate_epsilon(epsilon):
                fixed_record['measured_epsilon'] = np.clip(epsilon, 0.0, 1.0)
                warnings.append(f"Epsilon值超出范围，已修正: {epsilon} -> {fixed_record['measured_epsilon']}")
        
        if 'thickness_um' in fixed_record:
            thickness = fixed_record['thickness_um']
            if not DataValidator.validate_thickness(thickness):
                fixed_record['thickness_um'] = np.clip(thickness, 0.1, 200.0)
                warnings.append(f"厚度值超出范围，已修正: {thickness} -> {fixed_record['thickness_um']}")
        
        if 'time_min' in fixed_record:
            time_val = fixed_record['time_min']
            if not DataValidator.validate_time(time_val):
                fixed_record['time_min'] = np.clip(time_val, 0.1, 120.0)
                warnings.append(f"时间值超出范围，已修正: {time_val} -> {fixed_record['time_min']}")
        
        # 验证系统类型
        if 'system' in fixed_record:
            if not DataValidator.validate_system(fixed_record['system']):
                fixed_record['system'] = 'silicate'  # 默认值
                warnings.append(f"无效的系统类型，已设为默认值: silicate")
        
        return fixed_record, warnings


def create_experiment_id(base_name: str, index: int, date_str: str) -> str:
    """创建实验ID"""
    return f"{base_name}_{index:03d}_{date_str}"


def create_batch_id(source: str, date_str: str) -> str:
    """创建批次ID"""
    return f"{source}_{date_str}"


def extract_date_from_filename(filename: str) -> str:
    """从文件名中提取日期"""
    # 尝试提取YYYYMMDD格式的日期
    date_pattern = r'(\d{8})'
    match = re.search(date_pattern, filename)
    if match:
        return match.group(1)
    else:
        return datetime.now().strftime("%Y%m%d")


def safe_float_conversion(value: Any, default: float = 0.0) -> float:
    """安全的浮点数转换"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int_conversion(value: Any, default: int = 0) -> int:
    """安全的整数转换"""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default
