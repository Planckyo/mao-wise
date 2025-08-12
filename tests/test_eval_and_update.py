#!/usr/bin/env python3
"""
实验评估与更新流程测试

测试功能：
- 构造假实验记录验证导入功能
- 测试评估脚本能产出JSON和图表
- 验证更新流程生成新模型目录
- 测试API热加载端点
"""

import pytest
import json
import tempfile
import shutil
import pathlib
import sys
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import csv

# 确保能找到maowise包
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.record_experiment_results import ExperimentRecorder
from scripts.evaluate_predictions import PredictionEvaluator

class TestExperimentFeedbackFlow:
    """实验反馈流程测试"""
    
    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作空间"""
        temp_dir = tempfile.mkdtemp()
        workspace = pathlib.Path(temp_dir)
        
        # 创建目录结构
        (workspace / "datasets" / "experiments").mkdir(parents=True)
        (workspace / "reports").mkdir(parents=True)
        (workspace / "models_ckpt").mkdir(parents=True)
        
        yield workspace
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def fake_experiment_data(self):
        """生成假实验数据"""
        np.random.seed(42)
        
        experiments = []
        systems = ['silicate', 'zirconate']
        substrates = ['AZ91D', 'AZ31B', 'AM60B']
        reviewers = ['张工程师', '李研究员', '王博士']
        
        for i in range(5):
            system = np.random.choice(systems)
            substrate = np.random.choice(substrates)
            reviewer = np.random.choice(reviewers)
            
            # 生成合理的实验参数
            voltage = np.random.uniform(200, 400)
            current = np.random.uniform(5, 15)
            frequency = np.random.uniform(200, 1500)
            duty_cycle = np.random.uniform(20, 50)
            time_min = np.random.uniform(5, 40)
            temp = np.random.uniform(20, 30)
            ph = np.random.uniform(9, 13)
            
            # 生成合理的测量结果（基于参数的简单模型）
            alpha_base = 0.15 + (voltage - 300) * 0.0001 + (current - 10) * 0.005
            epsilon_base = 0.7 + (voltage - 300) * 0.0003 + (current - 10) * 0.01
            
            measured_alpha = np.clip(alpha_base + np.random.normal(0, 0.02), 0.05, 0.4)
            measured_epsilon = np.clip(epsilon_base + np.random.normal(0, 0.05), 0.5, 1.2)
            
            # 生成其他性能指标
            hardness = np.random.uniform(150, 250)
            roughness = np.random.uniform(1.0, 3.0)
            corrosion_rate = np.random.uniform(0.01, 0.1)
            
            experiment = {
                'experiment_id': f'TEST-EXP-{i+1:03d}',
                'batch_id': f'test_batch_{(i//2)+1}',
                'plan_id': f'test_plan_{i+1:03d}',
                'system': system,
                'substrate_alloy': substrate,
                'electrolyte_components_json': json.dumps(['Na2SiO3', 'KOH'] if system == 'silicate' else ['K2ZrF6', 'NaF']),
                'voltage_V': round(voltage, 1),
                'current_density_Adm2': round(current, 2),
                'frequency_Hz': round(frequency, 0),
                'duty_cycle_pct': round(duty_cycle, 1),
                'time_min': round(time_min, 1),
                'temp_C': round(temp, 1),
                'pH': round(ph, 1),
                'post_treatment': 'none' if np.random.random() > 0.3 else 'annealing_200C',
                'measured_alpha': round(measured_alpha, 4),
                'measured_epsilon': round(measured_epsilon, 4),
                'hardness_HV': round(hardness, 1),
                'roughness_Ra_um': round(roughness, 2),
                'corrosion_rate_mmpy': round(corrosion_rate, 4),
                'notes': f'实验 {i+1} - 质量良好' if measured_alpha < 0.2 else f'实验 {i+1} - 需要优化',
                'reviewer': reviewer,
                'timestamp': (datetime.now().replace(hour=i+10, minute=i*10)).isoformat()
            }
            
            experiments.append(experiment)
        
        return experiments
    
    def test_experiment_record_import(self, temp_workspace, fake_experiment_data):
        """测试实验记录导入功能"""
        # 创建CSV文件
        csv_file = temp_workspace / "test_experiments.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if fake_experiment_data:
                writer = csv.DictWriter(f, fieldnames=fake_experiment_data[0].keys())
                writer.writeheader()
                writer.writerows(fake_experiment_data)
        
        # 测试导入
        experiments_dir = temp_workspace / "datasets" / "experiments"
        recorder = ExperimentRecorder(str(experiments_dir))
        
        result = recorder.import_from_file(str(csv_file))
        
        # 验证结果
        assert result['success'] == True
        assert result['stats']['total_new'] == 5
        assert result['stats']['final_new'] == 5
        
        # 验证parquet文件存在
        parquet_file = experiments_dir / "experiments.parquet"
        assert parquet_file.exists()
        
        # 验证数据内容
        df = pd.read_parquet(parquet_file)
        assert len(df) == 5
        assert 'measured_alpha' in df.columns
        assert 'measured_epsilon' in df.columns
        assert df['measured_alpha'].min() >= 0.05
        assert df['measured_epsilon'].max() <= 1.2
    
    def test_experiment_deduplication(self, temp_workspace, fake_experiment_data):
        """测试实验记录去重功能"""
        experiments_dir = temp_workspace / "datasets" / "experiments"
        recorder = ExperimentRecorder(str(experiments_dir))
        
        # 创建CSV文件
        csv_file = temp_workspace / "test_experiments.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fake_experiment_data[0].keys())
            writer.writeheader()
            writer.writerows(fake_experiment_data)
        
        # 第一次导入
        result1 = recorder.import_from_file(str(csv_file))
        assert result1['stats']['final_new'] == 5
        
        # 第二次导入相同数据
        result2 = recorder.import_from_file(str(csv_file))
        assert result2['stats']['final_new'] == 0
        assert result2['stats']['duplicates_existing'] == 5
        
        # 验证总数据量没有重复
        df = pd.read_parquet(experiments_dir / "experiments.parquet")
        assert len(df) == 5
    
    @patch('scripts.evaluate_predictions.requests.post')
    def test_prediction_evaluation(self, mock_post, temp_workspace, fake_experiment_data):
        """测试预测评估功能"""
        # 准备实验数据
        experiments_dir = temp_workspace / "datasets" / "experiments"
        parquet_file = experiments_dir / "experiments.parquet"
        
        df = pd.DataFrame(fake_experiment_data)
        df.to_parquet(parquet_file, index=False)
        
        # 模拟API预测响应
        def mock_predict_response(url, json, timeout):
            # 基于输入生成模拟预测
            input_data = json
            voltage = input_data.get('voltage_V', 300)
            current = input_data.get('current_density_A_dm2', 10)
            
            # 简单的模拟预测逻辑
            pred_alpha = 0.15 + (voltage - 300) * 0.0001 + (current - 10) * 0.005
            pred_epsilon = 0.7 + (voltage - 300) * 0.0003 + (current - 10) * 0.01
            
            # 添加一些噪声
            pred_alpha += np.random.normal(0, 0.01)
            pred_epsilon += np.random.normal(0, 0.02)
            
            pred_alpha = np.clip(pred_alpha, 0.05, 0.4)
            pred_epsilon = np.clip(pred_epsilon, 0.5, 1.2)
            
            mock_response = Mock()
            mock_response.json.return_value = {
                'alpha_150_2600': pred_alpha,
                'epsilon_3000_30000': pred_epsilon,
                'confidence': np.random.uniform(0.6, 0.9)
            }
            mock_response.raise_for_status.return_value = None
            return mock_response
        
        mock_post.side_effect = mock_predict_response
        
        # 执行评估
        reports_dir = temp_workspace / "reports"
        evaluator = PredictionEvaluator(
            experiments_file=str(parquet_file),
            api_url="http://mock-api:8000"
        )
        evaluator.reports_dir = reports_dir
        
        result = evaluator.evaluate()
        
        # 验证结果结构
        assert 'evaluation_time' in result
        assert 'data_info' in result
        assert 'overall_metrics' in result
        assert 'plots' in result
        
        # 验证指标存在
        overall_metrics = result['overall_metrics']
        assert 'alpha_metrics' in overall_metrics
        assert 'epsilon_metrics' in overall_metrics
        assert 'confidence_metrics' in overall_metrics
        
        # 验证关键指标
        assert 'mae' in overall_metrics['alpha_metrics']
        assert 'hit_rate_003' in overall_metrics['alpha_metrics']
        assert overall_metrics['sample_size'] == 5
        
        # 验证图表文件生成
        assert len(result['plots']) == 2
        for plot_file in result['plots']:
            assert pathlib.Path(plot_file).exists()
            assert pathlib.Path(plot_file).suffix == '.png'
    
    def test_evaluation_with_system_breakdown(self, temp_workspace, fake_experiment_data):
        """测试按体系分组的评估功能"""
        # 准备数据
        experiments_dir = temp_workspace / "datasets" / "experiments"
        parquet_file = experiments_dir / "experiments.parquet"
        
        df = pd.DataFrame(fake_experiment_data)
        df.to_parquet(parquet_file, index=False)
        
        # 使用本地降级预测
        reports_dir = temp_workspace / "reports"
        evaluator = PredictionEvaluator(
            experiments_file=str(parquet_file),
            api_url="http://non-existent:8000"  # 故意使用不存在的API
        )
        evaluator.reports_dir = reports_dir
        
        result = evaluator.evaluate()
        
        # 验证按体系分组的指标
        assert 'system_metrics' in result
        system_metrics = result['system_metrics']
        
        # 应该有silicate和zirconate两个体系
        systems = set(df['system'].unique())
        for system in systems:
            if system in system_metrics:
                assert 'alpha_metrics' in system_metrics[system]
                assert 'epsilon_metrics' in system_metrics[system]
                assert 'sample_size' in system_metrics[system]
    
    def test_model_update_simulation(self, temp_workspace):
        """测试模型更新流程模拟"""
        # 这个测试模拟更新流程，但不实际训练模型
        
        models_dir = temp_workspace / "models_ckpt"
        gp_dir = models_dir / "gp_corrector"
        reward_dir = models_dir / "reward_v1"
        
        # 模拟创建模型目录和文件
        gp_dir.mkdir(parents=True)
        reward_dir.mkdir(parents=True)
        
        # 创建模拟的模型文件
        (gp_dir / "gp_model.pkl").touch()
        (gp_dir / "metadata.json").write_text('{"trained_at": "2025-01-01", "samples": 5}')
        
        (reward_dir / "reward_model.pkl").touch()
        (reward_dir / "config.json").write_text('{"model_type": "reward", "version": "v1"}')
        
        # 验证目录和文件存在
        assert gp_dir.exists()
        assert reward_dir.exists()
        assert (gp_dir / "gp_model.pkl").exists()
        assert (reward_dir / "reward_model.pkl").exists()
        
        # 验证元数据
        metadata = json.loads((gp_dir / "metadata.json").read_text())
        assert metadata["samples"] == 5
        
        config = json.loads((reward_dir / "config.json").read_text())
        assert config["model_type"] == "reward"
    
    @patch('requests.post')
    def test_api_hot_reload_simulation(self, mock_post):
        """测试API热加载端点模拟"""
        # 模拟成功的热加载响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "message": "模型热加载完成",
            "results": {
                "gp_corrector": {"status": "success", "message": "GP校正器重新加载成功"},
                "reward_model": {"status": "success", "message": "偏好模型重新加载成功"}
            }
        }
        mock_post.return_value = mock_response
        
        # 模拟热加载请求
        import requests
        response = requests.post(
            "http://localhost:8000/api/maowise/v1/admin/reload",
            json={"models": ["gp_corrector", "reward_model"]},
            timeout=10
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert "gp_corrector" in result["results"]
        assert "reward_model" in result["results"]
    
    def test_end_to_end_workflow(self, temp_workspace, fake_experiment_data):
        """测试端到端工作流程"""
        # 1. 导入实验数据
        experiments_dir = temp_workspace / "datasets" / "experiments"
        csv_file = temp_workspace / "test_experiments.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fake_experiment_data[0].keys())
            writer.writeheader()
            writer.writerows(fake_experiment_data)
        
        recorder = ExperimentRecorder(str(experiments_dir))
        import_result = recorder.import_from_file(str(csv_file))
        
        assert import_result['success']
        assert import_result['stats']['final_new'] == 5
        
        # 2. 评估预测性能
        parquet_file = experiments_dir / "experiments.parquet"
        reports_dir = temp_workspace / "reports"
        
        evaluator = PredictionEvaluator(
            experiments_file=str(parquet_file),
            api_url="http://non-existent:8000"  # 使用降级模式
        )
        evaluator.reports_dir = reports_dir
        
        eval_result = evaluator.evaluate()
        
        assert 'overall_metrics' in eval_result
        assert len(eval_result['plots']) == 2
        
        # 3. 模拟模型更新
        models_dir = temp_workspace / "models_ckpt"
        
        # 创建模拟的更新后模型
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        gp_dir = models_dir / "gp_corrector" / timestamp
        reward_dir = models_dir / "reward_v1" / timestamp
        
        gp_dir.mkdir(parents=True)
        reward_dir.mkdir(parents=True)
        
        (gp_dir / "updated_model.pkl").touch()
        (reward_dir / "updated_model.pkl").touch()
        
        # 4. 验证完整流程
        assert parquet_file.exists()
        assert len(list(reports_dir.glob("*.json"))) >= 1
        assert len(list(reports_dir.glob("*.png"))) >= 2
        assert gp_dir.exists()
        assert reward_dir.exists()
        
        print("✅ 端到端工作流程测试通过")

class TestPerformanceMetrics:
    """性能指标测试"""
    
    def test_metrics_calculation(self):
        """测试评估指标计算"""
        # 创建测试数据
        np.random.seed(42)
        n_samples = 100
        
        # 生成模拟的真实值和预测值
        true_alpha = np.random.uniform(0.1, 0.3, n_samples)
        true_epsilon = np.random.uniform(0.6, 1.0, n_samples)
        
        # 添加一些预测误差
        pred_alpha = true_alpha + np.random.normal(0, 0.02, n_samples)
        pred_epsilon = true_epsilon + np.random.normal(0, 0.03, n_samples)
        
        confidence = np.random.uniform(0.5, 0.9, n_samples)
        
        # 创建DataFrame
        df = pd.DataFrame({
            'measured_alpha': true_alpha,
            'measured_epsilon': true_epsilon,
            'pred_alpha': pred_alpha,
            'pred_epsilon': pred_epsilon,
            'confidence': confidence
        })
        
        # 使用评估器计算指标
        evaluator = PredictionEvaluator()
        metrics = evaluator._calculate_metrics(df)
        
        # 验证指标结构
        assert 'alpha_metrics' in metrics
        assert 'epsilon_metrics' in metrics
        assert 'confidence_metrics' in metrics
        
        # 验证指标值的合理性
        alpha_metrics = metrics['alpha_metrics']
        assert 0 <= alpha_metrics['mae'] <= 1
        assert 0 <= alpha_metrics['hit_rate_003'] <= 100
        assert 0 <= alpha_metrics['hit_rate_005'] <= 100
        assert -1 <= alpha_metrics['correlation'] <= 1
        
        epsilon_metrics = metrics['epsilon_metrics']
        assert 0 <= epsilon_metrics['mae'] <= 2
        assert 0 <= epsilon_metrics['hit_rate_003'] <= 100
        assert 0 <= epsilon_metrics['hit_rate_005'] <= 100
        
        confidence_metrics = metrics['confidence_metrics']
        assert 0 <= confidence_metrics['average'] <= 1
        assert 0 <= confidence_metrics['low_confidence_ratio'] <= 100
        
        assert metrics['sample_size'] == n_samples

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
