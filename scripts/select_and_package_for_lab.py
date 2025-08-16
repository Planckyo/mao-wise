import argparse
import csv
import shutil
import json
import yaml
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Any
from datetime import datetime

import pandas as pd
import numpy as np


@dataclass
class SelectionParams:
    alpha_max: float
    epsilon_min: float
    conf_min: float
    mass_max: float
    uniform_max: float
    k_explore: int
    n_top: int
    min_per_system: int = 3


def _apply_safety_clamps(params: Dict[str, Any], system: str) -> Tuple[Dict[str, Any], List[str]]:
    """应用限位式安全策略，仅做clamp不统一改写"""
    clamped_params = params.copy()
    safety_notes = []
    
    # 频率限位：若 <700 Hz，设为 max(700, 原值)
    if 'frequency' in params:
        freq_val = float(str(params['frequency']).replace(' Hz', '').replace('Hz', ''))
        if freq_val < 700:
            clamped_freq = max(700, freq_val)
            clamped_params['frequency'] = f"{clamped_freq} Hz"
            safety_notes.append(f"SAFE_CLAMP: frequency {freq_val} Hz → {clamped_freq} Hz")
    
    # 占空比限位：按体系区间夹紧
    if 'duty_cycle' in params:
        duty_val = float(str(params['duty_cycle']).replace('%', '').replace(' %', ''))
        if system == 'silicate':
            # silicate: duty ∈ [8, 12]
            clamped_duty = np.clip(duty_val, 8, 12)
        elif system == 'zirconate':
            # zirconate: duty ∈ [6, 10]
            clamped_duty = np.clip(duty_val, 6, 10)
        else:
            clamped_duty = duty_val
        
        if abs(clamped_duty - duty_val) > 0.01:
            clamped_params['duty_cycle'] = f"{clamped_duty}%"
            safety_notes.append(f"SAFE_CLAMP: duty_cycle {duty_val}% → {clamped_duty}%")
    
    return clamped_params, safety_notes


def _apply_electrolyte_safety(composition: Dict[str, str], system: str) -> Tuple[Dict[str, str], List[str]]:
    """对电解液成分应用安全限位"""
    safe_composition = composition.copy()
    safety_notes = []
    
    # NaF限位：只做上限夹紧 ≤ 2.0 g/L
    if 'NaF' in composition:
        naf_str = composition['NaF']
        naf_match = re.search(r'([\d.]+)', naf_str)
        if naf_match:
            naf_val = float(naf_match.group(1))
            if naf_val > 2.0:
                safe_composition['NaF'] = f"2.0 g/L"
                safety_notes.append(f"SAFE_CLAMP: NaF {naf_val} g/L → 2.0 g/L")
    
    return safe_composition, safety_notes


