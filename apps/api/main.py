from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
import os

from maowise.api_schemas.schemas import PredictIn, PredictOut, RecommendIn, RecommendOut, IngestIn, IngestOut
from maowise.utils.config import load_config
from maowise.utils.logger import logger
from .middleware import LogSanitizationMiddleware, RequestTrackingMiddleware
from maowise.dataflow.ingest import main as ingest_main
from maowise.kb.build_index import build_index
from maowise.kb.search import kb_search
from maowise.models.infer_fwd import predict_performance
from maowise.optimize.engines import recommend_solutions


app = FastAPI(title="MAO-Wise API", version="1.0")

# 加载配置以确定调试模式
cfg = load_config()
debug_llm = cfg.get("llm", {}).get("debug", {}).get("print_full_prompts", False)

# 添加日志脱敏中间件
app.add_middleware(LogSanitizationMiddleware, debug_mode=debug_llm)

# 添加请求跟踪中间件  
app.add_middleware(RequestTrackingMiddleware)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/maowise/v1/ingest", response_model=IngestOut)
def ingest(body: IngestIn) -> Dict[str, Any]:
    cfg = load_config()
    out_dir = f"{cfg['paths']['versions']}/maowise_ds_v1"
    stats = ingest_main(body.pdf_dir, out_dir)
    # build KB
    corpus = f"{cfg['paths']['data_parsed']}/corpus.jsonl"
    build_index(corpus, cfg['paths']['index_store'])
    return {"ok": True, **stats}


@app.post("/api/maowise/v1/predict", response_model=PredictOut)
def predict(body: PredictIn) -> Dict[str, Any]:
    result = predict_performance(body.description, topk_cases=3)
    
    # 检查是否需要专家澄清
    need_expert = result.get("confidence", 1.0) < 0.7
    if need_expert:
        from maowise.experts.clarify import generate_clarify_questions
        
        # 尝试从描述中提取已有信息
        current_data = {}  # 这里可以集成更复杂的信息抽取
        
        questions = generate_clarify_questions(
            current_data=current_data,
            context_description=body.description,
            max_questions=3
        )
        
        if questions:
            result["need_expert"] = True
            result["clarify_questions"] = [q.model_dump() for q in questions]
    
    # 生成预测结果的解释
    try:
        from maowise.experts.explain import make_explanation
        
        explanation = make_explanation(
            result=result,
            result_type="prediction"
        )
        
        result["explanation"] = explanation
        
    except Exception as e:
        logger.warning(f"Failed to generate prediction explanation: {e}")
    
    return result


@app.post("/api/maowise/v1/recommend", response_model=RecommendOut)
def recommend(body: RecommendIn) -> Dict[str, Any]:
    result = recommend_solutions(
        target=body.target,
        current_hint=body.current_hint,
        constraints=body.constraints,
        n_solutions=body.n_solutions,
    )
    
    # 检查是否需要专家澄清
    current_hint = body.current_hint or ""
    confidence = result.get("confidence", 1.0) if isinstance(result, dict) else 1.0
    
    if confidence < 0.8 and current_hint:
        from maowise.experts.clarify import generate_clarify_questions
        
        # 从当前提示中提取已有信息
        current_data = {}  # 可以集成更复杂的信息抽取
        
        questions = generate_clarify_questions(
            current_data=current_data,
            context_description=current_hint,
            max_questions=2
        )
        
        if questions:
            if isinstance(result, dict):
                result["need_expert"] = True
                result["clarify_questions"] = [q.model_dump() for q in questions]
    
    # 为每个方案生成解释和工艺卡
    if isinstance(result, dict) and 'solutions' in result:
        from maowise.experts.explain import make_explanation
        from maowise.experts.plan_writer import make_plan_yaml
        
        enhanced_solutions = []
        for solution in result.get('solutions', []):
            try:
                # 生成解释
                explanation = make_explanation(
                    result={'solutions': [solution], 'target': body.target},
                    result_type="recommendation"
                )
                
                # 生成工艺卡
                plan = make_plan_yaml(solution)
                
                # 增强方案信息
                enhanced_solution = solution.copy()
                enhanced_solution['explanation'] = explanation
                enhanced_solution['plan_yaml'] = plan['yaml_text']
                enhanced_solution['plan_citations'] = plan['citation_map']
                enhanced_solution['hard_constraints_passed'] = plan['hard_constraints_passed']
                
                enhanced_solutions.append(enhanced_solution)
                
            except Exception as e:
                logger.warning(f"Failed to enhance solution: {e}")
                enhanced_solutions.append(solution)
        
        result['solutions'] = enhanced_solutions
    
    return result


