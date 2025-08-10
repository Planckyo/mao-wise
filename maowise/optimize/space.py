from __future__ import annotations

from typing import Dict, Any, Tuple, List
from ..utils import load_config


def get_variable_space(constraints: Dict[str, Any] | None = None) -> Dict[str, Tuple[float, float]]:
    cfg = load_config()
    bounds = dict(cfg["optimize"]["bounds"])  # copy
    if constraints:
        for k, v in constraints.items():
            if k in bounds and isinstance(v, (list, tuple)) and len(v) == 2:
                lo, hi = float(v[0]), float(v[1])
                lo0, hi0 = bounds[k]
                bounds[k] = [max(lo, lo0), min(hi, hi0)]
    return bounds


def vector_to_params(x: List[float], keys: List[str]) -> Dict[str, Any]:
    return {k: float(v) for k, v in zip(keys, x)}

