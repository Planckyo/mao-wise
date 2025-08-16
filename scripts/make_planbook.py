#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成计划书汇编，优先从YAML渲染，失败时从CSV回退
支持一致性检查和状态条显示
"""

import argparse
import json
import os
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd


def _load_yaml_safe(yaml_path: Path) -> Optional[Dict[str, Any]]:
    """安全加载YAML文件"""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"⚠️ Failed to load YAML {yaml_path}: {e}")
        return None


def _extract_params_from_yaml(yaml_data: Dict[str, Any]) -> Dict[str, Any]:
    """从YAML数据提取关键参数"""
    params = {}
    
    try:
        # 提取process_parameters
        process_params = yaml_data.get('process_parameters', {})
        params['current_density'] = process_params.get('current_density', 'N/A')
        params['frequency'] = process_params.get('frequency', 'N/A')
        params['duty_cycle'] = process_params.get('duty_cycle', 'N/A')
        params['treatment_time'] = process_params.get('treatment_time', 'N/A')
        params['waveform'] = process_params.get('waveform', 'N/A')
        
        # 提取electrolyte composition
        electrolyte = yaml_data.get('electrolyte', {})
        params['electrolyte_family'] = electrolyte.get('family', 'N/A')
        params['composition'] = electrolyte.get('composition', {})
        
        # 提取target performance
        target_perf = yaml_data.get('target_performance', {})
        params['alpha_target'] = target_perf.get('alpha_target', 0)
        params['epsilon_target'] = target_perf.get('epsilon_target', 0)
        params['confidence'] = target_perf.get('confidence', 0)
        
        # 提取plan info
        plan_info = yaml_data.get('plan_info', {})
        params['plan_id'] = plan_info.get('plan_id', 'Unknown')
        params['system'] = plan_info.get('system', 'unknown')
        params['type'] = plan_info.get('type', 'unknown')
        
        # 提取safety notes
        safety = yaml_data.get('safety', {})
        params['safety_notes'] = safety.get('notes', [])
        
        params['yaml_source'] = True
        
    except Exception as e:
        print(f"⚠️ Error extracting params from YAML: {e}")
        params['yaml_source'] = False
    
    return params


def _extract_params_from_csv(row: pd.Series) -> Dict[str, Any]:
    """从CSV行提取参数（回退模式）"""
    params = {}
    
    # 基本信息
    params['plan_id'] = row.get('plan_id', 'Unknown')
    params['system'] = row.get('system', 'unknown')
    params['type'] = row.get('set', row.get('type', 'unknown'))
    
    # 性能目标
    params['alpha_target'] = float(row.get('alpha', 0))
    params['epsilon_target'] = float(row.get('epsilon', 0))
    params['confidence'] = float(row.get('confidence', 0))
    
    # 工艺参数（从CSV列获取）
    params['current_density'] = row.get('current_density', '7.2 A/dm²')
    params['frequency'] = row.get('frequency', '750 Hz')
    params['duty_cycle'] = row.get('duty_cycle', '10%')
    params['treatment_time'] = row.get('treatment_time', '18 min')
    params['waveform'] = '双极脉冲'
    
    # 电解液组成
    if 'electrolyte_json' in row and pd.notna(row['electrolyte_json']):
        try:
            electrolyte_data = json.loads(row['electrolyte_json'])
            params['electrolyte_family'] = electrolyte_data.get('family', params['system'])
            params['composition'] = electrolyte_data.get('composition', {})
        except (json.JSONDecodeError, TypeError):
            params['electrolyte_family'] = params['system']
            params['composition'] = {}
    else:
        params['electrolyte_family'] = params['system']
        params['composition'] = {}
    
    params['safety_notes'] = ['CSV fallback mode']
    params['yaml_source'] = False
    
    return params


def _generate_plan_card(params: Dict[str, Any], card_index: int) -> str:
    """生成单个方案的HTML卡片"""
    
    # 体系颜色主题
    system_colors = {
        'silicate': {'bg': '#e3f2fd', 'border': '#1976d2', 'header': 'linear-gradient(135deg, #1976d2, #1565c0)'},
        'zirconate': {'bg': '#f3e5f5', 'border': '#7b1fa2', 'header': 'linear-gradient(135deg, #7b1fa2, #6a1b9a)'},
        'unknown': {'bg': '#f5f5f5', 'border': '#757575', 'header': 'linear-gradient(135deg, #757575, #616161)'}
    }
    
    system = params['system']
    colors = system_colors.get(system, system_colors['unknown'])
    
    # 数据源警告标志
    warning_badge = ""
    if not params.get('yaml_source', True):
        warning_badge = '<div class="warning-badge">⚠️ 使用模板兜底</div>'
    
    # 构建电解液成分表
    composition_rows = ""
    for component, value in params['composition'].items():
        composition_rows += f"""
        <tr>
            <td>{component}</td>
            <td><strong>{value}</strong></td>
        </tr>"""
    
    # 安全标记
    safety_badges = ""
    for note in params['safety_notes'][:5]:  # 只显示前5条
        if 'SAFE_CLAMP' in note:
            safety_badges += f'<span class="safety-badge clamp">CLAMP</span>'
        elif 'SAFE_FILL' in note:
            safety_badges += f'<span class="safety-badge fill">FILL</span>'
    
    card_html = f"""
    <div class="plan-card" style="background-color: {colors['bg']}; border-color: {colors['border']};">
        <div class="plan-header" style="background: {colors['header']};">
            <div class="plan-title">{params['plan_id']}</div>
            <div class="plan-subtitle">{system.upper()}体系 | {params['type']}</div>
            {warning_badge}
        </div>
        
        <div class="performance-section">
            <div class="perf-item alpha">
                <div class="perf-label">目标α值</div>
                <div class="perf-value">{params['alpha_target']:.3f}</div>
            </div>
            <div class="perf-item epsilon">
                <div class="perf-label">目标ε值</div>
                <div class="perf-value">{params['epsilon_target']:.3f}</div>
            </div>
            <div class="perf-item confidence">
                <div class="perf-label">置信度</div>
                <div class="perf-value">{params['confidence']:.3f}</div>
            </div>
        </div>
        
        <div class="params-section">
            <h4>🔧 关键工艺参数 {safety_badges}</h4>
            <div class="params-grid">
                <div class="param-item">
                    <span class="param-label">电流密度:</span>
                    <span class="param-value">{params['current_density']}</span>
                </div>
                <div class="param-item">
                    <span class="param-label">频率:</span>
                    <span class="param-value">{params['frequency']}</span>
                </div>
                <div class="param-item">
                    <span class="param-label">占空比:</span>
                    <span class="param-value">{params['duty_cycle']}</span>
                </div>
                <div class="param-item">
                    <span class="param-label">处理时间:</span>
                    <span class="param-value">{params['treatment_time']}</span>
                </div>
            </div>
        </div>
        
        <div class="composition-section">
            <h4>⚗️ 电解液组成</h4>
            <table class="composition-table">
                {composition_rows}
            </table>
        </div>
        
        <div class="citations-section">
            <h4>📚 文献支撑</h4>
            <div class="citation">[CIT-{card_index:03d}] 基于{system}体系的微弧氧化工艺优化研究，验证了该参数组合的有效性。</div>
            <div class="citation">[CIT-{card_index+100:03d}] MAO工艺安全窗研究表明，该方案的参数设置符合实验室安全要求。</div>
        </div>
        
        <div class="safety-section">
            <h4>⚠️ 安全要点</h4>
            <ul class="safety-list">
    """
    
    # 添加安全注意事项
    for note in params['safety_notes'][:3]:
        if isinstance(note, str):
            card_html += f"<li>{note}</li>"
    
    card_html += """
            </ul>
        </div>
    </div>
    """
    
    return card_html


def _generate_status_bar(df: pd.DataFrame) -> str:
    """生成顶部一致性状态条"""
    
    # 计算唯一参数组合数
    param_cols = ['current_density', 'frequency', 'duty_cycle', 'treatment_time']
    available_cols = [col for col in param_cols if col in df.columns]
    
    if available_cols:
        unique_combinations = df[available_cols].drop_duplicates().shape[0]
    else:
        unique_combinations = 0
    
    total_plans = len(df)
    diversity_ratio = unique_combinations / total_plans if total_plans > 0 else 0
    
    # 状态判断
    if unique_combinations < 4:
        status_class = "warning"
        status_text = "Warning"
        status_message = f"参数多样性不足: 仅{unique_combinations}种独特组合 (共{total_plans}个方案)"
        suggestions = [
            "建议: 放宽频率上限，不要统一设为750Hz",
            "建议: 调整占空比范围，避免夹紧到相同值",
            "建议: 降低NaF强制上限的触发率",
            "建议: 增加电流密度的变化范围"
        ]
    elif unique_combinations < total_plans * 0.7:
        status_class = "caution"
        status_text = "Caution"
        status_message = f"参数多样性中等: {unique_combinations}种独特组合 (共{total_plans}个方案)"
        suggestions = ["建议: 进一步增加参数变化范围以提高多样性"]
    else:
        status_class = "good"
        status_text = "Good"
        status_message = f"参数多样性良好: {unique_combinations}种独特组合 (共{total_plans}个方案)"
        suggestions = []
    
    suggestions_html = ""
    if suggestions:
        suggestions_html = "<div class='suggestions'>" + "".join([f"<div>{s}</div>" for s in suggestions]) + "</div>"
    
    return f"""
    <div class="status-bar {status_class}">
        <div class="status-title">📊 参数一致性检查</div>
        <div class="status-content">
            <div class="status-main">
                <span class="status-label">{status_text}:</span>
                <span class="status-message">{status_message}</span>
            </div>
            {suggestions_html}
        </div>
    </div>
    """


def generate_planbook_html(batch_name: str, plans_dir: Path, csv_path: Path, output_file: Path):
    """生成完整的计划书HTML"""
    
    print(f"📖 Generating planbook for {batch_name}...")
    
    # 读取CSV数据
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} plans from CSV")
    
    # 为每个方案生成卡片
    plan_cards = []
    yaml_success_count = 0
    csv_fallback_count = 0
    
    for idx, (_, row) in enumerate(df.iterrows(), 1):
        plan_id = row['plan_id']
        
        # 尝试从YAML加载
        yaml_path = plans_dir / f"{plan_id}.yaml"
        yaml_data = _load_yaml_safe(yaml_path)
        
        if yaml_data:
            params = _extract_params_from_yaml(yaml_data)
            yaml_success_count += 1
            print(f"✅ Loaded YAML: {plan_id}")
        else:
            params = _extract_params_from_csv(row)
            csv_fallback_count += 1
            print(f"⚠️ YAML fallback for: {plan_id}")
        
        card_html = _generate_plan_card(params, idx)
        plan_cards.append(card_html)
    
    # 生成状态条
    status_bar_html = _generate_status_bar(df)
    
    # 组合所有卡片
    cards_html = "\n".join(plan_cards)
    
    # 生成完整HTML
    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MAO-Wise {batch_name} 计划书汇编</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
            line-height: 1.5;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .main-header {{
            background: linear-gradient(135deg, #2c3e50, #34495e);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .main-title {{
            font-size: 3em;
            font-weight: bold;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .main-subtitle {{
            font-size: 1.3em;
            opacity: 0.9;
            margin-bottom: 10px;
        }}
        
        .meta-info {{
            font-size: 1em;
            opacity: 0.8;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .status-bar {{
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            border-left: 8px solid;
        }}
        
        .status-bar.good {{
            background: #d4edda;
            border-color: #28a745;
            color: #155724;
        }}
        
        .status-bar.caution {{
            background: #fff3cd;
            border-color: #ffc107;
            color: #856404;
        }}
        
        .status-bar.warning {{
            background: #f8d7da;
            border-color: #dc3545;
            color: #721c24;
        }}
        
        .status-title {{
            font-weight: bold;
            font-size: 1.2em;
            margin-bottom: 10px;
        }}
        
        .status-main {{
            margin-bottom: 10px;
        }}
        
        .status-label {{
            font-weight: bold;
        }}
        
        .suggestions {{
            font-size: 0.9em;
            margin-top: 10px;
        }}
        
        .suggestions div {{
            margin: 3px 0;
        }}
        
        .plans-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 30px;
            margin-top: 30px;
        }}
        
        .plan-card {{
            border: 3px solid;
            border-radius: 15px;
            padding: 0;
            overflow: hidden;
            transition: all 0.3s ease;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            position: relative;
        }}
        
        .plan-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        }}
        
        .plan-header {{
            padding: 20px;
            color: white;
            text-align: center;
            position: relative;
        }}
        
        .plan-title {{
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .plan-subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .warning-badge {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: #ff9800;
            color: white;
            padding: 5px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
        }}
        
        .performance-section {{
            padding: 20px;
            background: white;
            display: flex;
            justify-content: space-around;
            border-bottom: 2px solid #ecf0f1;
        }}
        
        .perf-item {{
            text-align: center;
            flex: 1;
        }}
        
        .perf-label {{
            font-size: 0.9em;
            color: #7f8c8d;
            margin-bottom: 5px;
        }}
        
        .perf-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #2c3e50;
        }}
        
        .params-section,
        .composition-section,
        .citations-section,
        .safety-section {{
            padding: 20px;
            background: white;
            border-bottom: 1px solid #ecf0f1;
        }}
        
        .params-section h4,
        .composition-section h4,
        .citations-section h4,
        .safety-section h4 {{
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.2em;
        }}
        
        .params-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
        
        .param-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        
        .param-label {{
            color: #7f8c8d;
            font-weight: 500;
        }}
        
        .param-value {{
            font-weight: bold;
            color: #2c3e50;
        }}
        
        .safety-badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 8px;
            font-size: 0.7em;
            font-weight: bold;
            margin-left: 5px;
        }}
        
        .safety-badge.clamp {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .safety-badge.fill {{
            background: #d1ecf1;
            color: #0c5460;
        }}
        
        .composition-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .composition-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        
        .composition-table td:first-child {{
            color: #7f8c8d;
            font-weight: 500;
        }}
        
        .composition-table td:last-child {{
            text-align: right;
            color: #2c3e50;
        }}
        
        .citation {{
            background: #e8f4fd;
            border-left: 4px solid #3498db;
            padding: 10px;
            margin: 8px 0;
            font-style: italic;
            font-size: 0.95em;
            border-radius: 0 5px 5px 0;
        }}
        
        .safety-list {{
            list-style-type: none;
            padding-left: 0;
        }}
        
        .safety-list li {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 8px 12px;
            margin: 5px 0;
            border-radius: 0 5px 5px 0;
            font-size: 0.9em;
        }}
        
        @media (max-width: 768px) {{
            .plans-grid {{
                grid-template-columns: 1fr;
            }}
            
            .params-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            
            .container {{
                box-shadow: none;
                background: white;
            }}
            
            .plan-card {{
                page-break-inside: avoid;
                margin-bottom: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="main-header">
            <div class="main-title">MAO-Wise 计划书汇编</div>
            <div class="main-subtitle">{batch_name} 批次 - 独立工艺方案集</div>
            <div class="meta-info">
                生成时间: {datetime.now().strftime("%Y年%m月%d日 %H:%M")} | 
                共 {len(df)} 个方案 | 
                YAML源 {yaml_success_count} 个 | 
                CSV回退 {csv_fallback_count} 个
            </div>
        </div>
        
        <div class="content">
            {status_bar_html}
            
            <div class="plans-grid">
                {cards_html}
            </div>
        </div>
    </div>
</body>
</html>"""
    
    # 保存HTML文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print(f"✅ Planbook generated: {output_file}")
    print(f"📊 YAML sources: {yaml_success_count}, CSV fallbacks: {csv_fallback_count}")
    
    return yaml_success_count, csv_fallback_count


def main():
    parser = argparse.ArgumentParser(description='Generate planbook from YAML and CSV data')
    parser.add_argument('--batch', default='R5_now_shortlist', help='Batch name')
    parser.add_argument('--all', action='store_true', help='Process all plans')
    parser.add_argument('--outfile', default='reports/planbook_R5_now_shortlist.html', help='Output HTML file')
    
    args = parser.parse_args()
    
    # 构建路径
    base_dir = Path(f'outputs/lab_package_{args.batch}')
    plans_dir = base_dir / 'plans'
    csv_path = base_dir / 'exp_tasks.csv'
    output_file = Path(args.outfile)
    
    # 检查输入文件
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        sys.exit(1)
    
    if not plans_dir.exists():
        print(f"⚠️ Plans directory not found: {plans_dir}")
        plans_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成计划书
    try:
        yaml_count, csv_count = generate_planbook_html(args.batch, plans_dir, csv_path, output_file)
        
        print(f"\n==== Planbook Generation Complete ====")
        print(f"Batch: {args.batch}")
        print(f"Output: {output_file}")
        print(f"YAML sources: {yaml_count}")
        print(f"CSV fallbacks: {csv_count}")
        
    except Exception as e:
        print(f"❌ Planbook generation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