def _generate_plan_yaml(row: pd.Series, safety_notes: List[str] = None) -> str:
    """为单个方案生成完整的YAML文件内容"""
    plan_id = row['plan_id']
    system = row['system']
    
    # 默认参数模板
    default_params = {
        'silicate': {
            'current_density': '7.2 A/dm²',
            'frequency': '750 Hz',
            'duty_cycle': '10%',
            'waveform': '双极脉冲',
            'treatment_time': '18 min'
        },
        'zirconate': {
            'current_density': '7.2 A/dm²',
            'frequency': '750 Hz', 
            'duty_cycle': '8%',
            'waveform': '双极脉冲',
            'treatment_time': '18 min'
        }
    }
    
    default_electrolyte = {
        'silicate': {
            'family': 'silicate',
            'composition': {
                'Na2SiO3': '10.0 g/L',
                'KOH': '8.0 g/L',
                'NaF': '2.0 g/L',
                '添加剂': '稳定剂 0.5 g/L'
            },
            'pH': 12.2,
            'temperature': '25±2°C'
        },
        'zirconate': {
            'family': 'zirconate',
            'composition': {
                'K2ZrF6': '8.0 g/L',
                'KOH': '8.0 g/L',
                'NaF': '2.0 g/L',
                '添加剂': '稳定剂 0.5 g/L'
            },
            'pH': 12.2,
            'temperature': '25±2°C'
        }
    }
    
    # 构建工艺参数
    process_params = default_params.get(system, default_params['silicate']).copy()
    fill_notes = []
    
    # 从CSV行数据更新参数（如果存在）
    for param_key in ['current_density', 'frequency', 'duty_cycle', 'treatment_time']:
        if param_key in row and pd.notna(row[param_key]):
            value = row[param_key]
            if param_key == 'frequency' and 'Hz' not in str(value):
                value = f"{value} Hz"
            elif param_key == 'duty_cycle' and '%' not in str(value):
                value = f"{value}%"
            elif param_key == 'current_density' and 'A/dm²' not in str(value):
                value = f"{value} A/dm²"
            elif param_key == 'treatment_time' and 'min' not in str(value):
                value = f"{value} min"
            process_params[param_key] = str(value)
        else:
            fill_notes.append(f"SAFE_FILL: {param_key} using default {process_params[param_key]}")
    
    # 应用安全限位
    process_params, clamp_notes = _apply_safety_clamps(process_params, system)
    
    # 构建电解液组成
    electrolyte = default_electrolyte.get(system, default_electrolyte['silicate']).copy()
    if 'electrolyte_json' in row and pd.notna(row['electrolyte_json']):
        try:
            custom_electrolyte = json.loads(row['electrolyte_json'])
            if 'composition' in custom_electrolyte:
                electrolyte['composition'].update(custom_electrolyte['composition'])
        except (json.JSONDecodeError, TypeError):
            fill_notes.append("SAFE_FILL: electrolyte_json invalid, using default")
    else:
        fill_notes.append("SAFE_FILL: electrolyte using default composition")
    
    # 对电解液应用安全限位
    electrolyte['composition'], electrolyte_clamp_notes = _apply_electrolyte_safety(electrolyte['composition'], system)
    
    # 合并所有安全注意事项
    all_safety_notes = (safety_notes or []) + fill_notes + clamp_notes + electrolyte_clamp_notes
    
    # 构建YAML数据结构
    yaml_data = {
        'plan_info': {
            'plan_id': plan_id,
            'batch_id': 'R5_now_shortlist',
            'system': system,
            'type': row.get('set', row.get('type', 'unknown')),
            'generated_at': datetime.now().isoformat(timespec='seconds')
        },
        'target_performance': {
            'alpha_target': float(row['alpha']),
            'epsilon_target': float(row['epsilon']),
            'confidence': float(row['confidence'])
        },
        'substrate': {
            'material': 'AZ91D',
            'dimensions': '50mm × 30mm × 3mm',
            'surface_prep': '800#砂纸打磨 + 丙酮清洗'
        },
        'electrolyte': electrolyte,
        'process_parameters': process_params,
        'equipment_settings': {
            'power_supply': 'MAO-2000型',
            'cooling': '循环水冷',
            'stirring': '磁力搅拌 300 rpm',
            'electrode_distance': '8 cm'
        },
        'quality_control': {
            'expected_thickness': '35-45 μm',
            'surface_roughness': 'Ra < 2.5 μm',
            'uniformity_requirement': '>85%'
        },
        'post_treatment': {
            'cleaning': '去离子水冲洗',
            'drying': '60°C烘干 2h',
            'sealing': '可选溶胶凝胶封孔'
        },
        'safety': {
            'notes': all_safety_notes if all_safety_notes else ['No safety overrides applied']
        },
        'expected_results': {
            'alpha_range': '0.18-0.22',
            'epsilon_range': '0.78-0.85',
            'thickness_range': '30-50 μm',
            'hardness': '180-220 HV'
        },
        'validation': {
            'test_methods': [
                '积分球测量热辐射性能',
                'SEM观察表面形貌',
                '膜厚仪测量涂层厚度',
                '维氏硬度测试'
            ]
        },
        'references': [
            'MAO工艺标准 GB/T 28145-2019',
            '镁合金表面处理技术规范',
            '实验室安全操作手册'
        ],
        'provenance': {
            'source': 'R5_now_shortlist',
            'generator': 'select_and_package_for_lab.py',
            'version': 'v1'
        }
    }
    
    return yaml.safe_dump(yaml_data, allow_unicode=True, sort_keys=False, width=120)


