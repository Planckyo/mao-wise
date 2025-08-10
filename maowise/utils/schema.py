from __future__ import annotations

from typing import Dict, Any, List
from copy import deepcopy
from .logger import logger


minimal_required_keys: List[str] = [
    "substrate_alloy",
    "electrolyte_family",
    "electrolyte_components",
    "mode",
    "voltage_V",
    "current_density_A_dm2",
    "frequency_Hz",
    "duty_cycle_pct",
    "time_min",
    "alpha_150_2600",
    "epsilon_3000_30000",
    "source_pdf",
    "page",
    "sample_id",
    "extraction_status",
]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _normalize_units(rec: Dict[str, Any]) -> None:
    # Current density: if alternative keys exist, convert
    if "current_density_A_cm2" in rec and "current_density_A_dm2" not in rec:
        # 1 dm^2 = 100 cm^2 → A/cm^2 * 100 = A/dm^2
        rec["current_density_A_dm2"] = float(rec["current_density_A_cm2"]) * 100.0

    # Duty cycle stored in percent
    if 0 < rec.get("duty_cycle_pct", 0) <= 1.0:
        rec["duty_cycle_pct"] = float(rec["duty_cycle_pct"]) * 100.0

    # Time to minutes if seconds detected
    if "time_s" in rec and "time_min" not in rec:
        rec["time_min"] = float(rec["time_s"]) / 60.0


def _range_checks(rec: Dict[str, Any], warnings: List[str]) -> None:
    # Clamp alpha/epsilon to [0,1]
    if "alpha_150_2600" in rec:
        a = float(rec["alpha_150_2600"]) if rec["alpha_150_2600"] is not None else None
        if a is not None:
            if not (0.0 <= a <= 1.0):
                warnings.append(f"alpha out of range: {a}")
            rec["alpha_150_2600"] = _clamp(a, 0.0, 1.0)

    if "epsilon_3000_30000" in rec:
        e = float(rec["epsilon_3000_30000"]) if rec["epsilon_3000_30000"] is not None else None
        if e is not None:
            if not (0.0 <= e <= 1.0):
                warnings.append(f"epsilon out of range: {e}")
            rec["epsilon_3000_30000"] = _clamp(e, 0.0, 1.0)

    # Reasonable ranges for process params (soft checks)
    reasonable = {
        "voltage_V": (0, 1000),
        "current_density_A_dm2": (0, 200),
        "frequency_Hz": (0, 5000),
        "duty_cycle_pct": (0, 100),
        "time_min": (0, 360),
        "temp_C": (-20, 200),
        "pH": (0, 14),
        "thickness_um": (0, 500),
        "roughness_Ra_um": (0, 50),
        "porosity_pct": (0, 80),
    }
    for k, (lo, hi) in reasonable.items():
        if k in rec and rec[k] is not None:
            v = float(rec[k])
            if not (lo <= v <= hi):
                warnings.append(f"{k}={v} out of [{lo},{hi}]")


def validate_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    单条样本的单位换算、范围校验与缺失检查。
    返回副本，增加 `warnings` 与修正后的字段。
    失败样本自动标注 extraction_status="partial"。
    """
    rec = deepcopy(rec)
    rec.setdefault("extraction_status", "ok")
    warnings: List[str] = []

    try:
        _normalize_units(rec)
        _range_checks(rec, warnings)
    except Exception as e:
        warnings.append(f"normalization_error: {e}")

    missing = [k for k in minimal_required_keys if k not in rec or rec[k] in (None, "", [])]
    if missing:
        warnings.append("missing_required:" + ",".join(missing))
        rec["extraction_status"] = "partial"

    rec["warnings"] = warnings
    if warnings:
        logger.debug(f"validate_record warnings: {warnings}")
    return rec

