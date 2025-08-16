# 确保能找到maowise包 - 运行时注入项目根目录
import sys
import pathlib
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
import os
from datetime import datetime
from pydantic import BaseModel

from maowise.api_schemas.schemas import PredictIn, PredictOut, RecommendIn, RecommendOut, IngestIn, IngestOut
from maowise.utils.config import load_config
from maowise.utils.logger import logger
from .middleware import LogSanitizationMiddleware, RequestTrackingMiddleware
from maowise.dataflow.ingest import main as ingest_main
from maowise.kb.build_index import build_index
from maowise.kb.search import kb_search
from maowise.models.infer_fwd import predict_performance
from maowise.models.ensemble import infer_ensemble, get_ensemble_model
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
    """预测性能（优先使用集成模型）"""
    
    # 优先尝试集成模型
    try:
        # 从描述构造payload（这里可以集成更复杂的信息抽取）
        payload = {"text": body.description}
        
        ensemble_result = infer_ensemble(payload)
        
        # 构造兼容的结果格式
        result = {
            "pred_alpha": ensemble_result["pred_alpha"],
            "pred_epsilon": ensemble_result["pred_epsilon"],
            "confidence": ensemble_result.get("confidence", 0.5),
            "uncertainty": ensemble_result.get("uncertainty", {}),
            "model_used": ensemble_result.get("model_used", "ensemble_v2"),
            "components_used": ensemble_result.get("components_used", []),
            "debug_info": ensemble_result.get("debug_info", {}),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Ensemble prediction: α={result['pred_alpha']:.3f}, ε={result['pred_epsilon']:.3f}, model={result['model_used']}")
        
    except Exception as ensemble_error:
        logger.warning(f"Ensemble model failed, falling back to forward model: {ensemble_error}")
        
        # 回退到原始前向模型
        result = predict_performance(body.description, topk_cases=3)
        
        # 添加集成模型格式的字段
        result["uncertainty"] = {"alpha": 0.03, "epsilon": 0.05}
        result["model_used"] = "fwd_v1_fallback"
        result["components_used"] = ["text"]
        result["timestamp"] = datetime.now().isoformat()
        
        logger.info(f"Fallback prediction: α={result['pred_alpha']:.3f}, ε={result['pred_epsilon']:.3f}")
    
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


# 热加载相关模型
class ReloadRequest(BaseModel):
    models: List[str] = ["gp_corrector", "reward_model"]
    force: bool = False

@app.get("/api/maowise/v1/admin/model_status")
def get_model_status() -> Dict[str, Any]:
    """
    获取模型状态端点
    
    返回当前加载的各种模型的路径、修改时间、校验信息等
    """
    try:
        import os
        from datetime import datetime
        
        model_status = {}
        model_paths = {
            "fwd_model": [
                "models_ckpt/fwd_v2",
                "models_ckpt/fwd_v1",
                "models_ckpt/fwd_text_v2"
            ],
            "tabular_model/ensemble": [
                "models_ckpt/tabular_stack_v2",
                "models_ckpt/tabular_v1"
            ],
            "gp_corrector": [
                "models_ckpt/fwd_v2",
                "models_ckpt/gp_corrector"
            ],
            "reward_model": [
                "models_ckpt/reward_v1"
            ]
        }
        
        for model_type, possible_paths in model_paths.items():
            model_info = {
                "type": model_type,
                "status": "missing",
                "path": None,
                "mtime": None,
                "size_mb": None,
                "files": []
            }
            
            # 查找存在的模型路径
            for path in possible_paths:
                if os.path.exists(path):
                    model_info["status"] = "found"
                    model_info["path"] = path
                    
                    # 获取目录信息
                    try:
                        # 获取目录修改时间
                        mtime = os.path.getmtime(path)
                        model_info["mtime"] = datetime.fromtimestamp(mtime).isoformat()
                        
                        # 计算目录大小和文件列表
                        total_size = 0
                        files = []
                        
                        if os.path.isdir(path):
                            for root, dirs, filenames in os.walk(path):
                                for filename in filenames:
                                    filepath = os.path.join(root, filename)
                                    try:
                                        size = os.path.getsize(filepath)
                                        total_size += size
                                        rel_path = os.path.relpath(filepath, path)
                                        files.append({
                                            "name": rel_path,
                                            "size_bytes": size,
                                            "mtime": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                                        })
                                    except (OSError, IOError):
                                        continue
                        else:
                            # 单个文件
                            size = os.path.getsize(path)
                            total_size = size
                            files.append({
                                "name": os.path.basename(path),
                                "size_bytes": size,
                                "mtime": model_info["mtime"]
                            })
                        
                        model_info["size_mb"] = round(total_size / (1024 * 1024), 2)
                        model_info["files"] = files[:10]  # 最多显示10个文件
                        if len(files) > 10:
                            model_info["total_files"] = len(files)
                        
                        # 特殊处理GP校正器：检测gp_epsilon_*.pkl和calib_epsilon_*.pkl文件
                        if model_type == "gp_corrector":
                            gp_files = [f for f in files if f["name"].startswith("gp_epsilon_") and f["name"].endswith(".pkl")]
                            calib_files = [f for f in files if f["name"].startswith("calib_epsilon_") and f["name"].endswith(".pkl")]
                            
                            model_info["gp_correctors"] = {}
                            model_info["isotonic_calibrators"] = {}
                            
                            # 提取体系名并记录状态
                            for gp_file in gp_files:
                                system = gp_file["name"].replace("gp_epsilon_", "").replace(".pkl", "")
                                model_info["gp_correctors"][system] = {
                                    "found": True,
                                    "file": gp_file["name"],
                                    "mtime": gp_file["mtime"],
                                    "size_bytes": gp_file["size_bytes"]
                                }
                            
                            for calib_file in calib_files:
                                system = calib_file["name"].replace("calib_epsilon_", "").replace(".pkl", "")
                                model_info["isotonic_calibrators"][system] = {
                                    "found": True,
                                    "file": calib_file["name"],
                                    "mtime": calib_file["mtime"],
                                    "size_bytes": calib_file["size_bytes"]
                                }
                            
                            # 统计校正器状态
                            systems_with_gp = set(model_info["gp_correctors"].keys())
                            systems_with_calib = set(model_info["isotonic_calibrators"].keys())
                            systems_complete = systems_with_gp & systems_with_calib
                            
                            model_info["corrector_summary"] = {
                                "total_gp_correctors": len(systems_with_gp),
                                "total_isotonic_calibrators": len(systems_with_calib),
                                "complete_systems": list(systems_complete),
                                "partial_systems": list((systems_with_gp | systems_with_calib) - systems_complete)
                            }
                        
                    except (OSError, IOError) as e:
                        model_info["error"] = f"Failed to read model info: {e}"
                    
                    break  # 找到第一个存在的路径就停止
            
            model_status[model_type] = model_info
        
        # 获取LLM配置状态
        from maowise.llm.client import get_llm_status
        llm_status = get_llm_status()
        
        # 计算总体状态
        total_models = len(model_status)
        found_models = len([m for m in model_status.values() if m["status"] == "found"])
        
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_models": total_models,
                "found_models": found_models,
                "missing_models": total_models - found_models,
                "overall_status": "healthy" if found_models >= total_models // 2 else "degraded"
            },
            "models": model_status,
            # 新增LLM状态信息
            "llm_provider": llm_status["llm_provider"],
            "llm_key_source": llm_status["llm_key_source"],
            "llm_providers_available": llm_status["providers_available"]
        }
        
    except Exception as e:
        logger.error(f"Model status check failed: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "summary": {
                "overall_status": "error"
            }
        }

