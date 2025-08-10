from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np
from joblib import dump
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sentence_transformers import SentenceTransformer
import mlflow

from ..utils import load_config
from ..utils.logger import logger
from .dataset_builder import render_training_text


def _embed_texts(texts: list[str], model_name: str) -> np.ndarray:
    try:
        model = SentenceTransformer(model_name)
    except Exception:
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return emb


def train(samples_file: str, out_dir: str, model_name: str = "BAAI/bge-m3") -> Dict[str, Any]:
    df = pd.read_parquet(samples_file)
    if df.empty:
        raise RuntimeError("empty samples for training")
    texts = [render_training_text(r) for r in df.fillna("").to_dict(orient="records")]
    X = _embed_texts(texts, model_name)
    y = df[["alpha_150_2600", "epsilon_3000_30000"]].values.astype(float)

    model = MultiOutputRegressor(Ridge(alpha=1.0))
    model.fit(X, y)
    y_pred = model.predict(X)

    metrics = {
        "mae_alpha": float(mean_absolute_error(y[:, 0], y_pred[:, 0])),
        "mae_epsilon": float(mean_absolute_error(y[:, 1], y_pred[:, 1])),
        "rmse_alpha": float(mean_squared_error(y[:, 0], y_pred[:, 0], squared=False)),
        "rmse_epsilon": float(mean_squared_error(y[:, 1], y_pred[:, 1], squared=False)),
        "r2_alpha": float(r2_score(y[:, 0], y_pred[:, 0])),
        "r2_epsilon": float(r2_score(y[:, 1], y_pred[:, 1])),
    }

    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    dump({"model": model, "embed_model": model_name}, out_dir_p / "model.joblib")

    cfg = load_config()
    Path(cfg["paths"]["reports"]).mkdir(parents=True, exist_ok=True)
    report_file = Path(cfg["paths"]["reports"]) / "fwd_eval_v1.json"
    import json
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    try:
        mlflow.set_tracking_uri(Path("mlruns").absolute().as_uri())
        with mlflow.start_run(run_name="train_fwd_v1"):
            for k, v in metrics.items():
                mlflow.log_metric(k, v)
            mlflow.log_param("embed_model", model_name)
            mlflow.log_artifact(str(report_file))
    except Exception:
        logger.warning("mlflow logging skipped")

    logger.info(f"training done, metrics: {metrics}")
    return {"ok": True, **metrics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, type=str)
    parser.add_argument("--model_name", required=False, type=str, default="BAAI/bge-m3")
    parser.add_argument("--out_dir", required=True, type=str)
    parser.add_argument("--epochs", required=False, type=int, default=8)  # 占位
    parser.add_argument("--lr", required=False, type=float, default=2e-5)  # 占位
    parser.add_argument("--batch", required=False, type=int, default=16)  # 占位
    args = parser.parse_args()
    train(args.samples, args.out_dir, model_name=args.model_name)

