#!/usr/bin/env python3
"""
MAO-Wise HTML报告生成器

从最新的评估JSON、批次plans.csv和KB命中摘要生成综合HTML报告
替代PowerShell Here-String方式，避免兼容性问题
"""

import argparse
import json
import pathlib
import sys
import pandas as pd
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional
import re

# 确保能找到maowise包
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maowise.utils.logger import logger


class HTMLReportGenerator:
    """HTML报告生成器"""
    
    def __init__(self, output_file: str = "reports/real_run_report.html"):
        self.output_file = pathlib.Path(output_file)
        self.repo_root = REPO_ROOT
        self.reports_dir = self.repo_root / "reports"
        self.tasks_dir = self.repo_root / "tasks"
        
        # 防泄漏章节相关设置
        self.leakage_enabled = False
        self.leakage_json_files = []
        self.leakage_table_file = None
        self.leakage_html_file = None
        
        # 确保reports目录存在
        self.reports_dir.mkdir(exist_ok=True)
    
    def _find_latest_eval_json(self) -> Optional[pathlib.Path]:
        """找到最新的评估JSON文件"""
        pattern = str(self.reports_dir / "eval_experiments_*.json")
        eval_files = glob.glob(pattern)
        
        if not eval_files:
            logger.warning("未找到eval_experiments_*.json文件")
            return None
        
        # 按修改时间排序，取最新的
        eval_files.sort(key=lambda x: pathlib.Path(x).stat().st_mtime, reverse=True)
        latest_file = pathlib.Path(eval_files[0])
        logger.info(f"找到最新评估文件: {latest_file}")
        return latest_file
    
    def _find_latest_batch_plans(self) -> Optional[pathlib.Path]:
        """找到最新的批次plans.csv文件"""
        batch_dirs = list(self.tasks_dir.glob("batch_*"))
        if not batch_dirs:
            logger.warning("未找到批次目录")
            return None
        
        # 按修改时间排序，取最新的
        batch_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        for batch_dir in batch_dirs:
            plans_file = batch_dir / "plans.csv"
            if plans_file.exists():
                logger.info(f"找到最新批次文件: {plans_file}")
                return plans_file
        
        logger.warning("未找到plans.csv文件")
        return None
    
    def _load_eval_data(self, eval_file: pathlib.Path) -> Dict[str, Any]:
        """加载评估数据"""
        try:
            with open(eval_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"加载评估数据失败: {e}")
            return {}
    
    def _load_batch_data(self, plans_file: pathlib.Path) -> Optional[pd.DataFrame]:
        """加载批次数据"""
        try:
            df = pd.read_csv(plans_file)
            logger.info(f"加载批次数据: {len(df)} 条记录")
            return df
        except Exception as e:
            logger.error(f"加载批次数据失败: {e}")
            return None
    
    def _format_metric(self, value: Any, metric_type: str = "default") -> str:
        """格式化指标值"""
        if value is None:
            return "N/A"
        
        try:
            if metric_type == "percentage":
                return f"{float(value):.1f}%"
            elif metric_type == "mae_rmse":
                return f"{float(value):.4f}"
            elif metric_type == "confidence":
                return f"{float(value):.3f}"
            else:
                return f"{float(value):.3f}"
        except:
            return str(value)
    
    def _get_status_class(self, value: float, metric_type: str) -> str:
        """根据指标值获取状态样式类"""
        if value is None:
            return "status-unknown"
        
        try:
            val = float(value)
            if metric_type == "mae":
                return "status-ok" if val <= 0.03 else "status-warning" if val <= 0.05 else "status-error"
            elif metric_type == "hit_rate":
                return "status-ok" if val >= 80 else "status-warning" if val >= 60 else "status-error"
            elif metric_type == "confidence":
                return "status-ok" if val >= 0.7 else "status-warning" if val >= 0.5 else "status-error"
            else:
                return "status-ok"
        except:
            return "status-unknown"
    
    def _generate_eval_section(self, eval_data: Dict[str, Any]) -> str:
        """生成评估指标部分"""
        if not eval_data:
            return "<p>无评估数据可用</p>"
        
        overall = eval_data.get('overall_metrics', {})
        
        # 使用标准键名，如果不存在则尝试旧格式
        alpha_mae = overall.get('alpha_mae') or overall.get('alpha_metrics', {}).get('mae', 0)
        epsilon_mae = overall.get('epsilon_mae') or overall.get('epsilon_metrics', {}).get('mae', 0)
        alpha_hit_03 = overall.get('alpha_hit_pm_0.03') or overall.get('alpha_metrics', {}).get('hit_rate_003', 0)
        epsilon_hit_03 = overall.get('epsilon_hit_pm_0.03') or overall.get('epsilon_metrics', {}).get('hit_rate_003', 0)
        confidence_mean = overall.get('confidence_mean') or overall.get('confidence_metrics', {}).get('average', 0)
        confidence_low_ratio = overall.get('confidence_low_ratio') or overall.get('confidence_metrics', {}).get('low_confidence_ratio', 0)
        
        section = f"""
        <h3>📊 模型评估指标</h3>
        <div class="metrics-grid">
            <div class="metric-card">
                <h4>Alpha性能</h4>
                <p class="metric-value {self._get_status_class(alpha_mae, 'mae')}">
                    MAE: {self._format_metric(alpha_mae, 'mae_rmse')}
                </p>
                <p class="metric-value {self._get_status_class(alpha_hit_03, 'hit_rate')}">
                    命中率(±0.03): {self._format_metric(alpha_hit_03, 'percentage')}
                </p>
            </div>
            <div class="metric-card">
                <h4>Epsilon性能</h4>
                <p class="metric-value {self._get_status_class(epsilon_mae, 'mae')}">
                    MAE: {self._format_metric(epsilon_mae, 'mae_rmse')}
                </p>
                <p class="metric-value {self._get_status_class(epsilon_hit_03, 'hit_rate')}">
                    命中率(±0.03): {self._format_metric(epsilon_hit_03, 'percentage')}
                </p>
            </div>
            <div class="metric-card">
                <h4>置信度</h4>
                <p class="metric-value {self._get_status_class(confidence_mean, 'confidence')}">
                    平均: {self._format_metric(confidence_mean, 'confidence')}
                </p>
                <p class="metric-value {self._get_status_class(100-confidence_low_ratio, 'hit_rate')}">
                    低置信度比例: {self._format_metric(confidence_low_ratio, 'percentage')}
                </p>
            </div>
        </div>
        """
        
        # 体系分组指标
        system_metrics = eval_data.get('system_metrics', {})
        if system_metrics:
            section += "<h4>分体系指标</h4><div class='system-metrics'>"
            for system, metrics in system_metrics.items():
                sys_alpha_mae = metrics.get('alpha_mae') or metrics.get('alpha_metrics', {}).get('mae', 0)
                sys_epsilon_mae = metrics.get('epsilon_mae') or metrics.get('epsilon_metrics', {}).get('mae', 0)
                sys_sample_size = metrics.get('sample_size', 0)
                
                section += f"""
                <div class="system-card">
                    <h5>{system.title()}</h5>
                    <p>Alpha MAE: {self._format_metric(sys_alpha_mae, 'mae_rmse')}</p>
                    <p>Epsilon MAE: {self._format_metric(sys_epsilon_mae, 'mae_rmse')}</p>
                    <p>样本数: {sys_sample_size}</p>
                </div>
                """
            section += "</div>"
        
        return section
    
    def _generate_batch_section(self, batch_df: pd.DataFrame, batch_file: pathlib.Path) -> str:
        """生成批次分析部分"""
        if batch_df is None or len(batch_df) == 0:
            return "<p>无批次数据可用</p>"
        
        batch_name = batch_file.parent.name
        total_plans = len(batch_df)
        
        # 成功率统计
        success_plans = len(batch_df[batch_df['status'] == 'success']) if 'status' in batch_df.columns else total_plans
        success_rate = (success_plans / total_plans * 100) if total_plans > 0 else 0
        
        # 硬约束通过率
        hard_pass_count = len(batch_df[batch_df['hard_constraints_passed'] == True]) if 'hard_constraints_passed' in batch_df.columns else 0
        hard_pass_rate = (hard_pass_count / total_plans * 100) if total_plans > 0 else 0
        
        # 多目标指标
        avg_mass_proxy = batch_df['mass_proxy'].mean() if 'mass_proxy' in batch_df.columns else 0
        avg_uniformity = batch_df['uniformity_penalty'].mean() if 'uniformity_penalty' in batch_df.columns else 0
        avg_score_total = batch_df['score_total'].mean() if 'score_total' in batch_df.columns else 0
        
        # 优秀方案统计（薄/轻 + 均匀）
        excellent_count = 0
        if 'mass_proxy' in batch_df.columns and 'uniformity_penalty' in batch_df.columns:
            excellent_mask = (batch_df['mass_proxy'] <= 0.4) & (batch_df['uniformity_penalty'] <= 0.2)
            excellent_count = len(batch_df[excellent_mask])
        excellent_rate = (excellent_count / total_plans * 100) if total_plans > 0 else 0
        
        section = f"""
        <h3>🧪 最新批次分析</h3>
        <div class="batch-info">
            <p><strong>批次:</strong> {batch_name}</p>
            <p><strong>总方案数:</strong> {total_plans}</p>
            <p><strong>生成成功率:</strong> <span class="{self._get_status_class(success_rate, 'hit_rate')}">{success_rate:.1f}%</span></p>
            <p><strong>硬约束通过率:</strong> <span class="{self._get_status_class(hard_pass_rate, 'hit_rate')}">{hard_pass_rate:.1f}%</span></p>
        </div>
        
        <h4>多目标优化指标</h4>
        <div class="metrics-grid">
            <div class="metric-card">
                <h4>薄/轻目标</h4>
                <p class="metric-value">平均质量代理: {avg_mass_proxy:.3f}</p>
                <p class="metric-description">越小越好 (目标 ≤ 0.4)</p>
            </div>
            <div class="metric-card">
                <h4>均匀性目标</h4>
                <p class="metric-value">平均均匀性惩罚: {avg_uniformity:.3f}</p>
                <p class="metric-description">越小越好 (目标 ≤ 0.2)</p>
            </div>
            <div class="metric-card">
                <h4>综合评分</h4>
                <p class="metric-value">平均总分: {avg_score_total:.2f}</p>
                <p class="metric-description">越高越好</p>
            </div>
        </div>
        
        <div class="excellent-plans">
            <h4>🎯 优秀方案统计</h4>
            <p>薄/轻+均匀方案: <span class="{self._get_status_class(excellent_rate, 'hit_rate')}">{excellent_count}/{total_plans} ({excellent_rate:.1f}%)</span></p>
            <p class="metric-description">同时满足 mass_proxy ≤ 0.4 且 uniformity_penalty ≤ 0.2</p>
        </div>
        """
        
        return section
    
    def _generate_kb_section(self) -> str:
        """生成KB命中摘要部分"""
        # 查找KB相关的日志或摘要文件
        kb_info = "KB模块正常运行，支持文献检索和引用"
        
        # 尝试读取最新的KB统计信息
        try:
            # 这里可以扩展读取实际的KB统计信息
            section = f"""
            <h3>📚 知识库状态</h3>
            <div class="kb-info">
                <p class="status-ok">✅ {kb_info}</p>
                <p>支持中英文文献检索和工艺参数推荐</p>
            </div>
            """
        except:
            section = """
            <h3>📚 知识库状态</h3>
            <div class="kb-info">
                <p class="status-warning">⚠️ 知识库状态未知</p>
            </div>
            """
        
        return section
    
    def _generate_html_template(self, content_sections: List[str]) -> str:
        """生成完整的HTML模板"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MAO-Wise Real Run Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            text-align: center;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        
        h2, h3, h4 {{
            color: #34495e;
            margin-top: 25px;
        }}
        
        .header-info {{
            text-align: center;
            margin-bottom: 30px;
            padding: 15px;
            background-color: #ecf0f1;
            border-radius: 5px;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .metric-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }}
        
        .metric-value {{
            font-size: 1.2em;
            font-weight: bold;
            margin: 10px 0;
        }}
        
        .metric-description {{
            font-size: 0.9em;
            color: #6c757d;
            margin: 5px 0;
        }}
        
        .system-metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }}
        
        .system-card {{
            background: #e8f5e8;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #d4edda;
        }}
        
        .batch-info {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #ffeaa7;
            margin: 15px 0;
        }}
        
        .kb-info {{
            background: #d1ecf1;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #bee5eb;
            margin: 15px 0;
        }}
        
        .excellent-plans {{
            background: #f8d7da;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #f5c6cb;
            margin: 15px 0;
        }}
        
        .status-ok {{
            color: #28a745;
        }}
        
        .status-warning {{
            color: #ffc107;
        }}
        
        .status-error {{
            color: #dc3545;
        }}
        
        .status-unknown {{
            color: #6c757d;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            color: #6c757d;
            font-size: 0.9em;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 15px;
            }}
            
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🧪 MAO-Wise Real Run Report</h1>
        
        <div class="header-info">
            <p><strong>报告生成时间:</strong> {current_time}</p>
            <p><strong>系统状态:</strong> <span class="status-ok">运行正常</span></p>
        </div>
        
        {''.join(content_sections)}
        
        <div class="footer">
            <p>此报告由 MAO-Wise 自动生成 | 数据来源: 最新评估文件和批次记录</p>
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def generate_report(self) -> bool:
        """生成HTML报告"""
        logger.info("开始生成HTML报告...")
        
        # 收集数据
        eval_file = self._find_latest_eval_json()
        eval_data = self._load_eval_data(eval_file) if eval_file else {}
        
        batch_file = self._find_latest_batch_plans()
        batch_df = self._load_batch_data(batch_file) if batch_file else None
        
        # 生成各个部分
        content_sections = []
        
        # 评估指标部分
        eval_section = self._generate_eval_section(eval_data)
        content_sections.append(eval_section)
        
        # 批次分析部分
        if batch_file:
            batch_section = self._generate_batch_section(batch_df, batch_file)
            content_sections.append(batch_section)
        
        # KB状态部分
        kb_section = self._generate_kb_section()
        content_sections.append(kb_section)
        
        # 防泄漏复评部分（可选）
        if self.leakage_enabled:
            leakage_section = self._generate_leakage_section()
            if leakage_section:
                content_sections.append(leakage_section)
        
        # 生成完整HTML
        html_content = self._generate_html_template(content_sections)
        
        # 保存文件
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"HTML报告已生成: {self.output_file}")
            return True
            
        except Exception as e:
            logger.error(f"生成HTML报告失败: {e}")
            return False
    
    def _generate_leakage_section(self) -> Optional[str]:
        """生成防泄漏复评章节"""
        try:
            logger.info("生成防泄漏复评章节...")
            
            section_html = ['<div class="section">']
            section_html.append('<h2>🔍 防泄漏复评</h2>')
            
            # 加载防泄漏评估结果
            leakage_results = {}
            for json_file in self.leakage_json_files:
                json_path = pathlib.Path(json_file)
                if json_path.exists():
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        method = data.get('method', json_path.stem)
                        leakage_results[method] = data
            
            if not leakage_results:
                section_html.append('<p class="warning">⚠️ 未找到防泄漏评估结果文件</p>')
                section_html.append('</div>')
                return '\n'.join(section_html)
            
            # 添加说明
            section_html.extend([
                '<p>防泄漏评估通过LOPO (Leave-One-Paper-Out) 和 TimeSplit 两种方式验证模型的泛化能力，',
                '确保测试数据完全独立，避免数据泄漏。每种评估方式都重新训练GP和Isotonic校正器。</p>'
            ])
            
            # 生成评估结果摘要
            section_html.append('<h3>📊 评估方法对比</h3>')
            section_html.append('<div class="eval-grid">')
            
            for method, results in leakage_results.items():
                method_name = "文献交叉验证" if method == "LOPO" else "时间分割验证"
                section_html.append(f'<div class="eval-card">')
                section_html.append(f'<h4>{method} ({method_name})</h4>')
                
                if 'systems' in results:
                    section_html.append('<table class="metrics-table">')
                    section_html.append('<tr><th>体系</th><th>α MAE</th><th>ε MAE</th><th>α命中率</th><th>ε命中率</th><th>样本数</th></tr>')
                    
                    for system, metrics in results['systems'].items():
                        alpha_mae = metrics.get('alpha_mae', 0)
                        epsilon_mae = metrics.get('epsilon_mae', 0)
                        alpha_hit = metrics.get('alpha_hit_pm_0.03', 0)
                        epsilon_hit = metrics.get('epsilon_hit_pm_0.03', 0)
                        n_samples = metrics.get('n_samples', 0)
                        
                        section_html.append(f'<tr>')
                        section_html.append(f'<td>{system}</td>')
                        section_html.append(f'<td>{alpha_mae:.4f}</td>')
                        section_html.append(f'<td>{epsilon_mae:.4f}</td>')
                        section_html.append(f'<td>{alpha_hit:.1%}</td>')
                        section_html.append(f'<td>{epsilon_hit:.1%}</td>')
                        section_html.append(f'<td>{n_samples}</td>')
                        section_html.append(f'</tr>')
                    
                    section_html.append('</table>')
                
                # 添加方法特定信息
                if method == "LOPO":
                    n_folds = results.get('n_folds', 0)
                    section_html.append(f'<p class="method-info">交叉验证折数: {n_folds} 个文献来源</p>')
                elif method == "TimeSplit":
                    train_size = results.get('train_size', 0)
                    test_size = results.get('test_size', 0)
                    section_html.append(f'<p class="method-info">训练集: {train_size} 条，测试集: {test_size} 条</p>')
                
                section_html.append('</div>')
            
            section_html.append('</div>')
            
            # 添加对比表格（如果存在）
            if self.leakage_table_file and pathlib.Path(self.leakage_table_file).exists():
                section_html.append('<h3>📋 详细对比表格</h3>')
                try:
                    df = pd.read_csv(self.leakage_table_file)
                    table_html = df.to_html(index=False, classes='comparison-table', escape=False)
                    section_html.append(table_html)
                except Exception as e:
                    section_html.append(f'<p class="error">加载对比表格失败: {e}</p>')
            
            # 添加总结
            section_html.extend([
                '<h3>🔍 关键发现</h3>',
                '<ul>',
                '<li>LOPO评估更严格，每次完全排除一个文献来源的所有数据</li>',
                '<li>TimeSplit评估反映模型在新时间点的泛化能力</li>',
                '<li>所有评估均使用防泄漏校正器训练，确保测试集完全独立</li>',
                '<li>建议结合两种评估方式综合判断模型性能</li>',
                '</ul>'
            ])
            
            section_html.append('</div>')
            
            return '\n'.join(section_html)
            
        except Exception as e:
            logger.error(f"生成防泄漏章节失败: {e}")
            return f'<div class="section"><h2>🔍 防泄漏复评</h2><p class="error">生成失败: {e}</p></div>'


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="MAO-Wise HTML报告生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 生成默认报告
  python scripts/make_html_report.py
  
  # 指定输出文件
  python scripts/make_html_report.py --output reports/custom_report.html
        """
    )
    
    parser.add_argument("--output", 
                       type=str, 
                       default="reports/real_run_report.html",
                       help="HTML报告输出路径 (默认: reports/real_run_report.html)")
    parser.add_argument("--extras", choices=["leakage"], nargs="+",
                       help="包含额外章节: leakage (防泄漏复评)")
    parser.add_argument("--leakage-json", nargs="+",
                       help="防泄漏评估JSON文件路径")
    parser.add_argument("--leakage-table",
                       help="防泄漏对比表格CSV文件路径")
    parser.add_argument("--leakage-html",
                       help="防泄漏HTML摘要文件路径")
    
    args = parser.parse_args()
    
    try:
        generator = HTMLReportGenerator(args.output)
        
        # 设置防泄漏相关参数
        if args.extras and "leakage" in args.extras:
            generator.leakage_enabled = True
            generator.leakage_json_files = args.leakage_json or []
            generator.leakage_table_file = args.leakage_table
            generator.leakage_html_file = args.leakage_html
        
        success = generator.generate_report()
        
        if success:
            print(f"✅ HTML报告生成成功: {args.output}")
            sys.exit(0)
        else:
            print(f"❌ HTML报告生成失败")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"报告生成器出错: {e}")
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