@app.post("/api/maowise/v1/kb/search")
def kb_search_api(body: Dict[str, Any]) -> Any:
    query = body.get("query", "")
    k = int(body.get("k", 5))
    filters = body.get("filters")
    return kb_search(query, k=k, filters=filters)


@app.post("/api/maowise/v1/llm/chat")
def llm_chat_api(body: Dict[str, Any]) -> Any:
    """LLM 聊天接口（含 RAG）"""
    from maowise.llm.client import llm_chat
    from maowise.llm.rag import build_rag_prompt
    
    query = body.get("query", "")
    use_rag = body.get("use_rag", True)
    system_prompt = body.get("system_prompt", "You are a helpful assistant for micro-arc oxidation research.")
    
    if use_rag:
        messages = build_rag_prompt(query, system_prompt)
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
    
    response = llm_chat(messages)
    return {
        "response": response.get("content", ""),
        "usage": response.get("usage", {}),
        "finish_reason": response.get("finish_reason", "unknown")
    }


@app.post("/api/maowise/v1/expert/clarify")
def expert_clarify_api(body: Dict[str, Any]) -> Any:
    """生成专家澄清问题"""
    from maowise.experts.clarify import generate_clarify_questions
    
    current_data = body.get("current_data", {})
    context_description = body.get("context_description", "")
    max_questions = body.get("max_questions", 3)
    
    questions = generate_clarify_questions(
        current_data=current_data,
        context_description=context_description,
        max_questions=max_questions
    )
    
    return {
        "questions": [q.model_dump() for q in questions],
        "count": len(questions)
    }


@app.post("/api/maowise/v1/expert/slotfill")
def expert_slotfill_api(body: Dict[str, Any]) -> Any:
    """从专家回答中抽取槽位值"""
    from maowise.experts.slotfill import extract_slot_values
    
    expert_answer = body.get("expert_answer", "")
    current_context = body.get("current_context", "")
    current_data = body.get("current_data")
    
    if not expert_answer:
        return {"error": "expert_answer is required"}
    
    result = extract_slot_values(
        expert_answer=expert_answer,
        current_context=current_context,
        current_data=current_data
    )
    
    return {
        "extracted_values": result.to_dict(),
        "count": len(result.to_dict())
    }


@app.post("/api/maowise/v1/expert/explain")
def expert_explain_api(body: Dict[str, Any]) -> Any:
    """生成带引用的解释"""
    from maowise.experts.explain import make_explanation
    
    result_data = body.get("result", {})
    result_type = body.get("result_type", "prediction")
    
    if not result_data:
        return {"error": "result data is required"}
    
    explanation = make_explanation(
        result=result_data,
        result_type=result_type
    )
    
    return explanation


@app.post("/api/maowise/v1/expert/plan")
def expert_plan_api(body: Dict[str, Any]) -> Any:
    """生成工艺卡YAML"""
    from maowise.experts.plan_writer import make_plan_yaml
    
    solution = body.get("solution", {})
    
    if not solution:
        return {"error": "solution data is required"}
    
    plan = make_plan_yaml(solution)
    
    return plan


