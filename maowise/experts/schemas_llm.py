from __future__ import annotations

from typing import Dict, Any, List, Optional, Union, Literal
from pydantic import BaseModel, Field


class ClarifyQuestion(BaseModel):
    """专家澄清问题的数据结构"""
    id: str = Field(description="问题的唯一标识符")
    question: str = Field(description="问题内容")
    kind: Literal["choice", "number", "text"] = Field(description="问题类型")
    options: Optional[List[str]] = Field(default=None, description="选择题的选项列表")
    unit: Optional[str] = Field(default=None, description="数值问题的单位")
    rationale: str = Field(description="为什么需要这个参数的理由说明")
    is_mandatory: bool = Field(default=False, description="是否为必答问题")
    is_followup: bool = Field(default=False, description="是否为追问")
    parent_question_id: Optional[str] = Field(default=None, description="父问题ID（追问时使用）")
    priority: Optional[str] = Field(default="medium", description="问题优先级")


class ClarifyQuestions(BaseModel):
    """澄清问题列表"""
    questions: List[ClarifyQuestion] = Field(description="问题列表")


class SlotFillResult(BaseModel):
    """槽位填充结果"""
    voltage_V: Optional[float] = Field(default=None, description="电压，单位V")
    current_density_Adm2: Optional[float] = Field(default=None, description="电流密度，单位A/dm²")
    frequency_Hz: Optional[float] = Field(default=None, description="频率，单位Hz")
    duty_cycle_pct: Optional[float] = Field(default=None, description="占空比，单位%")
    time_min: Optional[float] = Field(default=None, description="处理时间，单位min")
    temp_C: Optional[float] = Field(default=None, description="温度，单位°C")
    electrolyte_components_json: Optional[Dict[str, Any]] = Field(default=None, description="电解液成分JSON")
    post_treatment: Optional[str] = Field(default=None, description="后处理方法")
    notes: Optional[str] = Field(default=None, description="补充说明")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，过滤None值"""
        return {k: v for k, v in self.model_dump().items() if v is not None}


# JSON Schema 定义（用于 LLM 解析）
CLARIFY_SCHEMA = {
    "questions": list,
    "questions[].id": str,
    "questions[].question": str,
    "questions[].kind": str,
    "questions[].options": list,
    "questions[].unit": str,
    "questions[].rationale": str,
}

SLOTFILL_SCHEMA = {
    "voltage_V": float,
    "current_density_Adm2": float,
    "frequency_Hz": float,
    "duty_cycle_pct": float,
    "time_min": float,
    "temp_C": float,
    "electrolyte_components_json": dict,
    "post_treatment": str,
    "notes": str,
}
