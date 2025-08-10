from __future__ import annotations

from typing import Dict, Any
from ..models.infer_fwd import get_model
from ..models.dataset_builder import compose_input_text_from_slots


def evaluate_objectives(params: Dict[str, Any], target: Dict[str, float]) -> Dict[str, Any]:
    """
    调用正向模型，返回误差目标与预测值。
    """
    text = compose_input_text_from_slots(params)
    model = get_model()
    pred = model.predict(text)
    da = abs(pred["alpha"] - float(target.get("alpha", 0.0)))
    de = abs(pred["epsilon"] - float(target.get("epsilon", 0.0)))
    return {"f1": da, "f2": de, "pred": pred}