@app.post("/api/maowise/v1/admin/reload")
def reload_models(body: ReloadRequest) -> Dict[str, Any]:
    """
    热加载模型端点
    
    支持重新加载：
    - gp_corrector: 残差校正器
    - reward_model: 偏好模型
    """
    try:
        import os
        from datetime import datetime
        reload_results = {}
        missing_models = []
        
        # 预检查模型文件是否存在
        model_paths = {
            "gp_corrector": "models_ckpt/gp_corrector",
            "reward_model": "models_ckpt/reward_v1"
        }
        
        # 添加集成模型检查
        model_paths["ensemble"] = "models_ckpt"
        
        for model_name in body.models:
            if model_name in model_paths:
                model_path = model_paths[model_name]
                if model_name != "ensemble" and not os.path.exists(model_path):
                    missing_models.append({
                        "model": model_name,
                        "expected_path": model_path,
                        "message": f"模型文件不存在: {model_path}"
                    })
        
        # 如果有缺失的模型文件，返回409错误
        if missing_models and not body.force:
            logger.error(f"Model reload failed: missing model files {[m['model'] for m in missing_models]}")
            raise HTTPException(
                status_code=409, 
                detail={
                    "error": "模型文件缺失",
                    "message": "无法重新加载模型，因为以下模型文件不存在",
                    "missing_models": missing_models,
                    "suggestion": "请先训练相应模型或使用 force=true 强制重载"
                }
            )
        
        for model_name in body.models:
            try:
                if model_name == "gp_corrector":
                    model_path = model_paths.get(model_name, "")
                    
                    if not os.path.exists(model_path) and not body.force:
                        reload_results[model_name] = {
                            "status": "missing",
                            "message": f"GP校正器文件不存在: {model_path}"
                        }
                        continue
                        
                    # 重新加载GP校正器
                    try:
                        from maowise.models.residual.gp_corrector import reload_gp_corrector
                        success = reload_gp_corrector(force=body.force)
                        reload_results[model_name] = {
                            "status": "success" if success else "failed",
                            "message": "GP校正器重新加载成功" if success else "GP校正器重新加载失败",
                            "path": model_path if os.path.exists(model_path) else None
                        }
                    except ImportError:
                        reload_results[model_name] = {
                            "status": "not_implemented",
                            "message": "GP校正器重载功能未实现"
                        }
                    
                elif model_name == "reward_model":
                    model_path = model_paths.get(model_name, "")
                    
                    if not os.path.exists(model_path) and not body.force:
                        reload_results[model_name] = {
                            "status": "missing",
                            "message": f"偏好模型文件不存在: {model_path}"
                        }
                        continue
                        
                    # 重新加载偏好模型
                    try:
                        from maowise.models.reward.train_reward import reload_reward_model
                        success = reload_reward_model(force=body.force)
                        reload_results[model_name] = {
                            "status": "success" if success else "failed", 
                            "message": "偏好模型重新加载成功" if success else "偏好模型重新加载失败",
                            "path": model_path if os.path.exists(model_path) else None
                        }
                    except ImportError:
                        reload_results[model_name] = {
                            "status": "not_implemented",
                            "message": "偏好模型重载功能未实现"
                        }
                
                elif model_name == "ensemble":
                    # 重新加载集成模型
                    try:
                        ensemble = get_ensemble_model()
                        ensemble.reload_models()
                        
                        # 获取加载状态
                        status = ensemble.get_model_status()
                        loaded_components = sum(status['loaded_components'].values())
                        total_components = len(status['loaded_components'])
                        
                        reload_results[model_name] = {
                            "status": "success",
                            "message": f"集成模型重新加载成功 ({loaded_components}/{total_components} 组件)",
                            "loaded_components": status['loaded_components'],
                            "available_models": status['available_models']
                        }
                        
                    except Exception as e:
                        reload_results[model_name] = {
                            "status": "error",
                            "message": f"集成模型重载失败: {str(e)}"
                        }
                    
                else:
                    reload_results[model_name] = {
                        "status": "skipped",
                        "message": f"未知模型类型: {model_name}"
                    }
                    
            except Exception as e:
                logger.error(f"Failed to reload {model_name}: {e}")
                reload_results[model_name] = {
                    "status": "error",
                    "message": str(e)
                }
        
        # 判断整体状态
        all_success = all(result["status"] == "success" for result in reload_results.values())
        any_success = any(result["status"] == "success" for result in reload_results.values())
        
        return {
            "status": "success" if all_success else ("partial" if any_success else "failed"),
            "message": "模型热加载完成",
            "results": reload_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        # 重新抛出HTTP异常（如409）
        raise
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"模型热加载失败: {str(e)}")


