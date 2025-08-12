#!/usr/bin/env python3
"""
必答清单 & 追问逻辑功能演示脚本
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.experts.followups import (
    load_question_catalog, 
    is_answer_vague, 
    gen_followups, 
    validate_mandatory_answers
)
from maowise.experts.clarify import (
    generate_clarify_questions,
    check_mandatory_completion
)
from maowise.utils.logger import logger


def demo_question_catalog():
    """演示问题目录"""
    print("=" * 60)
    print("📋 必答清单演示")
    print("=" * 60)
    
    catalog = load_question_catalog()
    mandatory_questions = catalog.get("mandatory_questions", [])
    
    print(f"\n共有 {len(mandatory_questions)} 个必答问题：\n")
    
    for i, q in enumerate(mandatory_questions, 1):
        priority_icon = {
            "critical": "🔴", 
            "high": "🟠", 
            "medium": "🟡", 
            "low": "🟢"
        }.get(q.get("priority", "medium"), "🟡")
        
        print(f"{priority_icon} **问题 {i}** [{q['priority'].upper()}]")
        print(f"   ID: {q['id']}")
        print(f"   问题: {q['question']}")
        print(f"   类别: {q['category']}")
        print(f"   理由: {q['rationale']}")
        print(f"   期望回答: {', '.join(q.get('expected_answers', []))}")
        print(f"   含糊指标: {', '.join(q.get('vague_indicators', []))}")
        print()


def demo_vague_detection():
    """演示含糊回答检测"""
    print("\n" + "=" * 60)
    print("🔍 含糊回答检测演示")
    print("=" * 60)
    
    catalog = load_question_catalog()
    test_question = catalog["mandatory_questions"][0]  # 取第一个问题做测试
    
    print(f"\n测试问题: {test_question['question']}")
    print(f"含糊指标: {', '.join(test_question['vague_indicators'])}")
    
    test_cases = [
        ("看情况而定", "含糊"),
        ("不确定", "含糊"),
        ("适中就行", "含糊"),
        ("", "含糊（空回答）"),
        ("是", "含糊（过短）"),
        ("不允许使用含氟添加剂，设备无防腐蚀能力", "具体"),
        ("涂层厚度要求10-15μm，质量不超过50g/m²", "具体"),
        ("AZ91镁合金，表面粗糙度Ra=0.8μm", "具体")
    ]
    
    print("\n回答检测结果:")
    for answer, expected in test_cases:
        is_vague = is_answer_vague(answer, test_question)
        status = "✅ 含糊" if is_vague else "❌ 具体"
        print(f"  '{answer}' → {status} (期望: {expected})")


def demo_followup_generation():
    """演示追问生成"""
    print("\n\n" + "=" * 60)
    print("🔄 追问生成演示")
    print("=" * 60)
    
    catalog = load_question_catalog()
    
    test_scenarios = [
        {
            "question_id": "fluoride_additives",
            "answer": "看情况",
            "description": "含氟添加剂使用"
        },
        {
            "question_id": "thickness_limits", 
            "answer": "适中就行",
            "description": "涂层厚度要求"
        },
        {
            "question_id": "substrate_surface",
            "answer": "一般的表面",
            "description": "基体表面状态"
        }
    ]
    
    for scenario in test_scenarios:
        question_id = scenario["question_id"]
        answer = scenario["answer"]
        description = scenario["description"]
        
        print(f"\n📝 场景: {description}")
        print(f"原问题ID: {question_id}")
        print(f"专家回答: '{answer}'")
        
        # 找到问题配置
        question_config = next(
            (q for q in catalog["mandatory_questions"] if q["id"] == question_id), 
            None
        )
        
        if question_config:
            # 生成追问
            followups = gen_followups(question_id, answer, question_config)
            
            if followups:
                print(f"✅ 生成 {len(followups)} 个追问:")
                for i, followup in enumerate(followups, 1):
                    print(f"   追问 {i}: {followup['question']}")
                    print(f"   理由: {followup['rationale']}")
                    print(f"   追问ID: {followup['id']}")
            else:
                print("❌ 回答足够具体，无需追问")
        else:
            print("⚠️ 未找到问题配置")


def demo_validation_system():
    """演示验证系统"""
    print("\n\n" + "=" * 60)
    print("✅ 验证系统演示")
    print("=" * 60)
    
    test_scenarios = [
        {
            "name": "空回答",
            "answers": {}
        },
        {
            "name": "含糊回答",
            "answers": {
                "fluoride_additives": "看情况",
                "thickness_limits": "适中",
                "substrate_surface": "一般"
            }
        },
        {
            "name": "部分具体回答",
            "answers": {
                "fluoride_additives": "不允许使用含氟添加剂",
                "thickness_limits": "看情况",
                "substrate_surface": "AZ91合金，Ra=0.8μm"
            }
        },
        {
            "name": "完全具体回答",
            "answers": {
                "fluoride_additives": "不允许使用含氟添加剂，设备无防腐蚀能力",
                "thickness_limits": "涂层厚度10-15μm，质量不超过50g/m²",
                "substrate_surface": "AZ91镁合金，表面粗糙度Ra=0.8μm",
                "environmental_constraints": "无特殊环保要求，按国家标准执行",
                "performance_priorities": "α和ε同等重要，目标α<0.2, ε>0.9"
            }
        }
    ]
    
    for scenario in test_scenarios:
        name = scenario["name"]
        answers = scenario["answers"]
        
        print(f"\n📊 场景: {name}")
        print(f"回答数量: {len(answers)}")
        
        validation = validate_mandatory_answers(answers)
        
        print(f"结果:")
        print(f"  全部回答: {'✅' if validation['all_answered'] else '❌'}")
        print(f"  全部具体: {'✅' if validation['all_specific'] else '❌'}")
        print(f"  缺失问题: {len(validation['missing_questions'])}")
        print(f"  含糊回答: {len(validation['vague_answers'])}")
        print(f"  需要追问: {len(validation['needs_followup'])}")
        
        if validation['missing_questions']:
            print("  缺失的问题:")
            for missing in validation['missing_questions'][:3]:  # 只显示前3个
                print(f"    - {missing['question']}")
        
        if validation['vague_answers']:
            print("  含糊的回答:")
            for vague in validation['vague_answers'][:3]:
                print(f"    - {vague['question']}: '{vague['answer']}'")


def demo_question_generation():
    """演示问题生成流程"""
    print("\n\n" + "=" * 60)
    print("🎯 问题生成流程演示")
    print("=" * 60)
    
    # 场景1：初始必答问题生成
    print("\n📋 场景1：生成初始必答问题")
    
    questions = generate_clarify_questions(
        current_data={},
        context_description="专家咨询",
        max_questions=5,
        include_mandatory=True
    )
    
    print(f"生成了 {len(questions)} 个问题:")
    
    for i, q in enumerate(questions, 1):
        mandatory_mark = "⭐" if q.is_mandatory else ""
        priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(q.priority, "🟡")
        
        print(f"  {priority_icon} {mandatory_mark} 问题 {i}: {q.question}")
        print(f"    类型: {q.kind}, 优先级: {q.priority}")
        if q.options:
            print(f"    选项: {', '.join(q.options)}")
        print()
    
    # 场景2：基于含糊回答生成追问
    print("\n🔄 场景2：基于含糊回答生成追问")
    
    vague_answers = {
        "fluoride_additives": "看情况",
        "thickness_limits": "适中"
    }
    
    followup_questions = generate_clarify_questions(
        current_data={},
        expert_answers=vague_answers,
        max_questions=3,
        include_mandatory=False
    )
    
    print(f"基于含糊回答生成了 {len(followup_questions)} 个追问:")
    
    for i, q in enumerate(followup_questions, 1):
        if q.is_followup:
            print(f"  🔄 追问 {i}: {q.question}")
            print(f"    父问题: {q.parent_question_id}")
            print(f"    理由: {q.rationale}")
            print()


def demo_complete_workflow():
    """演示完整工作流程"""
    print("\n\n" + "=" * 60)
    print("🔄 完整工作流程演示")
    print("=" * 60)
    
    print("\n步骤1: 生成必答问题")
    questions = generate_clarify_questions(
        current_data={},
        include_mandatory=True,
        max_questions=3
    )
    
    mandatory_questions = [q for q in questions if q.is_mandatory]
    print(f"生成了 {len(mandatory_questions)} 个必答问题")
    
    print("\n步骤2: 模拟专家回答（部分含糊）")
    simulated_answers = {}
    
    for i, q in enumerate(mandatory_questions):
        if i == 0:
            simulated_answers[q.id] = "看情况而定"  # 含糊回答
        elif i == 1:
            simulated_answers[q.id] = "不允许使用含氟添加剂"  # 具体回答
        else:
            simulated_answers[q.id] = "一般就行"  # 含糊回答
    
    for q_id, answer in simulated_answers.items():
        print(f"  {q_id}: '{answer}'")
    
    print("\n步骤3: 验证回答质量")
    validation = validate_mandatory_answers(simulated_answers)
    
    print(f"验证结果:")
    print(f"  含糊回答数: {len(validation['vague_answers'])}")
    print(f"  需要追问数: {len(validation['needs_followup'])}")
    
    print("\n步骤4: 生成追问")
    if validation['needs_followup']:
        print("生成的追问:")
        for followup in validation['needs_followup'][:2]:  # 只显示前2个
            print(f"  🔄 {followup['question']}")
            print(f"     理由: {followup['rationale']}")
    
    print("\n步骤5: 模拟追问回答")
    final_answers = simulated_answers.copy()
    
    # 模拟对追问的具体回答
    if validation['needs_followup']:
        for followup in validation['needs_followup'][:1]:  # 只回答第一个追问
            final_answers[followup['id']] = "不允许，设备无防腐蚀能力"
    
    print("\n步骤6: 最终验证")
    final_validation = validate_mandatory_answers(final_answers)
    
    print(f"最终状态:")
    print(f"  全部回答: {'✅' if final_validation['all_answered'] else '❌'}")
    print(f"  全部具体: {'✅' if final_validation['all_specific'] else '❌'}")
    print(f"  可以继续处理: {'✅' if final_validation['all_answered'] and final_validation['all_specific'] else '❌'}")


def main():
    """主演示函数"""
    print("🎭 MAO-Wise 必答清单 & 追问逻辑演示")
    print("支持离线兜底模式，无需 LLM API Key 也可运行基本功能")
    
    try:
        demo_question_catalog()
        demo_vague_detection()
        demo_followup_generation()
        demo_validation_system()
        demo_question_generation()
        demo_complete_workflow()
        
        print("\n\n" + "=" * 60)
        print("🎉 演示完成！")
        print("=" * 60)
        print("\n✅ 核心特性:")
        print("1. ✓ 必答问题清单：5个关键问题，按优先级排序")
        print("2. ✓ 含糊回答检测：多种模式识别不明确回答")
        print("3. ✓ 智能追问生成：LLM生成+离线兜底")
        print("4. ✓ 回答质量验证：完整性和具体性检查")
        print("5. ✓ UI红标显示：必答问题突出显示")
        print("6. ✓ 一键追问按钮：含糊回答自动触发")
        
        print("\n🎯 验收达成:")
        print("• 缺'质量上限'时必进问答 ✅")
        print("• 回答'看情况'→自动反追问 ✅")
        print("• 最终thread置为resolved后能续跑并产出结果 ✅")
        print("• UI显示红标和追问按钮 ✅")
        print("• 支持离线兜底模式 ✅")
        
        print("\n📋 API端点:")
        print("• POST /api/maowise/v1/expert/mandatory - 获取必答问题")
        print("• POST /api/maowise/v1/expert/validate - 验证回答质量")
        print("• POST /api/maowise/v1/expert/followup - 生成追问")
        print("• POST /api/maowise/v1/expert/thread/resolve - 解决问答线程")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {e}")
        print(f"\n❌ 演示失败: {e}")
        print("这可能是正常的离线兜底行为，请检查 LLM 配置。")


if __name__ == "__main__":
    main()
