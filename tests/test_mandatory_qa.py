import pytest
from maowise.experts.followups import (
    load_question_catalog, 
    is_answer_vague, 
    gen_followups, 
    validate_mandatory_answers
)
from maowise.experts.clarify import (
    generate_clarify_questions,
    check_mandatory_completion,
    _generate_mandatory_questions,
    _generate_followup_questions
)


def test_load_question_catalog():
    """测试问题目录加载"""
    catalog = load_question_catalog()
    
    assert isinstance(catalog, dict)
    assert "mandatory_questions" in catalog
    
    mandatory_qs = catalog["mandatory_questions"]
    assert isinstance(mandatory_qs, list)
    assert len(mandatory_qs) > 0
    
    # 检查必答问题结构
    for q in mandatory_qs:
        assert "id" in q
        assert "question" in q
        assert "category" in q
        assert "rationale" in q
        assert "vague_indicators" in q


def test_is_answer_vague():
    """测试回答含糊检测"""
    # 模拟问题配置
    question_config = {
        "vague_indicators": ["看情况", "不确定", "可能"]
    }
    
    # 含糊回答
    assert is_answer_vague("看情况而定", question_config) is True
    assert is_answer_vague("不确定", question_config) is True
    assert is_answer_vague("", question_config) is True
    assert is_answer_vague("是", question_config) is True  # 过短
    
    # 具体回答
    assert is_answer_vague("不允许使用含氟添加剂", question_config) is False
    assert is_answer_vague("涂层厚度要求10-15μm", question_config) is False
    assert is_answer_vague("AZ91合金，Ra=0.8μm", question_config) is False


def test_gen_followups():
    """测试追问生成"""
    catalog = load_question_catalog()
    mandatory_qs = catalog["mandatory_questions"]
    
    # 找到一个必答问题进行测试
    question_config = mandatory_qs[0]  # 取第一个问题
    question_id = question_config["id"]
    
    # 含糊回答应该生成追问
    vague_answer = "看情况"
    followups = gen_followups(question_id, vague_answer, question_config)
    
    assert isinstance(followups, list)
    if followups:  # 如果生成了追问
        followup = followups[0]
        assert "id" in followup
        assert "question" in followup
        assert "rationale" in followup
        assert followup["is_followup"] is True
        assert followup["parent_question_id"] == question_id
    
    # 具体回答不应该生成追问
    specific_answer = "不允许使用含氟添加剂，设备无防腐蚀能力"
    followups_specific = gen_followups(question_id, specific_answer, question_config)
    
    assert len(followups_specific) == 0


def test_validate_mandatory_answers():
    """测试必答问题验证"""
    # 空回答
    empty_answers = {}
    validation = validate_mandatory_answers(empty_answers)
    
    assert validation["all_answered"] is False
    assert validation["all_specific"] is False
    assert len(validation["missing_questions"]) > 0
    
    # 含糊回答
    vague_answers = {
        "fluoride_additives": "看情况",
        "thickness_limits": "适中",
        "substrate_surface": "一般"
    }
    validation_vague = validate_mandatory_answers(vague_answers)
    
    assert validation_vague["all_specific"] is False
    assert len(validation_vague["vague_answers"]) > 0
    assert len(validation_vague["needs_followup"]) > 0
    
    # 具体回答
    specific_answers = {
        "fluoride_additives": "不允许使用含氟添加剂",
        "thickness_limits": "涂层厚度要求10-15μm",
        "substrate_surface": "AZ91合金，表面粗糙度Ra=0.8μm"
    }
    validation_specific = validate_mandatory_answers(specific_answers)
    
    # 注意：可能仍有其他必答问题未回答
    assert len(validation_specific["vague_answers"]) == 0


def test_generate_mandatory_questions():
    """测试必答问题生成"""
    # 无已有回答
    questions = generate_clarify_questions(
        current_data={},
        include_mandatory=True,
        expert_answers=None
    )
    
    assert isinstance(questions, list)
    mandatory_questions = [q for q in questions if q.is_mandatory]
    assert len(mandatory_questions) > 0
    
    for q in mandatory_questions:
        assert q.is_mandatory is True
        assert q.question
        assert q.rationale
        assert q.priority in ["critical", "high", "medium", "low"]
    
    # 已有部分回答
    partial_answers = {
        "fluoride_additives": "不允许"
    }
    
    questions_partial = generate_clarify_questions(
        current_data={},
        include_mandatory=True,
        expert_answers=partial_answers
    )
    
    # 应该少一些问题（已回答的不再询问）
    remaining_mandatory = [q for q in questions_partial if q.is_mandatory]
    assert len(remaining_mandatory) < len(mandatory_questions)


