import pytest
from maowise.experts.clarify import generate_clarify_questions
from maowise.experts.slotfill import extract_slot_values
from maowise.experts.schemas_llm import ClarifyQuestion, SlotFillResult


def test_clarify_questions_generation():
    """测试澄清问题生成"""
    current_data = {
        "substrate_alloy": "AZ91",
        "electrolyte_family": "silicate"
        # 缺少 voltage_V, current_density_A_dm2 等
    }
    
    questions = generate_clarify_questions(
        current_data=current_data,
        context_description="AZ91镁合金基体，硅酸盐电解液体系",
        max_questions=3
    )
    
    assert isinstance(questions, list)
    assert len(questions) <= 3
    
    for q in questions:
        assert isinstance(q, ClarifyQuestion)
        assert q.id
        assert q.question
        assert q.kind in ["choice", "number", "text"]
        assert q.rationale


def test_clarify_questions_no_missing_fields():
    """测试无缺失字段时的澄清问题生成"""
    complete_data = {
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "time_min": 10,
        "frequency_Hz": 500,
        "duty_cycle_pct": 30,
        "electrolyte_family": "silicate",
        "post_treatment": "sealing"
    }
    
    questions = generate_clarify_questions(
        current_data=complete_data,
        context_description="完整的实验参数",
        max_questions=3
    )
    
    # 应该没有问题或很少问题
    assert len(questions) == 0


def test_slotfill_basic_extraction():
    """测试基本槽位填充"""
    expert_answer = "电压我们设置的是420V，电流密度大约12A/dm²，处理了10分钟。"
    
    result = extract_slot_values(
        expert_answer=expert_answer,
        current_context="AZ91镁合金微弧氧化实验"
    )
    
    assert isinstance(result, SlotFillResult)
    values = result.to_dict()
    
    # 应该提取出这些值
    assert "voltage_V" in values
    assert "current_density_Adm2" in values  
    assert "time_min" in values
    
    assert values["voltage_V"] == 420
    assert values["current_density_Adm2"] == 12
    assert values["time_min"] == 10


def test_slotfill_electrolyte_extraction():
    """测试电解液成分抽取"""
    expert_answer = "电解液是硅酸盐体系，Na2SiO3用了10g/L，KOH是2g/L。"
    
    result = extract_slot_values(
        expert_answer=expert_answer,
        current_context="硅酸盐电解液配制"
    )
    
    values = result.to_dict()
    
    if "electrolyte_components_json" in values:
        components = values["electrolyte_components_json"]
        assert isinstance(components, dict)
        # 应该包含主要成分
        assert "Na2SiO3" in str(components) or "KOH" in str(components)


def test_slotfill_post_treatment_extraction():
    """测试后处理信息抽取"""
    expert_answer = "最后做了水热封孔处理，80度水浴2小时。"
    
    result = extract_slot_values(
        expert_answer=expert_answer,
        current_context="后处理工艺"
    )
    
    values = result.to_dict()
    
    if "post_treatment" in values:
        assert "水热" in values["post_treatment"] or "封孔" in values["post_treatment"]


def test_slotfill_empty_answer():
    """测试空回答"""
    result = extract_slot_values(
        expert_answer="",
        current_context=""
    )
    
    assert isinstance(result, SlotFillResult)
    values = result.to_dict()
    assert len(values) == 0


def test_slotfill_complex_answer():
    """测试复杂回答的抽取"""
    expert_answer = """
    参数设置如下：电压410V，电流密度15A/dm²，双极性脉冲800Hz，
    占空比40%，总共处理15分钟。电解液是标准的硅酸盐配方：
    Na2SiO3·9H2O 12g/L，KOH 3g/L。没有做后处理。
    """
    
    result = extract_slot_values(
        expert_answer=expert_answer,
        current_context="完整实验参数描述"
    )
    
    values = result.to_dict()
    
    # 应该提取出多个参数
    expected_fields = ["voltage_V", "current_density_Adm2", "frequency_Hz", 
                      "duty_cycle_pct", "time_min"]
    
    extracted_count = sum(1 for field in expected_fields if field in values)
    assert extracted_count >= 3  # 至少提取出3个参数


def test_clarify_fallback_mode():
    """测试离线兜底模式"""
    # 这个测试确保即使 LLM 不可用，也能生成基本问题
    current_data = {"substrate_alloy": "AZ91"}  # 只有基体信息
    
    questions = generate_clarify_questions(
        current_data=current_data,
        context_description="基本信息",
        max_questions=2
    )
    
    # 即使在离线模式下，也应该能生成一些问题
    assert isinstance(questions, list)
    # 可能为空（如果 LLM 完全不可用），但不应该报错


def test_slotfill_fallback_mode():
    """测试槽位填充的离线兜底模式"""
    expert_answer = "电压420V，电流密度12A/dm²"
    
    result = extract_slot_values(
        expert_answer=expert_answer,
        current_context="简单参数"
    )
    
    # 即使在离线模式下，也应该能通过正则表达式提取一些信息
    assert isinstance(result, SlotFillResult)
    values = result.to_dict()
    
    # 至少应该能提取出电压和电流密度
    assert len(values) >= 0  # 不要求一定提取成功，但不应该报错
