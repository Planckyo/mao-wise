from __future__ import annotations

from typing import Dict, Any


def normalize_record_values(rec: Dict[str, Any]) -> Dict[str, Any]:
    r = dict(rec)
    # clamp alpha/epsilon
    if "alpha_150_2600" in r and r["alpha_150_2600"] is not None:
        r["alpha_150_2600"] = max(0.0, min(1.0, float(r["alpha_150_2600"])))
    if "epsilon_3000_30000" in r and r["epsilon_3000_30000"] is not None:
        r["epsilon_3000_30000"] = max(0.0, min(1.0, float(r["epsilon_3000_30000"])))
    return r