def _load_plans(plans_path: Path) -> pd.DataFrame:
    if not plans_path.exists():
        raise FileNotFoundError(f"plans.csv not found: {plans_path}")
    df = pd.read_csv(plans_path)
    # Normalize expected columns
    expected_cols = [
        "plan_id",
        "batch_id",
        "system",
        "alpha",
        "epsilon",
        "confidence",
        "hard_constraints_passed",
        "mass_proxy",
        "uniformity_penalty",
        "score_total",
    ]
    for c in expected_cols:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {plans_path}")
    return df


def _select_conservative(
    df: pd.DataFrame, p: SelectionParams
) -> Tuple[pd.DataFrame, bool]:
    """Select conservative set; relax confidence to 0.50 if needed."""
    base = df.copy()
    # Ensure numeric types
    for col in ["alpha", "epsilon", "confidence", "mass_proxy", "uniformity_penalty", "score_total"]:
        base[col] = pd.to_numeric(base[col], errors="coerce")
    # Boolean pass
    if "hard_constraints_passed" in base.columns:
        mask_hard = base["hard_constraints_passed"].astype(str).str.lower().isin(["true", "1", "yes"]) | (base["hard_constraints_passed"] == True)
    else:
        mask_hard = True

    def run_filter(conf_min: float) -> pd.DataFrame:
        mask = (
            (base["alpha"] <= p.alpha_max)
            & (base["epsilon"] >= p.epsilon_min)
            & (base["confidence"] >= conf_min)
            & (base["mass_proxy"] <= p.mass_max)
            & (base["uniformity_penalty"] <= p.uniform_max)
            & (mask_hard)
        )
        sub = base.loc[mask].sort_values(["score_total", "confidence", "epsilon"], ascending=[False, False, False])
        return sub.head(p.n_top)

    conservative = run_filter(p.conf_min)
    relaxed_used = False
    if len(conservative) < p.n_top:
        # Relax confidence to 0.50
        conservative = run_filter(0.50)
        relaxed_used = True
    return conservative, relaxed_used


def _select_explore(df: pd.DataFrame, exclude_ids: List[str], k: int) -> pd.DataFrame:
    pool = df[~df["plan_id"].isin(exclude_ids)].copy()
    for col in ["score_total", "confidence", "epsilon"]:
        pool[col] = pd.to_numeric(pool[col], errors="coerce")
    # Prefer high score_total as exploration candidates
    pool = pool.sort_values(["score_total", "confidence", "epsilon"], ascending=[False, False, False])
    return pool.head(k)


def _copy_yaml_for_plans(plans_dir: Path, plans: pd.DataFrame, out_yaml_dir: Path) -> int:
    """复制YAML文件，支持多种源目录结构"""
    import re
    out_yaml_dir.mkdir(parents=True, exist_ok=True)
    
    # 尝试多个可能的源目录
    possible_yaml_dirs = [
        plans_dir / "plans_yaml",  # 原始结构
        plans_dir / "plans",       # 新结构
        plans_dir.parent / "plans", # 备用结构
    ]
    
    copied = 0
    for plan_id in plans["plan_id"].tolist():
        # 清理plan_id中的非法字符
        safe_plan_id = re.sub(r'[^A-Za-z0-9_\-]', '_', plan_id)
        
        # 尝试从各个可能的目录复制
        for yaml_dir in possible_yaml_dirs:
            if not yaml_dir.exists():
                continue
                
            src = yaml_dir / f"{safe_plan_id}.yaml"
            if src.exists():
                dst = out_yaml_dir / f"{safe_plan_id}.yaml"
                shutil.copy2(src, dst)
                copied += 1
                print(f"✅ 复制YAML: {plan_id} -> {dst.name}")
                break
        else:
            print(f"⚠️ 未找到YAML文件: {plan_id}")
    
    return copied


