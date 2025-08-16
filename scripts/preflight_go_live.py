#!/usr/bin/env python3
"""
MAO-Wise Go-Live 预检Python脚本
生成详细的HTML报告
"""

import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


class GoLiveReportGenerator:
    """Go-Live报告生成器"""
    
    def __init__(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.status_colors = {
            'PASS': '#28a745',  # 绿色
            'WARN': '#ffc107',  # 黄色  
            'FAIL': '#dc3545',  # 红色
            'SKIP': '#6c757d'   # 灰色
        }
        self.status_icons = {
            'PASS': '✓',
            'WARN': '⚠',
            'FAIL': '✗',
            'SKIP': '○'
        }
    
    def load_results(self, results_file: Path) -> List[Dict[str, Any]]:
        """加载检查结果"""
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            logger.info(f"加载了 {len(results)} 个检查结果")
            return results
        except Exception as e:
            logger.error(f"加载结果失败: {e}")
            return []
    
    def get_overall_status(self, results: List[Dict[str, Any]]) -> str:
        """计算整体状态"""
        if any(r['Status'] == 'FAIL' for r in results):
            return 'FAIL'
        elif any(r['Status'] == 'WARN' for r in results):
            return 'WARN'
        else:
            return 'PASS'
    
    def get_status_counts(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """统计各状态数量"""
        counts = {'PASS': 0, 'WARN': 0, 'FAIL': 0, 'SKIP': 0}
        for result in results:
            status = result.get('Status', 'UNKNOWN')
            if status in counts:
                counts[status] += 1
        return counts
    
    def generate_html_report(self, results: List[Dict[str, Any]], output_dir: Path) -> Path:
        """生成HTML报告"""
        if not results:
            logger.warning("没有检查结果，生成空报告")
        
        overall_status = self.get_overall_status(results)
        status_counts = self.get_status_counts(results)
        
        # 按类别分组
        categories = {}
        for result in results:
            category = result.get('Category', 'Unknown')
            if category not in categories:
                categories[category] = []
            categories[category].append(result)
        
        # 生成HTML内容
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MAO-Wise Go-Live 预检报告</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .header .subtitle {{
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.1em;
        }}
        .overall-status {{
            background: {self.status_colors[overall_status]};
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 1.5em;
            font-weight: bold;
        }}
        .summary {{
            padding: 30px;
            border-bottom: 1px solid #eee;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #ddd;
        }}
        .stat-card.pass {{ border-left-color: #28a745; }}
        .stat-card.warn {{ border-left-color: #ffc107; }}
        .stat-card.fail {{ border-left-color: #dc3545; }}
        .stat-card.skip {{ border-left-color: #6c757d; }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .category {{
            margin: 30px;
            border: 1px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
        }}
        .category-header {{
            background: #f8f9fa;
            padding: 15px 20px;
            font-weight: bold;
            font-size: 1.2em;
            border-bottom: 1px solid #ddd;
        }}
        .check-item {{
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: flex-start;
            gap: 15px;
        }}
        .check-item:last-child {{
            border-bottom: none;
        }}
        .status-icon {{
            font-size: 1.2em;
            font-weight: bold;
            min-width: 20px;
        }}
        .status-icon.pass {{ color: #28a745; }}
        .status-icon.warn {{ color: #ffc107; }}
        .status-icon.fail {{ color: #dc3545; }}
        .status-icon.skip {{ color: #6c757d; }}
        .check-content {{
            flex: 1;
        }}
        .check-title {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .check-details {{
            color: #666;
            margin-bottom: 8px;
        }}
        .check-suggestion {{
            background: #e7f3ff;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 0.9em;
            border-left: 3px solid #007bff;
        }}
        .suggestions {{
            background: #f8f9fa;
            padding: 30px;
            margin-top: 30px;
        }}
        .suggestions h2 {{
            color: #495057;
            margin-bottom: 20px;
        }}
        .suggestion-item {{
            margin: 10px 0;
            padding: 10px 15px;
            background: white;
            border-radius: 4px;
            border-left: 4px solid #007bff;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #ddd;
        }}
        .timestamp {{
            margin: 10px 0;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MAO-Wise Go-Live 预检报告</h1>
            <div class="subtitle">系统上线准备状态检查</div>
            <div class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        
        <div class="overall-status">
            {self.status_icons[overall_status]} 整体状态: {overall_status}
        </div>
        
        <div class="summary">
            <h2>检查结果统计</h2>
            <div class="stats">
                <div class="stat-card pass">
                    <div class="stat-number">{status_counts['PASS']}</div>
                    <div>通过 (PASS)</div>
                </div>
                <div class="stat-card warn">
                    <div class="stat-number">{status_counts['WARN']}</div>
                    <div>警告 (WARN)</div>
                </div>
                <div class="stat-card fail">
                    <div class="stat-number">{status_counts['FAIL']}</div>
                    <div>失败 (FAIL)</div>
                </div>
                <div class="stat-card skip">
                    <div class="stat-number">{status_counts['SKIP']}</div>
                    <div>跳过 (SKIP)</div>
                </div>
            </div>
        </div>
"""
        
        # 添加各类别的检查结果
        for category_name, category_results in categories.items():
            html_content += f"""
        <div class="category">
            <div class="category-header">{category_name}</div>
"""
            
            for result in category_results:
                status = result.get('Status', 'UNKNOWN').lower()
                icon = self.status_icons.get(result.get('Status', 'UNKNOWN'), '?')
                
                html_content += f"""
            <div class="check-item">
                <div class="status-icon {status}">{icon}</div>
                <div class="check-content">
                    <div class="check-title">{result.get('Item', 'Unknown')}</div>
                    <div class="check-details">{result.get('Details', '')}</div>
"""
                
                if result.get('Suggestion'):
                    html_content += f"""
                    <div class="check-suggestion">
                        💡 建议: {result.get('Suggestion')}
                    </div>
"""
                
                html_content += """
                </div>
            </div>
"""
            
            html_content += """
        </div>
"""
        
        # 添加建议部分
        suggestions = self._generate_suggestions(overall_status, results)
        html_content += f"""
        <div class="suggestions">
            <h2>下一步建议</h2>
            {suggestions}
        </div>
        
        <div class="footer">
            <div>MAO-Wise 预检系统 | 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            <div>如需帮助，请查阅文档或联系技术支持</div>
        </div>
    </div>
</body>
</html>"""
        
        # 保存HTML文件
        output_file = output_dir / "go_live_checklist.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML报告已生成: {output_file}")
        return output_file
    
    def _generate_suggestions(self, overall_status: str, results: List[Dict[str, Any]]) -> str:
        """生成建议HTML"""
        suggestions_html = ""
        
        if overall_status == 'PASS':
            suggestions_html += """
            <div class="suggestion-item">
                ✅ <strong>系统准备就绪</strong>，可以上线运行
            </div>
            <div class="suggestion-item">
                📋 建议定期运行此预检脚本确保系统健康
            </div>
            <div class="suggestion-item">
                📊 建议设置监控告警，及时发现潜在问题
            </div>
"""
        elif overall_status == 'WARN':
            suggestions_html += """
            <div class="suggestion-item">
                ⚠️ <strong>系统基本可用</strong>，但存在需要关注的问题
            </div>
            <div class="suggestion-item">
                🔧 建议修复警告项后再正式上线
            </div>
            <div class="suggestion-item">
                🧪 可在受控环境下进行测试验证
            </div>
"""
        else:
            suggestions_html += """
            <div class="suggestion-item">
                ❌ <strong>系统存在严重问题</strong>，不建议上线
            </div>
            <div class="suggestion-item">
                🔨 必须修复所有FAIL项才能继续
            </div>
            <div class="suggestion-item">
                🔄 建议重新运行完整的系统部署流程
            </div>
"""
        
        # 添加具体的修复建议
        fail_items = [r for r in results if r.get('Status') == 'FAIL' and r.get('Suggestion')]
        if fail_items:
            suggestions_html += """
            <div class="suggestion-item">
                <strong>🔧 紧急修复项目:</strong>
                <ul>
"""
            for item in fail_items:
                suggestions_html += f"<li>{item.get('Item', '')}: {item.get('Suggestion', '')}</li>"
            suggestions_html += """
                </ul>
            </div>
"""
        
        warn_items = [r for r in results if r.get('Status') == 'WARN' and r.get('Suggestion')]
        if warn_items:
            suggestions_html += """
            <div class="suggestion-item">
                <strong>⚠️ 优化建议:</strong>
                <ul>
"""
            for item in warn_items[:5]:  # 只显示前5个
                suggestions_html += f"<li>{item.get('Item', '')}: {item.get('Suggestion', '')}</li>"
            suggestions_html += """
                </ul>
            </div>
"""
        
        return suggestions_html
    
    def generate_text_summary(self, results: List[Dict[str, Any]], output_dir: Path) -> Path:
        """生成文本摘要"""
        overall_status = self.get_overall_status(results)
        status_counts = self.get_status_counts(results)
        
        summary_lines = [
            "=" * 60,
            "MAO-Wise Go-Live 预检摘要",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"整体状态: {overall_status}",
            "=" * 60,
            "",
            "统计信息:",
            f"  ✓ 通过: {status_counts['PASS']}",
            f"  ⚠ 警告: {status_counts['WARN']}",
            f"  ✗ 失败: {status_counts['FAIL']}",
            f"  ○ 跳过: {status_counts['SKIP']}",
            f"  总计: {sum(status_counts.values())}",
            "",
        ]
        
        # 添加失败项
        fail_items = [r for r in results if r.get('Status') == 'FAIL']
        if fail_items:
            summary_lines.extend([
                "🚨 需要立即修复的问题:",
                ""
            ])
            for item in fail_items:
                summary_lines.append(f"  ✗ {item.get('Category', '')} - {item.get('Item', '')}")
                summary_lines.append(f"    {item.get('Details', '')}")
                if item.get('Suggestion'):
                    summary_lines.append(f"    💡 {item.get('Suggestion')}")
                summary_lines.append("")
        
        # 添加警告项
        warn_items = [r for r in results if r.get('Status') == 'WARN']
        if warn_items:
            summary_lines.extend([
                "⚠️ 需要关注的问题:",
                ""
            ])
            for item in warn_items[:5]:  # 只显示前5个警告
                summary_lines.append(f"  ⚠ {item.get('Category', '')} - {item.get('Item', '')}")
                summary_lines.append(f"    {item.get('Details', '')}")
                summary_lines.append("")
        
        summary_lines.extend([
            "=" * 60,
            "详细报告请查看: go_live_checklist.html",
            "=" * 60
        ])
        
        # 保存摘要文件
        summary_file = output_dir / "go_live_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(summary_lines))
        
        logger.info(f"文本摘要已生成: {summary_file}")
        return summary_file


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="生成Go-Live预检报告")
    parser.add_argument("--results", required=True, help="检查结果JSON文件路径")
    parser.add_argument("--output", required=True, help="输出目录")
    
    args = parser.parse_args()
    
    setup_logging()
    
    try:
        generator = GoLiveReportGenerator()
        
        # 加载结果
        results_file = Path(args.results)
        results = generator.load_results(results_file)
        
        # 创建输出目录
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成报告
        html_file = generator.generate_html_report(results, output_dir)
        summary_file = generator.generate_text_summary(results, output_dir)
        
        print(f"✅ 报告生成完成:")
        print(f"   HTML报告: {html_file}")
        print(f"   文本摘要: {summary_file}")
        
        return 0
        
    except Exception as e:
        logger.error(f"报告生成失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
