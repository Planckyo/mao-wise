from __future__ import annotations

from typing import Dict, Any, List
import numpy as np

try:
    from pymoo.core.problem import Problem  # type: ignore
    from pymoo.optimize import minimize  # type: ignore
    from pymoo.algorithms.moo.nsga2 import NSGA2  # type: ignore
    from pymoo.termination import get_termination  # type: ignore
    PYMOO_AVAILABLE = True
except Exception:
    PYMOO_AVAILABLE = False

from .space import get_variable_space, vector_to_params
from .objectives import evaluate_objectives, calculate_weighted_score
from ..kb.search import kb_search
from ..utils.config import load_config
import copy
import random


if PYMOO_AVAILABLE:
    class OptProblem(Problem):
        def __init__(self, keys: List[str], bounds: Dict[str, List[float]], target: Dict[str, float]):
            self.keys = keys
            self.bounds = bounds
            xl = np.array([bounds[k][0] for k in keys], dtype=float)
            xu = np.array([bounds[k][1] for k in keys], dtype=float)
            # 更新为4目标优化：Alpha, Epsilon, 薄/轻, 均匀性
            super().__init__(n_var=len(keys), n_obj=4, xl=xl, xu=xu)
            self.target = target

        def _evaluate(self, X, out, *args, **kwargs):
            F = []
            for row in X:
                params = vector_to_params(row.tolist(), self.keys)
                obj = evaluate_objectives(params, self.target)
                # 4个目标：Alpha误差, Epsilon误差, 质量代理, 均匀性惩罚
                F.append([obj["f1"], obj["f2"], obj["f3"], obj["f4"]])
            out["F"] = np.array(F)


def _sample_random(bounds: Dict[str, List[float]], n: int) -> List[Dict[str, Any]]:
    keys = list(bounds.keys())
    sols = []
    for _ in range(n):
        p = {k: float(np.random.uniform(bounds[k][0], bounds[k][1])) for k in keys}
        sols.append(p)
    return sols


def _build_rationale(params: Dict[str, Any]) -> str:
    return (
        f"提高电压至 {params.get('voltage_V', '<unk>')} V，调整时间至 {params.get('time_min','<unk>')} min，"
        f"并保持占空比 {params.get('duty_cycle_pct','<unk>')}% 以靠近目标"
    )