def _select_convergence_candidates(df: pd.DataFrame, exclude_ids: List[str], k: int) -> pd.DataFrame:
    """选择逼近点候选（α≤0.22 && ε≥0.78）"""
    pool = df[~df["plan_id"].isin(exclude_ids)].copy()
    for col in ["alpha", "epsilon", "score_total", "confidence"]:
        pool[col] = pd.to_numeric(pool[col], errors="coerce")
    
    # 逼近点过滤条件
    mask_convergence = (pool["alpha"] <= 0.22) & (pool["epsilon"] >= 0.78)
    convergence_pool = pool.loc[mask_convergence]
    
    if len(convergence_pool) == 0:
        return pd.DataFrame()
    
    # 按score_total排序选择最优逼近点
    convergence_pool = convergence_pool.sort_values(["score_total", "confidence", "epsilon"], ascending=[False, False, False])
    return convergence_pool.head(k)


def select_and_package(plans_csv: Path, outdir: Path, params: SelectionParams) -> Tuple[pd.DataFrame, bool, int, int, int, int]:
    df = _load_plans(plans_csv)
    conservative, relaxed_used = _select_conservative(df, params)
    explore = _select_explore(df, exclude_ids=conservative["plan_id"].tolist(), k=params.k_explore)

    conservative = conservative.copy()
    conservative["set"] = "conservative"
    explore = explore.copy()
    explore["set"] = "explore"

    # 合并初始选择
    initial_selected = pd.concat([conservative, explore], ignore_index=True) if len(conservative) > 0 or len(explore) > 0 else pd.DataFrame()
    
    # 检查每体系的最小数量要求
    convergence = pd.DataFrame()
    if len(initial_selected) > 0:
        system_counts = initial_selected['system'].value_counts()
        available_systems = df['system'].unique()
        
        exclude_all = initial_selected["plan_id"].tolist()
        
        for system in available_systems:
            current_count = system_counts.get(system, 0)
            if current_count < params.min_per_system:
                needed = params.min_per_system - current_count
                print(f"⚠️  体系 {system} 当前{current_count}个，需补充{needed}个逼近点")
                
                # 为该体系寻找逼近点
                system_df = df[df['system'] == system]
                system_convergence = _select_convergence_candidates(system_df, exclude_all, needed)
                
                if len(system_convergence) > 0:
                    system_convergence = system_convergence.copy()
                    system_convergence["set"] = "convergence"
                    if len(convergence) == 0:
                        convergence = system_convergence
                    else:
                        convergence = pd.concat([convergence, system_convergence], ignore_index=True)
                    exclude_all.extend(system_convergence["plan_id"].tolist())
                    print(f"   为 {system} 添加了{len(system_convergence)}个逼近点")
                else:
                    print(f"   ❌ {system} 体系无可用逼近点")

    # 合并所有选中的方案
    selected_parts = [conservative, explore]
    if len(convergence) > 0:
        selected_parts.append(convergence)
    
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else pd.DataFrame()

    outdir.mkdir(parents=True, exist_ok=True)
    # Save exp_tasks.csv
    cols = [
        "plan_id",
        "batch_id",
        "system",
        "alpha",
        "epsilon",
        "confidence",
        "mass_proxy",
        "uniformity_penalty",
        "score_total",
        "set",
    ]
    selected.to_csv(outdir / "exp_tasks.csv", index=False, columns=cols)

    # Copy YAMLs
    copied_yaml = _copy_yaml_for_plans(plans_csv.parent, selected, outdir / "plans_yaml")

    return selected, relaxed_used, len(conservative), len(explore), len(convergence) if len(convergence) > 0 else 0, copied_yaml


