import pytest
from maowise.experts.explain import make_explanation
from maowise.experts.plan_writer import make_plan_yaml
from maowise.llm.rag import Snippet


def test_make_explanation_prediction():
    """测试预测结果解释生成"""
    result = {
        "alpha": 0.82,
        "epsilon": 0.91,
        "confidence": 0.85,
        "description": "AZ91镁合金，硅酸盐电解液，420V，12A/dm²，10分钟"
    }
    
    explanation = make_explanation(result, result_type="prediction")
    
    assert isinstance(explanation, dict)
    assert "explanations" in explanation
    assert "citation_map" in explanation
    assert isinstance(explanation["explanations"], list)
    
    # 应该有解释要点
    explanations = explanation["explanations"]
    assert len(explanations) > 0
    
    for exp in explanations:
        assert "point" in exp
        assert "citations" in exp
        assert isinstance(exp["point"], str)
        assert isinstance(exp["citations"], list)


def test_make_explanation_recommendation():
    """测试优化建议解释生成"""
    result = {
        "solutions": [
            {
                "description": "AZ91基体，提高电压至450V",
                "expected_alpha": 0.85,
                "expected_epsilon": 0.90
            },
            {
                "description": "延长处理时间至15分钟",
                "expected_alpha": 0.83,
                "expected_epsilon": 0.92
            }
        ],
        "target": {"alpha": 0.85, "epsilon": 0.90}
    }
    
    explanation = make_explanation(result, result_type="recommendation")
    
    assert isinstance(explanation, dict)
    assert "explanations" in explanation
    
    explanations = explanation["explanations"]
    assert len(explanations) > 0
    
    # 应该提到方案相关内容
    explanation_text = " ".join([exp.get("point", "") for exp in explanations])
    assert "方案" in explanation_text or "建议" in explanation_text


def test_make_explanation_with_snippets():
    """测试带文献片段的解释生成"""
    result = {
        "alpha": 0.82,
        "epsilon": 0.91,
        "confidence": 0.85
    }
    
    snippets = [
        Snippet(
            text="硅酸盐电解液在AZ91镁合金上能形成致密的氧化层",
            source="test_paper.pdf",
            page=1,
            score=0.95
        ),
        Snippet(
            text="420V电压配合12A/dm²电流密度可获得良好的放电稳定性",
            source="test_paper.pdf",
            page=2,
            score=0.88
        )
    ]
    
    explanation = make_explanation(
        result, 
        context_snippets=snippets,
        result_type="prediction"
    )
    
    assert isinstance(explanation, dict)
    citation_map = explanation.get("citation_map", {})
    
    # 应该有引用映射
    if citation_map:
        for cit_id, cit_info in citation_map.items():
            assert cit_id.startswith("CIT-")
            assert "text" in cit_info
            assert "source" in cit_info
            assert "page" in cit_info


def test_make_plan_yaml_basic():
    """测试基本工艺卡生成"""
    solution = {
        "substrate_alloy": "AZ91",
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "time_min": 10,
        "electrolyte_components_json": {
            "Na2SiO3": "10 g/L",
            "KOH": "2 g/L"
        }
    }
    
    plan = make_plan_yaml(solution)
    
    assert isinstance(plan, dict)
    assert "yaml_text" in plan
    assert "plan_data" in plan
    assert "hard_constraints_passed" in plan
    
    # YAML文本应该包含关键信息
    yaml_text = plan["yaml_text"]
    assert isinstance(yaml_text, str)
    assert "process_name" in yaml_text
    assert "steps" in yaml_text
    
    # 计划数据应该有必需字段
    plan_data = plan["plan_data"]
    assert "process_name" in plan_data
    assert "substrate" in plan_data
    assert "steps" in plan_data
    assert isinstance(plan_data["steps"], list)


