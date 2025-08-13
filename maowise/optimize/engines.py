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