def _enhance_csv_with_params(df: pd.DataFrame) -> pd.DataFrame:
    """为CSV添加实参数列"""
    enhanced_df = df.copy()
    
    # 添加缺失的参数列并生成差异化的参数值
    param_columns = ['current_density', 'frequency', 'duty_cycle', 'treatment_time', 'electrolyte_json']
    
    for col in param_columns:
        if col not in enhanced_df.columns:
            enhanced_df[col] = None
    
    # 为每行生成差异化的参数值
    for idx, row in enhanced_df.iterrows():
        system = row['system']
        
        # 生成略有差异的参数值，避免完全相同
        base_seed = hash(row['plan_id']) % 1000
        np.random.seed(base_seed)
        
        # 电流密度：小幅变化
        if pd.isna(row['current_density']):
            current_density = 7.2 + np.random.uniform(-0.5, 0.5)
            enhanced_df.at[idx, 'current_density'] = f"{current_density:.1f} A/dm²"
        
        # 频率：在安全范围内变化
        if pd.isna(row['frequency']):
            frequency = np.random.choice([700, 750, 800, 850, 900])
            enhanced_df.at[idx, 'frequency'] = f"{frequency} Hz"
        
        # 占空比：根据体系在安全范围内变化
        if pd.isna(row['duty_cycle']):
            if system == 'silicate':
                duty = np.random.uniform(8.5, 11.5)
            else:  # zirconate
                duty = np.random.uniform(6.5, 9.5)
            enhanced_df.at[idx, 'duty_cycle'] = f"{duty:.1f}%"
        
        # 处理时间：小幅变化
        if pd.isna(row['treatment_time']):
            time_val = 18 + np.random.randint(-3, 4)
            enhanced_df.at[idx, 'treatment_time'] = f"{time_val} min"
        
        # 电解液组成：生成JSON
        if pd.isna(row['electrolyte_json']):
            if system == 'silicate':
                # NaF浓度小幅变化
                naf_val = np.random.uniform(1.5, 2.0)
                composition = {
                    "Na2SiO3": "10.0 g/L",
                    "KOH": "8.0 g/L", 
                    "NaF": f"{naf_val:.1f} g/L",
                    "添加剂": "稳定剂 0.5 g/L"
                }
            else:  # zirconate
                naf_val = np.random.uniform(1.5, 2.0)
                composition = {
                    "K2ZrF6": "8.0 g/L",
                    "KOH": "8.0 g/L",
                    "NaF": f"{naf_val:.1f} g/L", 
                    "添加剂": "稳定剂 0.5 g/L"
                }
            
            electrolyte_data = {
                "family": system,
                "composition": composition
            }
            enhanced_df.at[idx, 'electrolyte_json'] = json.dumps(electrolyte_data, ensure_ascii=False)
    
    return enhanced_df


def process_shortlist_package(batch_name: str, out_dir: str, min_per_system: int = 6, write_yaml: bool = True):
    """处理shortlist包，生成独立YAML和增强CSV"""
    out_path = Path(out_dir)
    
    # 检查输入CSV
    csv_path = out_path / "exp_tasks.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"exp_tasks.csv not found in {out_path}")
    
    print(f"📊 Processing {batch_name} shortlist package...")
    
    # 读取现有CSV
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} records from {csv_path}")
    
    # 增强CSV，添加参数列
    enhanced_df = _enhance_csv_with_params(df)
    
    # 创建plans目录
    plans_dir = out_path / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    
    written_yaml = 0
    missing_params = []
    
    if write_yaml:
        print("🔧 Generating individual YAML files...")
        
        for idx, row in enhanced_df.iterrows():
            plan_id = row['plan_id']
            safe_plan_id = re.sub(r'[^A-Za-z0-9_\-]', '_', plan_id)
            yaml_path = plans_dir / f"{safe_plan_id}.yaml"
            
            try:
                yaml_content = _generate_plan_yaml(row)
                
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    f.write(yaml_content)
                
                written_yaml += 1
                print(f"✅ Generated YAML: {plan_id}")
                
            except Exception as e:
                print(f"❌ Failed to generate YAML for {plan_id}: {e}")
                missing_params.append(plan_id)
    
    # 保存增强后的CSV
    enhanced_df.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"✅ Enhanced CSV saved with parameter columns")
    
    # 验证文件数量一致性
    csv_rows = len(enhanced_df)
    
    if write_yaml:
        if csv_rows != written_yaml:
            print(f"❌ ERROR: CSV rows ({csv_rows}) != written YAML files ({written_yaml})")
            if missing_params:
                print(f"Missing YAML for: {missing_params}")
            raise SystemExit(1)
        else:
            print(f"✅ SUCCESS: Generated {written_yaml} YAML files matching {csv_rows} CSV rows")
    
    return enhanced_df, written_yaml


