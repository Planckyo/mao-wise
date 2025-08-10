from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from maowise.api_schemas.schemas import PredictIn, PredictOut, RecommendIn, RecommendOut, IngestIn, IngestOut
from maowise.utils.config import load_config
from maowise.utils.logger import logger
from maowise.dataflow.ingest import main as ingest_main
from maowise.kb.build_index import build_index
from maowise.kb.search import kb_search
from maowise.models.infer_fwd import predict_performance
from maowise.optimize.engines import recommend_solutions


app = FastAPI(title="MAO-Wise API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/maowise/v1/ingest", response_model=IngestOut)
def ingest(body: IngestIn) -> Dict[str, Any]:
    cfg = load_config()
    out_dir = f"{cfg['paths']['versions']}/maowise_ds_v1"
    stats = ingest_main(body.pdf_dir, out_dir)
    # build KB
    corpus = f"{cfg['paths']['data_parsed']}/corpus.jsonl"
    build_index(corpus, cfg['paths']['index_store'])
    return {"ok": True, **stats}


@app.post("/api/maowise/v1/predict", response_model=PredictOut)
def predict(body: PredictIn) -> Dict[str, Any]:
    return predict_performance(body.description, topk_cases=3)


@app.post("/api/maowise/v1/recommend", response_model=RecommendOut)
def recommend(body: RecommendIn) -> Dict[str, Any]:
    return recommend_solutions(
        target=body.target,
        current_hint=body.current_hint,
        constraints=body.constraints,
        n_solutions=body.n_solutions,
    )


@app.post("/api/maowise/v1/kb/search")
def kb_search_api(body: Dict[str, Any]) -> Any:
    query = body.get("query", "")
    k = int(body.get("k", 5))
    filters = body.get("filters")
    return kb_search(query, k=k, filters=filters)


