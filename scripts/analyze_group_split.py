#!/usr/bin/env python3
"""
防泄漏评估结果对比分析
生成LOPO vs TimeSplit的关键指标对比表和总览结论
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional

def load_evaluation_results() -> tuple[Optional[Dict], Optional[Dict]]:
    """加载LOPO和TimeSplit评估结果"""
    lopo_path = Path("reports/fwd_eval_lopo.json")
    timesplit_path = Path("reports/fwd_eval_timesplit.json")
    
    lopo_results = None
    timesplit_results = None
    
    if lopo_path.exists():
        with open(lopo_path, 'r', encoding='utf-8') as f:
            lopo_results = json.load(f)
        print(f"✅ 加载LOPO评估结果: {lopo_path}")
    else:
        print(f"❌ LOPO评估结果不存在: {lopo_path}")
    
    if timesplit_path.exists():
        with open(timesplit_path, 'r', encoding='utf-8') as f:
            timesplit_results = json.load(f)
        print(f"✅ 加载TimeSplit评估结果: {timesplit_path}")
    else:
        print(f"❌ TimeSplit评估结果不存在: {timesplit_path}")
    
    return lopo_results, timesplit_results


def create_comparison_table(lopo_results: Dict, timesplit_results: Dict) -> pd.DataFrame:
    """创建关键指标对比表"""
    comparison_data = []
    
    # 获取所有体系
    all_systems = set()
    if lopo_results and 'systems' in lopo_results:
        all_systems.update(lopo_results['systems'].keys())
    if timesplit_results and 'systems' in timesplit_results:
        all_systems.update(timesplit_results['systems'].keys())
    
    for system in sorted(all_systems):
        lopo_sys = lopo_results['systems'].get(system, {}) if lopo_results else {}
        time_sys = timesplit_results['systems'].get(system, {}) if timesplit_results else {}
        
        # LOPO行
        comparison_data.append({
            '体系': system,
            '评估方法': 'LOPO',
            'α_MAE': f"{lopo_sys.get('alpha_mae', 0):.4f}",
            'ε_MAE': f"{lopo_sys.get('epsilon_mae', 0):.4f}",
            'α_命中率(±0.03)': f"{lopo_sys.get('alpha_hit_pm_0.03', 0):.1%}",
            'ε_命中率(±0.03)': f"{lopo_sys.get('epsilon_hit_pm_0.03', 0):.1%}",
            '样本数': lopo_sys.get('n_samples', 0)
        })
        
        # TimeSplit行
        comparison_data.append({
            '体系': system,
            '评估方法': 'TimeSplit',
            'α_MAE': f"{time_sys.get('alpha_mae', 0):.4f}",
            'ε_MAE': f"{time_sys.get('epsilon_mae', 0):.4f}",
            'α_命中率(±0.03)': f"{time_sys.get('alpha_hit_pm_0.03', 0):.1%}",
            'ε_命中率(±0.03)': f"{time_sys.get('epsilon_hit_pm_0.03', 0):.1%}",
            '样本数': time_sys.get('n_samples', 0)
        })
    
    return pd.DataFrame(comparison_data)


def generate_summary_analysis(lopo_results: Dict, timesplit_results: Dict) -> str:
    """生成总览结论"""
    summary_lines = []
    
    # 计算平均指标
    if lopo_results and lopo_results.get('systems'):
        lopo_systems = lopo_results['systems']
        lopo_alpha_mae_avg = np.mean([sys['alpha_mae'] for sys in lopo_systems.values()])
        lopo_epsilon_mae_avg = np.mean([sys['epsilon_mae'] for sys in lopo_systems.values()])
        lopo_alpha_hit_avg = np.mean([sys['alpha_hit_pm_0.03'] for sys in lopo_systems.values()])
        lopo_epsilon_hit_avg = np.mean([sys['epsilon_hit_pm_0.03'] for sys in lopo_systems.values()])
    else:
        lopo_alpha_mae_avg = lopo_epsilon_mae_avg = lopo_alpha_hit_avg = lopo_epsilon_hit_avg = 0
    
    if timesplit_results and timesplit_results.get('systems'):
        time_systems = timesplit_results['systems']
        time_alpha_mae_avg = np.mean([sys['alpha_mae'] for sys in time_systems.values()])
        time_epsilon_mae_avg = np.mean([sys['epsilon_mae'] for sys in time_systems.values()])
        time_alpha_hit_avg = np.mean([sys['alpha_hit_pm_0.03'] for sys in time_systems.values()])
        time_epsilon_hit_avg = np.mean([sys['epsilon_hit_pm_0.03'] for sys in time_systems.values()])
    else:
        time_alpha_mae_avg = time_epsilon_mae_avg = time_alpha_hit_avg = time_epsilon_hit_avg = 0
    
    summary_lines.extend([
        "📈 防泄漏评估总览结论",
        "=" * 60,
        "",
        f"✅ LOPO 评估 (Leave-One-Paper-Out):",
        f"   - 交叉验证折数: {lopo_results.get('n_folds', 0) if lopo_results else 0} 个文献来源",
        f"   - α预测平均MAE: {lopo_alpha_mae_avg:.4f}",
        f"   - ε预测平均MAE: {lopo_epsilon_mae_avg:.4f}",
        f"   - α平均命中率: {lopo_alpha_hit_avg:.1%}",
        f"   - ε平均命中率: {lopo_epsilon_hit_avg:.1%}",
        "",
        f"✅ TimeSplit 评估 (时间分割):",
        f"   - 训练集大小: {timesplit_results.get('train_size', 0) if timesplit_results else 0} 条",
        f"   - 测试集大小: {timesplit_results.get('test_size', 0) if timesplit_results else 0} 条",
        f"   - α预测平均MAE: {time_alpha_mae_avg:.4f}",
        f"   - ε预测平均MAE: {time_epsilon_mae_avg:.4f}",
        f"   - α平均命中率: {time_alpha_hit_avg:.1%}",
        f"   - ε平均命中率: {time_epsilon_hit_avg:.1%}",
        "",
        f"🔍 关键发现:",
    ])
    
    # 对比分析
    if lopo_alpha_mae_avg > 0 and time_alpha_mae_avg > 0:
        alpha_comparison = "LOPO更优" if lopo_alpha_mae_avg < time_alpha_mae_avg else "TimeSplit更优"
        epsilon_comparison = "LOPO更优" if lopo_epsilon_mae_avg < time_epsilon_mae_avg else "TimeSplit更优"
        
        summary_lines.extend([
            f"   1. α预测性能: {alpha_comparison} (MAE: {lopo_alpha_mae_avg:.4f} vs {time_alpha_mae_avg:.4f})",
            f"   2. ε预测性能: {epsilon_comparison} (MAE: {lopo_epsilon_mae_avg:.4f} vs {time_epsilon_mae_avg:.4f})",
            f"   3. 泛化能力: {'LOPO表现更稳定' if lopo_alpha_mae_avg < time_alpha_mae_avg else '时间泛化存在挑战'}",
            f"   4. 命中率对比: α±0.03 ({lopo_alpha_hit_avg:.1%} vs {time_alpha_hit_avg:.1%}), ε±0.03 ({lopo_epsilon_hit_avg:.1%} vs {time_epsilon_hit_avg:.1%})"
        ])
    else:
        summary_lines.append("   数据不足，无法进行详细对比分析")
    
    summary_lines.extend([
        "",
        f"⚠️  注意事项:",
        f"   - 评估基于防泄漏校正器(GP+Isotonic)，确保测试集完全独立",
        f"   - LOPO评估更严格，每次完全排除一个文献来源",
        f"   - TimeSplit评估反映模型在新时间点的泛化能力",
        f"   - 建议结合两种评估方式综合判断模型性能"
    ])
    
    return "\n".join(summary_lines)


def save_results(comparison_df: pd.DataFrame, summary: str) -> None:
    """保存结果到文件"""
    # 保存CSV表格
    csv_path = Path("reports/group_split_summary.csv")
    comparison_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"📊 对比表格保存到: {csv_path}")
    
    # 保存HTML表格
    html_path = Path("reports/group_split_summary.html")
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>防泄漏评估对比分析</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            th {{ background-color: #f2f2f2; }}
            .summary {{ white-space: pre-line; background-color: #f9f9f9; padding: 15px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>防泄漏评估对比分析</h1>
        {comparison_df.to_html(index=False, classes='table')}
        <div class="summary">{summary}</div>
    </body>
    </html>
    """
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"📋 HTML报告保存到: {html_path}")
    
    # 保存纯文本摘要
    txt_path = Path("reports/group_split_summary.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("防泄漏评估关键指标对比表:\n")
        f.write("=" * 50 + "\n")
        f.write(comparison_df.to_string(index=False))
        f.write("\n\n")
        f.write(summary)
    print(f"📝 文本摘要保存到: {txt_path}")


def main():
    """主函数"""
    print("🎯 防泄漏评估结果对比分析")
    print("=" * 80)
    
    # 加载评估结果
    lopo_results, timesplit_results = load_evaluation_results()
    
    if not lopo_results and not timesplit_results:
        print("❌ 未找到任何评估结果文件，无法生成对比分析")
        return 1
    
    # 创建对比表
    comparison_df = create_comparison_table(
        lopo_results or {}, 
        timesplit_results or {}
    )
    
    if len(comparison_df) == 0:
        print("⚠️  评估结果为空，无法生成对比表")
        return 1
    
    print("\n📊 关键指标对比表:")
    print(comparison_df.to_string(index=False))
    
    # 生成总览结论
    summary = generate_summary_analysis(
        lopo_results or {}, 
        timesplit_results or {}
    )
    
    print(f"\n{summary}")
    
    # 保存结果
    save_results(comparison_df, summary)
    
    print(f"\n✅ 防泄漏评估对比分析完成！")
    return 0


if __name__ == "__main__":
    exit(main())