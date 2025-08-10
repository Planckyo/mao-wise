from __future__ import annotations

from typing import Dict, Any


def enforce_hard_constraints(params: Dict[str, Any], constraints: Dict[str, Any] | None) -> Dict[str, Any]:
    if not constraints:
        return params
    out = dict(params)
    for k, v in constraints.items():
        if isinstance(v, (list, tuple)) and len(v) == 2 and k in out:
            lo, hi = float(v[0]), float(v[1])
            out[k] = min(max(float(out[k]), lo), hi)
    return out