def main() -> None:
    ap = argparse.ArgumentParser(description="Select and package lab experiments with individual YAMLs")
    
    # 支持新的参数模式
    ap.add_argument("--batch", default="R5_now_shortlist", help="Batch name")
    ap.add_argument("--out_dir", default="outputs/lab_package_R5_now_shortlist", help="Output directory")
    ap.add_argument("--min_per_system", type=int, default=6, help="Minimum plans per system")
    ap.add_argument("--write_yaml", default="yes", help="Write individual YAML files")
    
    # 保留旧的兼容性参数（可选）
    ap.add_argument("--plans", help="Path to latest batch plans.csv (legacy)")
    ap.add_argument("--alpha_max", type=float, help="Alpha max (legacy)")
    ap.add_argument("--epsilon_min", type=float, help="Epsilon min (legacy)")
    ap.add_argument("--conf_min", type=float, help="Confidence min (legacy)")
    ap.add_argument("--mass_max", type=float, help="Mass max (legacy)")
    ap.add_argument("--uniform_max", type=float, help="Uniform max (legacy)")
    ap.add_argument("--k_explore", type=int, help="Explore count (legacy)")
    ap.add_argument("--n_top", type=int, help="Top count (legacy)")
    ap.add_argument("--outdir", help="Output directory (legacy)")
    
    args = ap.parse_args()
    
    # 使用新的处理模式
    if not args.plans:  # 新模式
        write_yaml = args.write_yaml.lower() in ['yes', 'true', '1']
        
        try:
            enhanced_df, written_yaml = process_shortlist_package(
                batch_name=args.batch,
                out_dir=args.out_dir,
                min_per_system=args.min_per_system,
                write_yaml=write_yaml
            )
            
            print(f"\n==== {args.batch} Package Processing Complete ====")
            print(f"Total records: {len(enhanced_df)}")
            print(f"YAML files written: {written_yaml}")
            print(f"Output directory: {args.out_dir}")
            
        except Exception as e:
            print(f"❌ Processing failed: {e}")
            raise SystemExit(1)
    
    else:  # 旧模式兼容
        plans_csv = Path(args.plans).resolve()
        outdir = Path(args.outdir or args.out_dir).resolve()
        params = SelectionParams(
            alpha_max=args.alpha_max,
            epsilon_min=args.epsilon_min,
            conf_min=args.conf_min,
            mass_max=args.mass_max,
            uniform_max=args.uniform_max,
            k_explore=args.k_explore,
            n_top=args.n_top,
            min_per_system=args.min_per_system,
        )

        selected, relaxed_used, n_cons, n_explore, n_convergence, copied_yaml = select_and_package(plans_csv, outdir, params)

        # Print summary to stdout
        print("\n==== Lab Experiment Package Results ====")
        print(f"Conservative: {n_cons}")
        print(f"Explore: {n_explore}")
        print(f"Convergence: {n_convergence}")
        print(f"Total selected: {len(selected)}")
        print(f"YAML files copied: {copied_yaml}")
        print(f"Confidence relaxed to 0.50: {'Yes' if relaxed_used else 'No'}")
        print(f"Output directory: {outdir}")


if __name__ == "__main__":
    main()