@app.post("/api/maowise/v1/expert/mandatory")
def expert_mandatory_api(body: Dict[str, Any]) -> Any:
    """获取必答问题清单"""
    from maowise.experts.clarify import generate_clarify_questions
    
    current_data = body.get("current_data", {})
    expert_answers = body.get("expert_answers", {})
    max_questions = body.get("max_questions", 5)
    
    questions = generate_clarify_questions(
        current_data=current_data,
        context_description="必答问题咨询",
        max_questions=max_questions,
        include_mandatory=True,
        expert_answers=expert_answers
    )
    
    return {
        "questions": [q.model_dump() for q in questions],
        "count": len(questions),
        "mandatory_count": len([q for q in questions if q.is_mandatory])
    }


@app.post("/api/maowise/v1/expert/validate")
def expert_validate_api(body: Dict[str, Any]) -> Any:
    """验证专家回答质量"""
    from maowise.experts.followups import validate_mandatory_answers
    
    answers = body.get("answers", {})
    
    if not answers:
        return {"error": "answers are required"}
    
    validation = validate_mandatory_answers(answers)
    
    return validation


@app.post("/api/maowise/v1/expert/followup")
def expert_followup_api(body: Dict[str, Any]) -> Any:
    """生成追问问题"""
    from maowise.experts.followups import gen_followups, load_question_catalog
    
    question_id = body.get("question_id", "")
    answer = body.get("answer", "")
    
    if not question_id or not answer:
        return {"error": "question_id and answer are required"}
    
    # 获取问题配置
    catalog = load_question_catalog()
    mandatory_questions = catalog.get("mandatory_questions", [])
    question_config = next((q for q in mandatory_questions if q["id"] == question_id), None)
    
    if not question_config:
        return {"error": f"Unknown question_id: {question_id}"}
    
    followups = gen_followups(question_id, answer, question_config)
    
    return {
        "followups": followups,
        "count": len(followups),
        "needs_followup": len(followups) > 0
    }


@app.post("/api/maowise/v1/expert/thread/resolve")
def expert_thread_resolve_api(body: Dict[str, Any]) -> Any:
    """解决专家问答线程并继续流程"""
    from maowise.experts.slotfill import extract_slot_values
    from maowise.experts.followups import validate_mandatory_answers
    
    thread_id = body.get("thread_id", "")
    answers = body.get("answers", {})
    
    if not answers:
        return {"error": "answers are required"}
    
    try:
        # 1. 验证回答质量
        validation = validate_mandatory_answers(answers)
        
        if not validation["all_answered"]:
            return {
                "error": "Not all mandatory questions answered",
                "validation": validation
            }
        
        # 2. 抽取结构化数据
        extracted_data = {}
        for question_id, answer in answers.items():
            if answer.strip():
                slot_result = extract_slot_values(
                    expert_answer=answer,
                    current_context=f"Question: {question_id}",
                    current_data=extracted_data
                )
                extracted_data.update(slot_result.to_dict())
        
        # 3. 标记线程为已解决
        return {
            "thread_id": thread_id,
            "status": "resolved",
            "extracted_data": extracted_data,
            "validation": validation,
            "ready_for_processing": validation["all_answered"] and validation["all_specific"]
        }
        
    except Exception as e:
        logger.error(f"Failed to resolve thread {thread_id}: {e}")
        return {"error": str(e)}


@app.get("/api/maowise/v1/stats/usage")
def get_usage_stats_api(days: int = 7) -> Any:
    """获取LLM使用统计"""
    try:
        from maowise.llm.client import get_usage_stats
        return get_usage_stats(days)
    except Exception as e:
        logger.error(f"Failed to get usage stats: {e}")
        return {"error": str(e)}


@app.get("/api/maowise/v1/health")
def health_check() -> Dict[str, Any]:
    """健康检查端点"""
    from maowise.utils.sanitizer import create_debug_info
    
    try:
        # 基本健康信息
        health_info = {
            "status": "healthy",
            "version": "1.0",
            "service": "MAO-Wise API"
        }
        
        # 如果启用调试模式，包含更多信息
        if debug_llm:
            health_info["debug"] = create_debug_info(include_full_env=True)
        
        return health_info
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": str(e),
            "service": "MAO-Wise API"
        }


