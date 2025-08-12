#!/usr/bin/env python3
"""
测试批量实验方案生成器

验证功能：
- 能生成 CSV + 若干 YAML 文件
- CSV 中 hard_constraints_passed 至少有 1 条为 True
- 若触发 clarifying 则 pending_questions_*.json 存在
- 支持离线兜底模式
- 统计摘要正确生成
"""

import pytest
import json
import csv
import yaml
import tempfile
import shutil
import pathlib
import sys
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# 确保能找到maowise包
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_batch_plans import BatchPlanGenerator, PlanResult, BatchSummary
from apps.api.main import app

class TestBatchPlanGenerator:
    """批量方案生成器测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录fixture"""
        temp_dir = tempfile.mkdtemp()
        yield pathlib.Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_generator(self, temp_dir):
        """模拟生成器fixture"""
        with patch('scripts.generate_batch_plans.REPO_ROOT', temp_dir):
            # 创建必要目录
            (temp_dir / "maowise" / "config").mkdir(parents=True)
            (temp_dir / "tasks").mkdir(parents=True)
            (temp_dir / "manifests").mkdir(parents=True)
            
            # 创建预设配置文件
            presets_content = {
                "silicate": {
                    "bounds": {
                        "voltage_V": [200, 520],
                        "current_density_Adm2": [5, 15],
                        "frequency_Hz": [200, 1500],
                        "duty_cycle_pct": [20, 45],
                        "time_min": [5, 40],
                        "pH": [10, 13]
                    },
                    "additives": {
                        "allowed": ["Na2SiO3", "KOH", "KF"],
                        "forbid": ["Cr6+", "HF"]
                    }
                },
                "zirconate": {
                    "bounds": {
                        "voltage_V": [180, 500],
                        "current_density_Adm2": [4, 12],
                        "frequency_Hz": [200, 1200],
                        "duty_cycle_pct": [20, 40],
                        "time_min": [4, 30],
                        "pH": [9, 12]
                    },
                    "additives": {
                        "allowed": ["K2ZrF6", "Na2SiO3", "KOH"],
                        "forbid": ["Cr6+"]
                    }
                }
            }
            
            with open(temp_dir / "maowise" / "config" / "presets.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(presets_content, f)
            
            generator = BatchPlanGenerator()
            generator.tasks_dir = temp_dir / "tasks"
            generator.manifests_dir = temp_dir / "manifests"
            
            return generator
    
    def test_load_presets(self, mock_generator):
        """测试预设配置加载"""
        assert "silicate" in mock_generator.presets
        assert "zirconate" in mock_generator.presets
        assert "voltage_V" in mock_generator.presets["silicate"]["bounds"]
        assert "K2ZrF6" in mock_generator.presets["zirconate"]["additives"]["allowed"]
    
    def test_generate_plan_description(self, mock_generator):
        """测试方案描述生成"""
        bounds = mock_generator.presets["silicate"]["bounds"]
        description = mock_generator._generate_plan_description("silicate", bounds, 42)
        
        assert "substrate" in description
        assert "electrolyte" in description
        assert "V;" in description
        assert "A/dm2;" in description
        
        # 测试锆盐体系
        bounds = mock_generator.presets["zirconate"]["bounds"]
        description = mock_generator._generate_plan_description("zirconate", bounds, 42)
        assert "K2ZrF6" in description or "zirconate" in description
    
    @patch('scripts.generate_batch_plans.httpx.Client')
    def test_api_call_success(self, mock_client, mock_generator):
        """测试API调用成功"""
        # 模拟成功响应
        mock_response = Mock()
        mock_response.json.return_value = {
            "need_expert": False,
            "suggestions": [{
                "alpha": 0.22,
                "epsilon": 0.82,
                "confidence": 0.75,
                "hard_constraints_passed": True,
                "rule_penalty": 2.0,
                "reward_score": 0.8,
                "plan_yaml": "description: 'test plan'",
                "citations": ["ref1", "ref2"]
            }]
        }
        mock_response.raise_for_status.return_value = None
        
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        result = mock_generator._call_recommend_api("test description", 0.20, 0.80)
        
        assert not result["need_expert"]
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["alpha"] == 0.22
    
    @patch('scripts.generate_batch_plans.httpx.Client')
    def test_api_call_expert_needed(self, mock_client, mock_generator):
        """测试需要专家回答的情况"""
        # 模拟需要专家回答的响应
        mock_response = Mock()
        mock_response.json.return_value = {
            "need_expert": True,
            "clarifying_questions": [
                "What is the substrate surface preparation method?",
                "What is the desired coating thickness?"
            ]
        }
        mock_response.raise_for_status.return_value = None
        
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        result = mock_generator._call_recommend_api("test description", 0.20, 0.80)
        
        assert result["need_expert"]
        assert len(result["clarifying_questions"]) == 2
    
    @patch('scripts.generate_batch_plans.httpx.Client')
    def test_api_call_failure_fallback(self, mock_client, mock_generator):
        """测试API调用失败时的兜底响应"""
        # 模拟API调用失败
        mock_client_instance = Mock()
        mock_client_instance.post.side_effect = Exception("Connection failed")
        mock_client.return_value = mock_client_instance
        
        result = mock_generator._call_recommend_api("test description", 0.20, 0.80)
        
        # 应该返回兜底响应
        assert not result["need_expert"]
        assert len(result["suggestions"]) == 1
        assert "alpha" in result["suggestions"][0]
    
    @patch('scripts.generate_batch_plans.httpx.Client')
    def test_generate_batch_success(self, mock_client, mock_generator):
        """测试批次生成成功"""
        # 模拟API成功响应
        mock_response = Mock()
        mock_response.json.return_value = {
            "need_expert": False,
            "suggestions": [{
                "alpha": 0.21,
                "epsilon": 0.81,
                "confidence": 0.7,
                "hard_constraints_passed": True,
                "rule_penalty": 1.5,
                "reward_score": 0.75,
                "plan_yaml": "description: 'generated plan'",
                "citations": ["ref1", "ref2", "ref3"]
            }]
        }
        mock_response.raise_for_status.return_value = None
        
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        batch_id, plans, summary = mock_generator.generate_batch(
            system="silicate",
            n=3,
            target_alpha=0.20,
            target_epsilon=0.80,
            seed=42,
            notes="Test batch"
        )
        
        # 验证结果
        assert batch_id.startswith("batch_")
        assert len(plans) == 3
        assert all(plan.status == "success" for plan in plans)
        assert all(plan.hard_constraints_passed for plan in plans)
        
        # 验证摘要
        assert summary.total_plans == 3
        assert summary.successful_plans == 3
        assert summary.pending_expert_plans == 0
        assert summary.hard_constraints_pass_rate == 1.0
        assert summary.system == "silicate"
    
    @patch('scripts.generate_batch_plans.httpx.Client')
    def test_generate_batch_with_expert_questions(self, mock_client, mock_generator):
        """测试生成包含专家问题的批次"""
        # 模拟部分需要专家回答
        call_count = 0
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = Mock()
            if call_count == 1:
                # 第一次调用需要专家回答
                mock_response.json.return_value = {
                    "need_expert": True,
                    "clarifying_questions": ["What is the substrate?"]
                }
            else:
                # 其他调用正常
                mock_response.json.return_value = {
                    "need_expert": False,
                    "suggestions": [{
                        "alpha": 0.20,
                        "epsilon": 0.80,
                        "confidence": 0.6,
                        "hard_constraints_passed": True,
                        "rule_penalty": 2.0,
                        "reward_score": 0.6,
                        "plan_yaml": "description: 'normal plan'",
                        "citations": ["ref1"]
                    }]
                }
            mock_response.raise_for_status.return_value = None
            return mock_response
        
        mock_client_instance = Mock()
        mock_client_instance.post.side_effect = mock_post
        mock_client.return_value = mock_client_instance
        
        batch_id, plans, summary = mock_generator.generate_batch(
            system="silicate",
            n=3,
            target_alpha=0.20,
            target_epsilon=0.80,
            seed=42
        )
        
        # 验证结果
        assert len(plans) == 3
        assert summary.pending_expert_plans == 1
        assert summary.successful_plans == 2
        
        # 验证专家问题文件存在
        questions_file = mock_generator.manifests_dir / f"pending_questions_{batch_id}.json"
        assert questions_file.exists()
        
        with open(questions_file, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        assert len(questions) == 1
        assert "What is the substrate?" in questions[0]["questions"]
    
    def test_export_batch(self, mock_generator):
        """测试批次导出功能"""
        # 创建测试数据
        batch_id = "batch_20240101_1200"
        plans = [
            PlanResult(
                plan_id=f"{batch_id}_plan_001",
                batch_id=batch_id,
                system="silicate",
                alpha=0.21,
                epsilon=0.81,
                confidence=0.75,
                hard_constraints_passed=True,
                rule_penalty=1.5,
                reward_score=0.8,
                plan_yaml="description: 'test plan 1'",
                citations=["ref1", "ref2"],
                citations_count=2,
                created_at="2024-01-01T12:00:00",
                status="success"
            ),
            PlanResult(
                plan_id=f"{batch_id}_plan_002",
                batch_id=batch_id,
                system="silicate",
                alpha=0.0,
                epsilon=0.0,
                confidence=0.0,
                hard_constraints_passed=False,
                rule_penalty=999.0,
                reward_score=0.0,
                plan_yaml="description: 'pending plan'",
                citations=[],
                citations_count=0,
                created_at="2024-01-01T12:01:00",
                status="pending_expert",
                expert_questions=["What is the substrate?"]
            )
        ]
        
        summary = BatchSummary(
            batch_id=batch_id,
            system="silicate",
            total_plans=2,
            successful_plans=1,
            pending_expert_plans=1,
            failed_plans=0,
            hard_constraints_pass_rate=0.5,
            avg_alpha=0.21,
            avg_epsilon=0.81,
            avg_confidence=0.75,
            top_citations=[("ref1", 1), ("ref2", 1)],
            generation_time=5.0,
            target_alpha=0.20,
            target_epsilon=0.80,
            notes="Test batch"
        )
        
        # 导出批次
        batch_dir = mock_generator.export_batch(batch_id, plans, summary)
        
        # 验证目录结构
        assert batch_dir.exists()
        assert (batch_dir / "plans.csv").exists()
        assert (batch_dir / "plans_yaml").exists()
        assert (batch_dir / "README.md").exists()
        
        # 验证CSV内容
        with open(batch_dir / "plans.csv", 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 2
        assert rows[0]["hard_constraints_passed"] == "True"
        assert rows[1]["status"] == "pending_expert"
        
        # 验证YAML文件
        yaml_files = list((batch_dir / "plans_yaml").glob("*.yaml"))
        assert len(yaml_files) == 2
        
        # 验证README
        with open(batch_dir / "README.md", 'r', encoding='utf-8') as f:
            readme_content = f.read()
        
        assert batch_id in readme_content
        assert "硬约束通过率: 50.0%" in readme_content
        assert "ref1" in readme_content
    
    def test_generate_summary(self, mock_generator):
        """测试摘要生成"""
        plans = [
            PlanResult(
                plan_id="plan_001", batch_id="batch_test", system="silicate",
                alpha=0.20, epsilon=0.80, confidence=0.7,
                hard_constraints_passed=True, rule_penalty=1.0, reward_score=0.8,
                plan_yaml="test", citations=["ref1", "ref2"], citations_count=2,
                created_at="2024-01-01T12:00:00", status="success"
            ),
            PlanResult(
                plan_id="plan_002", batch_id="batch_test", system="silicate",
                alpha=0.22, epsilon=0.82, confidence=0.8,
                hard_constraints_passed=True, rule_penalty=2.0, reward_score=0.7,
                plan_yaml="test", citations=["ref1", "ref3"], citations_count=2,
                created_at="2024-01-01T12:01:00", status="success"
            ),
            PlanResult(
                plan_id="plan_003", batch_id="batch_test", system="silicate",
                alpha=0.0, epsilon=0.0, confidence=0.0,
                hard_constraints_passed=False, rule_penalty=999.0, reward_score=0.0,
                plan_yaml="test", citations=[], citations_count=0,
                created_at="2024-01-01T12:02:00", status="pending_expert"
            )
        ]
        
        summary = mock_generator._generate_summary(
            "batch_test", "silicate", plans, 0.20, 0.80, 10.0, "Test notes"
        )
        
        assert summary.total_plans == 3
        assert summary.successful_plans == 2
        assert summary.pending_expert_plans == 1
        assert summary.hard_constraints_pass_rate == 2/3  # 2个成功方案都通过硬约束
        assert abs(summary.avg_alpha - 0.21) < 0.001  # (0.20 + 0.22) / 2
        assert summary.avg_epsilon == 0.81  # (0.80 + 0.82) / 2
        assert len(summary.top_citations) == 3  # ref1, ref2, ref3
        assert summary.top_citations[0] == ("ref1", 2)  # ref1出现2次

class TestIntegration:
    """集成测试"""
    
    def test_fastapi_integration(self):
        """测试与FastAPI的集成"""
        client = TestClient(app)
        
        # 测试推荐接口
        response = client.post("/api/maowise/v1/recommend_or_ask", json={
            "description": "AZ91 substrate; silicate electrolyte: Na2SiO3 10 g/L, KOH 2 g/L; bipolar 500 Hz 30% duty; 420 V; 12 A/dm2; 10 min; sealing none.",
            "target_alpha": 0.20,
            "target_epsilon": 0.80
        })
        
        # 接口应该能正常响应
        assert response.status_code == 200
        data = response.json()
        
        # 验证响应格式
        assert "need_expert" in data
        if not data["need_expert"]:
            assert "suggestions" in data
            if data["suggestions"]:
                suggestion = data["suggestions"][0]
                assert "alpha" in suggestion
                assert "epsilon" in suggestion
                assert "confidence" in suggestion

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