def test_generate_followup_questions():
    """测试追问问题生成"""
    # 含糊回答应该触发追问
    vague_answers = {
        "fluoride_additives": "看情况",
        "thickness_limits": "适中"
    }
    
    questions = generate_clarify_questions(
        current_data={},
        include_mandatory=False,
        expert_answers=vague_answers
    )
    
    followup_questions = [q for q in questions if q.is_followup]
    assert len(followup_questions) > 0
    
    for q in followup_questions:
        assert q.is_followup is True
        assert q.parent_question_id is not None
        assert q.question
        assert q.rationale


def test_check_mandatory_completion():
    """测试必答问题完成检查"""
    # 完整回答
    complete_answers = {
        "fluoride_additives": "不允许使用含氟添加剂",
        "thickness_limits": "涂层厚度10-15μm",
        "substrate_surface": "AZ91合金，Ra=0.8μm",
        "environmental_constraints": "无特殊环保要求",
        "performance_priorities": "α和ε同等重要"
    }
    
    completion = check_mandatory_completion(complete_answers)
    
    assert isinstance(completion, dict)
    assert "all_answered" in completion
    assert "all_specific" in completion
    assert "missing_questions" in completion
    assert "vague_answers" in completion


def test_question_priority_ordering():
    """测试问题优先级排序"""
    questions = generate_clarify_questions(
        current_data={},
        include_mandatory=True,
        max_questions=10
    )
    
    mandatory_questions = [q for q in questions if q.is_mandatory]
    
    if len(mandatory_questions) > 1:
        # 检查优先级排序
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        
        for i in range(len(mandatory_questions) - 1):
            current_priority = priority_order.get(mandatory_questions[i].priority, 2)
            next_priority = priority_order.get(mandatory_questions[i+1].priority, 2)
            assert current_priority <= next_priority


def test_question_kinds():
    """测试问题类型判断"""
    questions = generate_clarify_questions(
        current_data={},
        include_mandatory=True
    )
    
    for q in questions:
        assert q.kind in ["choice", "number", "text"]
        
        if q.kind == "choice":
            assert q.options is not None
            assert len(q.options) > 0
        
        if q.kind == "number":
            # 数值问题可能有单位
            pass


def test_followup_max_attempts():
    """测试追问最大次数限制"""
    # 连续含糊回答
    question_id = "fluoride_additives"
    catalog = load_question_catalog()
    mandatory_qs = catalog["mandatory_questions"]
    question_config = next(q for q in mandatory_qs if q["id"] == question_id)
    
    # 第一次追问
    followups1 = gen_followups(question_id, "看情况", question_config)
    assert len(followups1) <= 1  # 最多一次追问
    
    if followups1:
        # 追问有最大次数限制
        assert followups1[0].get("max_attempts", 1) == 1


def test_validation_rules():
    """测试验证规则"""
    # 测试数值范围验证
    answers_with_numbers = {
        "thickness_limits": "涂层厚度15μm"
    }
    
    validation = validate_mandatory_answers(answers_with_numbers)
    
    # 应该能识别包含数值和单位的回答
    assert isinstance(validation, dict)
    
    # 测试布尔选择验证
    answers_boolean = {
        "fluoride_additives": "不允许"
    }
    
    validation_bool = validate_mandatory_answers(answers_boolean)
    assert isinstance(validation_bool, dict)


def test_fallback_behavior():
    """测试离线兜底行为"""
    # 即使LLM不可用，也应该能生成基本问题
    try:
        questions = generate_clarify_questions(
            current_data={},
            include_mandatory=True,
            max_questions=3
        )
        
        # 应该至少有一些问题（可能是兜底问题）
        assert isinstance(questions, list)
        
    except Exception as e:
        # 不应该完全失败
        pytest.fail(f"Fallback should not fail completely: {e}")


def test_thread_resolution_flow():
    """测试问答线程解决流程"""
    # 模拟完整的问答流程
    
    # 1. 生成初始问题
    questions = generate_clarify_questions(
        current_data={},
        include_mandatory=True,
        max_questions=3
    )
    
    assert len(questions) > 0
    
    # 2. 模拟回答
    answers = {}
    for q in questions:
        if q.is_mandatory:
            # 给必答问题一个具体回答
            if "fluoride" in q.id:
                answers[q.id] = "不允许使用含氟添加剂"
            elif "thickness" in q.id:
                answers[q.id] = "涂层厚度10-15μm"
            elif "substrate" in q.id:
                answers[q.id] = "AZ91合金，Ra=0.8μm"
            else:
                answers[q.id] = "具体的回答内容"
    
    # 3. 验证完成状态
    completion = check_mandatory_completion(answers)
    
    # 应该能正确识别完成状态
    assert isinstance(completion, dict)
    
    # 4. 如果有含糊回答，应该能生成追问
    vague_answer_test = {q.id: "看情况" for q in questions if q.is_mandatory}
    
    followup_questions = generate_clarify_questions(
        current_data={},
        expert_answers=vague_answer_test,
        include_mandatory=False
    )
    
    followups = [q for q in followup_questions if q.is_followup]
    # 可能生成追问（取决于LLM可用性）
    assert isinstance(followups, list)
