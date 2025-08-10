from __future__ import annotations

from typing import Dict, Any
from ..dataflow.ner_rules import extract_fields_from_text


def render_training_text(rec: Dict[str, Any]) -> str:
    # 将结构化记录反渲染为模板文本
    parts = [
        f"合金: {rec.get('substrate_alloy','<unk>')}",
        f"电解质: {rec.get('electrolyte_family','mixed')}",
        f"模式: {rec.get('mode','dc')}",
        f"电压: {rec.get('voltage_V','<unk>')} V",
        f"电流密度: {rec.get('current_density_A_dm2','<unk>')} A/dm2",
        f"频率: {rec.get('frequency_Hz','<unk>')} Hz",
        f"占空比: {rec.get('duty_cycle_pct','<unk>')} %",
        f"时间: {rec.get('time_min','<unk>')} min",
    ]
    if rec.get("temp_C") is not None:
        parts.append(f"温度: {rec['temp_C']} C")
    if rec.get("pH") is not None:
        parts.append(f"pH: {rec['pH']}")
    return "；".join(parts)


def parse_free_text_to_slots(text: str) -> Dict[str, Any]:
    slots = extract_fields_from_text(text)
    # 填默认
    slots.setdefault("electrolyte_family", "mixed")
    slots.setdefault("mode", "dc")
    return slots


def compose_input_text_from_slots(slots: Dict[str, Any]) -> str:
    return render_training_text(slots)

