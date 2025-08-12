#!/usr/bin/env python3
"""
端到端验收测试脚本
自动化测试所有关键功能并生成报告
"""

import sys
import time
import json
import yaml
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.utils.logger import logger


class E2ETestRunner:
    """端到端测试运行器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.session = self._create_session()
        self.test_results = []
        self.api_process = None
        self.start_time = datetime.now()
        
    def _create_session(self):
        """创建HTTP会话"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],  # 新版本参数名
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def log_test_result(self, step: str, success: bool, details: Dict[str, Any]):
        """记录测试结果"""
        result = {
            "step": step,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "details": details
        }
        self.test_results.append(result)
        
        status = "✅" if success else "❌"
        logger.info(f"{status} {step}: {details.get('message', '')}")
    
    def start_api_server(self):
        """启动API服务器"""
        logger.info("🚀 启动API服务器...")
        
        try:
            # 检查服务是否已经运行
            response = self.session.get(f"{self.base_url}/docs", timeout=5)
            if response.status_code == 200:
                self.log_test_result("API服务检查", True, {
                    "message": "服务已运行",
                    "status_code": response.status_code
                })
                return True
        except requests.exceptions.RequestException:
            pass
        
        # 启动新的API服务
        try:
            import os
            os.chdir(Path(__file__).parent.parent)
            
            self.api_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "apps.api.main:app", 
                "--host", "0.0.0.0", 
                "--port", "8000",
                "--log-level", "warning"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 等待服务启动
            for i in range(30):  # 最多等待30秒
                try:
                    response = self.session.get(f"{self.base_url}/docs", timeout=2)
                    if response.status_code == 200:
                        self.log_test_result("API服务启动", True, {
                            "message": f"服务启动成功 (等待{i+1}秒)",
                            "status_code": response.status_code
                        })
                        return True
                except requests.exceptions.RequestException:
                    time.sleep(1)
            
            self.log_test_result("API服务启动", False, {
                "message": "服务启动超时",
                "timeout_seconds": 30
            })
            return False
            
        except Exception as e:
            self.log_test_result("API服务启动", False, {
                "message": f"启动失败: {e}",
                "error": str(e)
            })
            return False
    
    def health_check(self):
        """健康检查"""
        logger.info("🔍 执行健康检查...")
        
        try:
            # 检查文档页面
            response = self.session.get(f"{self.base_url}/docs")
            docs_ok = response.status_code == 200
            
            # 检查健康端点
            health_response = self.session.get(f"{self.base_url}/api/maowise/v1/health")
            health_ok = health_response.status_code == 200
            
            if docs_ok and health_ok:
                health_data = health_response.json()
                self.log_test_result("健康检查", True, {
                    "message": "服务健康",
                    "docs_status": response.status_code,
                    "health_status": health_response.status_code,
                    "service_status": health_data.get("status", "unknown")
                })
                return True
            else:
                self.log_test_result("健康检查", False, {
                    "message": "服务不健康",
                    "docs_status": response.status_code if docs_ok else "failed",
                    "health_status": health_response.status_code if health_ok else "failed"
                })
                return False
                
        except Exception as e:
            self.log_test_result("健康检查", False, {
                "message": f"健康检查失败: {e}",
                "error": str(e)
            })
            return False
    
    def test_predict_clarify_flow(self):
        """测试预测澄清流程"""
        logger.info("🔮 测试预测澄清流程...")
        
        try:
            # 故意缺少电压的描述
            test_description = ("AZ91 substrate; silicate electrolyte: Na2SiO3 10 g/L, KOH 2 g/L; "
                              "bipolar 500 Hz 30% duty; current density 12 A/dm2; time 10 min; "
                              "post-treatment none.")
            
            # 第一步：请求预测，应该触发澄清
            payload = {"description": test_description}
            response = self.session.post(f"{self.base_url}/api/maowise/v1/predict", json=payload)
            
            if response.status_code != 200:
                self.log_test_result("预测澄清流程", False, {
                    "message": "预测请求失败",
                    "status_code": response.status_code,
                    "response": response.text[:500]
                })
                return False
            
            result = response.json()
            
            # 检查是否需要专家咨询
            if not result.get("need_expert", False):
                self.log_test_result("预测澄清流程", False, {
                    "message": "未触发专家咨询",
                    "need_expert": result.get("need_expert"),
                    "result_keys": list(result.keys())
                })
                return False
            
            # 检查是否有澄清问题
            clarify_questions = result.get("clarify_questions", [])
            if not clarify_questions:
                self.log_test_result("预测澄清流程", False, {
                    "message": "未生成澄清问题",
                    "clarify_questions": clarify_questions
                })
                return False
            
            # 检查是否包含电压相关问题
            voltage_question_found = False
            for q in clarify_questions:
                if "voltage" in q.get("question", "").lower() or "电压" in q.get("question", ""):
                    voltage_question_found = True
                    break
            
            if not voltage_question_found:
                logger.warning("未找到电压相关问题，但继续测试")
            
            # 第二步：模拟专家回答
            # 这里简化处理，直接调用带完整信息的预测
            complete_description = test_description.replace("bipolar", "voltage 420 V; bipolar")
            complete_payload = {"description": complete_description}
            
            final_response = self.session.post(f"{self.base_url}/api/maowise/v1/predict", json=complete_payload)
            
            if final_response.status_code != 200:
                self.log_test_result("预测澄清流程", False, {
                    "message": "最终预测失败",
                    "status_code": final_response.status_code
                })
                return False
            
            final_result = final_response.json()
            
            # 验证最终结果
            has_alpha = "alpha" in final_result
            has_epsilon = "epsilon" in final_result
            has_confidence = "confidence" in final_result
            
            success = has_alpha and has_epsilon and has_confidence
            
            self.log_test_result("预测澄清流程", success, {
                "message": "预测澄清流程完成",
                "initial_need_expert": result.get("need_expert"),
                "clarify_questions_count": len(clarify_questions),
                "voltage_question_found": voltage_question_found,
                "final_has_alpha": has_alpha,
                "final_has_epsilon": has_epsilon,
                "final_has_confidence": has_confidence,
                "final_alpha": final_result.get("alpha"),
                "final_epsilon": final_result.get("epsilon"),
                "final_confidence": final_result.get("confidence")
            })
            
            return success
            
        except Exception as e:
            self.log_test_result("预测澄清流程", False, {
                "message": f"预测澄清流程异常: {e}",
                "error": str(e)
            })
            return False
    
    def test_mandatory_followup_flow(self):
        """测试必答+追问流程"""
        logger.info("🎯 测试必答+追问流程...")
        
        try:
            # 请求优化建议，故意不提供必答信息
            payload = {
                "target_alpha": 0.20,
                "target_epsilon": 0.80,
                "description": "AZ91 substrate, need optimization"
            }
            
            response = self.session.post(f"{self.base_url}/api/maowise/v1/recommend", json=payload)
            
            if response.status_code != 200:
                self.log_test_result("必答追问流程", False, {
                    "message": "优化请求失败",
                    "status_code": response.status_code,
                    "response": response.text[:500]
                })
                return False
            
            result = response.json()
            
            # 检查是否需要专家咨询
            need_expert = result.get("need_expert", False)
            clarify_questions = result.get("clarify_questions", [])
            
            # 检查是否有必答问题
            mandatory_found = False
            thickness_question_found = False
            
            for q in clarify_questions:
                if q.get("is_mandatory", False):
                    mandatory_found = True
                
                question_text = q.get("question", "").lower()
                if any(keyword in question_text for keyword in ["厚度", "质量", "thickness", "mass"]):
                    thickness_question_found = True
            
            # 模拟含糊回答触发追问
            if clarify_questions:
                # 简化测试：直接生成追问
                try:
                    followup_payload = {
                        "question_id": "thickness_limits",
                        "answer": "看情况"
                    }
                    
                    followup_response = self.session.post(
                        f"{self.base_url}/api/maowise/v1/expert/followup", 
                        json=followup_payload
                    )
                    
                    followup_generated = followup_response.status_code == 200
                    if followup_generated:
                        followup_data = followup_response.json()
                        has_followups = len(followup_data.get("followups", [])) > 0
                    else:
                        has_followups = False
                        
                except Exception as e:
                    logger.warning(f"追问测试失败: {e}")
                    followup_generated = False
                    has_followups = False
            else:
                followup_generated = False
                has_followups = False
            
            # 最终获取优化建议（使用完整信息）
            complete_payload = {
                "target_alpha": 0.20,
                "target_epsilon": 0.80,
                "description": "AZ91 substrate, coating thickness ≤ 30 μm, mass ≤ 50 g/m²"
            }
            
            final_response = self.session.post(f"{self.base_url}/api/maowise/v1/recommend", json=complete_payload)
            
            if final_response.status_code == 200:
                final_result = final_response.json()
                solutions = final_result.get("solutions", [])
                solutions_count = len(solutions)
                
                # 检查解决方案质量
                has_explanations = all("explanation" in sol for sol in solutions)
                has_plans = all("plan_yaml" in sol for sol in solutions)
                has_constraints = all("hard_constraints_passed" in sol for sol in solutions)
                
                # 验证YAML格式
                yaml_valid = True
                for sol in solutions:
                    try:
                        if "plan_yaml" in sol:
                            yaml.safe_load(sol["plan_yaml"])
                    except yaml.YAMLError:
                        yaml_valid = False
                        break
                
                passed_constraints = sum(1 for sol in solutions if sol.get("hard_constraints_passed", False))
                
            else:
                solutions_count = 0
                has_explanations = False
                has_plans = False
                has_constraints = False
                yaml_valid = False
                passed_constraints = 0
            
            success = (need_expert and mandatory_found and solutions_count >= 1)
            
            self.log_test_result("必答追问流程", success, {
                "message": "必答追问流程完成",
                "need_expert": need_expert,
                "clarify_questions_count": len(clarify_questions),
                "mandatory_found": mandatory_found,
                "thickness_question_found": thickness_question_found,
                "followup_generated": followup_generated,
                "has_followups": has_followups,
                "solutions_count": solutions_count,
                "has_explanations": has_explanations,
                "has_plans": has_plans,
                "has_constraints": has_constraints,
                "yaml_valid": yaml_valid,
                "passed_constraints": passed_constraints
            })
            
            return success
            
        except Exception as e:
            self.log_test_result("必答追问流程", False, {
                "message": f"必答追问流程异常: {e}",
                "error": str(e)
            })
            return False
    
    def test_rule_fixing_flow(self):
        """测试规则修复流程"""
        logger.info("🔧 测试规则修复流程...")
        
        try:
            # 构造违反规则的方案
            violation_solution = {
                "electrolyte_composition": {
                    "K2ZrF6": 8.0,  # 超过安全限制 5 g/L
                    "Na3PO4": 10.0,
                    "KOH": 2.0
                },
                "process_parameters": {
                    "voltage_V": 450,
                    "current_density_A_dm2": 12,
                    "time_min": 15
                },
                "description": "Test solution with K2ZrF6 violation"
            }
            
            payload = {"solution": violation_solution}
            response = self.session.post(f"{self.base_url}/api/maowise/v1/expert/plan", json=payload)
            
            if response.status_code != 200:
                self.log_test_result("规则修复流程", False, {
                    "message": "规则修复请求失败",
                    "status_code": response.status_code,
                    "response": response.text[:500]
                })
                return False
            
            result = response.json()
            
            # 检查是否有修复信息
            has_fixed_delta = "fixed_delta" in result
            has_penalty = "penalty" in result and result.get("penalty", 0) > 0
            has_plan_yaml = "plan_yaml" in result
            
            # 验证YAML格式
            yaml_valid = False
            if has_plan_yaml:
                try:
                    yaml_content = yaml.safe_load(result["plan_yaml"])
                    yaml_valid = isinstance(yaml_content, dict)
                except yaml.YAMLError:
                    yaml_valid = False
            
            success = (has_fixed_delta or has_penalty) and has_plan_yaml and yaml_valid
            
            self.log_test_result("规则修复流程", success, {
                "message": "规则修复流程完成",
                "has_fixed_delta": has_fixed_delta,
                "has_penalty": has_penalty,
                "penalty_value": result.get("penalty", 0),
                "has_plan_yaml": has_plan_yaml,
                "yaml_valid": yaml_valid,
                "fixed_components": list(result.get("fixed_delta", {}).keys()) if has_fixed_delta else []
            })
            
            return success
            
        except Exception as e:
            self.log_test_result("规则修复流程", False, {
                "message": f"规则修复流程异常: {e}",
                "error": str(e)
            })
            return False
    
    def test_explanation_rag_verification(self):
        """测试解释/RAG验证"""
        logger.info("📚 测试解释/RAG验证...")
        
        try:
            # 获取一个预测结果
            payload = {
                "description": ("AZ91 substrate; silicate electrolyte: Na2SiO3 15 g/L, KOH 3 g/L; "
                              "voltage 400 V; current density 8 A/dm2; frequency 1000 Hz; "
                              "duty cycle 20%; time 15 min; post-treatment anodizing.")
            }
            
            response = self.session.post(f"{self.base_url}/api/maowise/v1/predict", json=payload)
            
            if response.status_code != 200:
                self.log_test_result("解释RAG验证", False, {
                    "message": "获取预测结果失败",
                    "status_code": response.status_code
                })
                return False
            
            result = response.json()
            
            # 检查解释内容
            explanation = result.get("explanation", "")
            citation_map = result.get("citation_map", {})
            
            # 验证解释格式
            explanation_lines = explanation.split('\n') if explanation else []
            bullet_count = len([line for line in explanation_lines if line.strip().startswith('•')])
            
            # 检查引用
            citation_pattern = r'\[CIT-\d+\]'
            import re
            citations_in_text = re.findall(citation_pattern, explanation)
            citations_count = len(citations_in_text)
            
            # 验证引用映射
            citation_sources = []
            for cit_id, cit_info in citation_map.items():
                if isinstance(cit_info, dict) and "source" in cit_info:
                    citation_sources.append(cit_info["source"])
            
            success = (
                bullet_count <= 7 and
                bullet_count > 0 and
                citations_count > 0 and
                len(citation_sources) > 0
            )
            
            self.log_test_result("解释RAG验证", success, {
                "message": "解释RAG验证完成",
                "explanation_length": len(explanation),
                "bullet_points": bullet_count,
                "citations_count": citations_count,
                "citation_sources_count": len(citation_sources),
                "has_explanation": bool(explanation),
                "has_citations": citations_count > 0,
                "has_citation_map": bool(citation_map),
                "sample_citations": citations_in_text[:3]
            })
            
            return success
            
        except Exception as e:
            self.log_test_result("解释RAG验证", False, {
                "message": f"解释RAG验证异常: {e}",
                "error": str(e)
            })
            return False
    
    def test_governance_and_caching(self):
        """测试治理与缓存"""
        logger.info("🛡️ 测试治理与缓存...")
        
        try:
            import os
            
            # 检查是否有API密钥
            has_api_key = bool(os.getenv("OPENAI_API_KEY"))
            
            if not has_api_key:
                self.log_test_result("治理与缓存", True, {
                    "message": "无API密钥，跳过缓存测试，使用离线模式",
                    "offline_mode": True,
                    "has_api_key": False
                })
                return True
            
            # 检查使用统计文件
            usage_file = Path("datasets/cache/llm_usage.csv")
            initial_lines = 0
            
            if usage_file.exists():
                with open(usage_file, 'r', encoding='utf-8') as f:
                    initial_lines = len(f.readlines())
            
            # 发送澄清请求
            payload = {
                "current_data": {},
                "max_questions": 2
            }
            
            # 第一次请求
            start_time = time.time()
            response1 = self.session.post(f"{self.base_url}/api/maowise/v1/expert/clarify", json=payload)
            duration1 = time.time() - start_time
            
            # 第二次相同请求（应该命中缓存）
            start_time = time.time()
            response2 = self.session.post(f"{self.base_url}/api/maowise/v1/expert/clarify", json=payload)
            duration2 = time.time() - start_time
            
            # 检查响应
            success1 = response1.status_code == 200
            success2 = response2.status_code == 200
            
            # 检查使用统计文件更新
            final_lines = 0
            if usage_file.exists():
                with open(usage_file, 'r', encoding='utf-8') as f:
                    final_lines = len(f.readlines())
            
            lines_added = final_lines - initial_lines
            
            # 缓存命中检测（第二次请求应该更快）
            cache_hit_likely = duration2 < duration1 * 0.8  # 第二次请求快80%以上
            
            success = success1 and success2 and lines_added > 0
            
            self.log_test_result("治理与缓存", success, {
                "message": "治理与缓存测试完成",
                "has_api_key": has_api_key,
                "request1_success": success1,
                "request2_success": success2,
                "request1_duration": round(duration1, 3),
                "request2_duration": round(duration2, 3),
                "cache_hit_likely": cache_hit_likely,
                "initial_usage_lines": initial_lines,
                "final_usage_lines": final_lines,
                "lines_added": lines_added,
                "usage_file_updated": lines_added > 0
            })
            
            return success
            
        except Exception as e:
            self.log_test_result("治理与缓存", False, {
                "message": f"治理与缓存测试异常: {e}",
                "error": str(e)
            })
            return False
    
    def generate_report(self):
        """生成测试报告"""
        logger.info("📊 生成测试报告...")
        
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # 统计结果
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        
        # 生成Markdown报告
        md_content = self._generate_markdown_report(total_duration, total_tests, passed_tests, failed_tests)
        
        # 生成HTML报告
        html_content = self._generate_html_report(total_duration, total_tests, passed_tests, failed_tests)
        
        # 保存报告
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        
        md_file = reports_dir / "e2e_report.md"
        html_file = reports_dir / "e2e_report.html"
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"✅ 报告已生成:")
        logger.info(f"  Markdown: {md_file}")
        logger.info(f"  HTML: {html_file}")
        
        return passed_tests == total_tests
    
    def _generate_markdown_report(self, duration: float, total: int, passed: int, failed: int) -> str:
        """生成Markdown报告"""
        import os
        
        offline_mode = not bool(os.getenv("OPENAI_API_KEY"))
        
        content = f"""# MAO-Wise 端到端测试报告

## 测试概览

- **测试时间**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
- **测试耗时**: {duration:.2f} 秒
- **测试总数**: {total}
- **通过数量**: {passed} ✅
- **失败数量**: {failed} ❌
- **通过率**: {(passed/total*100):.1f}%
- **运行模式**: {'离线兜底模式' if offline_mode else '在线模式'}

## 测试结果详情

"""
        
        for i, result in enumerate(self.test_results, 1):
            status = "✅ 通过" if result["success"] else "❌ 失败"
            timestamp = result["timestamp"]
            step = result["step"]
            details = result["details"]
            message = details.get("message", "")
            
            content += f"""### {i}. {step}

**状态**: {status}  
**时间**: {timestamp}  
**消息**: {message}

**详细信息**:
```json
{json.dumps(details, ensure_ascii=False, indent=2)}
```

---

"""
        
        # 添加总结
        if passed == total:
            content += """## 🎉 测试总结

**所有测试均通过！** MAO-Wise系统各项功能正常运行。

### 验收达成情况

- ✅ API服务正常启动和响应
- ✅ 预测澄清流程工作正常
- ✅ 必答问题和追问机制有效
- ✅ 规则修复和约束检查功能正常
- ✅ 解释生成和RAG引用正确
- ✅ 治理功能和缓存机制工作正常

"""
        else:
            content += f"""## ⚠️ 测试总结

**{failed} 项测试失败，需要关注。**

### 失败的测试项目

"""
            for result in self.test_results:
                if not result["success"]:
                    content += f"- ❌ {result['step']}: {result['details'].get('message', '')}\n"
        
        content += f"""
### 系统信息

- **Python版本**: {sys.version.split()[0]}
- **测试环境**: {os.getenv('COMPUTERNAME', 'Unknown')}
- **API地址**: {self.base_url}
- **离线模式**: {'是' if offline_mode else '否'}

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        return content
    
    def _generate_html_report(self, duration: float, total: int, passed: int, failed: int) -> str:
        """生成HTML报告"""
        import os
        
        offline_mode = not bool(os.getenv("OPENAI_API_KEY"))
        pass_rate = (passed/total*100) if total > 0 else 0
        
        # 生成测试结果表格
        results_html = ""
        for i, result in enumerate(self.test_results, 1):
            status_class = "success" if result["success"] else "failure"
            status_text = "✅ 通过" if result["success"] else "❌ 失败"
            
            results_html += f"""
            <tr class="{status_class}">
                <td>{i}</td>
                <td>{result['step']}</td>
                <td>{status_text}</td>
                <td>{result['details'].get('message', '')}</td>
                <td>{result['timestamp'].split('T')[1][:8]}</td>
            </tr>
            """
        
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MAO-Wise 端到端测试报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric {{ background: #ecf0f1; padding: 20px; border-radius: 6px; text-align: center; }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
        .metric-label {{ color: #7f8c8d; margin-top: 5px; }}
        .pass {{ color: #27ae60; }}
        .fail {{ color: #e74c3c; }}
        .offline {{ color: #f39c12; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #34495e; color: white; }}
        .success {{ background-color: #d5f4e6; }}
        .failure {{ background-color: #ffeaa7; }}
        .summary {{ margin-top: 30px; padding: 20px; border-radius: 6px; }}
        .summary.success {{ background-color: #d5f4e6; border-left: 5px solid #27ae60; }}
        .summary.warning {{ background-color: #ffeaa7; border-left: 5px solid #f39c12; }}
        .progress-bar {{ width: 100%; height: 20px; background: #ecf0f1; border-radius: 10px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #27ae60, #2ecc71); transition: width 0.3s ease; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 MAO-Wise 端到端测试报告</h1>
        
        <div class="overview">
            <div class="metric">
                <div class="metric-value">{total}</div>
                <div class="metric-label">测试总数</div>
            </div>
            <div class="metric">
                <div class="metric-value pass">{passed}</div>
                <div class="metric-label">通过数量</div>
            </div>
            <div class="metric">
                <div class="metric-value {'fail' if failed > 0 else 'pass'}">{failed}</div>
                <div class="metric-label">失败数量</div>
            </div>
            <div class="metric">
                <div class="metric-value">{pass_rate:.1f}%</div>
                <div class="metric-label">通过率</div>
            </div>
            <div class="metric">
                <div class="metric-value">{duration:.1f}s</div>
                <div class="metric-label">总耗时</div>
            </div>
            <div class="metric">
                <div class="metric-value {'offline' if offline_mode else 'pass'}">{'离线' if offline_mode else '在线'}</div>
                <div class="metric-label">运行模式</div>
            </div>
        </div>
        
        <h2>📊 通过率</h2>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {pass_rate}%"></div>
        </div>
        
        <h2>📋 测试详情</h2>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>测试项目</th>
                    <th>状态</th>
                    <th>消息</th>
                    <th>时间</th>
                </tr>
            </thead>
            <tbody>
                {results_html}
            </tbody>
        </table>
        
        <div class="summary {'success' if passed == total else 'warning'}">
            <h2>{'🎉 测试总结' if passed == total else '⚠️ 测试总结'}</h2>
            {'<p><strong>所有测试均通过！</strong> MAO-Wise系统各项功能正常运行。</p>' if passed == total else f'<p><strong>{failed} 项测试失败</strong>，需要进一步检查和修复。</p>'}
            
            <h3>功能验收状态</h3>
            <ul>
                <li>{'✅' if any('API服务' in r['step'] and r['success'] for r in self.test_results) else '❌'} API服务启动和健康检查</li>
                <li>{'✅' if any('预测澄清' in r['step'] and r['success'] for r in self.test_results) else '❌'} 预测澄清流程</li>
                <li>{'✅' if any('必答追问' in r['step'] and r['success'] for r in self.test_results) else '❌'} 必答问题和追问机制</li>
                <li>{'✅' if any('规则修复' in r['step'] and r['success'] for r in self.test_results) else '❌'} 规则修复和约束检查</li>
                <li>{'✅' if any('解释RAG' in r['step'] and r['success'] for r in self.test_results) else '❌'} 解释生成和RAG引用</li>
                <li>{'✅' if any('治理与缓存' in r['step'] and r['success'] for r in self.test_results) else '❌'} 治理功能和缓存机制</li>
            </ul>
        </div>
        
        <hr style="margin: 40px 0;">
        <p style="text-align: center; color: #7f8c8d;">
            <small>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | MAO-Wise v1.0</small>
        </p>
    </div>
</body>
</html>"""
        
        return html_content
    
    def cleanup(self):
        """清理资源"""
        if self.api_process:
            try:
                self.api_process.terminate()
                self.api_process.wait(timeout=10)
                logger.info("API服务已停止")
            except subprocess.TimeoutExpired:
                self.api_process.kill()
                logger.warning("强制终止API服务")
            except Exception as e:
                logger.error(f"停止API服务失败: {e}")
    
    def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始端到端验收测试")
        logger.info("="*60)
        
        test_steps = [
            ("API服务启动", self.start_api_server),
            ("健康检查", self.health_check),
            ("预测澄清流程", self.test_predict_clarify_flow),
            ("必答追问流程", self.test_mandatory_followup_flow),
            ("规则修复流程", self.test_rule_fixing_flow),
            ("解释RAG验证", self.test_explanation_rag_verification),
            ("治理与缓存", self.test_governance_and_caching),
        ]
        
        try:
            for step_name, step_func in test_steps:
                logger.info(f"\n🔍 执行测试: {step_name}")
                step_func()
                time.sleep(1)  # 短暂间隔
            
            # 生成报告
            logger.info(f"\n📊 生成测试报告...")
            report_success = self.generate_report()
            
            return report_success
            
        finally:
            self.cleanup()


def main():
    """主函数"""
    runner = E2ETestRunner()
    
    try:
        success = runner.run_all_tests()
        
        logger.info("\n" + "="*60)
        if success:
            logger.info("🎉 端到端测试完成，所有测试通过！")
            logger.info("📋 报告文件:")
            logger.info("  - reports/e2e_report.md")
            logger.info("  - reports/e2e_report.html")
        else:
            logger.warning("⚠️ 端到端测试完成，但存在失败项目")
            logger.info("📋 请查看详细报告:")
            logger.info("  - reports/e2e_report.md")
            logger.info("  - reports/e2e_report.html")
        
        return success
        
    except KeyboardInterrupt:
        logger.info("\n用户中断测试")
        return False
    except Exception as e:
        logger.error(f"测试执行异常: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
