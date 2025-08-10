from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class PredictIn(BaseModel):
    description: str = Field(..., min_length=10, max_length=5000)


class CaseRef(BaseModel):
    doc_id: str
    page: int
    score: float
    snippet: str
    citation_url: Optional[str] = None


class PredictOut(BaseModel):
    alpha: float
    epsilon: float
    confidence: float
    nearest_cases: List[CaseRef] = []


class RecommendIn(BaseModel):
    target: Dict[str, float]
    current_hint: Optional[str] = None
    constraints: Optional[Dict[str, Any]] = None
    n_solutions: int = 5


class Solution(BaseModel):
    delta: Dict[str, Any]
    predicted: Dict[str, float]
    rationale: str
    evidence: List[CaseRef] = []


class RecommendOut(BaseModel):
    solutions: List[Solution]
    pareto_front_summary: Dict[str, Any] = {}


class IngestIn(BaseModel):
    pdf_dir: str


class IngestOut(BaseModel):
    ok: bool
    samples: int
    parsed: int