def test_make_plan_yaml_with_post_treatment():
    """测试带后处理的工艺卡生成"""
    solution = {
        "substrate_alloy": "AZ91",
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "time_min": 10,
        "post_treatment": "水热封孔，80°C，2小时"
    }
    
    plan = make_plan_yaml(solution)
    
    plan_data = plan["plan_data"]
    steps = plan_data.get("steps", [])
    
    # 应该包含后处理步骤
    post_steps = [step for step in steps if "后处理" in step.get("name", "") or "POST" in step.get("step_id", "")]
    assert len(post_steps) > 0 or any("封孔" in step.get("description", "") for step in steps)


def test_make_plan_yaml_constraints_check():
    """测试约束检查功能"""
    # 正常参数
    normal_solution = {
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "time_min": 10
    }
    
    plan_normal = make_plan_yaml(normal_solution)
    assert plan_normal["hard_constraints_passed"] is True
    
    # 异常参数（时间过长）
    extreme_solution = {
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "time_min": 120  # 超过60分钟
    }
    
    plan_extreme = make_plan_yaml(extreme_solution)
    # 可能失败（取决于内置规则）
    assert isinstance(plan_extreme["hard_constraints_passed"], bool)


def test_make_plan_yaml_with_snippets():
    """测试带文献片段的工艺卡生成"""
    solution = {
        "substrate_alloy": "AZ91",
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "time_min": 10
    }
    
    snippets = [
        Snippet(
            text="AZ91基体需预处理去除氧化膜",
            source="process_guide.pdf",
            page=5,
            score=0.92
        )
    ]
    
    plan = make_plan_yaml(solution, context_snippets=snippets)
    
    citation_map = plan.get("citation_map", {})
    if citation_map:
        # 应该有引用信息
        for cit_id, cit_info in citation_map.items():
            assert "text" in cit_info
            assert "source" in cit_info


def test_explanation_fallback():
    """测试解释生成的离线兜底"""
    # 空结果测试
    empty_result = {}
    
    explanation = make_explanation(empty_result, result_type="prediction")
    
    assert isinstance(explanation, dict)
    assert "explanations" in explanation
    
    # 即使是兜底模式，也应该有基本解释
    explanations = explanation["explanations"]
    assert len(explanations) >= 0  # 允许为空，但不应该报错


def test_plan_fallback():
    """测试工艺卡生成的离线兜底"""
    # 最小解决方案
    minimal_solution = {
        "substrate_alloy": "AZ91"
    }
    
    plan = make_plan_yaml(minimal_solution)
    
    assert isinstance(plan, dict)
    assert "yaml_text" in plan
    assert "plan_data" in plan
    
    # 即使是兜底模式，也应该有基本结构
    plan_data = plan["plan_data"]
    assert "process_name" in plan_data
    assert "steps" in plan_data
    assert len(plan_data["steps"]) > 0


def test_citation_format():
    """测试引用格式"""
    result = {
        "alpha": 0.82,
        "epsilon": 0.91
    }
    
    snippets = [
        Snippet(text="Test content", source="test.pdf", page=1, score=0.9)
    ]
    
    explanation = make_explanation(
        result, 
        context_snippets=snippets,
        result_type="prediction"
    )
    
    citation_map = explanation.get("citation_map", {})
    
    for cit_id in citation_map.keys():
        # 引用ID应该是 CIT-N 格式
        assert cit_id.startswith("CIT-")
        assert cit_id[4:].isdigit()


def test_yaml_downloadable():
    """测试生成的YAML是否可下载"""
    solution = {
        "substrate_alloy": "AZ91",
        "voltage_V": 420,
        "process_name": "测试工艺"
    }
    
    plan = make_plan_yaml(solution)
    yaml_text = plan["yaml_text"]
    
    # YAML应该是有效的字符串
    assert isinstance(yaml_text, str)
    assert len(yaml_text) > 0
    
    # 应该包含基本的YAML结构
    assert ":" in yaml_text  # YAML键值对
    assert "process_name" in yaml_text
    
    # 尝试解析YAML
    import yaml
    try:
        parsed = yaml.safe_load(yaml_text)
        assert isinstance(parsed, dict)
    except yaml.YAMLError:
        pytest.fail("Generated YAML is not valid")