def recommend_solutions(
    target: Dict[str, float],
    current_hint: str | None,
    constraints: Dict[str, Any] | None,
    n_solutions: int = 5,
) -> Dict[str, Any]:
    bounds = get_variable_space(constraints)
    keys = list(bounds.keys())

    try:
        if PYMOO_AVAILABLE:
            problem = OptProblem(keys=keys, bounds=bounds, target=target)  # type: ignore[name-defined]
            algo = NSGA2(pop_size=32)  # type: ignore[name-defined]
            res = minimize(problem, algo, get_termination("n_gen", 10), verbose=False)  # type: ignore[name-defined]
            X = res.X if res.X is not None else np.empty((0, len(keys)))
            if X.ndim == 1 and X.size > 0:
                X = X.reshape(1, -1)
            candidates = [vector_to_params(row.tolist(), keys) for row in X[: 5 * n_solutions]]
        else:
            raise RuntimeError("pymoo not available")
    except Exception:
        # fallback to random sampling
        candidates = _sample_random(bounds, 10 * n_solutions)

    # 加载配置权重
    try:
        config = load_config()
        weights = config.get('optimize', {}).get('weights', {
            'alpha': 0.4, 'epsilon': 0.4, 'thin_light': 0.15, 'uniform': 0.05
        })
    except Exception:
        weights = {'alpha': 0.4, 'epsilon': 0.4, 'thin_light': 0.15, 'uniform': 0.05}

    # 评分候选方案（使用加权总分）
    scored: List[Dict[str, Any]] = []
    for p in candidates:
        obj = evaluate_objectives(p, target)
        
        # 计算加权总分
        weighted_score = calculate_weighted_score(obj, weights)
        
        # 保存完整的目标信息
        scored.append({
            "params": p, 
            "pred": obj["pred"], 
            "score": weighted_score,
            "objectives": obj,
            "mass_proxy": obj.get("mass_proxy", 0.0),
            "uniformity_penalty": obj.get("uniformity_penalty", 0.0)
        })
    
    scored.sort(key=lambda x: x["score"])  # lower is better
    top = scored[:n_solutions]

    solutions = []
    for item in top:
        params = item["params"]
        pred = item["pred"]
        objectives = item["objectives"]
        rationale = _build_rationale(params)
        
        # 扩展rationale包含薄/轻/均匀信息
        mass_info = "薄膜" if item["mass_proxy"] < 0.3 else "中等厚度" if item["mass_proxy"] < 0.6 else "厚膜"
        uniform_info = "均匀" if item["uniformity_penalty"] < 0.2 else "一般" if item["uniformity_penalty"] < 0.5 else "不均匀"
        
        enhanced_rationale = f"{rationale}。预期{mass_info}，形貌{uniform_info}。"
        
        # evidence from KB
        q = f"MAO {params.get('voltage_V','')} V {params.get('time_min','')} min {params.get('duty_cycle_pct','')}%"
        try:
            evidence = kb_search(q, k=3)
        except Exception:
            evidence = []
            
        solutions.append({
            "delta": params,
            "predicted": {
                "alpha": pred["alpha"], 
                "epsilon": pred["epsilon"], 
                "confidence": pred["confidence"]
            },
            "rationale": enhanced_rationale,
            "evidence": evidence,
            # 新增字段
            "mass_proxy": item["mass_proxy"],
            "uniformity_penalty": item["uniformity_penalty"],
            "score_total": item["score"],
            "objectives_breakdown": {
                "alpha_error": objectives.get("f1", 0.0),
                "epsilon_error": objectives.get("f2", 0.0),
                "mass_proxy": objectives.get("f3", 0.0),
                "uniformity_penalty": objectives.get("f4", 0.0)
            }
        })

    pareto = {
        "target": target,
        "best_error_sum": top[0]["score"] if top else None,
        "num_candidates": len(candidates),
    }
    return {"solutions": solutions, "pareto_front_summary": pareto}


