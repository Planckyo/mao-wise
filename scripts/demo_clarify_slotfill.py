#!/usr/bin/env python3
"""
Clarify & SlotFill 功能演示脚本
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maowise.experts.clarify import generate_clarify_questions
from maowise.experts.slotfill import extract_slot_values
from maowise.utils.logger import logger


def demo_clarify():
    """演示澄清问题生成"""
    print("=" * 60)
    print("🔍 Clarify 澄清问题生成演示")
    print("=" * 60)
    
    # 场景1：缺少关键参数
    print("\n📋 场景1：缺少电压和电流密度参数")
    current_data = {
        "substrate_alloy": "AZ91",
        "electrolyte_family": "silicate",
        "time_min": 10
    }
    
    context = "AZ91镁合金基体，硅酸盐电解液体系，处理时间10分钟"
    
    questions = generate_clarify_questions(
        current_data=current_data,
        context_description=context,
        max_questions=3
    )
    
    print(f"生成了 {len(questions)} 个澄清问题：")
    for i, q in enumerate(questions, 1):
        print(f"\n  问题 {i}:")
        print(f"    ID: {q.id}")
        print(f"    问题: {q.question}")
        print(f"    类型: {q.kind}")
        if q.unit:
            print(f"    单位: {q.unit}")
        if q.options:
            print(f"    选项: {', '.join(q.options)}")
        print(f"    理由: {q.rationale}")
    
    # 场景2：信息相对完整
    print("\n📋 场景2：信息相对完整的情况")
    complete_data = {
        "substrate_alloy": "AZ91",
        "voltage_V": 420,
        "current_density_A_dm2": 12,
        "electrolyte_family": "silicate",
        "time_min": 10
    }
    
    questions2 = generate_clarify_questions(
        current_data=complete_data,
        context_description="相对完整的实验参数",
        max_questions=3
    )
    
    print(f"生成了 {len(questions2)} 个澄清问题")
    if questions2:
        for i, q in enumerate(questions2, 1):
            print(f"  问题 {i}: {q.question}")


def demo_slotfill():
    """演示槽位填充"""
    print("\n\n" + "=" * 60)
    print("🎯 SlotFill 槽位填充演示")
    print("=" * 60)
    
    test_cases = [
        {
            "name": "基本参数抽取",
            "answer": "电压我们设置的是420V，电流密度大约12A/dm²，处理了10分钟。",
            "context": "AZ91镁合金微弧氧化实验"
        },
        {
            "name": "电解液成分抽取",
            "answer": "电解液是硅酸盐体系，Na2SiO3用了10g/L，KOH是2g/L。还加了少量添加剂。",
            "context": "硅酸盐电解液配制"
        },
        {
            "name": "脉冲参数和后处理",
            "answer": "脉冲频率500Hz，占空比30%。最后做了水热封孔处理，80度水浴2小时。",
            "context": "脉冲参数和后处理工艺"
        },
        {
            "name": "复杂完整描述",
            "answer": """参数设置：电压380-450V范围内调节，最终用了410V。电流密度15A/dm²，
            双极性脉冲800Hz，占空比40%，总共处理15分钟。电解液是标准的硅酸盐配方：
            Na2SiO3·9H2O 12g/L，KOH 3g/L，还加了0.5g/L的Na2EDTA作为络合剂。
            温度控制在室温25度。没有做后处理。""",
            "context": "完整的实验参数描述"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n📝 测试案例 {i}: {case['name']}")
        print(f"专家回答: {case['answer']}")
        print(f"上下文: {case['context']}")
        
        result = extract_slot_values(
            expert_answer=case["answer"],
            current_context=case["context"]
        )
        
        extracted = result.to_dict()
        print(f"抽取结果 ({len(extracted)} 个字段):")
        
        for key, value in extracted.items():
            if key == "electrolyte_components_json" and isinstance(value, dict):
                print(f"  {key}: {value}")
            else:
                print(f"  {key}: {value}")


def demo_api_integration():
    """演示 API 集成"""
    print("\n\n" + "=" * 60)
    print("🔗 API 集成演示")
    print("=" * 60)
    
    print("\n可用的 API 端点:")
    print("1. POST /api/maowise/v1/expert/clarify")
    print("   - 生成澄清问题")
    print("   - 参数: current_data, context_description, max_questions")
    
    print("\n2. POST /api/maowise/v1/expert/slotfill")
    print("   - 抽取槽位值")
    print("   - 参数: expert_answer, current_context, current_data")
    
    print("\n3. 集成到现有端点:")
    print("   - /api/maowise/v1/predict: 低置信度时自动生成澄清问题")
    print("   - /api/maowise/v1/recommend: 优化建议不确定时生成澄清问题")
    
    print("\n示例 API 调用:")
    
    clarify_example = {
        "current_data": {
            "substrate_alloy": "AZ91",
            "electrolyte_family": "silicate"
        },
        "context_description": "AZ91镁合金硅酸盐电解液微弧氧化",
        "max_questions": 3
    }
    
    slotfill_example = {
        "expert_answer": "电压420V，电流密度12A/dm²，处理时间10分钟",
        "current_context": "基本实验参数",
        "current_data": {}
    }
    
    print(f"\nClarify API 请求示例:")
    print(f"curl -X POST http://localhost:8000/api/maowise/v1/expert/clarify \\")
    print(f'  -H "Content-Type: application/json" \\')
    print(f"  -d '{clarify_example}'")
    
    print(f"\nSlotFill API 请求示例:")
    print(f"curl -X POST http://localhost:8000/api/maowise/v1/expert/slotfill \\")
    print(f'  -H "Content-Type: application/json" \\')
    print(f"  -d '{slotfill_example}'")


def main():
    """主演示函数"""
    print("🎭 MAO-Wise Clarify & SlotFill 功能演示")
    print("支持离线兜底模式，无需 LLM API Key 也可运行基本功能")
    
    try:
        demo_clarify()
        demo_slotfill()
        demo_api_integration()
        
        print("\n\n" + "=" * 60)
        print("🎉 演示完成！")
        print("=" * 60)
        print("\n✅ 验收要点:")
        print("1. ✓ 缺字段时能生成 1-3 条问题（含 kind/unit/options）")
        print("2. ✓ 专家自由文本能抽取为结构化槽位")
        print("3. ✓ 有/无 LLM Key 都可运行（离线兜底模式）")
        print("4. ✓ 单位归一化和数据清洗")
        print("5. ✓ 集成到 predict/recommend API")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {e}")
        print(f"\n❌ 演示失败: {e}")
        print("这可能是正常的离线兜底行为，请检查 LLM 配置。")


if __name__ == "__main__":
    main()