def make_variants(plan: Dict[str, Any], mode: str, constraints: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    生成参数微调变体，用于联立收敛优化
    
    Args:
        plan: 基础方案参数
        mode: 微调模式
            - "reduce_alpha": 降低Alpha（适用于ε高但α偏高的点）
            - "boost_epsilon": 提升Epsilon（适用于α低但ε偏低的点）
        constraints: 参数约束边界
        
    Returns:
        变体方案列表（2-3个）
    """
    if constraints is None:
        bounds = get_variable_space(None)
    else:
        bounds = get_variable_space(constraints)
    
    variants = []
    base_plan = copy.deepcopy(plan)
    
    # 确保基础参数在边界内
    def clamp_value(value: float, param_name: str) -> float:
        if param_name in bounds:
            return max(bounds[param_name][0], min(bounds[param_name][1], value))
        return value
    
    if mode == "reduce_alpha":
        # 模式1：降低Alpha（ε 高、α 偏高）
        # 策略：time -15%、duty -5pp、voltage -2~5%、frequency=600~900、waveform="bipolar"
        
        # 变体1：保守调整
        variant1 = copy.deepcopy(base_plan)
        variant1["time_min"] = clamp_value(variant1.get("time_min", 15) * 0.85, "time_min")  # -15%
        variant1["duty_cycle_pct"] = clamp_value(variant1.get("duty_cycle_pct", 25) - 5, "duty_cycle_pct")  # -5pp
        variant1["voltage_V"] = clamp_value(variant1.get("voltage_V", 350) * 0.98, "voltage_V")  # -2%
        variant1["frequency_Hz"] = clamp_value(750, "frequency_Hz")  # 中等频率
        variant1["waveform"] = "bipolar"
        variants.append(variant1)
        
        # 变体2：激进调整
        variant2 = copy.deepcopy(base_plan)
        variant2["time_min"] = clamp_value(variant2.get("time_min", 15) * 0.85, "time_min")  # -15%
        variant2["duty_cycle_pct"] = clamp_value(variant2.get("duty_cycle_pct", 25) - 5, "duty_cycle_pct")  # -5pp
        variant2["voltage_V"] = clamp_value(variant2.get("voltage_V", 350) * 0.95, "voltage_V")  # -5%
        variant2["frequency_Hz"] = clamp_value(600, "frequency_Hz")  # 低频率
        variant2["waveform"] = "bipolar"
        variants.append(variant2)
        
        # 变体3：平衡调整
        variant3 = copy.deepcopy(base_plan)
        variant3["time_min"] = clamp_value(variant3.get("time_min", 15) * 0.85, "time_min")  # -15%
        variant3["duty_cycle_pct"] = clamp_value(variant3.get("duty_cycle_pct", 25) - 5, "duty_cycle_pct")  # -5pp
        variant3["voltage_V"] = clamp_value(variant3.get("voltage_V", 350) * 0.96, "voltage_V")  # -4%
        variant3["frequency_Hz"] = clamp_value(900, "frequency_Hz")  # 高频率
        variant3["waveform"] = "bipolar"
        variants.append(variant3)
        
    elif mode == "boost_epsilon":
        # 模式2：提升Epsilon（α 低、ε 偏低）
        # 策略：frequency +150~200Hz、duty +3~5pp、time +10~15%、保持电压区间
        
        # 变体1：保守提升
        variant1 = copy.deepcopy(base_plan)
        variant1["frequency_Hz"] = clamp_value(variant1.get("frequency_Hz", 1000) + 150, "frequency_Hz")  # +150Hz
        variant1["duty_cycle_pct"] = clamp_value(variant1.get("duty_cycle_pct", 25) + 3, "duty_cycle_pct")  # +3pp
        variant1["time_min"] = clamp_value(variant1.get("time_min", 15) * 1.10, "time_min")  # +10%
        variants.append(variant1)
        
        # 变体2：激进提升
        variant2 = copy.deepcopy(base_plan)
        variant2["frequency_Hz"] = clamp_value(variant2.get("frequency_Hz", 1000) + 200, "frequency_Hz")  # +200Hz
        variant2["duty_cycle_pct"] = clamp_value(variant2.get("duty_cycle_pct", 25) + 5, "duty_cycle_pct")  # +5pp
        variant2["time_min"] = clamp_value(variant2.get("time_min", 15) * 1.15, "time_min")  # +15%
        variants.append(variant2)
        
        # 变体3：平衡提升
        variant3 = copy.deepcopy(base_plan)
        variant3["frequency_Hz"] = clamp_value(variant3.get("frequency_Hz", 1000) + 175, "frequency_Hz")  # +175Hz
        variant3["duty_cycle_pct"] = clamp_value(variant3.get("duty_cycle_pct", 25) + 4, "duty_cycle_pct")  # +4pp
        variant3["time_min"] = clamp_value(variant3.get("time_min", 15) * 1.12, "time_min")  # +12%
        variants.append(variant3)
    
    else:
        raise ValueError(f"未知的微调模式: {mode}")
    
    return variants


def find_convergence_seeds(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    从候选方案中找到联立收敛的种子点
    
    Args:
        candidates: 候选方案列表
        
    Returns:
        种子点字典，包含"reduce_alpha"和"boost_epsilon"两类
    """
    seeds = {
        "reduce_alpha": [],    # ε>=0.82 && α>0.20
        "boost_epsilon": []    # α<=0.20 && ε<0.80
    }
    
    for candidate in candidates:
        pred = candidate.get("pred", {})
        alpha = pred.get("alpha", 0.0)
        epsilon = pred.get("epsilon", 0.0)
        
        # 种子1：高ε但α偏高（需要降低Alpha）
        if epsilon >= 0.82 and alpha > 0.20:
            seeds["reduce_alpha"].append(candidate)
        
        # 种子2：低α但ε偏低（需要提升Epsilon）
        if alpha <= 0.20 and epsilon < 0.80:
            seeds["boost_epsilon"].append(candidate)
    
    return seeds


def generate_convergence_variants(
    initial_candidates: List[Dict[str, Any]], 
    constraints: Dict[str, Any] = None,
    target: Dict[str, float] = None
) -> List[Dict[str, Any]]:
    """
    基于初始候选生成联立收敛变体
    
    Args:
        initial_candidates: 初始候选列表
        constraints: 参数约束
        target: 目标值
        
    Returns:
        包含原始候选和新变体的完整列表
    """
    if target is None:
        target = {"alpha": 0.20, "epsilon": 0.80}
    
    # 找到种子点
    seeds = find_convergence_seeds(initial_candidates)
    
    all_variants = []
    
    # 生成reduce_alpha变体
    for seed in seeds["reduce_alpha"][:3]:  # 最多取3个种子
        variants = make_variants(seed["params"], "reduce_alpha", constraints)
        for variant_params in variants:
            # 重新评估变体
            obj = evaluate_objectives(variant_params, target)
            
            # 加载配置权重
            try:
                config = load_config()
                weights = config.get('optimize', {}).get('weights', {
                    'alpha': 0.4, 'epsilon': 0.4, 'thin_light': 0.15, 'uniform': 0.05
                })
            except Exception:
                weights = {'alpha': 0.4, 'epsilon': 0.4, 'thin_light': 0.15, 'uniform': 0.05}
            
            weighted_score = calculate_weighted_score(obj, weights)
            
            variant_candidate = {
                "params": variant_params,
                "pred": obj["pred"],
                "score": weighted_score,
                "objectives": obj,
                "mass_proxy": obj.get("mass_proxy", 0.0),
                "uniformity_penalty": obj.get("uniformity_penalty", 0.0),
                "variant_source": "reduce_alpha"
            }
            all_variants.append(variant_candidate)
    
    # 生成boost_epsilon变体
    for seed in seeds["boost_epsilon"][:3]:  # 最多取3个种子
        variants = make_variants(seed["params"], "boost_epsilon", constraints)
        for variant_params in variants:
            # 重新评估变体
            obj = evaluate_objectives(variant_params, target)
            
            # 加载配置权重
            try:
                config = load_config()
                weights = config.get('optimize', {}).get('weights', {
                    'alpha': 0.4, 'epsilon': 0.4, 'thin_light': 0.15, 'uniform': 0.05
                })
            except Exception:
                weights = {'alpha': 0.4, 'epsilon': 0.4, 'thin_light': 0.15, 'uniform': 0.05}
            
            weighted_score = calculate_weighted_score(obj, weights)
            
            variant_candidate = {
                "params": variant_params,
                "pred": obj["pred"],
                "score": weighted_score,
                "objectives": obj,
                "mass_proxy": obj.get("mass_proxy", 0.0),
                "uniformity_penalty": obj.get("uniformity_penalty", 0.0),
                "variant_source": "boost_epsilon"
            }
            all_variants.append(variant_candidate)
    
    # 合并原始候选和变体，去重
    combined = initial_candidates + all_variants
    
    # 基于参数去重（避免完全相同的方案）
    unique_candidates = []
    seen_params = set()
    
    for candidate in combined:
        # 创建参数的哈希键用于去重
        params = candidate["params"]
        param_key = tuple(sorted([(k, round(v, 4) if isinstance(v, (int, float)) else v) 
                                 for k, v in params.items()]))
        
        if param_key not in seen_params:
            seen_params.add(param_key)
            unique_candidates.append(candidate)
    
    # 按score排序
    unique_candidates.sort(key=lambda x: x["score"], reverse=False)  # 越小越好
    
    return unique_candidates

